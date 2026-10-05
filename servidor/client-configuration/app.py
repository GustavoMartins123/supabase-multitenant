"""Public data-plane discovery with a read-only publishable database identity."""

from contextlib import asynccontextmanager
import os
import re
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

REFERENCE = re.compile(r'[a-z]{20}\Z', re.ASCII)
NO_STORE = {'Cache-Control': 'no-store, max-age=0', 'Pragma': 'no-cache'}


def public_base_url(server_url: str, server_proto: str) -> str:
    if '://' not in server_url:
        if server_proto not in {'http', 'https'}:
            raise ValueError('SERVER_PROTO must be http or https')
        server_url = server_proto + '://' + server_url
    url = urlsplit(server_url)
    if (url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password
            or url.query or url.fragment or url.path not in {'', '/'}):
        raise ValueError('SERVER_URL must be a canonical public origin')
    url.port
    return urlunsplit((url.scheme, url.netloc, '', '', ''))


@asynccontextmanager
async def lifespan(app):
    dsn = os.environ['DB_DSN']
    app.state.public_origin = public_base_url(os.environ['SERVER_URL'], os.environ['SERVER_PROTO'])
    app.state.pool = await asyncpg.create_pool(dsn, min_size=1, max_size=8, command_timeout=3,
        server_settings={'default_transaction_read_only': 'on', 'statement_timeout': '3000'})
    app.state.admission_secret = os.environ['ACCESS_ADMISSION_SECRET']
    app.state.admission_http = httpx.AsyncClient(timeout=3, follow_redirects=False)
    try:
        async with app.state.pool.acquire() as conn:
            if await conn.fetchval('SELECT current_user') != 'client_configuration_reader':
                raise RuntimeError('Dedicated client_configuration_reader identity is required')
            await conn.fetch('SELECT application_ref FROM public_client_configurations LIMIT 0')
        yield
    finally:
        await app.state.admission_http.aclose()
        await app.state.pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


class ClientConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    supabase_url: str
    publishable_key: str
    key_id: str
    expires_at: str | None


@app.middleware('http')
async def public_request_boundary(request: Request, call_next):
    if request.url.path != '/healthz':
        raw = request.scope.get('raw_path', b'')
        ref = request.url.path.removeprefix('/config/')
        if (not REFERENCE.fullmatch(ref) or raw != ('/config/' + ref).encode('ascii')
                or request.scope.get('query_string') or request.url.query):
            response = JSONResponse({'detail': 'Invalid application configuration reference'}, status_code=400)
        elif request.method == 'OPTIONS':
            response = JSONResponse(None, status_code=204)
            response.body = b''
            response.headers['Content-Length'] = '0'
        elif request.method != 'GET':
            response = JSONResponse({'detail': 'Only GET and OPTIONS are allowed'}, status_code=405,
                headers={'Allow': 'GET, OPTIONS'})
        elif request.headers.get('transfer-encoding') or request.headers.get('content-length', '0') != '0':
            response = JSONResponse({'detail': 'Configuration requests must not contain a body'}, status_code=400)
        else:
            response = await check_admission(request)
            if response is None:
                response = await call_next(request)
        response.headers.update(NO_STORE)
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Accept'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response
    return await call_next(request)


async def check_admission(request):
    uri = request.headers.get('x-admission-uri')
    method = request.headers.get('x-admission-method')
    ticket = request.headers.get('x-gateway-admission')
    if uri != request.url.path or method != request.method or not ticket:
        return JSONResponse({'error':'admission_denied','message':'Admission ticket required'}, status_code=403)
    try:
        response = await app.state.admission_http.post('http://key-authorizer:18010/v1/check-discovery',
            headers={'X-Admission-Secret':app.state.admission_secret,'X-Gateway-Admission':ticket},
            json={'project_ref':'','gateway_token':'','uri':uri,'method':method,
                'client_ip':request.headers.get('x-admission-origin-ip',''),
                'api_key':request.headers.get('apikey',''),'authorization':request.headers.get('authorization','')})
        if response.status_code == 204:
            return None
        if response.status_code != 403:
            raise ValueError('Admission protocol failed')
        return JSONResponse({'error':'admission_denied','message':'Admission ticket rejected'}, status_code=403)
    except (httpx.HTTPError, ValueError):
        return JSONResponse({'error':'admission_unavailable','message':'Admission could not be verified'}, status_code=503)


@app.get('/healthz', include_in_schema=False)
async def healthz():
    try:
        await app.state.pool.fetch('SELECT application_ref FROM public_client_configurations LIMIT 0')
    except (OSError, TimeoutError, RuntimeError, asyncpg.PostgresError, asyncpg.InterfaceError):
        raise HTTPException(503, 'Configuration database is unavailable') from None
    return {'status': 'ok'}


@app.get('/config/{application_ref}', response_model=ClientConfigurationResponse,
    responses={403: {'description': 'Geographic denial or invalid admission ticket'},
        404: {'description': 'Unknown application reference'},
        410: {'description': 'No effective publishable key'},
        429: {'description': 'Discovery rate exhausted; Retry-After indicates the wait'},
        503: {'description': 'Configuration or admission dependency unavailable'}})
async def get_client_configuration(application_ref: str):
    try:
        rows = await app.state.pool.fetch('''
            SELECT public_ref, available, key_id, expires_at, publishable_key
            FROM public_client_configurations WHERE application_ref = $1
        ''', application_ref)
    except (OSError, TimeoutError, RuntimeError, asyncpg.PostgresError, asyncpg.InterfaceError):
        raise HTTPException(503, 'Application configuration could not be verified') from None
    if not rows:
        raise HTTPException(404, 'Application configuration not found')
    if len(rows) != 1:
        raise HTTPException(503, 'Canonical publishable key is unavailable')
    row = rows[0]
    if not row['available'] or row['key_id'] is None:
        raise HTTPException(410, 'No valid publishable key for this application')
    if row['publishable_key'] is None or not REFERENCE.fullmatch(row['public_ref']):
        raise HTTPException(503, 'Canonical publishable configuration is unavailable')
    return {
        'supabase_url': app.state.public_origin + '/' + row['public_ref'],
        'publishable_key': row['publishable_key'],
        'key_id': str(row['key_id']),
        'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None,
    }
