"""Studio-managed, tenant-bound drafts and publication for the shared runtime."""
from __future__ import annotations

from contextlib import asynccontextmanager, suppress
import asyncio
import base64
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import io
import json
import logging
import os
from pathlib import Path, PurePosixPath
import re
import time
from types import SimpleNamespace
from typing import Any, Literal
from urllib.parse import urlsplit
import uuid
import zipfile

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Request, Response
import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr

from app import edge_bundler, edge_function_store as store, edge_functions
from app.database import get_pool
from app.dependencies import ensure_project_member_access, get_public_project_row, resolve_authenticated_user
from app.functions_network import network_hosts
from app.meta_connections import get_project_meta_connection_string
from app.opaque_keys import generate_opaque_key, parse_opaque_key
from app.project_secret_service import encrypt_project_material, decrypt_project_material
from app.validation import validate_project_ref

ROOT = Path('/docker')
logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/projects/{ref}/edge-functions', tags=['studio-edge-functions'])
SETTINGS = {'EDGE_FUNCTIONS_ENABLED', 'FUNCTIONS_ALLOWED_NETWORK_HOSTS'}


class CodeFile(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr = Field(min_length=1, max_length=240)
    content: StrictStr = Field(max_length=(store.MAX_BYTES_CEILING * 4) // 3 + 16)
    encoding: Literal['utf-8', 'base64'] | None = None


class DraftBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: StrictStr | None = Field(..., max_length=64)
    files: list[CodeFile] = Field(min_length=1, max_length=store.MAX_FILES_CEILING)


class PublishBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    expected_published_revision: StrictStr | None = Field(..., max_length=64)


class BundleBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    force: StrictBool = False


class RegistryCreateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr = Field(min_length=1, max_length=80)
    kind: Literal['npm', 'jsr']
    scope: StrictStr = Field(default='', max_length=130)
    registry_url: StrictStr = Field(min_length=10, max_length=512)
    auth_type: Literal['none', 'bearer', 'basic'] = 'bearer'
    token: StrictStr | None = Field(default=None, max_length=edge_bundler.MAX_REGISTRY_TOKEN_BYTES)
    allow_private_network: StrictBool = False
    ca_pem: StrictStr = Field(default='', max_length=edge_bundler.MAX_REGISTRY_CA_PEM_BYTES)
    enabled: StrictBool = True


class RegistryUpdateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=80)
    kind: Literal['npm', 'jsr'] | None = None
    scope: StrictStr | None = Field(default=None, max_length=130)
    registry_url: StrictStr | None = Field(default=None, min_length=10, max_length=512)
    auth_type: Literal['none', 'bearer', 'basic'] | None = None
    token: StrictStr | None = Field(default=None, max_length=edge_bundler.MAX_REGISTRY_TOKEN_BYTES)
    clear_token: StrictBool = False
    allow_private_network: StrictBool | None = None
    ca_pem: StrictStr | None = Field(default=None, max_length=edge_bundler.MAX_REGISTRY_CA_PEM_BYTES)
    clear_ca_pem: StrictBool = False
    enabled: StrictBool | None = None


class SecretEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr = Field(min_length=1, max_length=128)
    value: StrictStr = Field(min_length=1, max_length=edge_functions.MAX_SECRET_VALUE_BYTES)


class SecretsUpdateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    secrets: list[SecretEntry] = Field(min_length=1, max_length=edge_functions.QUOTA_SPECS['max_secrets']['max'])


class QuotasUpdateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    max_functions: StrictInt | None = None
    max_files: StrictInt | None = None
    max_bytes: StrictInt | None = None
    memory_limit_mb: StrictInt | None = None
    worker_timeout_ms: StrictInt | None = None
    max_concurrent_project: StrictInt | None = None
    max_secrets: StrictInt | None = None
    max_secrets_total_bytes: StrictInt | None = None
    alert_threshold_pct: StrictInt | None = None
    reset_defaults: StrictBool = False


class FunctionConfigBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    verify_jwt: StrictBool


ALLOWED_INVOKE_METHODS = frozenset({'GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'})
ALLOWED_AUTH_MODES = frozenset({'anon', 'service_role', 'none', 'custom'})
MAX_INVOKE_BODY_BYTES = 1048576
MAX_RESPONSE_BODY_BYTES = 262144
MAX_LOG_ROWS_PER_PROJECT = 200
MAX_LOG_MESSAGE_LEN = 1024
HEADER_NAME_RE = re.compile(r'^[A-Za-z0-9-]+$')
BEARER_RE = re.compile(r'(?<![A-Za-z0-9_-])Bearer\s+(?!Bearer(?:\s|$))\S+', re.IGNORECASE)
JWT_RE = re.compile(r'\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b')
OPAQUE_KEY_RE = re.compile(r'\bsb_(?:secret|publishable)_[A-Za-z0-9_-]+\b')
DSN_PASS_RE = re.compile(r'(postgres(?:ql)?://[^:@\s]+:)([^@\s]+)(@)', re.IGNORECASE)
FORBIDDEN_INVOKE_HEADERS = frozenset({
    'host', 'connection', 'content-length', 'transfer-encoding', 'keep-alive',
    'upgrade', 'te', 'trailer', 'proxy-authorization', 'proxy-connection', 'cookie',
})
FORBIDDEN_INVOKE_PREFIXES = (
    'x-project-', 'x-gateway-', 'x-admission-', 'x-opaque-', 'x-api-key-',
    'x-internal-', 'x-user-', 'remote-', 'x-shared-token', 'x-logs-',
    'x-event-', 'x-forwarded-', 'x-real-ip',
)
OMITTED_RESPONSE_HEADERS = frozenset({
    'set-cookie', 'connection', 'keep-alive', 'transfer-encoding', 'te', 'trailer', 'upgrade',
})


class InvokeBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    method: StrictStr = Field(default='POST', min_length=1, max_length=16)
    path: StrictStr = Field(default='/', max_length=2048)
    headers: dict[StrictStr, StrictStr] = Field(default_factory=dict)
    body: StrictStr | None = Field(default=None, max_length=MAX_INVOKE_BODY_BYTES)
    auth_mode: StrictStr = Field(default='anon', min_length=1, max_length=16)


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    expected_revision: StrictStr | None = Field(..., max_length=64)


class GcBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    min_age_seconds: StrictInt = Field(default=store.DEFAULT_ORPHAN_RETENTION_SECONDS, ge=0, le=31536000)


class ScheduleCreateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr = Field(min_length=1, max_length=80)
    cron: StrictStr = Field(min_length=5, max_length=100)
    timezone: Literal['UTC'] = 'UTC'
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] = 'POST'
    path: StrictStr = Field(default='/', min_length=1, max_length=256)
    headers: dict[StrictStr, StrictStr] = Field(default_factory=dict)
    body: StrictStr = Field(default='', max_length=65536)
    auth_mode: Literal['anon', 'service_role', 'none'] = 'service_role'
    enabled: StrictBool = True


class ScheduleUpdateBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: StrictStr | None = Field(default=None, min_length=1, max_length=80)
    cron: StrictStr | None = Field(default=None, min_length=5, max_length=100)
    timezone: Literal['UTC'] | None = None
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] | None = None
    path: StrictStr | None = Field(default=None, min_length=1, max_length=256)
    headers: dict[StrictStr, StrictStr] | None = None
    body: StrictStr | None = Field(default=None, max_length=65536)
    auth_mode: Literal['anon', 'service_role', 'none'] | None = None
    enabled: StrictBool | None = None


def governance_limits(quotas: dict[str, int] | None = None) -> dict[str, int]:
    effective = edge_functions.validate_quotas(quotas)
    return {
        **effective,
        'max_concurrent_global': edge_functions.PLATFORM_MAX_CONCURRENT_GLOBAL,
        'max_secret_value_bytes': edge_functions.MAX_SECRET_VALUE_BYTES,
    }


def _build_function_bundle_zip(slug: str, revision: str, files: list[dict], *, verify_jwt: bool) -> bytes:
    validated = store.validate_files(files, max_files=store.MAX_FILES_CEILING, max_bytes=store.MAX_BYTES_CEILING)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for file_entry in validated:
            info = zipfile.ZipInfo(f"{slug}/{file_entry['name']}", date_time=(2024, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, store.file_bytes(file_entry))
        manifest = {
            'name': slug,
            'revision': revision,
            'verify_jwt': verify_jwt,
            'runtime': {'deno_entrypoint': 'index.ts'},
            'files': [file_entry['name'] for file_entry in validated],
            'exported_at': datetime.now(timezone.utc).isoformat(),
        }
        m_info = zipfile.ZipInfo(f'{slug}/manifest.json', date_time=(2024, 1, 1, 0, 0, 0))
        m_info.external_attr = 0o644 << 16
        archive.writestr(m_info, json.dumps(manifest, indent=2).encode('utf-8'))
    return buf.getvalue()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _mint_hs256_jwt(secret: str, role: str, ttl_seconds: int = 300) -> str:
    now = int(time.time())
    header = _b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode('utf-8'))
    payload = _b64url(json.dumps({
        'iss': 'supabase',
        'role': role,
        'iat': now,
        'exp': now + ttl_seconds,
    }, separators=(',', ':')).encode('utf-8'))
    signing_input = f'{header}.{payload}'.encode('ascii')
    sig = _b64url(hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest())
    return f'{header}.{payload}.{sig}'


def _redact_log_message(message: str, sensitive: list[str]) -> str:
    cleaned = re.sub(r'[\r\n\t]+', ' ', message or '').strip()
    for secret in sorted((s for s in set(sensitive) if isinstance(s, str) and len(s) >= 4), key=len, reverse=True):
        if secret in cleaned:
            cleaned = cleaned.replace(secret, '[REDACTED]')
    cleaned = DSN_PASS_RE.sub(r'\1[REDACTED]\3', cleaned)
    cleaned = BEARER_RE.sub('Bearer [REDACTED]', cleaned)
    cleaned = JWT_RE.sub('[REDACTED_JWT]', cleaned)
    cleaned = OPAQUE_KEY_RE.sub('[REDACTED_KEY]', cleaned)
    if len(cleaned) > MAX_LOG_MESSAGE_LEN:
        cleaned = cleaned[: MAX_LOG_MESSAGE_LEN - 3] + '...'
    return cleaned


def _validate_invoke_request(body: InvokeBody | SimpleNamespace) -> tuple[str, str, str, dict[str, str], bytes | None]:
    method = body.method.upper()
    if method not in ALLOWED_INVOKE_METHODS:
        raise HTTPException(400, f'Unsupported HTTP method: {body.method}')
    auth_mode = body.auth_mode.lower()
    if auth_mode not in ALLOWED_AUTH_MODES:
        raise HTTPException(400, f'Unsupported auth_mode: {body.auth_mode}')
    raw_path = body.path if body.path != '' else '/'
    if any(bad in raw_path for bad in ('\r', '\n', '\x00', '\\', '://')):
        raise HTTPException(400, 'Invalid function invocation path')
    parts = urlsplit(raw_path)
    if parts.scheme or parts.netloc or parts.fragment:
        raise HTTPException(400, 'Invalid function invocation path')
    posix_path = parts.path or '/'
    if '..' in PurePosixPath(posix_path).parts:
        raise HTTPException(400, 'Path traversal is not permitted')
    normalized_path = '/' + posix_path.lstrip('/') if posix_path != '/' else ''
    path_with_query = f'{normalized_path}?{parts.query}' if parts.query else normalized_path

    if len(body.headers) > 32:
        raise HTTPException(400, 'Too many request headers')
    safe_headers: dict[str, str] = {}
    for key, val in body.headers.items():
        if len(key) > 128 or not HEADER_NAME_RE.fullmatch(key):
            raise HTTPException(400, f'Invalid header name: {key}')
        if len(val) > 4096 or any(c in val for c in ('\r', '\n', '\x00')):
            raise HTTPException(400, f'Invalid header value for {key}')
        lower = key.lower()
        if lower in FORBIDDEN_INVOKE_HEADERS or lower.startswith(FORBIDDEN_INVOKE_PREFIXES):
            raise HTTPException(400, f'Disallowed header: {key}')
        if auth_mode != 'custom' and lower in {'authorization', 'apikey'}:
            raise HTTPException(400, f"Header '{key}' requires auth_mode='custom'")
        safe_headers[lower] = val

    body_bytes: bytes | None = None
    if body.body is not None:
        encoded = body.body.encode('utf-8')
        if len(encoded) > MAX_INVOKE_BODY_BYTES:
            raise HTTPException(400, 'Request body exceeds maximum size')
        if method in {'GET', 'HEAD'} and encoded:
            raise HTTPException(400, f'{method} requests cannot include a body')
        body_bytes = encoded
    return method, auth_mode, path_with_query, safe_headers, body_bytes


def _parse_log_query(request: Request, *, allow_function: bool) -> tuple[str | None, str | None, int]:
    allowed = {'level', 'limit'} | ({'function'} if allow_function else set())
    unknown = set(request.query_params.keys()) - allowed
    if unknown:
        raise HTTPException(400, f"Unsupported query parameters: {', '.join(sorted(unknown))}")
    fn_filter: str | None = None
    if allow_function and request.query_params.get('function'):
        fn_filter = request.query_params['function']
        try:
            store.function_name(fn_filter)
        except ValueError as error:
            raise HTTPException(400, 'Invalid function filter') from error
    level_filter: str | None = None
    if request.query_params.get('level'):
        level_filter = request.query_params['level']
        if level_filter not in {'info', 'warn', 'error'}:
            raise HTTPException(400, 'Invalid log level filter')
    limit = 50
    limit_raw = request.query_params.get('limit')
    if limit_raw is not None and limit_raw != '':
        if not limit_raw.isdigit():
            raise HTTPException(400, 'Invalid log limit')
        limit = int(limit_raw)
        if limit < 1 or limit > 200:
            raise HTTPException(400, 'Log limit must be between 1 and 200')
    return fn_filter, level_filter, limit


def _runtime_base_url() -> str:
    return os.environ.get('EDGE_FUNCTIONS_RUNTIME_URL', 'http://functions:9000').rstrip('/')


async def configuration(conn, project_id):
    row = await conn.fetchrow('SELECT enabled,network_allowlist FROM project_edge_functions WHERE project_id=$1', project_id)
    if row is None:
        return {'enabled': False, 'network_allowlist': []}
    allowlist = row['network_allowlist']
    if isinstance(allowlist, str):
        allowlist = json.loads(allowlist)
    return {'enabled': row['enabled'], 'network_allowlist': network_hosts(allowlist)}


async def load_project_quotas(conn, project_id) -> tuple[dict[str, int], dict[str, int]]:
    row = await conn.fetchval('SELECT quotas FROM project_edge_functions WHERE project_id=$1', project_id)
    if not row:
        return edge_functions.default_quotas(), {}
    raw = json.loads(row) if isinstance(row, str) else dict(row)
    return edge_functions.validate_quotas(raw), raw


async def settings_values(conn, project_id):
    value = await configuration(conn, project_id)
    return {'EDGE_FUNCTIONS_ENABLED': str(value['enabled']).lower(),
            'FUNCTIONS_ALLOWED_NETWORK_HOSTS': ','.join(value['network_allowlist'])}


@asynccontextmanager
async def management_context(ref, request, response, pool, *, allow_query: bool = False):
    ref = validate_project_ref(ref)
    if getattr(request.state, 'internal_service', None) != 'studio-nginx':
        raise HTTPException(403, 'Function management requires the authenticated Studio gateway')
    if not allow_query and request.query_params:
        raise HTTPException(400, 'Function management does not accept query parameters')
    if response is not None:
        response.headers['Cache-Control'] = 'no-store'
    user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, ref)
        await ensure_project_member_access(conn, project_id=project['id'], auth_user=user)
    locked_project = (project['id'], project['name'], project['tenant_uuid'])
    async with edge_functions.configuration_lock(ROOT, project['name']):
        # No database connection is held while waiting for lifecycle or directory I/O.
        user = await resolve_authenticated_user(request, pool)
        async with pool.acquire() as conn:
            project = await get_public_project_row(conn, ref)
            if (project['id'], project['name'], project['tenant_uuid']) != locked_project:
                raise HTTPException(409, 'Project identity changed while waiting; reload before continuing')
            await ensure_project_member_access(conn, project_id=project['id'], auth_user=user)
            request.state.edge_actor_label = str(
                user.get('username') or user.get('display_name') or user['db_user_id']
            )[:128]
            request.state.edge_actor_is_global_admin = bool(user.get('is_global_admin'))
            try:
                yield conn, project, user['db_user_id'], await configuration(conn, project['id'])
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, UnicodeError) as error:
                edge_functions.withdraw(ROOT, project['name'])
                raise HTTPException(503, 'Function storage or project configuration failed integrity validation') from error


def dependency_summary(files: list[dict]) -> dict:
    try:
        return edge_bundler.inspect_dependencies(files)
    except edge_bundler.DependencyPolicyError as error:
        raise HTTPException(400, str(error)) from error


def identity(project):
    return str(project['tenant_uuid'])


def load(project):
    return store.load(ROOT, project['name'], identity(project))


def _dependency_metadata(state: dict, slug: str, value: dict) -> dict:
    try:
        summary = edge_bundler.inspect_dependencies(value.get('files') or [])
    except ValueError:
        summary = {'npm': [], 'jsr': [], 'requires_bundle': False}
    rev = value.get('revision')
    bundled_size = store.bundle_size(ROOT, state, slug, rev) if rev and slug in state.get('functions', {}) else None
    if not isinstance(bundled_size, int) or isinstance(bundled_size, bool):
        bundled_size = None
    return {
        **summary,
        'bundled': bundled_size is not None,
        'bundle_bytes': bundled_size,
    }


def detail(project, state, slug, enabled, *, verify_jwt: bool = True, quotas: dict[str, int] | None = None):
    value = store.item(ROOT, state, slug, {})
    if value is None:
        raise HTTPException(404, 'Function not found')
    return {
        **value,
        'enabled': enabled,
        'verify_jwt': verify_jwt,
        'limits': governance_limits(quotas),
        'dependencies': _dependency_metadata(state, slug, value),
    }


async def load_function_configs(conn, project_id) -> dict[str, bool]:
    rows = await conn.fetch(
        'SELECT function_name, verify_jwt FROM project_edge_function_configs WHERE project_id=$1',
        project_id,
    )
    if not isinstance(rows, (list, tuple)):
        return {}
    return {row['function_name']: bool(row['verify_jwt']) for row in rows}


async def sync_function_config_publication(conn, project_id, slug: str, action: str, actor) -> None:
    if action == 'delete':
        await conn.execute(
            'DELETE FROM project_edge_function_configs WHERE project_id=$1 AND function_name=$2',
            project_id, slug,
        )
    elif action in {'publish', 'unpublish'}:
        published = action == 'publish'
        await conn.execute(
            '''INSERT INTO project_edge_function_configs(project_id,function_name,verify_jwt,published,updated_by)
               VALUES($1,$2,true,$3,$4)
               ON CONFLICT (project_id, function_name) DO UPDATE
               SET published=EXCLUDED.published,updated_by=EXCLUDED.updated_by,updated_at=now()''',
            project_id, slug, published, actor,
        )


async def audit(conn, project, actor, action, slug=None, revision=None):
    return await conn.fetchval('''INSERT INTO studio_edge_audit(project_id,actor_id,action,function_name,revision,outcome)
        VALUES($1,$2,$3,$4,$5,'requested') RETURNING id''', project['id'], actor, action, slug, revision)


async def _record_revision_author(conn, project_id, slug: str, revision: str, actor_id, actor_label: str, action: str = 'save_draft') -> None:
    """Persist the original creator metadata for an immutable function revision."""
    await conn.execute(
        '''INSERT INTO project_edge_function_revisions(project_id,function_name,revision,author_id,author_label,action)
           VALUES($1,$2,$3,$4,$5,$6)
           ON CONFLICT (project_id, function_name, revision) DO NOTHING''',
        project_id, slug, revision, actor_id, actor_label[:128], action,
    )


async def _load_revision_authors(conn, project_id, slug: str) -> dict[str, dict[str, str | None]]:
    """Load author attribution per revision, falling back to legacy audit records."""
    authors: dict[str, dict[str, str | None]] = {}
    rev_rows = await conn.fetch(
        '''SELECT r.revision, r.author_id,
                  COALESCE(NULLIF(u.authelia_username, ''), NULLIF(u.display_name, ''), NULLIF(r.author_label, ''), r.author_id::text) AS label
           FROM project_edge_function_revisions r
           LEFT JOIN users u ON u.id = r.author_id
           WHERE r.project_id=$1 AND r.function_name=$2''',
        project_id, slug,
    )
    for row in rev_rows or ():
        authors[row['revision']] = {
            'author_id': str(row['author_id']) if row['author_id'] is not None else None,
            'author_label': row['label'] or None,
        }
    audit_rows = await conn.fetch(
        '''SELECT DISTINCT ON (a.revision) a.revision, a.actor_id,
                  COALESCE(NULLIF(u.authelia_username, ''), NULLIF(u.display_name, ''), a.actor_id::text) AS label
           FROM studio_edge_audit a
           LEFT JOIN users u ON u.id = a.actor_id
           WHERE a.project_id=$1 AND a.function_name=$2 AND a.action IN ('save_draft', 'rollback') AND a.revision IS NOT NULL
           ORDER BY a.revision, a.created_at ASC''',
        project_id, slug,
    )
    for row in audit_rows or ():
        if row['revision'] not in authors:
            authors[row['revision']] = {
                'author_id': str(row['actor_id']) if row['actor_id'] is not None else None,
                'author_label': row['label'] or None,
            }
    return authors


def _resolve_revision_snapshot(state: dict, slug: str, selector: str) -> tuple[str, list[dict]]:
    """Resolve 'draft', 'published', or a 64-hex revision SHA-256 to its files."""
    current = store.item(ROOT, state, slug, {})
    if current is None:
        raise HTTPException(404, 'Function not found')
    if selector == 'draft':
        return current['revision'], current['files']
    if selector == 'published':
        if current['published_revision'] is None:
            raise HTTPException(409, 'Function has no published revision')
        target_rev = current['published_revision']
        return target_rev, store.read_version(ROOT, state, slug, target_rev)
    if store.REVISION.fullmatch(selector):
        try:
            return selector, store.read_version(ROOT, state, slug, selector)
        except FileNotFoundError as error:
            raise HTTPException(404, 'Function version not found') from error
    raise HTTPException(400, 'Invalid version selector')


async def outcome(conn, audit_id, result):
    try:
        await conn.execute('UPDATE studio_edge_audit SET outcome=$2 WHERE id=$1', audit_id, result)
    except Exception:
        logger.error('Could not finalize Studio function audit outcome')


async def internal_keys(conn, project):
    result = {}
    async with conn.transaction():
        await conn.execute('SELECT id FROM projects WHERE id=$1 FOR UPDATE', project['id'])
        for kind in ('publishable', 'secret'):
            purpose = 'functions-' + kind + '-key'
            row = await conn.fetchrow('SELECT secret_ciphertext,secret_hash,is_active FROM project_function_keys WHERE project_id=$1 AND kind=$2', project['id'], kind)
            if row is None:
                key = generate_opaque_key(project['id'], kind)
                ciphertext = await encrypt_project_material(conn, project_id=project['id'], purpose=purpose, plaintext=key.token)
                await conn.execute('INSERT INTO project_function_keys(project_id,kind,secret_hash,secret_ciphertext) VALUES($1,$2,$3,$4)',
                                   project['id'], kind, key.digest, ciphertext)
                result[kind] = key.token
            else:
                if not row['is_active']:
                    raise HTTPException(403, 'Function credential has been revoked')
                token = await decrypt_project_material(conn, project_id=project['id'], purpose=purpose, ciphertext=row['secret_ciphertext'])
                parsed = parse_opaque_key(project['id'], token)
                if parsed.kind != kind or parsed.digest != bytes(row['secret_hash']):
                    raise RuntimeError('Function credential integrity mismatch')
                result[kind] = token
    return result


def canonical_projection_credentials(project) -> dict[str, str]:
    name, tenant_id = project['name'], identity(project)
    path = ROOT / 'projects' / name / '.env'
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise RuntimeError('Refusing symlinked project environment')
    # The host-agent projection must exist; an in-progress lifecycle never permits publication.
    projected = json.loads(store.regular_bytes(ROOT / '.functions-tenants' / (name + '.json'), 65536))
    env = dotenv_values(path)
    for key, expected in (('PROJECT_ID', name), ('PROJECT_UUID', tenant_id), ('PROJECT_PUBLIC_REF', project['public_ref'])):
        if env.get(key) != expected:
            raise RuntimeError('Project environment identity mismatch')
    if (projected.get('technical_name') != name or projected.get('project_uuid') != tenant_id
            or projected.get('project_ref') != project['public_ref'] or projected.get('jwt_secret') != env.get('JWT_SECRET_PROJETO')):
        raise RuntimeError('Project lifecycle projection unavailable or divergent')
    url = (env.get('API_EXTERNAL_URL') or '').removesuffix('/auth/v1').rstrip('/')
    if not url:
        raise RuntimeError('Project public API URL unavailable')
    return {
        'jwt_secret': str(env['JWT_SECRET_PROJETO'] or ''),
        'public_url': url,
        'anon_key': str(projected.get('anon_key') or env.get('ANON_KEY_PROJETO') or ''),
        'service_role_key': str(projected.get('service_role_key') or env.get('SERVICE_ROLE_KEY_PROJETO') or ''),
        'postgres_password': str(env.get('POSTGRES_PASSWORD') or ''),
        'auth_db_password': str(env.get('AUTH_DB_PASSWORD') or ''),
        'postgrest_db_password': str(env.get('POSTGREST_DB_PASSWORD') or ''),
        'edge_gateway_token': str(projected.get('edge_gateway_token') or env.get('API_GATEWAY_TOKEN_PROJETO') or ''),
    }


def canonical_environment(project):
    creds = canonical_projection_credentials(project)
    return creds['jwt_secret'], creds['public_url']


def _collect_sensitive_values(project: dict, creds: dict[str, str], secrets: dict[str, str]) -> list[str]:
    excluded = {project['name'], project['public_ref'], identity(project)}
    values = [v for v in secrets.values() if isinstance(v, str) and len(v) >= 4 and v not in excluded]
    for field in (
        'jwt_secret',
        'anon_key',
        'service_role_key',
        'postgres_password',
        'auth_db_password',
        'postgrest_db_password',
        'edge_gateway_token',
    ):
        val = creds.get(field, '')
        if isinstance(val, str) and len(val) >= 4 and val not in excluded:
            values.append(val)
    return values


async def _persist_invocation_log(
    conn, project_id, function_name: str, request_id: str, method: str,
    path: str, status: int, duration_ms: int, source: str, level: str,
    published: bool, message: str, sensitive: list[str],
) -> None:
    redacted = _redact_log_message(message, sensitive)
    await conn.execute(
        '''INSERT INTO studio_edge_invocation_logs
           (project_id, function_name, request_id, method, path, status, duration_ms, source, level, published, message)
           VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)''',
        project_id, function_name, request_id, method, path or '/',
        status, duration_ms, source, level, published, redacted,
    )
    await conn.execute(
        f'''DELETE FROM studio_edge_invocation_logs
            WHERE project_id=$1 AND id NOT IN (
                SELECT id FROM studio_edge_invocation_logs
                WHERE project_id=$1
                ORDER BY created_at DESC, id DESC
                LIMIT {MAX_LOG_ROWS_PER_PROJECT}
            )''',
        project_id,
    )


async def _fetch_merged_logs(
    conn, project: dict, creds: dict[str, str], secrets: dict[str, str],
    *, function_name: str | None, level: str | None, limit: int,
) -> dict:
    sensitive = _collect_sensitive_values(project, creds, secrets)
    runtime_logs: list[dict] = []
    runtime_connected = False
    jwt_secret = creds.get('jwt_secret', '')
    if jwt_secret:
        ts = str(int(time.time()))
        tenant_id = identity(project)
        sig_payload = f"edge-logs-v1\n{project['name']}\n{tenant_id}\n{project['public_ref']}\n{ts}".encode('utf-8')
        sig = hmac.new(jwt_secret.encode('utf-8'), sig_payload, hashlib.sha256).hexdigest()
        params: dict[str, str] = {'limit': str(limit)}
        if function_name:
            params['function'] = function_name
        if level:
            params['level'] = level
        try:
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
                resp = await client.get(
                    f'{_runtime_base_url()}/__logs',
                    headers={
                        'X-Project-Name': project['name'],
                        'X-Project-Ref': project['public_ref'],
                        'X-Logs-Timestamp': ts,
                        'X-Logs-Signature': sig,
                    },
                    params=params,
                )
            if resp.status_code in {200, 404}:
                runtime_connected = True
            if resp.status_code == 200:
                data = resp.json()
                for entry in data.get('logs', []):
                    if not isinstance(entry, dict):
                        continue
                    entry_fn = str(entry.get('function_name', ''))
                    entry_lvl = str(entry.get('level', 'info'))
                    if function_name and entry_fn != function_name:
                        continue
                    if level and entry_lvl != level:
                        continue
                    runtime_logs.append({
                        'id': str(entry.get('id', '')),
                        'timestamp': str(entry.get('timestamp', '')),
                        'function_name': entry_fn,
                        'level': entry_lvl,
                        'source': str(entry.get('source', 'runtime')),
                        'message': _redact_log_message(str(entry.get('message', '')), sensitive),
                        'status': entry.get('status'),
                        'duration_ms': entry.get('duration_ms'),
                        **({'request_id': str(entry['request_id'])} if entry.get('request_id') else {}),
                    })
        except (httpx.HTTPError, ValueError):
            runtime_connected = False

    clauses = ['project_id=$1']
    args: list[object] = [project['id']]
    if function_name:
        args.append(function_name)
        clauses.append(f'function_name=${len(args)}')
    if level:
        args.append(level)
        clauses.append(f'level=${len(args)}')
    args.append(limit)
    rows = await conn.fetch(
        f'''SELECT id, function_name, request_id, method, path, status, duration_ms,
                   source, level, published, message, created_at
            FROM studio_edge_invocation_logs
            WHERE {' AND '.join(clauses)}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(args)}''',
        *args,
    )
    db_logs = []
    if isinstance(rows, (list, tuple)):
        for row in rows:
            db_logs.append({
                'id': f"db-{row['id']}",
                'timestamp': row['created_at'].isoformat(),
                'function_name': row['function_name'],
                'level': row['level'],
                'source': row['source'],
                'message': _redact_log_message(row['message'], sensitive),
                'status': row['status'],
                'duration_ms': row['duration_ms'],
                'request_id': row['request_id'],
            })

    combined = sorted(runtime_logs + db_logs, key=lambda item: item.get('timestamp', ''), reverse=True)[:limit]
    return {'logs': combined, 'runtime_connected': runtime_connected}


async def load_project_secrets(conn, project, *, tolerate: frozenset[str] | bool = frozenset()) -> dict[str, str]:
    rows = await conn.fetch(
        'SELECT name, secret_ciphertext FROM project_function_secrets WHERE project_id=$1 ORDER BY name',
        project['id'],
    )
    if not isinstance(rows, (list, tuple)) or not rows:
        return {}
    secrets: dict[str, str] = {}
    broken: list[str] = []
    for row in rows:
        name = edge_functions.validate_secret_name(row['name'])
        try:
            value = await decrypt_project_material(
                conn,
                project_id=project['id'],
                purpose=f'functions-env-secret:{name}',
                ciphertext=row['secret_ciphertext'],
            )
            secrets[name] = edge_functions.validate_secret_value(value)
        except (ValueError, UnicodeError, TypeError):
            broken.append(name)
    tolerated = tolerate if isinstance(tolerate, frozenset) else frozenset()
    unresolved = [] if tolerate is True else sorted(name for name in broken if name not in tolerated)
    if unresolved:
        raise HTTPException(
            409,
            'Edge Function secrets cannot be decrypted: ' + ', '.join(unresolved)
            + '. Set new values for these secrets or delete them.',
        )
    return edge_functions.validate_secrets(
        secrets,
        max_secrets=edge_functions.QUOTA_SPECS['max_secrets']['max'],
        max_total_bytes=edge_functions.QUOTA_SPECS['max_secrets_total_bytes']['max'],
    )


async def list_secret_metadata(conn, project_id) -> list[dict]:
    rows = await conn.fetch(
        'SELECT name, created_at, updated_at FROM project_function_secrets WHERE project_id=$1 ORDER BY name',
        project_id,
    )
    if not isinstance(rows, (list, tuple)):
        return []
    return [
        {
            'name': row['name'],
            'created_at': row['created_at'].isoformat(),
            'updated_at': row['updated_at'].isoformat(),
            'has_value': True,
        }
        for row in rows
    ]


def secret_limits(quotas: dict[str, int] | None = None) -> dict[str, int]:
    effective = edge_functions.validate_quotas(quotas)
    return {
        'max_secrets': effective['max_secrets'],
        'max_value_bytes': edge_functions.MAX_SECRET_VALUE_BYTES,
        'max_total_bytes': effective['max_secrets_total_bytes'],
    }


async def _record_quota_event(
    conn,
    project_id,
    kind: str,
    severity: str,
    message: str,
    *,
    function_name: str | None = None,
    detail: dict | None = None,
) -> None:
    """Persist an operational quota/saturation event while keeping storage bounded."""
    await conn.execute(
        '''INSERT INTO studio_edge_quota_events(project_id, function_name, kind, severity, message, detail)
           VALUES($1,$2,$3,$4,$5,$6::jsonb)''',
        project_id, function_name, kind, severity, message[:500], json.dumps(detail or {}),
    )
    await conn.execute(
        '''DELETE FROM studio_edge_quota_events
           WHERE project_id=$1 AND id NOT IN (
               SELECT id FROM studio_edge_quota_events
               WHERE project_id=$1
               ORDER BY created_at DESC, id DESC
               LIMIT 100
           )''',
        project_id,
    )


def _parse_log_timestamp(raw: object) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _detail_obj(raw: object) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
            return loaded if isinstance(loaded, dict) else {}
        except ValueError:
            return {}
    return {}


async def _load_429_ack_and_known_ids(conn, project_id) -> tuple[datetime | None, set[str], set[str]]:
    last_ack_raw = await conn.fetchval(
        '''SELECT max(acknowledged_at) FROM studio_edge_quota_events
           WHERE project_id=$1 AND kind='concurrency_429' AND acknowledged_at IS NOT NULL''',
        project_id,
    )
    last_ack_at = last_ack_raw if isinstance(last_ack_raw, datetime) else None
    if last_ack_at is not None and last_ack_at.tzinfo is None:
        last_ack_at = last_ack_at.replace(tzinfo=timezone.utc)
    known_runtime_ids: set[str] = set()
    known_request_ids: set[str] = set()
    rows = await conn.fetch(
        '''SELECT detail FROM studio_edge_quota_events
           WHERE project_id=$1 AND kind='concurrency_429'
           ORDER BY created_at DESC, id DESC
           LIMIT 100''',
        project_id,
    )
    if isinstance(rows, (list, tuple)):
        for row in rows:
            detail = _detail_obj(row['detail'] if isinstance(row, dict) or hasattr(row, '__getitem__') else None)
            rt_id = detail.get('runtime_log_id')
            if isinstance(rt_id, str) and rt_id:
                known_runtime_ids.add(rt_id)
            req_id = detail.get('request_id')
            if isinstance(req_id, str) and req_id:
                known_request_ids.add(req_id)
    return last_ack_at, known_runtime_ids, known_request_ids


async def _ingest_runtime_429_events(conn, project_id, runtime_logs: list[dict]) -> None:
    if not runtime_logs:
        return
    last_ack_at, known_runtime_ids, known_request_ids = await _load_429_ack_and_known_ids(conn, project_id)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    for entry in reversed(runtime_logs):
        if entry.get('source') != 'worker' or entry.get('status') != 429:
            continue
        entry_id = str(entry.get('id') or '').strip()
        if not entry_id or entry_id in known_runtime_ids:
            continue
        req_id = str(entry.get('request_id') or '').strip()
        if req_id and req_id in known_request_ids:
            continue
        ts_raw = entry.get('timestamp')
        entry_ts = _parse_log_timestamp(ts_raw)
        if entry_ts is not None:
            if entry_ts <= cutoff or (last_ack_at is not None and entry_ts <= last_ack_at):
                continue
        detail_obj: dict[str, object] = {
            'status': 429,
            'source': 'runtime_worker',
            'runtime_log_id': entry_id,
        }
        if req_id:
            detail_obj['request_id'] = req_id
        if isinstance(ts_raw, str) and ts_raw:
            detail_obj['log_timestamp'] = ts_raw
        await _record_quota_event(
            conn,
            project_id,
            'concurrency_429',
            'critical',
            str(entry.get('message') or 'Concurrency limit reached (HTTP 429)'),
            function_name=(entry.get('function_name') or None),
            detail=detail_obj,
        )
        known_runtime_ids.add(entry_id)
        if req_id:
            known_request_ids.add(req_id)


async def _recent_429_count(conn, project_id, runtime_logs: list[dict] | None = None) -> int:
    last_ack_at, known_runtime_ids, known_request_ids = await _load_429_ack_and_known_ids(conn, project_id)
    if last_ack_at is not None:
        db_hits = await conn.fetchval(
            '''SELECT count(*) FROM studio_edge_invocation_logs
               WHERE project_id=$1 AND status=429
                 AND created_at > now() - interval '15 minutes'
                 AND created_at > $2''',
            project_id,
            last_ack_at,
        )
    else:
        db_hits = await conn.fetchval(
            '''SELECT count(*) FROM studio_edge_invocation_logs
               WHERE project_id=$1 AND status=429 AND created_at > now() - interval '15 minutes' ''',
            project_id,
        )
    evt_hits = await conn.fetchval(
        '''SELECT count(*) FROM studio_edge_quota_events
           WHERE project_id=$1 AND kind='concurrency_429' AND acknowledged_at IS NULL
             AND created_at > now() - interval '15 minutes' ''',
        project_id,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    runtime_hits = 0
    for item in (runtime_logs or []):
        if item.get('status') != 429:
            continue
        entry_id = str(item.get('id') or '').strip()
        req_id = str(item.get('request_id') or '').strip()
        if (entry_id and entry_id in known_runtime_ids) or (req_id and req_id in known_request_ids):
            continue
        entry_ts = _parse_log_timestamp(item.get('timestamp'))
        if entry_ts is not None and (entry_ts <= cutoff or (last_ack_at is not None and entry_ts <= last_ack_at)):
            continue
        runtime_hits += 1
    return max(int(db_hits or 0), int(evt_hits or 0)) + runtime_hits


async def _build_quota_report(conn, project: dict, state: dict, quotas: dict[str, int], raw_quotas: dict[str, int]) -> dict:
    secrets = await load_project_secrets(conn, project, tolerate=True)
    secrets_total_bytes = sum(len(k.encode('utf-8')) + len(v.encode('utf-8')) for k, v in secrets.items())
    runtime_logs: list[dict] = []
    try:
        creds = canonical_projection_credentials(project)
        merged = await _fetch_merged_logs(conn, project, creds, secrets, function_name=None, level='warn', limit=200)
        runtime_logs = [entry for entry in merged.get('logs', []) if entry.get('source') == 'worker' and entry.get('status') == 429]
    except Exception:
        runtime_logs = []
    await _ingest_runtime_429_events(conn, project['id'], runtime_logs)
    recent_429 = await _recent_429_count(conn, project['id'], runtime_logs=runtime_logs)
    status = store.compute_quota_status(
        ROOT, state, {},
        quotas=quotas,
        secrets_count=len(secrets),
        secrets_total_bytes=secrets_total_bytes,
        recent_429_count=recent_429,
    )
    return {
        'quotas': governance_limits(quotas),
        'defaults': governance_limits(),
        'bounds': edge_functions.quota_bounds(),
        'customized': bool(raw_quotas),
        **status,
    }


async def prepare(conn, project, state, config, *, secrets_override: dict[str, str] | None = None,
                  configs_override: dict[str, bool] | None = None,
                  limits_override: dict[str, int] | None = None):
    secret, public_url = canonical_environment(project)
    keys = await internal_keys(conn, project)
    env = {
        'SUPABASE_URL': f"http://supabase-nginx-{project['name']}:8080",
        'SUPABASE_PUBLIC_URL': public_url,
        'SUPABASE_ANON_KEY': keys['publishable'],
        'SUPABASE_SERVICE_ROLE_KEY': keys['secret'],
        'SUPABASE_DB_URL': get_project_meta_connection_string(
            project['name'],
            project['tenant_uuid'],
            host_override=os.getenv('EDGE_DB_HOST') or 'supabase-db',
        ),
    }
    secrets = secrets_override if secrets_override is not None else await load_project_secrets(conn, project)
    configs = configs_override if configs_override is not None else await load_function_configs(conn, project['id'])
    files = store.published_files(ROOT, project['name'], identity(project), state=state)
    published_slugs = {path.split('/', 1)[0] for path in files}
    public_functions = sorted(slug for slug, verify in configs.items() if not verify and slug in published_slugs)
    if limits_override is not None:
        runtime_limits = limits_override
    elif 'quotas' in config:
        runtime_limits = edge_functions.runtime_limits_override(config['quotas'])
    else:
        quotas, _ = await load_project_quotas(conn, project['id'])
        runtime_limits = edge_functions.runtime_limits_override(quotas)
    kwargs: dict[str, Any] = {}
    if secrets:
        kwargs['secrets'] = secrets
    if public_functions:
        kwargs['public_functions'] = public_functions
    if runtime_limits:
        kwargs['limits'] = runtime_limits
    return edge_functions.prepare_context(ROOT, project['name'], identity(project), secret, env, files, config['network_allowlist'], **kwargs)


async def configure_project(ref, updates, request, pool):
    if not updates:
        return
    if updates.keys() - SETTINGS:
        raise HTTPException(400, 'Invalid Function settings')
    async with management_context(ref, request, None, pool) as (conn, project, actor, current):
        desired = {
            'enabled': updates.get('EDGE_FUNCTIONS_ENABLED', str(current['enabled']).lower()) == 'true',
            'network_allowlist': network_hosts(updates.get('FUNCTIONS_ALLOWED_NETWORK_HOSTS', current['network_allowlist'])),
        }
        audit_id = await audit(conn, project, actor, 'configure')
        try:
            state = load(project)
        except (OSError, RuntimeError, ValueError, KeyError, TypeError, UnicodeError):
            if desired['enabled']:
                raise
            # Corrupt drafts must never prevent an administrative block.
            state = None
        # Persist a block before preparing credentials or changing the network
        # policy. A process killed at any later step cannot expose an uncommitted configuration.
        await conn.execute('''INSERT INTO project_edge_functions(project_id,enabled,network_allowlist,updated_by)
            VALUES($1,false,$2::jsonb,$3) ON CONFLICT(project_id) DO UPDATE SET enabled=false,
            updated_by=EXCLUDED.updated_by,updated_at=now()''',
            project['id'], json.dumps(current['network_allowlist']), actor)
        # Recover any committed publication before withdrawing its context.
        edge_functions.withdraw(ROOT, project['name'])
        try:
            if desired['enabled']:
                context = await prepare(conn, project, state, desired)
                edge_functions.activate_context(ROOT, context)
            await conn.execute('''INSERT INTO project_edge_functions(project_id,enabled,network_allowlist,updated_by)
                VALUES($1,$2,$3::jsonb,$4) ON CONFLICT(project_id) DO UPDATE SET enabled=EXCLUDED.enabled,
                network_allowlist=EXCLUDED.network_allowlist,updated_by=EXCLUDED.updated_by,updated_at=now()''',
                project['id'], desired['enabled'], json.dumps(desired['network_allowlist']), actor)
            if not desired['enabled']:
                await conn.execute(
                    '''UPDATE project_edge_function_schedules
                       SET enabled=false, next_run_at=NULL,
                           last_error='Disabled when Edge Functions were turned off',
                           updated_by=$2, updated_at=now()
                       WHERE project_id=$1 AND enabled=true''',
                    project['id'], actor,
                )
        except Exception:
            edge_functions.withdraw(ROOT, project['name'])
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')


@router.get('')
async def function_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, _, config):
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        quotas, _ = await load_project_quotas(conn, project['id'])
        values = [store.item(ROOT, state, slug, {}) for slug in sorted(state['functions'])]
        return {'enabled': config['enabled'], 'functions': [
            {**{key: item[key] for key in ('name', 'revision', 'published_revision')},
             'verify_jwt': configs.get(item['name'], True)} for item in values], 'limits': governance_limits(quotas)}


@router.get('/templates')
async def templates_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool):
        return {'templates': store.list_templates()}


@router.get('/quotas')
async def quotas_get(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        state = load(project)
        quotas, raw_quotas = await load_project_quotas(conn, project['id'])
        project_snap = dict(project)
    async with pool.acquire() as conn:
        return await _build_quota_report(conn, project_snap, state, quotas, raw_quotas)


@router.put('/quotas')
async def quotas_update(ref: str, body: QuotasUpdateBody, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        is_global_admin = bool(getattr(request.state, 'edge_actor_is_global_admin', False))
        current_quotas, current_raw = await load_project_quotas(conn, project['id'])
        if body.reset_defaults:
            raw_updates: dict[str, int] = {}
            proposed_quotas = edge_functions.default_quotas()
        else:
            supplied = {k: v for k, v in body.model_dump(exclude={'reset_defaults'}).items() if v is not None}
            if not supplied:
                raise HTTPException(400, 'Provide at least one quota field or reset_defaults=true')
            merged_raw = {**current_raw, **supplied}
            try:
                proposed_quotas = edge_functions.validate_quotas(
                    merged_raw, is_global_admin=is_global_admin, check_elevation=True,
                )
            except PermissionError as error:
                raise HTTPException(403, str(error)) from error
            except ValueError as error:
                raise HTTPException(400, str(error)) from error
            defaults = edge_functions.default_quotas()
            raw_updates = {k: v for k, v in proposed_quotas.items() if v != defaults[k]}

        audit_rev = hashlib.sha256(json.dumps({'action': 'configure_quotas', 'quotas': raw_updates}, sort_keys=True).encode()).hexdigest()
        audit_id = await audit(conn, project, actor, 'configure_quotas', None, audit_rev)
        state = load(project)
        has_published = bool(store.published_files(ROOT, project['name'], identity(project), state=state))
        runtime_limits_prev = edge_functions.runtime_limits_override(current_quotas)
        runtime_limits_next = edge_functions.runtime_limits_override(proposed_quotas)
        needs_runtime_sync = config['enabled'] and has_published and runtime_limits_prev != runtime_limits_next
        previous = edge_functions.read_context(ROOT, project['name'], identity(project)) if needs_runtime_sync else None
        proposed_config = {**config, 'quotas': proposed_quotas}
        try:
            async with conn.transaction():
                await conn.execute(
                    '''INSERT INTO project_edge_functions(project_id,enabled,network_allowlist,quotas,updated_by)
                       VALUES($1,$2,$3::jsonb,$4::jsonb,$5)
                       ON CONFLICT (project_id) DO UPDATE
                       SET quotas=EXCLUDED.quotas,updated_by=EXCLUDED.updated_by,updated_at=now()''',
                    project['id'], config['enabled'], json.dumps(config['network_allowlist']),
                    json.dumps(raw_updates), actor,
                )
                if needs_runtime_sync:
                    context = await prepare(conn, project, state, proposed_config, limits_override=runtime_limits_next)
                    edge_functions.activate_context(ROOT, context)
            await _record_quota_event(
                conn, project['id'], 'quota_updated', 'info',
                'Project Edge Functions quotas updated' if raw_updates else 'Project Edge Functions quotas reset to defaults',
                detail={'quotas': raw_updates},
            )
        except Exception:
            if needs_runtime_sync:
                if previous is None:
                    edge_functions.withdraw(ROOT, project['name'])
                else:
                    edge_functions.activate_context(ROOT, previous)
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        project_snap = dict(project)
    async with pool.acquire() as conn:
        return await _build_quota_report(conn, project_snap, state, proposed_quotas, raw_updates)


@router.get('/alerts')
async def alerts_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool, allow_query=True) as (conn, project, _, _):
        unknown = set(request.query_params.keys()) - {'include_acknowledged', 'limit'}
        if unknown:
            raise HTTPException(400, f"Unsupported query parameters: {', '.join(sorted(unknown))}")
        include_ack = (request.query_params.get('include_acknowledged') or 'false').lower() == 'true'
        limit_raw = request.query_params.get('limit') or '50'
        if not limit_raw.isdigit() or not (1 <= int(limit_raw) <= 100):
            raise HTTPException(400, 'Alert limit must be between 1 and 100')
        limit = int(limit_raw)
        state = load(project)
        quotas, raw_quotas = await load_project_quotas(conn, project['id'])
        project_snap = dict(project)
    async with pool.acquire() as conn:
        report = await _build_quota_report(conn, project_snap, state, quotas, raw_quotas)
        clause = '' if include_ack else 'AND acknowledged_at IS NULL'
        rows = await conn.fetch(
            f'''SELECT id, function_name, kind, severity, message, detail, acknowledged_by, acknowledged_at, created_at
                FROM studio_edge_quota_events
                WHERE project_id=$1 {clause}
                ORDER BY created_at DESC, id DESC
                LIMIT $2''',
            project_snap['id'], limit,
        )
        events = [
            {
                'id': int(r['id']),
                'function_name': r['function_name'],
                'kind': r['kind'],
                'severity': r['severity'],
                'message': r['message'],
                'detail': json.loads(r['detail']) if isinstance(r['detail'], str) else (r['detail'] or {}),
                'acknowledged': r['acknowledged_at'] is not None,
                'acknowledged_at': r['acknowledged_at'].isoformat() if r['acknowledged_at'] else None,
                'created_at': r['created_at'].isoformat(),
            }
            for r in (rows or ())
        ]
        return {
            'active_alerts': report['active_alerts'],
            'events': events,
            'usage': report['usage'],
            'utilization_pct': report['utilization_pct'],
            'quotas': report['quotas'],
        }


@router.post('/alerts/{event_id}/ack')
async def alert_acknowledge(ref: str, event_id: int, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, actor, _):
        row = await conn.fetchrow(
            '''UPDATE studio_edge_quota_events
               SET acknowledged_by=COALESCE(acknowledged_by, $3),
                   acknowledged_at=COALESCE(acknowledged_at, now())
               WHERE project_id=$1 AND id=$2
               RETURNING id, acknowledged_at''',
            project['id'], event_id, actor,
        )
        if row is None:
            raise HTTPException(404, 'Quota alert event not found')
        return {'id': int(row['id']), 'acknowledged': True, 'acknowledged_at': row['acknowledged_at'].isoformat()}


@router.get('/schedules')
async def schedules_list_project(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        rows = await conn.fetch(
            '''SELECT id, project_id, function_name, name, cron, timezone, method, path, headers_json,
                      body, auth_mode, enabled, next_run_at, last_run_at, last_status, last_duration_ms,
                      last_request_id, last_error, created_at, updated_at
               FROM project_edge_function_schedules
               WHERE project_id=$1
               ORDER BY function_name ASC, name ASC''',
            project['id'],
        )
        return {'schedules': [_schedule_row_dict(r) for r in rows]}


def _is_global_admin(request: Request) -> bool:
    return bool(getattr(request.state, 'edge_actor_is_global_admin', False))


def _parse_registry_uuid(registry_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(registry_id)
    except ValueError as error:
        raise HTTPException(400, 'Invalid registry identifier') from error


def _validate_ca_with_x509(raw_pem: str | None) -> str:
    try:
        normalized = edge_bundler.normalize_ca_pem(raw_pem)
    except edge_bundler.DependencyPolicyError as error:
        raise HTTPException(400, str(error)) from error
    if not normalized:
        return ''
    try:
        from cryptography import x509
        certs = [
            x509.load_pem_x509_certificate(match.group(0).encode('ascii'))
            for match in edge_bundler.PEM_CERT_RE.finditer(normalized)
        ]
    except Exception as error:
        raise HTTPException(400, f'Invalid custom CA PEM certificate: {error}') from error
    if not certs:
        raise HTTPException(400, 'Custom CA PEM must contain at least one valid X.509 certificate')
    return normalized


def _registry_row_public(row) -> dict:
    return {
        'id': str(row['id']),
        'name': row['name'],
        'kind': row['kind'],
        'scope': row['scope'] or '',
        'registry_url': row['registry_url'],
        'auth_type': row['auth_type'],
        'has_token': bool(row['token_ciphertext']),
        'allow_private_network': bool(row['allow_private_network']),
        'has_custom_ca': bool(row['ca_pem']),
        'enabled': bool(row['enabled']),
        'created_at': row['created_at'].isoformat(),
        'updated_at': row['updated_at'].isoformat(),
    }


def _registry_unique_error(exc: Exception) -> HTTPException:
    constraint = str(getattr(exc, 'constraint_name', '') or '')
    if 'active_slot' in constraint:
        return HTTPException(409, 'An enabled registry already exists for this kind and scope; disable or update it first')
    return HTTPException(409, 'A registry with this name already exists in this project')


async def load_active_registries_for_bundle(conn, project: dict) -> list[dict[str, object]]:
    rows = await conn.fetch(
        '''SELECT id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                  allow_private_network, ca_pem
           FROM project_edge_function_registries
           WHERE project_id=$1 AND enabled=true
           ORDER BY kind ASC, scope ASC, name ASC''',
        project['id'],
    )
    if not isinstance(rows, (list, tuple)) or not rows:
        return []
    result: list[dict[str, object]] = []
    for row in rows:
        token = ''
        if row['auth_type'] != 'none':
            if not row['token_ciphertext']:
                raise HTTPException(409, f"Registry '{row['name']}' is missing credentials; set a token before bundling")
            try:
                async with conn.transaction():
                    token = await decrypt_project_material(
                        conn,
                        project_id=project['id'],
                        purpose=f"functions-registry:{row['id']}",
                        ciphertext=row['token_ciphertext'],
                    )
            except Exception as error:
                raise HTTPException(
                    409,
                    f"Registry '{row['name']}' credentials cannot be decrypted; rotate the token or delete the registry",
                ) from error
        result.append({
            'kind': row['kind'],
            'scope': row['scope'] or '',
            'registry_url': row['registry_url'],
            'auth_type': row['auth_type'],
            'token': token,
            'allow_private_network': bool(row['allow_private_network']),
            'ca_pem': row['ca_pem'] or '',
        })
    return result


@router.get('/registries')
async def registries_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        is_global_admin = _is_global_admin(request)
        rows = await conn.fetch(
            '''SELECT id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                      allow_private_network, ca_pem, enabled, created_at, updated_at
               FROM project_edge_function_registries
               WHERE project_id=$1
               ORDER BY kind ASC, scope ASC, name ASC''',
            project['id'],
        )
        return {
            'registries': [_registry_row_public(r) for r in (rows or ())],
            'limits': {
                'max_registries': edge_bundler.MAX_REGISTRIES_PER_PROJECT,
                'max_token_bytes': edge_bundler.MAX_REGISTRY_TOKEN_BYTES,
                'max_ca_pem_bytes': edge_bundler.MAX_REGISTRY_CA_PEM_BYTES,
                'can_configure_private_network': is_global_admin,
            },
        }


@router.post('/registries')
async def registry_create(ref: str, body: RegistryCreateBody, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, actor, _):
        is_global_admin = _is_global_admin(request)
        if not is_global_admin and (body.allow_private_network or bool((body.ca_pem or '').strip())):
            raise HTTPException(
                403,
                'Only platform administrators can configure private-network registries or custom CA certificates',
            )
        try:
            clean_name = edge_bundler.validate_registry_name(body.name)
            clean = edge_bundler.validate_registry_spec({
                'kind': body.kind,
                'scope': body.scope,
                'registry_url': body.registry_url,
                'auth_type': body.auth_type,
                'token': body.token,
                'allow_private_network': body.allow_private_network,
                'ca_pem': body.ca_pem,
            })
        except edge_bundler.DependencyPolicyError as error:
            raise HTTPException(400, str(error)) from error
        ca_pem = _validate_ca_with_x509(str(clean['ca_pem']))

        count = await conn.fetchval(
            'SELECT count(*) FROM project_edge_function_registries WHERE project_id=$1',
            project['id'],
        )
        if (count or 0) >= edge_bundler.MAX_REGISTRIES_PER_PROJECT:
            raise HTTPException(
                409,
                f'Project reached maximum of {edge_bundler.MAX_REGISTRIES_PER_PROJECT} configured registries',
            )

        reg_uuid = uuid.uuid4()
        audit_rev = hashlib.sha256(
            json.dumps({'action': 'configure_registry', 'id': str(reg_uuid), 'name': clean_name}, sort_keys=True).encode()
        ).hexdigest()
        audit_id = await audit(conn, project, actor, 'configure_registry', f'registry:{clean_name}'[:120], audit_rev)
        try:
            async with conn.transaction():
                ciphertext = (
                    await encrypt_project_material(
                        conn,
                        project_id=project['id'],
                        purpose=f'functions-registry:{reg_uuid}',
                        plaintext=str(clean['token']),
                    )
                    if clean['auth_type'] != 'none'
                    else ''
                )
                row = await conn.fetchrow(
                    '''INSERT INTO project_edge_function_registries
                       (id, project_id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                        allow_private_network, ca_pem, enabled, created_by, updated_by)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$12)
                       RETURNING id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                                 allow_private_network, ca_pem, enabled, created_at, updated_at''',
                    reg_uuid, project['id'], clean_name, clean['kind'], clean['scope'], clean['registry_url'],
                    clean['auth_type'], ciphertext, bool(clean['allow_private_network']), ca_pem, body.enabled, actor,
                )
        except Exception as exc:
            await outcome(conn, audit_id, 'failed')
            if exc.__class__.__name__ == 'UniqueViolationError':
                raise _registry_unique_error(exc) from exc
            raise
        await outcome(conn, audit_id, 'completed')
        return {'registry': _registry_row_public(row)}


@router.put('/registries/{registry_id}')
async def registry_update(
    ref: str, registry_id: str, body: RegistryUpdateBody,
    request: Request, response: Response, pool=Depends(get_pool),
):
    reg_uuid = _parse_registry_uuid(registry_id)
    async with management_context(ref, request, response, pool) as (conn, project, actor, _):
        is_global_admin = _is_global_admin(request)
        existing = await conn.fetchrow(
            '''SELECT id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                      allow_private_network, ca_pem, enabled
               FROM project_edge_function_registries
               WHERE id=$1 AND project_id=$2''',
            reg_uuid, project['id'],
        )
        if existing is None:
            raise HTTPException(404, 'Registry not found')

        target_name_raw = body.name if body.name is not None else existing['name']
        target_kind = body.kind if body.kind is not None else existing['kind']
        target_scope = body.scope if body.scope is not None else existing['scope']
        target_url = body.registry_url if body.registry_url is not None else existing['registry_url']
        target_auth_type = body.auth_type if body.auth_type is not None else existing['auth_type']
        target_allow_private = (
            bool(existing['allow_private_network'])
            if body.allow_private_network is None
            else bool(body.allow_private_network)
        )
        target_ca_raw = (
            '' if body.clear_ca_pem
            else (body.ca_pem if body.ca_pem is not None else existing['ca_pem'])
        )
        target_enabled = bool(existing['enabled']) if body.enabled is None else bool(body.enabled)

        if target_allow_private != bool(existing['allow_private_network']) and not is_global_admin:
            raise HTTPException(403, 'Only platform administrators can modify private-network registry permissions')
        if body.ca_pem is not None and bool(body.ca_pem.strip()) and not is_global_admin:
            raise HTTPException(403, 'Only platform administrators can configure custom CA certificates')
        if body.clear_ca_pem and bool(existing['ca_pem']) and not is_global_admin:
            raise HTTPException(403, 'Only platform administrators can modify custom CA certificates')

        try:
            clean_name = edge_bundler.validate_registry_name(target_name_raw)
            clean = edge_bundler.validate_registry_spec(
                {
                    'kind': target_kind,
                    'scope': target_scope,
                    'registry_url': target_url,
                    'auth_type': target_auth_type,
                    'token': body.token,
                    'allow_private_network': target_allow_private,
                    'ca_pem': target_ca_raw,
                },
                require_token_if_auth=False,
            )
        except edge_bundler.DependencyPolicyError as error:
            raise HTTPException(400, str(error)) from error
        ca_pem = _validate_ca_with_x509(str(clean['ca_pem']))

        if not is_global_admin and (
            (bool(existing['allow_private_network']) and (
                clean['registry_url'] != existing['registry_url']
                or clean['kind'] != existing['kind']
                or clean['scope'] != existing['scope']
                or not target_allow_private
            ))
            or ca_pem != (existing['ca_pem'] or '')
        ):
            raise HTTPException(
                403,
                'Only platform administrators can alter private-network registry targets or custom CA settings',
            )

        if target_auth_type != 'none' and body.token is None:
            if body.clear_token:
                raise HTTPException(400, f"Registry token is required for auth_type '{target_auth_type}'")
            if not existing['token_ciphertext'] or target_auth_type != existing['auth_type']:
                raise HTTPException(400, f"Registry token must be provided when configuring auth_type '{target_auth_type}'")

        audit_rev = hashlib.sha256(
            json.dumps({'action': 'configure_registry', 'id': str(reg_uuid), 'name': clean_name}, sort_keys=True).encode()
        ).hexdigest()
        audit_id = await audit(conn, project, actor, 'configure_registry', f'registry:{clean_name}'[:120], audit_rev)
        try:
            async with conn.transaction():
                if target_auth_type == 'none':
                    ciphertext = ''
                elif body.token is not None:
                    ciphertext = await encrypt_project_material(
                        conn,
                        project_id=project['id'],
                        purpose=f'functions-registry:{reg_uuid}',
                        plaintext=str(clean['token']),
                    )
                else:
                    ciphertext = existing['token_ciphertext']
                row = await conn.fetchrow(
                    '''UPDATE project_edge_function_registries
                       SET name=$3, kind=$4, scope=$5, registry_url=$6, auth_type=$7,
                           token_ciphertext=$8, allow_private_network=$9, ca_pem=$10,
                           enabled=$11, updated_by=$12, updated_at=now()
                       WHERE id=$1 AND project_id=$2
                       RETURNING id, name, kind, scope, registry_url, auth_type, token_ciphertext,
                                 allow_private_network, ca_pem, enabled, created_at, updated_at''',
                    reg_uuid, project['id'], clean_name, clean['kind'], clean['scope'], clean['registry_url'],
                    clean['auth_type'], ciphertext, bool(clean['allow_private_network']), ca_pem, target_enabled, actor,
                )
        except Exception as exc:
            await outcome(conn, audit_id, 'failed')
            if exc.__class__.__name__ == 'UniqueViolationError':
                raise _registry_unique_error(exc) from exc
            raise
        await outcome(conn, audit_id, 'completed')
        return {'registry': _registry_row_public(row)}


@router.delete('/registries/{registry_id}')
async def registry_delete(ref: str, registry_id: str, request: Request, response: Response, pool=Depends(get_pool)):
    reg_uuid = _parse_registry_uuid(registry_id)
    async with management_context(ref, request, response, pool) as (conn, project, actor, _):
        existing = await conn.fetchrow(
            'SELECT id, name FROM project_edge_function_registries WHERE id=$1 AND project_id=$2',
            reg_uuid, project['id'],
        )
        if existing is None:
            raise HTTPException(404, 'Registry not found')
        audit_rev = hashlib.sha256(
            json.dumps({'action': 'delete_registry', 'id': str(reg_uuid), 'name': existing['name']}, sort_keys=True).encode()
        ).hexdigest()
        audit_id = await audit(conn, project, actor, 'delete_registry', f"registry:{existing['name']}"[:120], audit_rev)
        deleted = await conn.fetchval(
            'DELETE FROM project_edge_function_registries WHERE id=$1 AND project_id=$2 RETURNING id',
            reg_uuid, project['id'],
        )
        if deleted is None:
            await outcome(conn, audit_id, 'failed')
            raise HTTPException(404, 'Registry not found')
        await outcome(conn, audit_id, 'completed')
        return {'id': str(deleted), 'deleted': True}


@router.post('/gc')
async def versions_gc(ref: str, request: Request, response: Response, body: GcBody | None = None, pool=Depends(get_pool)):
    min_age = body.min_age_seconds if body is not None else store.DEFAULT_ORPHAN_RETENTION_SECONDS
    async with management_context(ref, request, response, pool) as (_, project, _, _):
        state = load(project)
        return store.purge_orphan_versions(ROOT, state, min_age_seconds=min_age)


@router.get('/logs')
async def logs_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool, allow_query=True) as (conn, project, _, _):
        fn_filter, level_filter, limit = _parse_log_query(request, allow_function=True)
        secrets = await load_project_secrets(conn, project, tolerate=True)
        try:
            creds = canonical_projection_credentials(project)
        except RuntimeError:
            creds = {'jwt_secret': '', 'public_url': '', 'anon_key': '', 'service_role_key': '', 'postgres_password': ''}
        project = dict(project)
    async with pool.acquire() as conn:
        return await _fetch_merged_logs(
            conn, project, creds, secrets,
            function_name=fn_filter, level=level_filter, limit=limit,
        )


@router.get('/secrets')
async def secrets_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        quotas, _ = await load_project_quotas(conn, project['id'])
        return {'secrets': await list_secret_metadata(conn, project['id']), 'limits': secret_limits(quotas)}


@router.put('/secrets')
async def secrets_upsert(ref: str, body: SecretsUpdateBody, request: Request, response: Response, pool=Depends(get_pool)):
    updates: dict[str, str] = {}
    try:
        for item in body.secrets:
            name = edge_functions.validate_secret_name(item.name)
            if name in updates:
                raise ValueError(f"Duplicate secret '{name}' in request")
            updates[name] = edge_functions.validate_secret_value(item.value)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        quotas, _ = await load_project_quotas(conn, project['id'])
        current_secrets = await load_project_secrets(conn, project, tolerate=frozenset(updates))
        proposed_secrets = {**current_secrets, **updates}
        try:
            validated = edge_functions.validate_secrets(
                proposed_secrets,
                max_secrets=quotas['max_secrets'],
                max_total_bytes=quotas['max_secrets_total_bytes'],
            )
        except ValueError as error:
            raise HTTPException(400, str(error)) from error
        audit_target = next(iter(updates)) if len(updates) == 1 else ','.join(sorted(updates))[:120]
        audit_rev = hashlib.sha256(json.dumps({'action': 'set_secret', 'names': sorted(updates)}).encode()).hexdigest()
        audit_id = await audit(conn, project, actor, 'set_secret', audit_target, audit_rev)
        state = load(project)
        has_published = bool(store.published_files(ROOT, project['name'], identity(project), state=state))
        runtime_synced = False
        previous = edge_functions.read_context(ROOT, project['name'], identity(project)) if config['enabled'] and has_published else None
        try:
            async with conn.transaction():
                for name, value in sorted(updates.items()):
                    ciphertext = await encrypt_project_material(
                        conn,
                        project_id=project['id'],
                        purpose=f'functions-env-secret:{name}',
                        plaintext=value,
                    )
                    await conn.execute(
                        '''INSERT INTO project_function_secrets(project_id,name,secret_ciphertext,created_by,updated_by)
                           VALUES($1,$2,$3,$4,$4)
                           ON CONFLICT (project_id, name) DO UPDATE
                           SET secret_ciphertext=EXCLUDED.secret_ciphertext,updated_by=EXCLUDED.updated_by,updated_at=now()''',
                        project['id'], name, ciphertext, actor,
                    )
                if config['enabled'] and has_published:
                    context = await prepare(conn, project, state, config, secrets_override=validated)
                    edge_functions.activate_context(ROOT, context)
                    runtime_synced = True
        except Exception:
            if config['enabled'] and has_published:
                if previous is None:
                    edge_functions.withdraw(ROOT, project['name'])
                else:
                    edge_functions.activate_context(ROOT, previous)
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        return {'secrets': await list_secret_metadata(conn, project['id']), 'limits': secret_limits(quotas), 'runtime_synced': runtime_synced}


@router.delete('/secrets/{secret_name}')
async def secret_delete(ref: str, secret_name: str, request: Request, response: Response, pool=Depends(get_pool)):
    try:
        secret_name = edge_functions.validate_secret_name(secret_name)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        quotas, _ = await load_project_quotas(conn, project['id'])
        current_secrets = await load_project_secrets(conn, project, tolerate=frozenset({secret_name}))
        if secret_name not in current_secrets:
            row = await conn.fetchval(
                'SELECT 1 FROM project_function_secrets WHERE project_id=$1 AND name=$2',
                project['id'], secret_name,
            )
            if not row:
                raise HTTPException(404, 'Secret not found')
        proposed_secrets = {k: v for k, v in current_secrets.items() if k != secret_name}
        audit_rev = hashlib.sha256(json.dumps({'action': 'delete_secret', 'name': secret_name}).encode()).hexdigest()
        audit_id = await audit(conn, project, actor, 'delete_secret', secret_name, audit_rev)
        state = load(project)
        has_published = bool(store.published_files(ROOT, project['name'], identity(project), state=state))
        runtime_synced = False
        previous = edge_functions.read_context(ROOT, project['name'], identity(project)) if config['enabled'] and has_published else None
        try:
            async with conn.transaction():
                removed = await conn.fetchval(
                    'DELETE FROM project_function_secrets WHERE project_id=$1 AND name=$2 RETURNING name',
                    project['id'], secret_name,
                )
                if not removed:
                    raise HTTPException(404, 'Secret not found')
                if config['enabled'] and has_published:
                    context = await prepare(conn, project, state, config, secrets_override=proposed_secrets)
                    edge_functions.activate_context(ROOT, context)
                    runtime_synced = True
        except Exception:
            if config['enabled'] and has_published:
                if previous is None:
                    edge_functions.withdraw(ROOT, project['name'])
                else:
                    edge_functions.activate_context(ROOT, previous)
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        return {'deleted': True, 'name': secret_name, 'secrets': await list_secret_metadata(conn, project['id']),
                'limits': secret_limits(quotas), 'runtime_synced': runtime_synced}


@router.get('/{slug}')
async def function_get(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, _, config):
        configs = await load_function_configs(conn, project['id'])
        quotas, _ = await load_project_quotas(conn, project['id'])
        return detail(project, load(project), slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)


def validate_slug(slug):
    try:
        store.function_name(slug)
    except ValueError as error:
        raise HTTPException(400, 'Invalid function name') from error


@router.put('/{slug}')
async def function_save(ref: str, slug: str, body: DraftBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    raw_files = [file.model_dump(exclude_none=True) for file in body.files]
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        quotas, _ = await load_project_quotas(conn, project['id'])
        try:
            files = store.validate_files(raw_files, max_files=quotas['max_files'], max_bytes=quotas['max_bytes'])
            edge_bundler.validate_dependency_policy(files)
        except (ValueError, UnicodeError) as error:
            raise HTTPException(400, str(error)) from error
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if body.expected_revision != (current['revision'] if current else None):
            raise HTTPException(409, 'Function draft changed; reload before saving')
        if not current and sum(1 for ptrs in state['functions'].values() if ptrs.get('draft') is not None) >= quotas['max_functions']:
            raise HTTPException(409, 'Project function limit reached')
        revision = store.store_version(ROOT, project['name'], identity(project), slug, files,
                                       max_files=quotas['max_files'], max_bytes=quotas['max_bytes'])
        state['functions'][slug] = {'draft': revision, 'published': current['published_revision'] if current else None}
        audit_id = await audit(conn, project, actor, 'save_draft', slug, revision)
        try:
            store.atomic_json(store.directory(ROOT, project['name'], identity(project)) / 'state.json', state)
            actor_label = getattr(request.state, 'edge_actor_label', None) or str(actor)
            await _record_revision_author(conn, project['id'], slug, revision, actor, actor_label, 'save_draft')
        except Exception:
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        configs = await load_function_configs(conn, project['id'])
        return detail(project, state, slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)


async def commit_change(conn, project, actor, config, state, proposed, slug, revision, action):
    name, tenant = project['name'], identity(project)
    store.validate_transition(ROOT, state, proposed, action)
    context = await prepare(conn, project, proposed, config) if config['enabled'] else None
    previous = edge_functions.read_context(ROOT, name, tenant) if context else None
    audit_id = await audit(conn, project, actor, action, slug, revision)
    try:
        if context:
            store.begin_publication(ROOT, state, proposed, context, action=action)
            edge_functions.activate_context(ROOT, context)
        else:
            edge_functions.withdraw(ROOT, name)
        store.atomic_json(store.directory(ROOT, name, tenant) / 'state.json', proposed)
    except Exception:
        if context:
            if previous is None:
                edge_functions.withdraw(ROOT, name)
            else:
                edge_functions.activate_context(ROOT, previous)
            store.atomic_json(store.directory(ROOT, name, tenant) / 'state.json', state)
            store.finish_publication(ROOT, name, tenant)
        await outcome(conn, audit_id, 'failed')
        raise
    if context:
        store.finish_publication(ROOT, name, tenant)
    await sync_function_config_publication(conn, project['id'], slug, action, actor)
    if action == 'delete':
        await conn.execute(
            'DELETE FROM project_edge_function_revisions WHERE project_id=$1 AND function_name=$2',
            project['id'], slug,
        )
        await conn.execute(
            'DELETE FROM project_edge_function_schedules WHERE project_id=$1 AND function_name=$2',
            project['id'], slug,
        )
    elif action == 'unpublish':
        await conn.execute(
            '''UPDATE project_edge_function_schedules
               SET enabled=false, next_run_at=NULL,
                   last_error='Disabled on function unpublish',
                   updated_by=$3, updated_at=now()
               WHERE project_id=$1 AND function_name=$2 AND enabled=true''',
            project['id'], slug, actor,
        )
    await outcome(conn, audit_id, 'completed')


def current_version(project, state, slug, enabled, body):
    current = detail(project, state, slug, enabled)
    if body.revision != current['revision'] or body.expected_published_revision != current['published_revision']:
        raise HTTPException(409, 'Function version changed; reload before changing publication')
    return current


async def _bundle_outside_lock(files_to_bundle: list[dict], *, registries: list[dict] | None = None) -> bytes:
    try:
        return await edge_bundler.bundle_function_eszip(files_to_bundle, registries=registries)
    except edge_bundler.DependencyPolicyError as error:
        raise HTTPException(400, str(error)) from error
    except edge_bundler.BundleBuildError as error:
        raise HTTPException(422, str(error)) from error


@router.post('/{slug}/bundle')
async def function_bundle(ref: str, slug: str, body: BundleBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    files_to_bundle: list[dict] | None = None
    registries_to_bundle: list[dict] | None = None
    async with management_context(ref, request, response, pool) as (conn, project, _, config):
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        quotas, _ = await load_project_quotas(conn, project['id'])
        current = detail(project, state, slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)
        if body.revision != current['revision']:
            raise HTTPException(409, 'Function version changed; reload before bundling')
        dep_info = dependency_summary(current['files'])
        if not dep_info['requires_bundle'] or (store.has_bundle(ROOT, state, slug, body.revision) and not body.force):
            return current
        registries_to_bundle = await load_active_registries_for_bundle(conn, project)
        files_to_bundle = copy.deepcopy(current['files'])
    eszip_bytes = await _bundle_outside_lock(files_to_bundle, registries=registries_to_bundle)
    async with management_context(ref, request, response, pool) as (conn, project, _, config):
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        quotas, _ = await load_project_quotas(conn, project['id'])
        current = detail(project, state, slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)
        if body.revision != current['revision']:
            raise HTTPException(409, 'Function version changed; reload before bundling')
        store.write_bundle(ROOT, state, slug, body.revision, eszip_bytes)
        return detail(project, state, slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)


@router.post('/{slug}/publish')
async def function_publish(ref: str, slug: str, body: PublishBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    files_to_bundle: list[dict] | None = None
    registries_to_bundle: list[dict] | None = None
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        if not config['enabled']:
            raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        current = current_version(project, state, slug, True, body)
        verify_jwt = configs.get(slug, True)
        if current['published_revision'] == body.revision:
            await sync_function_config_publication(conn, project['id'], slug, 'publish', actor)
            return {**current, 'verify_jwt': verify_jwt}
        dep_info = dependency_summary(current['files'])
        if dep_info['requires_bundle'] and not store.has_bundle(ROOT, state, slug, body.revision):
            registries_to_bundle = await load_active_registries_for_bundle(conn, project)
            files_to_bundle = copy.deepcopy(current['files'])
        else:
            proposed = copy.deepcopy(state)
            proposed['functions'][slug]['published'] = body.revision
            await commit_change(conn, project, actor, config, state, proposed, slug, body.revision, 'publish')
            quotas, _ = await load_project_quotas(conn, project['id'])
            return detail(project, proposed, slug, True, verify_jwt=verify_jwt, quotas=quotas)

    eszip_bytes = await _bundle_outside_lock(files_to_bundle, registries=registries_to_bundle)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        if not config['enabled']:
            raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        current = current_version(project, state, slug, True, body)
        verify_jwt = configs.get(slug, True)
        store.write_bundle(ROOT, state, slug, body.revision, eszip_bytes)
        proposed = copy.deepcopy(state)
        proposed['functions'][slug]['published'] = body.revision
        await commit_change(conn, project, actor, config, state, proposed, slug, body.revision, 'publish')
        quotas, _ = await load_project_quotas(conn, project['id'])
        return detail(project, proposed, slug, True, verify_jwt=verify_jwt, quotas=quotas)


@router.post('/{slug}/unpublish')
async def function_unpublish(ref: str, slug: str, body: PublishBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        configs = await load_function_configs(conn, project['id'])
        current = current_version(project, state, slug, config['enabled'], body)
        verify_jwt = configs.get(slug, True)
        if current['published_revision'] is None:
            await sync_function_config_publication(conn, project['id'], slug, 'unpublish', actor)
            return {**current, 'verify_jwt': verify_jwt}
        proposed = copy.deepcopy(state)
        proposed['functions'][slug]['published'] = None
        await commit_change(conn, project, actor, config, state, proposed, slug, current['revision'], 'unpublish')
        quotas, _ = await load_project_quotas(conn, project['id'])
        return detail(project, proposed, slug, config['enabled'], verify_jwt=verify_jwt, quotas=quotas)


@router.put('/{slug}/config')
async def function_configure(ref: str, slug: str, body: FunctionConfigBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = detail(project, state, slug, config['enabled'])
        is_published = current['published_revision'] is not None
        configs = await load_function_configs(conn, project['id'])
        proposed_configs = {**configs, slug: bool(body.verify_jwt)}
        audit_rev = hashlib.sha256(json.dumps({'action': 'configure_function', 'slug': slug, 'verify_jwt': bool(body.verify_jwt)}).encode()).hexdigest()
        audit_id = await audit(conn, project, actor, 'configure_function', slug, audit_rev)
        previous = edge_functions.read_context(ROOT, project['name'], identity(project)) if config['enabled'] and is_published else None
        try:
            async with conn.transaction():
                await conn.execute(
                    '''INSERT INTO project_edge_function_configs(project_id,function_name,verify_jwt,published,updated_by)
                       VALUES($1,$2,$3,$4,$5)
                       ON CONFLICT (project_id, function_name) DO UPDATE
                       SET verify_jwt=EXCLUDED.verify_jwt,published=EXCLUDED.published,updated_by=EXCLUDED.updated_by,updated_at=now()''',
                    project['id'], slug, bool(body.verify_jwt), is_published, actor,
                )
                if config['enabled'] and is_published:
                    context = await prepare(conn, project, state, config, configs_override=proposed_configs)
                    edge_functions.activate_context(ROOT, context)
        except Exception:
            if config['enabled'] and is_published:
                if previous is None:
                    edge_functions.withdraw(ROOT, project['name'])
                else:
                    edge_functions.activate_context(ROOT, previous)
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        quotas, _ = await load_project_quotas(conn, project['id'])
        return detail(project, state, slug, config['enabled'], verify_jwt=bool(body.verify_jwt), quotas=quotas)


@router.get('/{slug}/logs')
async def function_logs(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool, allow_query=True) as (conn, project, _, _):
        state = load(project)
        if store.item(ROOT, state, slug, {}) is None:
            raise HTTPException(404, 'Function not found')
        _, level_filter, limit = _parse_log_query(request, allow_function=False)
        secrets = await load_project_secrets(conn, project, tolerate=True)
        try:
            creds = canonical_projection_credentials(project)
        except RuntimeError:
            creds = {'jwt_secret': '', 'public_url': '', 'anon_key': '', 'service_role_key': '', 'postgres_password': ''}
        project = dict(project)
    async with pool.acquire() as conn:
        return await _fetch_merged_logs(
            conn, project, creds, secrets,
            function_name=slug, level=level_filter, limit=limit,
        )


async def _execute_function_http(
    pool,
    project_snapshot: dict,
    creds: dict[str, str],
    keys: dict[str, str],
    secrets_snapshot: dict[str, str],
    sensitive: list[str],
    *,
    slug: str,
    published_rev: str,
    method: str,
    auth_mode: str,
    path_with_query: str,
    req_headers: dict[str, str],
    req_body: bytes | None,
    source: str = 'studio_test',
    audit_id: int | None = None,
    worker_timeout_ms: int | None = None,
) -> tuple[int, dict[str, str], str, bool, int, str, str | None]:
    request_id = str(uuid.uuid4())
    headers = dict(req_headers)
    target_url = f'{_runtime_base_url()}/{slug}{path_with_query}'
    headers['x-project-name'] = project_snapshot['name']
    headers['x-project-ref'] = project_snapshot['public_ref']
    headers['x-request-id'] = request_id
    if creds.get('edge_gateway_token'):
        headers['x-edge-gateway-token'] = creds['edge_gateway_token']
    if auth_mode == 'anon':
        headers['apikey'] = creds['anon_key'] or keys['publishable']
        headers['authorization'] = f"Bearer {_mint_hs256_jwt(creds['jwt_secret'], 'anon')}"
    elif auth_mode == 'service_role':
        headers['apikey'] = creds['service_role_key'] or keys['secret']
        headers['authorization'] = f"Bearer {_mint_hs256_jwt(creds['jwt_secret'], 'service_role')}"

    started = time.monotonic()
    resp_status = 502
    resp_headers: dict[str, str] = {}
    resp_body_bytes = bytearray()
    truncated = False
    default_timeout_ms = edge_functions.QUOTA_SPECS['worker_timeout_ms']['default']
    effective_timeout_ms = worker_timeout_ms if isinstance(worker_timeout_ms, int) and worker_timeout_ms > 0 else default_timeout_ms
    http_timeout_sec = max(65.0, (effective_timeout_ms / 1000.0) + 5.0)
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(http_timeout_sec, connect=5.0),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            async with client.stream(method, target_url, headers=headers, content=req_body) as upstream:
                resp_status = upstream.status_code
                for k, v in upstream.headers.multi_items():
                    kl = k.lower()
                    if kl not in OMITTED_RESPONSE_HEADERS and len(resp_headers) < 64:
                        resp_headers[kl] = v[:4096]
                async for chunk in upstream.aiter_bytes():
                    remaining = (MAX_RESPONSE_BODY_BYTES + 1) - len(resp_body_bytes)
                    if remaining <= 0:
                        truncated = True
                        break
                    resp_body_bytes.extend(chunk[:remaining])
                    if len(resp_body_bytes) > MAX_RESPONSE_BODY_BYTES:
                        del resp_body_bytes[MAX_RESPONSE_BODY_BYTES:]
                        truncated = True
                        break
    except httpx.HTTPError as error:
        duration_ms = int((time.monotonic() - started) * 1000)
        err_name = type(error).__name__
        async with pool.acquire() as conn:
            await _persist_invocation_log(
                conn, project_snapshot['id'], slug, request_id, method,
                path_with_query or '/', 502, duration_ms, source, 'error', True,
                f'{method} /{slug}{path_with_query} -> upstream unavailable ({err_name})',
                sensitive,
            )
            if audit_id is not None:
                await outcome(conn, audit_id, 'failed')
        return 502, {}, '', False, duration_ms, request_id, err_name

    duration_ms = int((time.monotonic() - started) * 1000)
    level = 'error' if resp_status >= 500 else 'warn' if resp_status >= 400 else 'info'
    async with pool.acquire() as conn:
        await _persist_invocation_log(
            conn, project_snapshot['id'], slug, request_id, method,
            path_with_query or '/', resp_status, duration_ms, source, level, True,
            f'{method} /{slug}{path_with_query} -> {resp_status}',
            sensitive,
        )
        if resp_status == 429:
            await _record_quota_event(
                conn, project_snapshot['id'], 'concurrency_429', 'critical',
                f"Function '{slug}' returned HTTP 429 during invocation",
                function_name=slug, detail={'status': 429, 'request_id': request_id, 'source': source},
            )
        if audit_id is not None:
            await outcome(conn, audit_id, 'completed')
    effective_req_id = resp_headers.get('x-request-id', request_id)
    return (
        resp_status,
        resp_headers,
        bytes(resp_body_bytes).decode('utf-8', errors='replace'),
        truncated,
        duration_ms,
        effective_req_id,
        None,
    )


@router.post('/{slug}/invoke')
async def function_invoke(ref: str, slug: str, body: InvokeBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    method, auth_mode, path_with_query, req_headers, req_body = _validate_invoke_request(body)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        if not config['enabled']:
            raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        published_rev = current['published_revision']
        if published_rev is None:
            raise HTTPException(409, 'Function has no published revision; publish it before invoking')
        draft_rev = current['revision']
        creds = canonical_projection_credentials(project)
        keys = await internal_keys(conn, project)
        secrets = await load_project_secrets(conn, project, tolerate=True)
        sensitive = _collect_sensitive_values(project, creds, secrets)
        quotas, _ = await load_project_quotas(conn, project['id'])
        worker_timeout_ms = quotas.get('worker_timeout_ms')
        project_snapshot = dict(project)
        secrets_snapshot = dict(secrets)
        audit_id = await audit(conn, project, actor, 'test_invoke', slug, published_rev)

    resp_status, resp_headers, body_str, truncated, duration_ms, effective_req_id, err_name = (
        await _execute_function_http(
            pool, project_snapshot, creds, keys, secrets_snapshot, sensitive,
            slug=slug, published_rev=published_rev, method=method, auth_mode=auth_mode,
            path_with_query=path_with_query, req_headers=req_headers, req_body=req_body,
            source='studio_test', audit_id=audit_id, worker_timeout_ms=worker_timeout_ms,
        )
    )
    if err_name is not None:
        raise HTTPException(502, 'Edge Function runtime unavailable')
    async with pool.acquire() as conn:
        recent = await _fetch_merged_logs(
            conn, project_snapshot, creds, secrets_snapshot,
            function_name=slug, level=None, limit=20,
        )

    return {
        'status': resp_status,
        'headers': resp_headers,
        'body': body_str,
        'truncated': truncated,
        'duration_ms': duration_ms,
        'request_id': effective_req_id,
        'executed_revision': published_rev,
        'draft_revision': draft_rev,
        'stale_draft_warning': draft_rev != published_rev,
        'logs': recent['logs'],
    }


@router.get('/{slug}/versions')
async def function_versions(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        authors = await _load_revision_authors(conn, project['id'], slug)
        versions = []
        for entry in store.list_versions(ROOT, state, slug):
            meta = authors.get(entry['revision'], {})
            versions.append({
                **entry,
                'author_id': meta.get('author_id'),
                'author_label': meta.get('author_label'),
            })
        return {
            'name': slug,
            'draft_revision': current['revision'],
            'published_revision': current['published_revision'],
            'versions': versions,
        }


@router.get('/{slug}/versions/{revision}')
async def function_version_detail(ref: str, slug: str, revision: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    if not store.REVISION.fullmatch(revision):
        raise HTTPException(400, 'Invalid function revision')
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        try:
            files = store.read_version(ROOT, state, slug, revision)
        except FileNotFoundError as error:
            raise HTTPException(404, 'Function version not found') from error
        authors = await _load_revision_authors(conn, project['id'], slug)
        meta = authors.get(revision, {})
        version_entry = next((v for v in store.list_versions(ROOT, state, slug) if v['revision'] == revision), None)
        return {
            'name': slug,
            'revision': revision,
            'created_at': version_entry['created_at'] if version_entry else None,
            'is_draft': current['revision'] == revision,
            'is_published': current['published_revision'] == revision,
            'author_id': meta.get('author_id'),
            'author_label': meta.get('author_label'),
            'files': files,
        }


@router.get('/{slug}/diff')
async def function_version_diff(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool, allow_query=True) as (_, project, _, _):
        unknown = set(request.query_params.keys()) - {'from', 'to'}
        if unknown:
            raise HTTPException(400, f"Unsupported query parameters: {', '.join(sorted(unknown))}")
        from_sel = request.query_params.get('from')
        to_sel = request.query_params.get('to') or 'draft'
        if not from_sel:
            raise HTTPException(400, "Query parameter 'from' is required")
        state = load(project)
        from_rev, from_files = _resolve_revision_snapshot(state, slug, from_sel)
        to_rev, to_files = _resolve_revision_snapshot(state, slug, to_sel)
        return store.compute_version_diff(slug, from_rev, from_files, to_rev, to_files)


@router.get('/{slug}/download')
async def function_download(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool, allow_query=True) as (conn, project, _, _):
        unknown = set(request.query_params.keys()) - {'version'}
        if unknown:
            raise HTTPException(400, f"Unsupported query parameters: {', '.join(sorted(unknown))}")
        selector = request.query_params.get('version') or 'draft'
        state = load(project)
        target_rev, files = _resolve_revision_snapshot(state, slug, selector)
        configs = await load_function_configs(conn, project['id'])
        zip_bytes = _build_function_bundle_zip(slug, target_rev, files, verify_jwt=configs.get(slug, True))
        return Response(
            content=zip_bytes,
            media_type='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{slug}-{target_rev[:12]}.zip"',
                'Cache-Control': 'no-store',
                'X-Content-Type-Options': 'nosniff',
            },
        )


@router.post('/{slug}/rollback')
async def function_rollback(ref: str, slug: str, body: RollbackBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        if body.expected_revision != current['revision']:
            raise HTTPException(409, 'Function draft changed; reload before rolling back')
        try:
            store.read_version(ROOT, state, slug, body.revision)
        except FileNotFoundError as error:
            raise HTTPException(404, 'Function version not found') from error
        state['functions'][slug] = {'draft': body.revision, 'published': current['published_revision']}
        audit_id = await audit(conn, project, actor, 'rollback', slug, body.revision)
        try:
            store.atomic_json(store.directory(ROOT, project['name'], identity(project)) / 'state.json', state)
        except Exception:
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        configs = await load_function_configs(conn, project['id'])
        quotas, _ = await load_project_quotas(conn, project['id'])
        return detail(project, state, slug, config['enabled'], verify_jwt=configs.get(slug, True), quotas=quotas)


@router.delete('/{slug}')
async def function_delete(ref: str, slug: str, body: PublishBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = current_version(project, state, slug, config['enabled'], body)
        proposed = copy.deepcopy(state)
        proposed['functions'].pop(slug)
        await commit_change(conn, project, actor, config, state, proposed, slug, current['revision'], 'delete')
        return {'name': slug, 'deleted': True}


_SCHEDULE_LOCK_NAME = 'edge-function-schedules-v1'
_SCHEDULE_POLL_SECONDS = max(5, int(os.environ.get('EDGE_FUNCTION_SCHEDULE_POLL_SECONDS', '15')))
_schedule_task: asyncio.Task | None = None


def _schedule_row_dict(row) -> dict:
    raw_headers = row['headers_json']
    headers = json.loads(raw_headers) if isinstance(raw_headers, str) else dict(raw_headers or {})
    return {
        'id': str(row['id']),
        'project_id': str(row['project_id']),
        'function_name': row['function_name'],
        'name': row['name'],
        'cron': row['cron'],
        'timezone': row['timezone'],
        'method': row['method'],
        'path': row['path'],
        'headers': headers,
        'body': row['body'],
        'auth_mode': row['auth_mode'],
        'enabled': bool(row['enabled']),
        'next_run_at': row['next_run_at'].isoformat() if row['next_run_at'] else None,
        'last_run_at': row['last_run_at'].isoformat() if row['last_run_at'] else None,
        'last_status': row['last_status'],
        'last_duration_ms': row['last_duration_ms'],
        'last_request_id': row['last_request_id'],
        'last_error': row['last_error'] or '',
        'created_at': row['created_at'].isoformat(),
        'updated_at': row['updated_at'].isoformat(),
    }


def _validate_schedule_inputs(
    *, name: str, cron: str, method: str, path: str, headers: dict, body: str, auth_mode: str,
) -> tuple[str, str, str, str, str, dict[str, str], bytes | None]:
    try:
        clean_name = store.validate_schedule_name(name)
        clean_cron = store.validate_cron_expression(cron)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if len(body.encode('utf-8')) > 65536:
        raise HTTPException(400, 'Schedule payload body exceeds 64 KiB limit')
    v_method, v_auth_mode, path_with_query, v_headers, v_body = _validate_invoke_request(
        SimpleNamespace(
            method=method,
            path=path,
            headers=headers,
            body=body if body != '' else None,
            auth_mode=auth_mode,
        )
    )
    if v_method not in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}:
        raise HTTPException(400, f'Unsupported schedule HTTP method: {method}')
    if v_auth_mode not in {'anon', 'service_role', 'none'}:
        raise HTTPException(400, f'Unsupported schedule auth_mode: {auth_mode}')
    db_path = f'/{path_with_query}' if path_with_query.startswith('?') else (path_with_query or '/')
    if len(db_path) > 256:
        raise HTTPException(400, 'Schedule request path exceeds 256 characters')
    return clean_name, clean_cron, v_method, db_path, v_auth_mode, v_headers, v_body


def _parse_schedule_uuid(schedule_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(schedule_id)
    except ValueError as error:
        raise HTTPException(400, 'Invalid schedule identifier') from error


@router.get('/{slug}/schedules')
async def function_schedules_list(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, _, _):
        state = load(project)
        if store.item(ROOT, state, slug, {}) is None:
            raise HTTPException(404, 'Function not found')
        rows = await conn.fetch(
            '''SELECT id, project_id, function_name, name, cron, timezone, method, path, headers_json,
                      body, auth_mode, enabled, next_run_at, last_run_at, last_status, last_duration_ms,
                      last_request_id, last_error, created_at, updated_at
               FROM project_edge_function_schedules
               WHERE project_id=$1 AND function_name=$2
               ORDER BY name ASC''',
            project['id'], slug,
        )
        return {'schedules': [_schedule_row_dict(r) for r in rows]}


@router.post('/{slug}/schedules')
async def function_schedule_create(ref: str, slug: str, body: ScheduleCreateBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    clean_name, clean_cron, v_method, db_path, v_auth_mode, v_headers, _ = _validate_schedule_inputs(
        name=body.name, cron=body.cron, method=body.method, path=body.path,
        headers=body.headers, body=body.body, auth_mode=body.auth_mode,
    )
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        if body.enabled:
            if not config['enabled']:
                raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
            if current['published_revision'] is None:
                raise HTTPException(409, 'Function must be published before enabling a schedule')
        proj_count = await conn.fetchval(
            'SELECT count(*) FROM project_edge_function_schedules WHERE project_id=$1',
            project['id'],
        )
        if proj_count >= store.MAX_SCHEDULES_PER_PROJECT:
            raise HTTPException(409, f'Project reached maximum of {store.MAX_SCHEDULES_PER_PROJECT} schedules')
        fn_count = await conn.fetchval(
            'SELECT count(*) FROM project_edge_function_schedules WHERE project_id=$1 AND function_name=$2',
            project['id'], slug,
        )
        if fn_count >= store.MAX_SCHEDULES_PER_FUNCTION:
            raise HTTPException(409, f'Function reached maximum of {store.MAX_SCHEDULES_PER_FUNCTION} schedules')

        next_run = store.next_cron_run(clean_cron) if body.enabled else None
        rev_marker = current['published_revision'] or current['revision']
        audit_id = await audit(conn, project, actor, 'configure_schedule', slug, rev_marker)
        try:
            row = await conn.fetchrow(
                '''INSERT INTO project_edge_function_schedules
                   (project_id, function_name, name, cron, timezone, method, path, headers_json,
                    body, auth_mode, enabled, next_run_at, created_by, updated_by)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,$13,$13)
                   RETURNING id, project_id, function_name, name, cron, timezone, method, path, headers_json,
                             body, auth_mode, enabled, next_run_at, last_run_at, last_status, last_duration_ms,
                             last_request_id, last_error, created_at, updated_at''',
                project['id'], slug, clean_name, clean_cron, body.timezone, v_method, db_path,
                json.dumps(v_headers), body.body, v_auth_mode, body.enabled, next_run, actor,
            )
        except Exception as exc:
            await outcome(conn, audit_id, 'failed')
            if exc.__class__.__name__ == 'UniqueViolationError':
                raise HTTPException(409, 'A schedule with this name already exists for this function') from exc
            raise
        await outcome(conn, audit_id, 'completed')
        return {'schedule': _schedule_row_dict(row)}


@router.put('/{slug}/schedules/{schedule_id}')
async def function_schedule_update(
    ref: str, slug: str, schedule_id: str, body: ScheduleUpdateBody,
    request: Request, response: Response, pool=Depends(get_pool),
):
    validate_slug(slug)
    sched_uuid = _parse_schedule_uuid(schedule_id)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        existing = await conn.fetchrow(
            '''SELECT id, name, cron, timezone, method, path, headers_json, body, auth_mode, enabled, next_run_at
               FROM project_edge_function_schedules
               WHERE id=$1 AND project_id=$2 AND function_name=$3''',
            sched_uuid, project['id'], slug,
        )
        if existing is None:
            raise HTTPException(404, 'Schedule not found')

        existing_headers = existing['headers_json']
        if isinstance(existing_headers, str):
            existing_headers = json.loads(existing_headers)
        target_enabled = bool(existing['enabled']) if body.enabled is None else body.enabled
        clean_name, clean_cron, v_method, db_path, v_auth_mode, v_headers, _ = _validate_schedule_inputs(
            name=body.name if body.name is not None else existing['name'],
            cron=body.cron if body.cron is not None else existing['cron'],
            method=body.method if body.method is not None else existing['method'],
            path=body.path if body.path is not None else existing['path'],
            headers=body.headers if body.headers is not None else dict(existing_headers or {}),
            body=body.body if body.body is not None else existing['body'],
            auth_mode=body.auth_mode if body.auth_mode is not None else existing['auth_mode'],
        )
        target_body = body.body if body.body is not None else existing['body']
        if target_enabled:
            if not config['enabled']:
                raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
            if current['published_revision'] is None:
                raise HTTPException(409, 'Function must be published before enabling a schedule')
            next_run = (
                store.next_cron_run(clean_cron)
                if (body.cron is not None or not existing['enabled'] or existing['next_run_at'] is None)
                else existing['next_run_at']
            )
        else:
            next_run = None

        rev_marker = current['published_revision'] or current['revision']
        audit_id = await audit(conn, project, actor, 'configure_schedule', slug, rev_marker)
        try:
            row = await conn.fetchrow(
                '''UPDATE project_edge_function_schedules
                   SET name=$4, cron=$5, timezone=$6, method=$7, path=$8, headers_json=$9::jsonb,
                       body=$10, auth_mode=$11, enabled=$12, next_run_at=$13,
                       last_error=CASE WHEN $12 THEN '' ELSE last_error END,
                       updated_by=$14, updated_at=now()
                   WHERE id=$1 AND project_id=$2 AND function_name=$3
                   RETURNING id, project_id, function_name, name, cron, timezone, method, path, headers_json,
                             body, auth_mode, enabled, next_run_at, last_run_at, last_status, last_duration_ms,
                             last_request_id, last_error, created_at, updated_at''',
                sched_uuid, project['id'], slug, clean_name, clean_cron,
                body.timezone or existing['timezone'], v_method, db_path, json.dumps(v_headers),
                target_body, v_auth_mode, target_enabled, next_run, actor,
            )
        except Exception as exc:
            await outcome(conn, audit_id, 'failed')
            if exc.__class__.__name__ == 'UniqueViolationError':
                raise HTTPException(409, 'A schedule with this name already exists for this function') from exc
            raise
        await outcome(conn, audit_id, 'completed')
        return {'schedule': _schedule_row_dict(row)}


@router.delete('/{slug}/schedules/{schedule_id}')
async def function_schedule_delete(
    ref: str, slug: str, schedule_id: str,
    request: Request, response: Response, pool=Depends(get_pool),
):
    validate_slug(slug)
    sched_uuid = _parse_schedule_uuid(schedule_id)
    async with management_context(ref, request, response, pool) as (conn, project, actor, _):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        rev_marker = (current['published_revision'] or current['revision']) if current else None
        audit_id = await audit(conn, project, actor, 'delete_schedule', slug, rev_marker)
        deleted = await conn.fetchval(
            '''DELETE FROM project_edge_function_schedules
               WHERE id=$1 AND project_id=$2 AND function_name=$3
               RETURNING id''',
            sched_uuid, project['id'], slug,
        )
        if deleted is None:
            await outcome(conn, audit_id, 'failed')
            raise HTTPException(404, 'Schedule not found')
        await outcome(conn, audit_id, 'completed')
        return {'id': str(deleted), 'deleted': True}


@router.post('/{slug}/schedules/{schedule_id}/trigger')
async def function_schedule_trigger(
    ref: str, slug: str, schedule_id: str,
    request: Request, response: Response, pool=Depends(get_pool),
):
    validate_slug(slug)
    sched_uuid = _parse_schedule_uuid(schedule_id)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        if not config['enabled']:
            raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if current is None:
            raise HTTPException(404, 'Function not found')
        published_rev = current['published_revision']
        if published_rev is None:
            raise HTTPException(409, 'Function has no published revision; publish it before invoking')
        sched = await conn.fetchrow(
            '''SELECT id, name, method, path, headers_json, body, auth_mode
               FROM project_edge_function_schedules
               WHERE id=$1 AND project_id=$2 AND function_name=$3''',
            sched_uuid, project['id'], slug,
        )
        if sched is None:
            raise HTTPException(404, 'Schedule not found')
        headers_raw = sched['headers_json']
        headers_map = json.loads(headers_raw) if isinstance(headers_raw, str) else dict(headers_raw or {})
        _, _, path_with_query, v_headers, v_body = _validate_invoke_request(
            SimpleNamespace(
                method=sched['method'],
                path=sched['path'],
                headers=headers_map,
                body=sched['body'] if sched['body'] != '' else None,
                auth_mode=sched['auth_mode'],
            )
        )
        creds = canonical_projection_credentials(project)
        keys = await internal_keys(conn, project)
        secrets = await load_project_secrets(conn, project, tolerate=True)
        sensitive = _collect_sensitive_values(project, creds, secrets)
        quotas, _ = await load_project_quotas(conn, project['id'])
        worker_timeout_ms = quotas.get('worker_timeout_ms')
        project_snapshot = dict(project)
        secrets_snapshot = dict(secrets)
        method_snapshot = sched['method']
        auth_snapshot = sched['auth_mode']
        audit_id = await audit(conn, project, actor, 'test_invoke', slug, published_rev)

    resp_status, resp_headers, body_str, truncated, duration_ms, effective_req_id, err_name = (
        await _execute_function_http(
            pool, project_snapshot, creds, keys, secrets_snapshot, sensitive,
            slug=slug, published_rev=published_rev, method=method_snapshot, auth_mode=auth_snapshot,
            path_with_query=path_with_query, req_headers=v_headers, req_body=v_body,
            source='cron', audit_id=audit_id, worker_timeout_ms=worker_timeout_ms,
        )
    )
    err_text = f'Upstream unavailable ({err_name})' if err_name else (f'HTTP {resp_status}' if resp_status >= 500 else '')
    async with pool.acquire() as conn:
        updated_row = await conn.fetchrow(
            '''UPDATE project_edge_function_schedules
               SET last_run_at=now(), last_status=$2, last_duration_ms=$3,
                   last_request_id=$4, last_error=$5, updated_at=now()
               WHERE id=$1
               RETURNING id, project_id, function_name, name, cron, timezone, method, path, headers_json,
                         body, auth_mode, enabled, next_run_at, last_run_at, last_status, last_duration_ms,
                         last_request_id, last_error, created_at, updated_at''',
            sched_uuid, resp_status, duration_ms, effective_req_id, err_text,
        )
    if err_name is not None:
        raise HTTPException(502, 'Edge Function runtime unavailable')
    return {
        'schedule': _schedule_row_dict(updated_row),
        'invocation': {
            'status': resp_status,
            'headers': resp_headers,
            'body': body_str,
            'truncated': truncated,
            'duration_ms': duration_ms,
            'request_id': effective_req_id,
        },
    }


async def scan_edge_function_schedules(pool, *, now: datetime | None = None) -> int:
    """Claim due cron-scheduled Edge Function invocations under a short advisory lock, then execute concurrently."""
    current_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    claimed_jobs: list[dict[str, Any]] = []
    async with pool.acquire() as lock_conn:
        owns = await lock_conn.fetchval(
            'SELECT pg_try_advisory_lock(hashtextextended($1, 0))',
            _SCHEDULE_LOCK_NAME,
        )
        if not owns:
            return 0
        try:
            due_rows = await lock_conn.fetch(
                '''SELECT s.id, s.project_id, s.function_name, s.cron, s.method, s.path,
                          s.headers_json, s.body, s.auth_mode,
                          p.name AS project_name, p.public_ref, p.tenant_uuid
                   FROM project_edge_function_schedules s
                   JOIN projects p ON p.id = s.project_id
                   WHERE s.enabled = true AND s.next_run_at IS NOT NULL AND s.next_run_at <= $1
                   ORDER BY s.next_run_at ASC
                   LIMIT 16''',
                current_now,
            )
            for row in due_rows:
                sched_id = row['id']
                slug = row['function_name']
                project_row = {
                    'id': row['project_id'],
                    'name': row['project_name'],
                    'public_ref': row['public_ref'],
                    'tenant_uuid': row['tenant_uuid'],
                }
                config = await configuration(lock_conn, project_row['id'])
                published_rev: str | None = None
                if config['enabled']:
                    with suppress(OSError, RuntimeError, ValueError, KeyError, TypeError, UnicodeError):
                        state = store.read_state(ROOT, project_row['name'], identity(project_row))
                        current = store.item(ROOT, state, slug, {})
                        if current is not None:
                            published_rev = current['published_revision']
                if not config['enabled'] or published_rev is None:
                    reason = (
                        'Auto-disabled: Edge Functions disabled'
                        if not config['enabled']
                        else 'Auto-disabled: function missing or unpublished'
                    )
                    await lock_conn.execute(
                        '''UPDATE project_edge_function_schedules
                           SET enabled=false, next_run_at=NULL, last_error=$2, updated_at=now()
                           WHERE id=$1''',
                        sched_id, reason,
                    )
                    continue

                upcoming = store.next_cron_run(row['cron'], after=current_now)
                await lock_conn.execute(
                    '''UPDATE project_edge_function_schedules
                       SET next_run_at=$2, last_run_at=$3, updated_at=now()
                       WHERE id=$1''',
                    sched_id, upcoming, current_now,
                )

                try:
                    headers_raw = row['headers_json']
                    headers_map = json.loads(headers_raw) if isinstance(headers_raw, str) else dict(headers_raw or {})
                    _, _, path_with_query, v_headers, v_body = _validate_invoke_request(
                        SimpleNamespace(
                            method=row['method'],
                            path=row['path'],
                            headers=headers_map,
                            body=row['body'] if row['body'] != '' else None,
                            auth_mode=row['auth_mode'],
                        )
                    )
                    creds = canonical_projection_credentials(project_row)
                    keys = await internal_keys(lock_conn, project_row)
                    secrets = await load_project_secrets(lock_conn, project_row, tolerate=True)
                    sensitive = _collect_sensitive_values(project_row, creds, secrets)
                    quotas, _ = await load_project_quotas(lock_conn, project_row['id'])
                    timeout_ms = quotas.get('worker_timeout_ms')
                except Exception as prep_err:
                    await lock_conn.execute(
                        '''UPDATE project_edge_function_schedules
                           SET last_status=500, last_error=$2, updated_at=now()
                           WHERE id=$1''',
                        sched_id, f'Preparation failed: {str(prep_err)[:300]}',
                    )
                    continue

                claimed_jobs.append({
                    'sched_id': sched_id,
                    'project_row': project_row,
                    'creds': creds,
                    'keys': keys,
                    'secrets': secrets,
                    'sensitive': sensitive,
                    'slug': slug,
                    'published_rev': published_rev,
                    'method': row['method'],
                    'auth_mode': row['auth_mode'],
                    'path_with_query': path_with_query,
                    'req_headers': v_headers,
                    'req_body': v_body,
                    'timeout_ms': timeout_ms,
                })
        finally:
            await lock_conn.fetchval(
                'SELECT pg_advisory_unlock(hashtextextended($1, 0))',
                _SCHEDULE_LOCK_NAME,
            )

    if not claimed_jobs:
        return 0

    sem = asyncio.Semaphore(4)

    async def _run_one(item: dict[str, Any]) -> int:
        async with sem:
            resp_status, _, _, _, duration_ms, req_id, err_name = await _execute_function_http(
                pool, item['project_row'], item['creds'], item['keys'], item['secrets'], item['sensitive'],
                slug=item['slug'], published_rev=item['published_rev'], method=item['method'],
                auth_mode=item['auth_mode'], path_with_query=item['path_with_query'],
                req_headers=item['req_headers'], req_body=item['req_body'], source='cron',
                worker_timeout_ms=item['timeout_ms'],
            )
            if err_name:
                err_text = f'Upstream unavailable ({err_name})'
            elif resp_status == 429:
                err_text = 'HTTP 429 (concurrency limit reached)'
            elif resp_status >= 500:
                err_text = f'HTTP {resp_status}'
            else:
                err_text = ''
            async with pool.acquire() as update_conn:
                await update_conn.execute(
                    '''UPDATE project_edge_function_schedules
                       SET last_status=$2, last_duration_ms=$3, last_request_id=$4, last_error=$5, updated_at=now()
                       WHERE id=$1''',
                    item['sched_id'], resp_status, duration_ms, req_id, err_text,
                )
            return 1

    results = await asyncio.gather(*(_run_one(item) for item in claimed_jobs))
    return sum(results)


async def _edge_schedule_loop() -> None:
    while True:
        try:
            pool = await get_pool()
            await scan_edge_function_schedules(pool)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Edge Function schedule scan failed: %s', exc)
        await asyncio.sleep(_SCHEDULE_POLL_SECONDS)


async def start_edge_function_scheduler() -> None:
    global _schedule_task
    if _schedule_task is not None:
        return
    _schedule_task = asyncio.create_task(_edge_schedule_loop(), name='edge-function-schedules')


async def stop_edge_function_scheduler() -> None:
    global _schedule_task
    if _schedule_task is None:
        return
    _schedule_task.cancel()
    with suppress(asyncio.CancelledError):
        await _schedule_task
    _schedule_task = None
