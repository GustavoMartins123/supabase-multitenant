"""Grant de step-up nao e consumido a toa no delete (LOG-19).

tenant_uuid ausente precisa falhar antes do consume: grant one-time
queimado exige reautenticacao do usuario. Job e grant passam a commitar
na mesma transacao.
"""

from __future__ import annotations

import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

import json

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

import app.routers.projects as router  # noqa: E402


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

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        assert "FROM projects" in query, query
        return {
            "id": self.pool.project_id,
            "tenant_uuid": self.pool.tenant_uuid,
        }

    async def execute(self, query: str, *args: object) -> str:
        self.pool.executes.append((query, args))
        return "UPDATE 1"


class FakePool:
    def __init__(self, tenant_uuid: object) -> None:
        self.executes: list = []
        self.project_id = uuid.uuid4()
        self.tenant_uuid = tenant_uuid
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


class DeleteGrantOrderTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.consumed: list = []
        self.created_jobs: list = []
        self.user_id = uuid.uuid4()

        async def _auth(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id, "is_global_admin": True}

        async def _consume(*args: object, **kwargs: object) -> dict:
            self.consumed.append(kwargs)
            return {}

        async def _create(
            pool: object,
            project_name: str,
            user: object,
            **kwargs: object,
        ) -> str:
            self.created_jobs.append((project_name, kwargs))
            return str(uuid.uuid4())

        async def _enqueue(*args: object, **kwargs: object) -> int:
            return 0

        async def _serialize(
            pool: object, job_id: str, position: int, message: str, **kwargs: object
        ) -> dict:
            return {"job_id": job_id}

        patches = [
            mock.patch.object(router, "resolve_authenticated_user", _auth),
            mock.patch.object(router, "consume_step_up_grant", _consume),
            mock.patch.object(router, "_create_project_job", _create),
            mock.patch.object(router, "_enqueue_project_action", _enqueue),
            mock.patch.object(router, "_serialize_queued_job", _serialize),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def test_missing_tenant_uuid_keeps_grant(self) -> None:
        pool = FakePool(tenant_uuid=None)
        with self.assertRaises(HTTPException) as ctx:
            await router.delete_project("demo", object(), None, pool)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.consumed, [])
        self.assertEqual(self.created_jobs, [])

    async def test_valid_project_consumes_once_and_creates_job(self) -> None:
        tenant = uuid.uuid4()
        pool = FakePool(tenant_uuid=tenant)
        body = await router.delete_project("demo", object(), None, pool)
        self.assertEqual(len(self.consumed), 1)
        self.assertEqual(len(self.created_jobs), 1)
        self.assertIn("job_id", json.loads(body.body))
        payload = self.created_jobs[0][1]["payload"]
        self.assertEqual(payload["tenant_uuid"], str(tenant))


if __name__ == "__main__":
    unittest.main()
