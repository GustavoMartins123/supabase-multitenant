"""Exercise public discovery against the real versioned registry in disposable SQL."""

import asyncio
import datetime as dt
import os
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.export_openapi import build_schema

build_schema()
from app.database import initialize_pool, close_pool
from app.internal_hmac import build_internal_hmac_headers
from app.internal_service_auth import InternalServiceAuthenticationMiddleware
from app.opaque_key_service import (
    bootstrap_project_opaque_keys, create_slot_with_active_key, rotate_slot_immediately,
    prepare_slot_rotation, confirm_pending_key_installation, disable_slot,
)
from app.routers import client_configuration
from app.project_secret_service import encrypt_project_material
from app.runtime_config import STUDIO_GATEWAY_HMAC_SECRET
from app.schema_migrations import apply_migrations


async def main():
    conn = await asyncpg.connect(os.environ['DB_DSN'])
    pool = await initialize_pool(os.environ['DB_DSN'])
    actor, projects = uuid.uuid4(), []
    try:
        await apply_migrations(conn)
        await conn.execute('INSERT INTO users(id, authelia_username) VALUES($1,$2)', actor, str(actor))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            issued = []
            for index in range(2):
                pid, ref, name = uuid.uuid4(), chr(97 + index) * 20, f'client_config_{index}'
                projects.append(pid)
                await conn.execute('''INSERT INTO projects(id,tenant_uuid,name,display_name,owner_id,public_ref)
                    VALUES($1,$1,$2,$2,$3,$4)''', pid, name, actor, ref)
                async with conn.transaction():
                    publishable, secret = await bootstrap_project_opaque_keys(conn,
                        project_id=pid, created_by=actor, gateway_token=chr(97+index) * 64)
                directory = root / name
                directory.mkdir()
                (directory / '.env').write_text(f'PROJECT_UUID={pid}\nPROJECT_PUBLIC_REF={ref}\n'
                    f'API_EXTERNAL_URL=https://api.example.test/{ref}/auth/v1\n')
                issued.append((publishable, secret))
            app = FastAPI()
            app.include_router(client_configuration.router)
            app.add_middleware(InternalServiceAuthenticationMiddleware)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                async def request(path, status=200, *, signed=True):
                    headers = build_internal_hmac_headers(STUDIO_GATEWAY_HMAC_SECRET, 'GET', path, b'',
                        service='studio-nginx') if signed else {}
                    response = await client.get(path, headers=headers)
                    assert response.status_code == status, (status, response.status_code, response.text)
                    if status == 200:
                        assert response.headers['cache-control'].startswith('no-store')
                        assert set(response.json()) == {'supabase_url','publishable_key','key_id','expires_at'}
                    return response

                with patch.object(client_configuration, 'PROJECTS_ROOT', root):
                    refs = [await conn.fetchval('SELECT application_ref FROM project_api_key_slots WHERE id=$1', pair[0].slot_id)
                        for pair in issued]
                    assert len(set(refs)) == 2 and all(len(ref) == 20 for ref in refs)
                    assert await conn.fetchval("SELECT count(*) FROM project_api_key_slots WHERE kind='secret' AND application_ref IS NOT NULL") == 0
                    for index, ref in enumerate(refs):
                        payload = (await request('/config/' + ref)).json()
                        assert payload['publishable_key'] == issued[index][0].token
                        assert payload['supabase_url'] == f'https://api.example.test/{chr(97+index)*20}'
                        assert issued[index][1].token not in str(payload)
                    await request('/config/' + refs[0], 401, signed=False)
                    for path in ('/config/' + 'z'*20, '/config/' + str(issued[0][0].slot_id),
                                 '/config/client_config_0', '/config/' + refs[0] + '?slot=other'):
                        await request(path, 404 if path.endswith('z'*20) else 400)
                    print('PASS: explicit per-slot binding, unknown/malformed references, no secrets and internal HMAC')

                    async with conn.transaction():
                        rotated, _ = await rotate_slot_immediately(conn, project_id=projects[0], slot_id=issued[0][0].slot_id)
                    path = '/config/' + refs[0]
                    assert (await request(path)).json()['publishable_key'] == rotated.token
                    assert (await request('/config/' + refs[1])).json()['publishable_key'] == issued[1][0].token
                    assert await conn.fetchval('SELECT application_ref FROM project_api_key_slots WHERE id=$1', rotated.slot_id) == refs[0]
                    print('PASS: immediate rotation changes only the bound consumer, without changing its discovery URL')

                    now = await conn.fetchval('SELECT now()')
                    async with conn.transaction():
                        pending, _ = await prepare_slot_rotation(conn, project_id=projects[0], slot_id=rotated.slot_id,
                            activate_at=now + dt.timedelta(days=1), disclosed_inline=True)
                    assert (await request(path)).json()['key_id'] == str(rotated.key_id)
                    async with conn.transaction():
                        await confirm_pending_key_installation(conn, project_id=projects[0], slot_id=pending.slot_id, key_id=pending.key_id)
                    assert (await request(path)).json()['key_id'] == str(rotated.key_id)
                    await conn.execute("UPDATE project_api_keys SET activate_at=now()-interval '1 second' WHERE id=$1", pending.key_id)
                    assert (await request(path)).json()['publishable_key'] == pending.token
                    await conn.execute("UPDATE project_api_keys SET created_at=now()-interval '2 days', expires_at=now()-interval '1 day' WHERE id=$1", pending.key_id)
                    await request(path, 410)
                    print('PASS: future/unconfirmed versions are not published; effective cutover matches authorizer; expired pending never restores old key')

                    async with conn.transaction():
                        permanent, _ = await create_slot_with_active_key(conn, project_id=projects[1], name='android_client',
                            kind='publishable', allowed_services=['rest'], created_by=actor,
                            automatic_rotation_enabled=False, rotation_interval_days=None)
                    permanent_ref = await conn.fetchval('SELECT application_ref FROM project_api_key_slots WHERE id=$1', permanent.slot_id)
                    assert (await request('/config/' + permanent_ref)).json()['expires_at'] is None
                    await conn.execute("UPDATE projects SET display_name='Renamed freely' WHERE id=$1", projects[1])
                    assert (await request('/config/' + permanent_ref)).json()['publishable_key'] == permanent.token
                    await conn.execute("UPDATE projects SET public_ref=$1 WHERE id=$2", 'c'*20, projects[1])
                    env = root / 'client_config_1' / '.env'
                    env.write_text(env.read_text().replace('b'*20, 'c'*20))
                    assert (await request('/config/' + permanent_ref)).json()['supabase_url'].endswith('/' + 'c'*20)
                    async with conn.transaction():
                        await disable_slot(conn, project_id=projects[1], slot_id=permanent.slot_id)
                    await request('/config/' + permanent_ref, 410)
                    print('PASS: no-expiration policy, name independence, regenerated project URL, and revocation')

                    await conn.execute('DELETE FROM project_api_key_reveals WHERE key_id=$1', issued[1][0].key_id)
                    await request('/config/' + refs[1], 503)
                    print('PASS: missing canonical plaintext fails closed')
                    ciphertext = await encrypt_project_material(conn, project_id=projects[1],
                        purpose=f'opaque-api-key-reveal:{issued[1][0].key_id}', plaintext=issued[1][1].token)
                    await conn.execute('INSERT INTO project_api_key_reveals(key_id,ciphertext) VALUES($1,$2)',
                        issued[1][0].key_id, ciphertext)
                    response = await request('/config/' + refs[1], 503)
                    assert issued[1][1].token not in response.text
                    with patch.object(client_configuration, 'read_client_configuration',
                                      AsyncMock(side_effect=asyncpg.PostgresError('private database details'))):
                        response = await request('/config/' + refs[1], 503)
                        assert 'private database details' not in response.text
                    print('PASS: secret-material mismatch and SQL failure never disclose or substitute another credential')
    finally:
        if projects:
            await conn.execute('DELETE FROM projects WHERE id=ANY($1::uuid[])', projects)
        await conn.execute('DELETE FROM users WHERE id=$1', actor)
        await close_pool()
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
