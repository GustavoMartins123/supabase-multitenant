"""Dedup de jobs de lifecycle idempotentes (LOG-12).

Duplo clique em stop/start/restart/recreate com os mesmos alvos precisa
acompanhar o job em andamento em vez de enfileirar outro. Acoes distintas
ou recreates com servicos distintos continuam criando jobs.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DB_DSN", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("HOST_AGENT_HMAC_SECRET", "x" * 32)
try:
    from cryptography.fernet import Fernet

    _keys = [Fernet.generate_key().decode() for _ in range(3)]
except Exception:
    _keys = ["x" * 44, "y" * 44, "z" * 44]
os.environ.setdefault("PROJECT_SECRETS_MASTER_KEY", _keys[0])
os.environ.setdefault("PG_META_CRYPTO_KEY", _keys[1])
os.environ.setdefault("STUDIO_SERVICE_KEY_ENCRYPTION_KEY", _keys[2])
os.environ.setdefault("NGINX_HMAC_SECRET", "v" * 32)
os.environ.setdefault("STUDIO_GATEWAY_HMAC_SECRET", "u" * 32)
os.environ.setdefault("PROJECTS_API_HMAC_SECRET", "t" * 32)
os.environ.setdefault("LOGFLARE_PRIVATE_ACCESS_TOKEN", "s" * 16)

from app.schemas import RecreateServices  # noqa: E402

import app.routers.project_lifecycle_ops as ops  # noqa: E402


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeConn:
    def __init__(self, jobs: list[dict], clock: itertools.count) -> None:
        self.jobs = jobs
        self.clock = clock

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def execute(self, query: str, *args: object) -> str:
        return "SELECT 1"

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        if "status IN ('queued', 'running')" in query:
            project_name, action = args[0], args[1]
            active = [
                job
                for job in self.jobs
                if job["project"] == project_name
                and job["action"] == action
                and job["status"] in ("queued", "running")
            ]
            if not active:
                return None
            return max(active, key=lambda job: job["created_at"])
        if "FROM jobs WHERE job_id" in query:
            wanted = str(args[0])
            for job in self.jobs:
                if job["job_id"] == wanted:
                    return job
            return None
        raise AssertionError(f"unexpected fetchrow: {query}")


class FakePool:
    def __init__(self) -> None:
        self.jobs: list[dict] = []
        self.clock = itertools.count()
        self.conn = FakeConn(self.jobs, self.clock)

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        return await self.conn.fetchrow(query, *args)


class FakeAcquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


def make_job(
    job_id: str,
    project: str,
    action: str,
    payload: dict,
    clock: itertools.count,
) -> dict:
    tick = next(clock)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(
        microseconds=tick
    )
    return {
        "job_id": job_id,
        "project": project,
        "project_uuid": str(uuid.uuid4()),
        "created_by": str(uuid.uuid4()),
        "action": action,
        "status": "queued",
        "message": "queued",
        "progress": 0,
        "current_step": "queued",
        "total_steps": 1,
        "started_at": None,
        "finished_at": None,
        "error_code": None,
        "is_idempotent": True,
        "retryable": True,
        "retry_of": None,
        "attempt": 1,
        "created_at": stamp,
        "updated_at": stamp,
        "payload": payload,
    }


class LifecycleDedupTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.pool = FakePool()
        self.user_id = uuid.uuid4()
        self.enqueued = 0

        async def _auth(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id}

        async def _row(*args: object, **kwargs: object) -> dict:
            return {
                "id": uuid.uuid4(),
                "name": "demo",
                "opaque_gateway_ready_at": "2026-01-01T00:00:00+00:00",
            }

        async def _admin(*args: object, **kwargs: object) -> None:
            return None

        async def _containers(*args: object, **kwargs: object) -> list:
            return [{"Names": "supabase-nginx-demo"}]

        async def _create(
            pool: object,
            project_name: str,
            user: object,
            *,
            message: object = None,
            action: str,
            payload: dict | None = None,
            total_steps: int = 1,
            **kwargs: object,
        ) -> str:
            job_id = str(uuid.uuid4())
            self.pool.jobs.append(
                make_job(job_id, project_name, action, payload or {}, self.pool.clock)
            )
            return job_id

        async def _enqueue(*args: object, **kwargs: object) -> int:
            self.enqueued += 1
            return 0

        patches = [
            mock.patch.object(ops, "resolve_authenticated_user", _auth),
            mock.patch.object(ops, "get_project_row", _row),
            mock.patch.object(ops, "ensure_project_admin_access", _admin),
            mock.patch.object(ops, "get_project_containers", _containers),
            mock.patch.object(ops, "_create_project_job", _create),
            mock.patch.object(ops, "_enqueue_project_action", _enqueue),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    def job_ids(self) -> list[str]:
        return [job["job_id"] for job in self.pool.jobs]

    async def test_double_stop_returns_the_in_flight_job(self) -> None:
        first = await ops.stop_project("demo", object(), self.pool)
        second = await ops.stop_project("demo", object(), self.pool)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(self.pool.jobs), 1)
        first_body = json.loads(first.body)
        second_body = json.loads(second.body)
        self.assertEqual(first_body["job_id"], second_body["job_id"])
        self.assertEqual(self.enqueued, 1)

    async def test_stop_then_start_creates_two_jobs(self) -> None:
        await ops.stop_project("demo", object(), self.pool)
        await ops.start_project("demo", object(), self.pool)
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(self.enqueued, 2)

    async def test_recreate_same_services_dedups(self) -> None:
        body = RecreateServices(services=["nginx"])
        first = await ops.recreate_project_services(
            "demo", body, object(), self.pool
        )
        second = await ops.recreate_project_services(
            "demo", body, object(), self.pool
        )
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(self.pool.jobs), 1)

    async def test_recreate_different_services_creates_another_job(self) -> None:
        await ops.recreate_project_services(
            "demo", RecreateServices(services=["nginx"]), object(), self.pool
        )
        await ops.recreate_project_services(
            "demo", RecreateServices(services=["auth"]), object(), self.pool
        )
        self.assertEqual(len(self.pool.jobs), 2)
        self.assertEqual(self.enqueued, 2)


if __name__ == "__main__":
    unittest.main()
