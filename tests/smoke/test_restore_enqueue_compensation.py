"""Compensacao quando o enqueue de backup/restore falha (LOG-14).

Se `_enqueue_project_action` levanta depois do commit, o ponto nao pode
ficar preso em creating/restoring/deleting: create vira failed, restore
devolve o alvo para ready e falha o safety, delete restaura o status
anterior. Tudo com guarda de status para nao atropelar transicao concorrente.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
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

from fastapi import HTTPException  # noqa: E402

from app.schemas import RestorePointCreate  # noqa: E402

import app.routers.restore_points as router  # noqa: E402


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeConn:
    def __init__(self, pool: FakePool) -> None:
        self.pool = pool

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def execute(self, query: str, *args: object) -> str:
        self.pool.executes.append((query, args))
        if "INSERT INTO jobs" in query:
            self.pool.jobs.append({"job_id": str(args[0]), "status": "queued"})
        return "UPDATE 1"

    async def fetchval(self, query: str, *args: object) -> object:
        if "count(*)" in query:
            return 0
        raise AssertionError(f"unexpected fetchval: {query}")


class FakePool:
    def __init__(self) -> None:
        self.executes: list = []
        self.jobs: list = []
        self.conn = FakeConn(self)

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


class FakeAcquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


def point_updates(pool: FakePool, wanted: str) -> list:
    return [
        (query, args)
        for query, args in pool.executes
        if "UPDATE project_restore_points" in query and wanted in query
    ]


class RestoreEnqueueCompensationTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.pool = FakePool()
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.point_id = uuid.uuid4()

        async def _auth(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id}

        async def _row(*args: object, **kwargs: object) -> dict:
            return {
                "id": self.project_id,
                "name": "demo",
                "tenant_uuid": self.project_id,
                "owner_id": self.user_id,
            }

        async def _access(*args: object, **kwargs: object) -> None:
            return None

        async def _point(*args: object, **kwargs: object) -> dict:
            return {"id": self.point_id, "status": "ready", "title": "p1"}

        async def _boom(*args: object, **kwargs: object):
            raise RuntimeError("queue down")

        patches = [
            mock.patch.object(router, "resolve_authenticated_user", _auth),
            mock.patch.object(router, "get_project_row", _row),
            mock.patch.object(router, "ensure_project_admin_access", _access),
            mock.patch.object(router, "ensure_project_owner_access", _access),
            mock.patch.object(router, "_fetch_restore_point_locked", _point),
            mock.patch.object(router, "_enqueue_project_action", _boom),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def test_create_marks_point_failed(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await router.create_project_restore_point(
                "demo", RestorePointCreate(), object(), self.pool
            )
        self.assertEqual(ctx.exception.status_code, 503)
        inserted = [
            args
            for query, args in self.pool.executes
            if "INSERT INTO project_restore_points" in query
        ]
        self.assertEqual(len(inserted), 1)
        failed = point_updates(self.pool, "status = 'failed'")
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0][1][0], inserted[0][0])
        creating_guards = [
            query for query, _ in failed if "status = 'creating'" in query
        ]
        self.assertEqual(len(creating_guards), 1)

    async def test_restore_fails_safety_and_readies_target(self) -> None:
        target = str(uuid.uuid4())
        with self.assertRaises(HTTPException) as ctx:
            await router.restore_project_restore_point(
                "demo", target, object(), self.pool
            )
        self.assertEqual(ctx.exception.status_code, 503)
        safety_failed = [
            (query, args)
            for query, args in point_updates(self.pool, "status = 'failed'")
            if str(args[0]) != target
        ]
        self.assertEqual(len(safety_failed), 1)
        readied = point_updates(self.pool, "status = 'ready'")
        self.assertEqual(len(readied), 1)
        self.assertEqual(str(readied[0][1][0]), target)

    async def test_delete_restores_previous_status(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            await router.delete_project_restore_point(
                "demo", str(self.point_id), object(), self.pool
            )
        self.assertEqual(ctx.exception.status_code, 503)
        reverted = [
            (query, args)
            for query, args in self.pool.executes
            if "UPDATE project_restore_points" in query
            and "SET status = $2" in query
            and "status = 'deleting'" in query
        ]
        self.assertEqual(len(reverted), 1)
        self.assertEqual(reverted[0][1][1], "ready")


if __name__ == "__main__":
    unittest.main()
