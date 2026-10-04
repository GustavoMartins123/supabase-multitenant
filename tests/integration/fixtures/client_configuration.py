"""Exercise public discovery against the real versioned registry in disposable SQL."""

import asyncio
import datetime as dt
import os
import importlib.util
import secrets
from urllib.parse import urlsplit, urlunsplit
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.export_openapi import build_schema

build_schema()
from app.database import initialize_pool, close_pool
from app.opaque_key_service import (
    bootstrap_project_opaque_keys, create_slot_with_active_key, rotate_slot_immediately,
    prepare_slot_rotation, confirm_pending_key_installation, disable_slot,
)
from app.control_plane_roles import ensure_client_configuration_reader_role
from app.migrate_client_configuration_material import populate_public_client_configuration_keys
from app.runtime_config import project_secret_manager
spec = importlib.util.spec_from_file_location('public_config_service', Path(__file__).resolve().parents[3] / 'servidor/client-configuration/app.py')
client_configuration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_configuration)
from app.schema_migrations import apply_migrations


async def main():
    conn = await asyncpg.connect(os.environ['DB_DSN'])
    pool = await initialize_pool(os.environ['DB_DSN'])
    actor, projects = uuid.uuid4(), []
    try:
        await apply_migrations(conn)
        password = secrets.token_urlsafe(32)
        await ensure_client_configuration_reader_role(pool, password=password)
        dsn = urlsplit(os.environ['DB_DSN'])
        authority = 'client_configuration_reader:' + password + '@' + dsn.hostname + ':' + str(dsn.port)
        reader = await asyncpg.create_pool(urlunsplit(dsn._replace(netloc=authority)), min_size=1, max_size=2)
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
            app = client_configuration.app
            app.state.pool = reader
            app.state.public_origin = 'https://api.example.test'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                async def request(path, status=200):
                    response = await client.get(path)
                    assert response.status_code == status, (status, response.status_code, response.text)
                    if status == 200:
                        assert response.headers['cache-control'].startswith('no-store')
                        assert set(response.json()) == {'supabase_url','publishable_key','key_id','expires_at'}
                    return response

                with patch.object(app.state, 'public_origin', 'https://api.example.test'):
                    refs = [await conn.fetchval('SELECT application_ref FROM project_api_key_slots WHERE id=$1', pair[0].slot_id)
                        for pair in issued]
                    assert len(set(refs)) == 2 and all(len(ref) == 20 for ref in refs)
                    assert await conn.fetchval("SELECT count(*) FROM project_api_key_slots WHERE kind='secret' AND application_ref IS NOT NULL") == 0
                    for index, ref in enumerate(refs):
                        payload = (await request('/config/' + ref)).json()
                        assert payload['publishable_key'] == issued[index][0].token
                        assert payload['supabase_url'] == f'https://api.example.test/{chr(97+index)*20}'
                        assert issued[index][1].token not in str(payload)
                    for path in ('/config/' + 'z'*20, '/config/' + str(issued[0][0].slot_id),
                                 '/config/client_config_0', '/config/' + refs[0] + '?slot=other'):
                        await request(path, 404 if path.endswith('z'*20) else 400)
                    print('PASS: explicit per-slot binding, unknown/malformed references, no secrets and no control-plane proxy')

                    transaction = conn.transaction()
                    await transaction.start()
                    await rotate_slot_immediately(conn, project_id=projects[0], slot_id=issued[0][0].slot_id)
                    assert (await request('/config/' + refs[0])).json()['publishable_key'] == issued[0][0].token
                    await transaction.rollback()
                    assert (await request('/config/' + refs[0])).json()['publishable_key'] == issued[0][0].token
                    print('PASS: uncommitted rotation remains invisible; rollback preserves canonical public material')
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

                    await conn.execute('DELETE FROM public_client_configuration_keys WHERE key_id=$1', issued[1][0].key_id)
                    await request('/config/' + refs[1], 503)
                    print('PASS: missing canonical publishable projection fails closed')
                    try:
                        await conn.execute('INSERT INTO public_client_configuration_keys(key_id,publishable_key) VALUES($1,$2)',
                            issued[1][0].key_id, issued[1][1].token)
                    except asyncpg.PostgresError:
                        pass
                    else:
                        raise AssertionError('Secret material must never enter public projection')
                    assert await populate_public_client_configuration_keys(conn, project_secret_manager) == 1
                    assert await populate_public_client_configuration_keys(conn, project_secret_manager) == 0
                    assert (await request('/config/' + refs[1])).json()['publishable_key'] == issued[1][0].token
                    for table in ('projects','project_api_keys','project_api_key_reveals','project_key_envelopes',
                                  'public_client_configuration_keys','users'):
                        async with reader.acquire() as restricted:
                            try:
                                await restricted.fetch('SELECT * FROM ' + table)
                            except asyncpg.InsufficientPrivilegeError:
                                pass
                            else:
                                raise AssertionError('Discovery identity can only read the public view')
                    async with reader.acquire() as restricted:
                        try:
                            await restricted.execute("DELETE FROM public_client_configurations")
                        except asyncpg.PostgresError:
                            pass
                        else:
                            raise AssertionError('Discovery identity must never write')
                    for error in (asyncpg.PostgresError('private database details'), TimeoutError('private database details')):
                        with patch.object(type(reader), 'fetch', AsyncMock(side_effect=error)):
                            response = await request('/config/' + refs[1], 503)
                            assert 'private database details' not in response.text
                            response = await client.get('/healthz')
                            assert response.status_code == 503
                            assert 'private database details' not in response.text
                    print('PASS: projection validation, idempotent backfill, least-privilege read-only role and sanitized SQL failure')
            await reader.close()
    finally:
        if projects:
            await conn.execute('DELETE FROM projects WHERE id=ANY($1::uuid[])', projects)
        await conn.execute('DELETE FROM users WHERE id=$1', actor)
        await close_pool()
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
