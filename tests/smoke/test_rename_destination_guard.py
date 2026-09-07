"""Guarda de destino do rename (LOG-15).

Dois renames para o mesmo destino precisam serializar no lock do nome e
na reserva duravel em project_name_history (queued/running): o segundo
recebe 409 sem enfileirar. Se o enqueue falha depois do commit,
display_name volta ao valor anterior de forma guardada.
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

from app.schemas import ProjectRenameRequest  # noqa: E402

import app.routers.project_rename as router  # noqa: E402


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
        return "UPDATE 1"

    async def fetchval(self, query: str, *args: object) -> object:
        if "FROM projects WHERE name" in query:
            return None
        if "FROM project_name_history" in query:
            if "new_name" in query:
                return 1 if self.pool.destination_reserved else None
            return None
        if "RETURNING id" in query:
            return 1
        raise AssertionError(f"unexpected fetchval: {query}")


class FakePool:
    def __init__(self, destination_reserved: bool = False) -> None:
        self.executes: list = []
        self.jobs: list = []
        self.destination_reserved = destination_reserved
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


def job_inserts(pool: FakePool) -> list:
    return [
        (query, args)
        for query, args in pool.executes
        if "INSERT INTO jobs" in query
    ]


class RenameDestinationGuardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.pool = FakePool()
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()

        async def _auth(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id}

        async def _row(*args: object, **kwargs: object) -> dict:
            return {
                "id": self.project_id,
                "name": "demo",
                "display_name": "Old",
            }

        async def _admin(*args: object, **kwargs: object) -> None:
            return None

        async def _audit(*args: object, **kwargs: object) -> None:
            return None

        async def _enqueue(*args: object, **kwargs: object) -> int:
            return 0

        async def _serialize(
            pool: object, job_id: str, position: int, message: str, **kwargs: object
        ) -> dict:
            return {"job_id": job_id}

        patches = [
            mock.patch.object(router, "resolve_authenticated_user", _auth),
            mock.patch.object(router, "get_project_row", _row),
            mock.patch.object(router, "ensure_project_admin_access", _admin),
            mock.patch.object(router, "audit_studio_action", _audit),
            mock.patch.object(router, "_enqueue_project_action", _enqueue),
            mock.patch.object(router, "_serialize_queued_job", _serialize),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def test_reserved_destination_is_rejected_before_job(self) -> None:
        self.pool.destination_reserved = True
        with self.assertRaises(HTTPException) as ctx:
            await router.rename_project(
                "demo",
                ProjectRenameRequest(new_name="zed"),
                object(),
                self.pool,
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(job_inserts(self.pool), [])

    async def test_free_destination_proceeds(self) -> None:
        body = await router.rename_project(
            "demo",
            ProjectRenameRequest(new_name="zed"),
            object(),
            self.pool,
        )
        self.assertEqual(len(job_inserts(self.pool)), 1)
        self.assertEqual(body.status_code, 202)

    async def test_destination_lock_is_taken(self) -> None:
        source = Path(router.__file__).read_text(encoding="utf-8")
        self.assertIn('f"project-name:{new_name}"', source)

    async def test_display_name_is_reverted_when_enqueue_fails(self) -> None:
        with mock.patch.object(
            router, "_enqueue_project_action",
            side_effect=RuntimeError("queue down"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await router.rename_project(
                    "demo",
                    ProjectRenameRequest(new_name="zed", display_name="New"),
                    object(),
                    self.pool,
                )
        self.assertEqual(ctx.exception.status_code, 503)
        reverts = [
            (query, args)
            for query, args in self.pool.executes
            if "SET display_name = $1" in query
            and "AND display_name = $3" in query
        ]
        self.assertEqual(len(reverts), 1)
        self.assertEqual(
            reverts[0][1], ("Old", self.project_id, "New")
        )


if __name__ == "__main__":
    unittest.main()
