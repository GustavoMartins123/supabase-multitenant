"""Committed notifications, authorization and bounded waiting on disposable SQL."""

import asyncio
import os
import uuid
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
from fastapi import FastAPI, HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.export_openapi import build_schema

build_schema()
from app.database import initialize_pool, close_pool
from app.job_watch import job_change_hub, job_snapshot
from app.routers import jobs_api
from app.schema_migrations import apply_migrations


async def main():
    dsn = os.environ["DB_DSN"]
    connection = await asyncpg.connect(dsn)
    pool = await initialize_pool(dsn)
    try:
        await apply_migrations(connection)
        user, stranger = uuid.uuid4(), uuid.uuid4()
        for uid in (user, stranger):
            await connection.execute(
                "INSERT INTO users(id, authelia_username) VALUES($1,$2)", uid, str(uid))
        job = uuid.uuid4()
        await job_change_hub.start(dsn)
        before = job_change_hub.version
        transaction = connection.transaction()
        await transaction.start()
        await connection.execute("""INSERT INTO jobs(job_id, project, public_ref, created_by,
            action, status) VALUES($1,'select',$2,$3,'start','queued')""", job, 'a' * 20, user)
        await asyncio.sleep(0.05)
        assert job_change_hub.version == before
        await transaction.rollback()
        await asyncio.sleep(0.05)
        assert job_change_hub.version == before
        await connection.execute("""INSERT INTO jobs(job_id, project, public_ref, created_by,
            action, status) VALUES($1,'select',$2,$3,'start','queued')""", job, 'a' * 20, user)
        await asyncio.wait_for(job_change_hub.wait(before, 1), 2)
        assert job_change_hub.version > before
        print('PASS: uncommitted and rolled-back changes do not wake watchers; committed changes do')

        principal = {'db_user_id': user, 'is_global_admin': False}
        snapshot = await job_snapshot(pool, principal, [job])
        assert snapshot['items'][0]['status'] == 'queued'
        assert 'stdout_tail' not in snapshot['items'][0]
        assert (await job_snapshot(pool, {'db_user_id': stranger, 'is_global_admin': False}, []))['items'] == []
        try:
            await job_snapshot(pool, {'db_user_id': stranger, 'is_global_admin': False}, [job])
        except HTTPException as error:
            assert error.status_code == 403
        else:
            raise AssertionError('Unauthorized watched ID was accepted')

        app = FastAPI()
        app.include_router(jobs_api.router)
        authenticate = AsyncMock(return_value=principal)
        with (patch.object(jobs_api, 'resolve_user_claims_from_hmac_token', return_value=(user, {})) as token,
             patch.object(jobs_api, 'resolve_current_user', authenticate),
             patch.object(jobs_api, 'WATCH_TIMEOUT_SECONDS', 0.3)):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                initial = await client.get('/api/jobs/watch')
                assert initial.status_code == 200, initial.text
                assert initial.headers['cache-control'] == 'no-store'
                cursor = initial.json()['cursor']
                token.reset_mock()
                authenticate.reset_mock()
                pending = asyncio.create_task(client.get('/api/jobs/watch', params={'cursor': cursor, 'job_id': str(job)}))
                await asyncio.sleep(0.08)
                assert not pending.done()
                assert pool.get_idle_size() == pool.get_size()
                await connection.execute("UPDATE jobs SET status='running', progress=50, updated_at=now() WHERE job_id=$1", job)
                changed = await asyncio.wait_for(pending, 1)
                assert changed.status_code == 200, changed.text
                assert changed.json()['items'][0]['progress'] == 50
                assert token.call_count == 1 and authenticate.call_count >= 2
                cursor = changed.json()['cursor']
                clock = asyncio.get_running_loop()
                started = clock.time()
                unchanged = await client.get('/api/jobs/watch', params={'cursor': cursor, 'job_id': str(job)})
                assert clock.time() - started >= 0.28
                assert unchanged.json()['cursor'] == cursor
                print('PASS: one pending request; no query connection held; change wakes immediately; unchanged cursor waits')

                pending = asyncio.create_task(client.get('/api/jobs/watch', params={'cursor': cursor, 'job_id': str(job)}))
                await asyncio.sleep(0.05)
                await connection.execute("UPDATE jobs SET status='done', progress=100, updated_at=now() WHERE job_id=$1", job)
                completed = await asyncio.wait_for(pending, 1)
                assert completed.json()['items'][0]['status'] == 'done'
                assert (await client.get('/api/jobs/watch')).json()['items'] == []
                print('PASS: watched terminal jobs remain visible; idle snapshot excludes history')

                empty = (await client.get('/api/jobs/watch')).json()['cursor']
                pending = asyncio.create_task(client.get('/api/jobs/watch', params={'cursor': empty}))
                await asyncio.sleep(0.05)
                authenticate.side_effect = HTTPException(403, 'Directory revoked')
                await connection.execute("SELECT pg_notify('project_jobs_changed','')")
                assert (await pending).status_code == 403
                authenticate.side_effect = None
                print('PASS: directory/role revalidation rejects a revoked principal before replying')

        # Capture-before-snapshot sequence cannot lose an intervening commit.
        before = job_change_hub.version
        await job_snapshot(pool, principal, [])
        await connection.execute("UPDATE jobs SET message='committed' WHERE job_id=$1", job)
        await asyncio.sleep(0.05)
        await asyncio.wait_for(job_change_hub.wait(before, 5), 0.2)
        assert job_change_hub.version > before
        await connection.execute("SELECT pg_terminate_backend($1)", job_change_hub._connection.get_server_pid())
        await asyncio.sleep(0.05)
        try:
            await job_change_hub.wait(job_change_hub.version, 1)
        except HTTPException as error:
            assert error.status_code == 503
        else:
            raise AssertionError('Dead listener did not fail closed')
        print('PASS: snapshot race is covered; listener failure returns 503 without polling fallback')
    finally:
        await job_change_hub.close()
        await close_pool()
        await connection.close()


if __name__ == '__main__':
    asyncio.run(main())
