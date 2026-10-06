"""Fail-closed data-plane opaque identity and project/slot admission."""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import urllib.parse

import asyncpg
import httpx
from redis.asyncio import Redis
from redis.exceptions import RedisError
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from opaque_keys import ALLOWED_SERVICES, OpaqueKeyError, parse_opaque_key, should_preserve_authorization
from admission import AdmissionEngine, AdmissionRequest, query_key, route

PROJECT_RE = re.compile(r'^[a-z_][a-z0-9_]{2,39}$')
GATEWAY_TOKEN_RE = re.compile(r'^[a-f0-9]{64}$')
DB_DSN = os.environ['DB_DSN']
ADMISSION_SECRET = os.environ['ACCESS_ADMISSION_SECRET']
if not GATEWAY_TOKEN_RE.fullmatch(ADMISSION_SECRET):
    raise RuntimeError('Invalid ACCESS_ADMISSION_SECRET')
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
_pool = None
_engine = None

def _forbidden() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail="Invalid API key",
        headers={"Cache-Control": "no-store"},
    )


def _canonical_query_key(
    query_key: str | None, original_args: str | None
) -> str:
    forwarded = query_key or ""
    if forwarded != forwarded.strip():
        raise OpaqueKeyError("API key query value has non-canonical whitespace")
    raw_values: list[str] = []
    for part in (original_args or "").split("&"):
        if not part:
            continue
        raw_name, separator, raw_value = part.partition("=")
        name = urllib.parse.unquote_plus(raw_name)
        if name.lower() != "apikey":
            continue
        if raw_name != "apikey" or name != "apikey" or not separator:
            raise OpaqueKeyError("API key query parameter is not canonical")
        decoded_value = urllib.parse.unquote_plus(raw_value)
        if raw_value != decoded_value:
            raise OpaqueKeyError("API key query value is not canonical")
        raw_values.append(decoded_value)
    if len(raw_values) > 1:
        raise OpaqueKeyError("duplicate API key query parameters")
    raw_value = raw_values[0] if raw_values else ""
    if not hmac.compare_digest(forwarded, raw_value):
        raise OpaqueKeyError("API key query parsing mismatch")
    return forwarded


def _candidate_key(
    header_key: str | None,
    query_key: str | None,
    original_args: str | None,
    *,
    allow_missing: bool,
) -> str | None:
    header_value = header_key or ""
    if header_value != header_value.strip():
        raise OpaqueKeyError("API key header has non-canonical whitespace")
    query_value = _canonical_query_key(query_key, original_args)
    if header_value and query_value and not hmac.compare_digest(
        header_value, query_value
    ):
        raise OpaqueKeyError("ambiguous API key sources")
    candidate = header_value or query_value
    if not candidate:
        if allow_missing:
            return None
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={
                "WWW-Authenticate": "ApiKey",
                "Cache-Control": "no-store",
            },
        )
    return candidate




@app.on_event('startup')
async def startup():
    global _pool, _engine
    _pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=20, command_timeout=3)
    redis = Redis(host='traffic-redis', port=6379, password=os.environ['ACCESS_RATE_REDIS_PASSWORD'],
        decode_responses=True, socket_timeout=2, socket_connect_timeout=2, retry_on_timeout=False)
    _engine = AdmissionEngine(_pool, redis, os.environ['ACCESS_ADMIN_CIDRS'])
    await _engine.startup()


@app.on_event('shutdown')
async def shutdown():
    if _engine:
        await _engine.redis.aclose()
        await _engine.http.aclose()
    if _pool:
        await _pool.close()


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    headers = dict(exc.headers or {})
    headers['Cache-Control'] = 'no-store'
    return JSONResponse({'error': 'admission_denied' if exc.status_code < 500 else 'admission_unavailable',
        'message': str(exc.detail)}, status_code=exc.status_code, headers=headers)


@app.middleware('http')
async def dependency_boundary(request, call_next):
    try:
        return await call_next(request)
    except (asyncpg.PostgresError, asyncpg.InterfaceError, OSError, TimeoutError, RedisError,
        httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
        return JSONResponse({'error':'admission_unavailable','message':'Admission could not be verified'},
            status_code=503, headers={'Cache-Control':'no-store'})


@app.get('/healthz')
async def healthz():
    if not _pool or not _engine:
        raise HTTPException(503, 'Admission evaluator not ready')
    await _pool.fetchval('SELECT 1')
    if await _engine.redis.get('access:epoch') != _engine.epoch:
        raise HTTPException(503, 'Traffic counter epoch unavailable')
    return {'status':'ok'}


async def project_identity(conn, name, token):
    if not PROJECT_RE.fullmatch(name) or not GATEWAY_TOKEN_RE.fullmatch(token):
        raise _forbidden()
    project = await conn.fetchrow('SELECT id,public_ref,api_gateway_token_hash,api_keyset_version,opaque_keys_activated_at FROM projects WHERE name=$1', name)
    if project is None or project['api_gateway_token_hash'] is None or project['opaque_keys_activated_at'] is None:
        raise _forbidden()
    if not hmac.compare_digest(hashlib.sha256(token.encode()).digest(), bytes(project['api_gateway_token_hash'])):
        raise _forbidden()
    return project


async def key_identity(conn, project, body, service, missing, required):
    _, _, _, parts = route(body.uri, project['public_ref'])
    try:
        api_key = _candidate_key(body.api_key, query_key(parts.query), parts.query, allow_missing=missing)
    except OpaqueKeyError:
        raise _forbidden() from None
    authorization = body.authorization
    if authorization != authorization.strip():
        raise _forbidden()
    if api_key is None:
        if re.match(r'^Bearer\s+sb_(?:publishable|secret)_', authorization, flags=re.IGNORECASE):
            raise _forbidden()
        return None, None, True
    try:
        parsed = parse_opaque_key(project['id'], api_key)
        preserve = bool(service in {'storage','functions'} and authorization and not re.match(r'^Bearer\s+', authorization, re.IGNORECASE))
        if not preserve:
            preserve = should_preserve_authorization(api_key, authorization)
    except OpaqueKeyError:
        raise _forbidden() from None
    key = await conn.fetchrow('''                SELECT k.id, s.id AS slot_id, false AS administrative, s.kind, s.allowed_services
                FROM project_api_keys k
                JOIN project_api_key_slots s ON s.id = k.slot_id
                WHERE s.project_id = $1
                  AND s.status = 'active'
                  AND k.secret_hash = $2
                  AND (k.expires_at IS NULL OR k.expires_at > now())
                  AND (
                      (
                          k.status = 'active'
                          AND k.activated_at IS NOT NULL
                          AND NOT EXISTS (
                              SELECT 1
                              FROM project_api_keys due
                              WHERE due.slot_id = k.slot_id
                                AND due.status = 'pending'
                                AND due.activate_at <= now()
                                AND due.confirmed_at IS NOT NULL
                          )
                      )
                      OR (
                          k.status = 'pending'
                          AND k.activate_at <= now()
                          AND k.confirmed_at IS NOT NULL
                      )
                  )
                UNION ALL
                SELECT sk.project_id AS id, NULL::uuid AS slot_id, true AS administrative, 'secret' AS kind,
                       ARRAY['rest','graphql','storage']::text[] AS allowed_services
                FROM project_studio_keys sk
                WHERE sk.project_id = $1 AND sk.secret_hash = $2 AND sk.is_active
''', project['id'], parsed.digest)
    if key is None or key['kind'] != parsed.kind or service not in key['allowed_services'] or (required and parsed.role != required):
        raise _forbidden()
    return key, parsed, preserve


async def discovery_identity(conn, body):
    service, _, _, parts = route(body.uri, None)
    ref = parts.path.removeprefix('/config/')
    slot = await conn.fetchrow("SELECT id,project_id FROM project_api_key_slots WHERE application_ref=$1 AND kind='publishable'", ref)
    if slot is None:
        raise HTTPException(404, 'Application configuration not found')
    row = await conn.fetchrow('SELECT available,key_id FROM public_client_configurations WHERE application_ref=$1', ref)
    if row is None or not row['available'] or row['key_id'] is None:
        raise HTTPException(410, 'Application configuration unavailable')
    return {'id': slot['project_id']}, {'id': row['key_id'], 'slot_id':slot['id'], 'administrative':False}, service


@app.post('/v1/admit', status_code=204)
async def admit(body: AdmissionRequest, x_admission_secret: str = Header()):
    if not hmac.compare_digest(x_admission_secret, ADMISSION_SECRET):
        raise _forbidden()
    if body.method not in {'GET','HEAD','POST','PUT','PATCH','DELETE','OPTIONS'}:
        raise HTTPException(405, 'Method not permitted')
    async with _pool.acquire() as conn:
        if body.project_ref == '' and body.gateway_token == '':
            if body.method not in {'GET','OPTIONS'}:
                raise HTTPException(405, 'Only GET and OPTIONS are supported')
            project, identity, service = await discovery_identity(conn, body)
            discovery = True
        else:
            project = await project_identity(conn, body.project_ref, body.gateway_token)
            service, missing, required, _ = route(body.uri, project['public_ref'])
            identity, _, _ = await key_identity(conn, project, body, service, missing, required) if body.method != 'OPTIONS' else (None,None,True)
            discovery = False
    ticket = await _engine.issue(body, identity, project, service, discovery)
    return Response(status_code=204, headers={'X-Gateway-Admission':ticket} if ticket else {})


@app.get('/v1/authorize', status_code=204)
async def authorize(request: Request):
    h = request.headers
    if not h.get('x-gateway-admission'):
        raise _forbidden()
    body = AdmissionRequest(project_ref=h.get('x-project-ref',''), gateway_token=h.get('x-project-gateway-token',''),
        uri=h.get('x-admission-uri',''), method=h.get('x-admission-method',''), client_ip='127.0.0.1',
        api_key=h.get('x-api-key-header',''), authorization=h.get('x-original-authorization',''))
    async with _pool.acquire() as conn:
        project = await project_identity(conn, body.project_ref, body.gateway_token)
        service, missing, required, parts = route(body.uri, project['public_ref'])
        if body.uri != '/' + project['public_ref'] + h.get('x-gateway-request-uri',''):
            raise _forbidden()
        if h.get('x-target-service') not in {service, 'callback'} or body.method != h.get('x-gateway-request-method'):
            raise _forbidden()
        if h.get('x-target-service') == 'callback' and not missing:
            raise _forbidden()
        key, parsed, preserve = await key_identity(conn, project, body, service, missing, required)
        await _engine.redeem(h.get('x-gateway-admission',''), body, project, key)
        if key and not key['administrative']:
            await conn.execute("UPDATE project_api_keys SET last_used_at=now() WHERE id=$1 AND (last_used_at IS NULL OR last_used_at < now()-interval '5 minutes')", key['id'])
    headers = {'Cache-Control':'no-store','X-Opaque-Key-Present':'1' if key else '0',
        'X-Opaque-Preserve-Authorization':'1' if preserve else '0','X-Opaque-Keyset-Version':str(project['api_keyset_version'])}
    if parsed:
        headers.update({'X-Opaque-Key-Role':parsed.role,'X-Opaque-Key-Id':str(key['id'])})
    return Response(status_code=204, headers=headers)


@app.post('/v1/check-discovery', status_code=204)
async def check_discovery(body: AdmissionRequest, x_admission_secret: str = Header(), x_gateway_admission: str = Header()):
    if not hmac.compare_digest(x_admission_secret, ADMISSION_SECRET) or body.project_ref or body.gateway_token:
        raise _forbidden()
    async with _pool.acquire() as conn:
        project, key, _ = await discovery_identity(conn, body)
    await _engine.redeem(x_gateway_admission, body, project, key)
    return Response(status_code=204)
