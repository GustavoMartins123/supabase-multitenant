"""Exclusao mutua das mutacoes de migracao opaca (LOG-13).

Prepare/cutover/abort precisam serializar no mesmo lock consultivo por
projeto: a segunda mutacao concorrente recebe 409 sem tocar no gateway.
Retry apos falha (lock livre, corte iniciado, sem ready) precisa prosseguir
ate o stage — guardar com `cutover_started_at IS NULL` travaria a migracao.
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

import app.routers.opaque_keys as router  # noqa: E402


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakeConn:
    def __init__(self, pool: FakePool, state: dict) -> None:
        self.pool = pool
        self.state = state

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def fetchval(self, query: str, *args: object) -> object:
        if "pg_try_advisory_lock" in query:
            name = str(args[0])
            if name in self.pool.locks:
                return False
            self.pool.locks.add(name)
            return True
        if "pg_advisory_unlock" in query:
            self.pool.locks.discard(str(args[0]))
            return True
        raise AssertionError(f"unexpected fetchval: {query}")

    async def fetchrow(self, query: str, *args: object) -> dict | None:
        if "FROM projects WHERE name" in query:
            return {
                "id": self.pool.project_id,
                "tenant_uuid": uuid.uuid4(),
                "name": "demo",
                "display_name": "Demo",
                "owner_id": uuid.uuid4(),
                "automatic_key_rotation_enabled": True,
                "automatic_key_rotation_blocked_at": None,
                "automatic_key_rotation_last_error": None,
                "opaque_gateway_ready_at": None,
                "resource_profile": "medium",
            }
        if "opaque_keys_prepared_at" in query:
            return dict(self.state)
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def execute(self, query: str, *args: object) -> str:
        self.pool.executes.append((query, args))
        return "UPDATE 1"


class FakePool:
    def __init__(self, state: dict | None = None) -> None:
        self.locks: set[str] = set()
        self.executes: list = []
        self.project_id = uuid.uuid4()
        self.state = state or {}
        self.released: list = []

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(FakeConn(self, self.state))

    async def release(self, conn: FakeConn) -> None:
        self.released.append(conn)


class FakeAcquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def __await__(self):
        async def _self() -> FakeConn:
            return self._conn

        return _self().__await__()


READY_STATE = {
    "opaque_keys_prepared_at": "2026-01-01",
    "opaque_keys_activated_at": None,
    "opaque_gateway_cutover_started_at": "2026-01-02",
    "opaque_gateway_ready_at": None,
    "api_keyset_version": 3,
}


class MigrationMutualExclusionTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.user_id = uuid.uuid4()
        self.aborted: list = []
        self.host_calls: list = []

        async def _resolve(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id}

        async def _auth(*args: object, **kwargs: object):
            return {"db_user_id": self.user_id}, {"id": uuid.uuid4()}

        async def _admin(*args: object, **kwargs: object) -> None:
            return None

        async def _abort(conn: object, **kwargs: object) -> int:
            self.aborted.append(kwargs)
            return 4

        async def _audit(*args: object, **kwargs: object) -> None:
            return None

        async def _host(pool: object, **kwargs: object) -> dict:
            self.host_calls.append(kwargs)
            return {"status": "done"}

        patches = [
            mock.patch.object(router, "resolve_authenticated_user", _resolve),
            mock.patch.object(router, "_authorize_project_admin", _auth),
            mock.patch.object(router, "ensure_project_admin_access", _admin),
            mock.patch.object(
                router, "abort_prepared_project_opaque_keys", _abort
            ),
            mock.patch.object(router, "audit_studio_action", _audit),
            mock.patch.object(router, "run_host_agent_command", _host),
            mock.patch.object(
                router,
                "validate_prepared_project_opaque_keys",
                return_value=None,
            ),
            mock.patch.object(
                router,
                "activate_prepared_project_opaque_keys",
                return_value=4,
            ),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def test_abort_during_cutover_gets_409_without_touching_keys(
        self,
    ) -> None:
        pool = FakePool()
        pool.locks.add(f"opaque-api-key-migration:{pool.project_id}")
        with self.assertRaises(HTTPException) as ctx:
            await router.abort_opaque_api_key_migration(
                "demo", object(), pool
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.aborted, [])

    async def test_free_abort_runs_and_releases_the_lock(self) -> None:
        pool = FakePool()
        body = await router.abort_opaque_api_key_migration(
            "demo", object(), pool
        )
        self.assertEqual(body["status"], "legacy")
        self.assertEqual(len(self.aborted), 1)
        self.assertEqual(pool.locks, set())
        self.assertEqual(len(pool.released), 1)

    async def test_second_cutover_gets_409_without_touching_gateway(
        self,
    ) -> None:
        pool = FakePool(dict(READY_STATE))
        pool.locks.add(f"opaque-api-key-migration:{pool.project_id}")
        with self.assertRaises(HTTPException) as ctx:
            await router.cutover_opaque_api_key_migration(
                "demo", object(), pool
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(self.host_calls, [])

    async def test_retry_after_failure_proceeds_to_stage(self) -> None:
        pool = FakePool(dict(READY_STATE))
        body = await router.cutover_opaque_api_key_migration(
            "demo", object(), pool
        )
        self.assertEqual(body["status"], "active")
        stages = [
            call
            for call in self.host_calls
            if call.get("command") == "stage_opaque_gateway"
        ]
        self.assertEqual(len(stages), 1)
        self.assertEqual(pool.locks, set())


if __name__ == "__main__":
    unittest.main()
