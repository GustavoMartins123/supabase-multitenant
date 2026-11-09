"""Studio-managed, tenant-bound drafts and publication for the shared runtime."""
from __future__ import annotations

from contextlib import asynccontextmanager
import copy
import json
import logging
from pathlib import Path

from dotenv import dotenv_values
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictStr

from app import edge_function_store as store, edge_functions
from app.database import get_pool
from app.dependencies import ensure_project_admin_access, get_public_project_row, resolve_authenticated_user
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
    content: StrictStr = Field(max_length=store.MAX_BYTES)


class DraftBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    expected_revision: StrictStr | None = Field(..., max_length=64)
    files: list[CodeFile] = Field(min_length=1, max_length=store.MAX_FILES)


class PublishBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    revision: StrictStr = Field(pattern=r'^[0-9a-f]{64}$')
    expected_published_revision: StrictStr | None = Field(..., max_length=64)


async def configuration(conn, project_id):
    row = await conn.fetchrow('SELECT enabled,network_allowlist FROM project_edge_functions WHERE project_id=$1', project_id)
    if row is None:
        return {'enabled': False, 'network_allowlist': []}
    allowlist = row['network_allowlist']
    if isinstance(allowlist, str):
        allowlist = json.loads(allowlist)
    return {'enabled': row['enabled'], 'network_allowlist': network_hosts(allowlist)}


async def settings_values(conn, project_id):
    value = await configuration(conn, project_id)
    return {'EDGE_FUNCTIONS_ENABLED': str(value['enabled']).lower(),
            'FUNCTIONS_ALLOWED_NETWORK_HOSTS': ','.join(value['network_allowlist'])}


@asynccontextmanager
async def management_context(ref, request, response, pool):
    ref = validate_project_ref(ref)
    if getattr(request.state, 'internal_service', None) != 'studio-nginx':
        raise HTTPException(403, 'Function management requires the authenticated Studio gateway')
    if request.query_params:
        raise HTTPException(400, 'Function management does not accept query parameters')
    if response is not None:
        response.headers['Cache-Control'] = 'no-store'
    user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, ref)
        await ensure_project_admin_access(conn, project_id=project['id'], auth_user=user)
    locked_project = (project['id'], project['name'], project['tenant_uuid'])
    async with edge_functions.configuration_lock(ROOT, project['name']):
        # No database connection is held while waiting for lifecycle or directory I/O.
        user = await resolve_authenticated_user(request, pool)
        async with pool.acquire() as conn:
            project = await get_public_project_row(conn, ref)
            if (project['id'], project['name'], project['tenant_uuid']) != locked_project:
                raise HTTPException(409, 'Project identity changed while waiting; reload before continuing')
            await ensure_project_admin_access(conn, project_id=project['id'], auth_user=user)
            try:
                yield conn, project, user['db_user_id'], await configuration(conn, project['id'])
            except (OSError, RuntimeError, ValueError, KeyError, TypeError, UnicodeError) as error:
                edge_functions.withdraw(ROOT, project['name'])
                raise HTTPException(503, 'Function storage or project configuration failed integrity validation') from error


def identity(project):
    return str(project['tenant_uuid'])


def load(project):
    return store.load(ROOT, project['name'], identity(project))


def detail(project, state, slug, enabled):
    value = store.item(ROOT, state, slug, {})
    if value is None:
        raise HTTPException(404, 'Function not found')
    return {**value, 'enabled': enabled}


async def audit(conn, project, actor, action, slug=None, revision=None):
    return await conn.fetchval('''INSERT INTO studio_edge_audit(project_id,actor_id,action,function_name,revision,outcome)
        VALUES($1,$2,$3,$4,$5,'requested') RETURNING id''', project['id'], actor, action, slug, revision)


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


def canonical_environment(project):
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
    return env['JWT_SECRET_PROJETO'], url


async def prepare(conn, project, state, config):
    secret, public_url = canonical_environment(project)
    keys = await internal_keys(conn, project)
    env = {
        'SUPABASE_URL': f"http://supabase-nginx-{project['name']}:8080",
        'SUPABASE_PUBLIC_URL': public_url,
        'SUPABASE_ANON_KEY': keys['publishable'],
        'SUPABASE_SERVICE_ROLE_KEY': keys['secret'],
        'SUPABASE_DB_URL': get_project_meta_connection_string(project['name'], project['tenant_uuid']),
    }
    files = store.published_files(ROOT, project['name'], identity(project), state=state)
    return edge_functions.prepare_context(ROOT, project['name'], identity(project), secret, env, files, config['network_allowlist'])


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
        except Exception:
            edge_functions.withdraw(ROOT, project['name'])
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')


@router.get('')
async def function_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    async with management_context(ref, request, response, pool) as (_, project, _, config):
        state = load(project)
        values = [store.item(ROOT, state, slug, {}) for slug in sorted(state['functions'])]
        return {'enabled': config['enabled'], 'functions': [
            {key: item[key] for key in ('name', 'revision', 'published_revision')} for item in values]}


@router.get('/{slug}')
async def function_get(ref: str, slug: str, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (_, project, _, config):
        return detail(project, load(project), slug, config['enabled'])


def validate_slug(slug):
    try:
        store.function_name(slug)
    except ValueError as error:
        raise HTTPException(400, 'Invalid function name') from error


@router.put('/{slug}')
async def function_save(ref: str, slug: str, body: DraftBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    try:
        files = store.validate_files([file.model_dump() for file in body.files])
    except (ValueError, UnicodeError) as error:
        raise HTTPException(400, 'Invalid function files') from error
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = store.item(ROOT, state, slug, {})
        if body.expected_revision != (current['revision'] if current else None):
            raise HTTPException(409, 'Function draft changed; reload before saving')
        if not current and len(state['functions']) >= store.MAX_FUNCTIONS:
            raise HTTPException(409, 'Project function limit reached')
        revision = store.store_version(ROOT, project['name'], identity(project), slug, files)
        state['functions'][slug] = {'draft': revision, 'published': current['published_revision'] if current else None}
        audit_id = await audit(conn, project, actor, 'save_draft', slug, revision)
        try:
            store.atomic_json(store.directory(ROOT, project['name'], identity(project)) / 'state.json', state)
        except Exception:
            await outcome(conn, audit_id, 'failed')
            raise
        await outcome(conn, audit_id, 'completed')
        return detail(project, state, slug, config['enabled'])


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
    await outcome(conn, audit_id, 'completed')


def current_version(project, state, slug, enabled, body):
    current = detail(project, state, slug, enabled)
    if body.revision != current['revision'] or body.expected_published_revision != current['published_revision']:
        raise HTTPException(409, 'Function version changed; reload before changing publication')
    return current


@router.post('/{slug}/publish')
async def function_publish(ref: str, slug: str, body: PublishBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        if not config['enabled']:
            raise HTTPException(409, 'Edge Functions are disabled by the project administrator')
        state = load(project)
        current = current_version(project, state, slug, True, body)
        if current['published_revision'] == body.revision:
            return current
        proposed = copy.deepcopy(state)
        proposed['functions'][slug]['published'] = body.revision
        await commit_change(conn, project, actor, config, state, proposed, slug, body.revision, 'publish')
        return detail(project, proposed, slug, True)


@router.post('/{slug}/unpublish')
async def function_unpublish(ref: str, slug: str, body: PublishBody, request: Request, response: Response, pool=Depends(get_pool)):
    validate_slug(slug)
    async with management_context(ref, request, response, pool) as (conn, project, actor, config):
        state = load(project)
        current = current_version(project, state, slug, config['enabled'], body)
        if current['published_revision'] is None:
            return current
        proposed = copy.deepcopy(state)
        proposed['functions'][slug]['published'] = None
        await commit_change(conn, project, actor, config, state, proposed, slug, current['revision'], 'unpublish')
        return detail(project, proposed, slug, config['enabled'])


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
