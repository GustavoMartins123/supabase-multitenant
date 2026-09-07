"""Guarda do DELETE de membros (LOG-16).

Remover quem nao e membro precisa dar 404 em vez de ok silencioso, e
remover o ultimo admin precisa dar 409: sem admin o projeto fica
ingerenciavel, pois ensure_project_admin_access exige role admin.
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

import app.routers.project_members as router  # noqa: E402


class FakeConn:
    def __init__(self, pool: FakePool) -> None:
        self.pool = pool

    async def execute(self, query: str, *args: object) -> str:
        self.pool.executes.append((query, args))
        return "DELETE 1"

    async def fetchval(self, query: str, *args: object) -> object:
        if "role = 'admin'" in query:
            return self.pool.admin_count
        raise AssertionError(f"unexpected fetchval: {query}")


class FakePool:
    def __init__(self, admin_count: int = 2) -> None:
        self.executes: list = []
        self.admin_count = admin_count
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


def deletes(pool: FakePool) -> list:
    return [
        (query, args)
        for query, args in pool.executes
        if "DELETE FROM project_members" in query
    ]


class RemoveMemberGuardTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.pool = FakePool()
        self.actor_id = uuid.uuid4()
        self.owner_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.target_id = uuid.uuid4()
        self.target_role: str | None = "member"
        self.known_user = True
        self.actor_is_owner = False
        self.audits: list = []

        async def _auth(*args: object, **kwargs: object) -> dict:
            return {
                "db_user_id": (
                    self.owner_id if self.actor_is_owner else self.actor_id
                ),
                "is_global_admin": False,
            }

        async def _row(*args: object, **kwargs: object) -> dict:
            return {
                "id": self.project_id,
                "name": "demo",
                "owner_id": self.owner_id,
            }

        async def _admin(*args: object, **kwargs: object) -> None:
            return None

        async def _user_record(*args: object, **kwargs: object) -> dict | None:
            if not self.known_user:
                return None
            return {"id": self.target_id}

        async def _member_row(*args: object, **kwargs: object) -> dict | None:
            if self.target_role is None:
                return None
            return {"role": self.target_role}

        async def _audit(*args: object, **kwargs: object) -> None:
            self.audits.append(kwargs)

        patches = [
            mock.patch.object(router, "resolve_authenticated_user", _auth),
            mock.patch.object(router, "get_project_row", _row),
            mock.patch.object(router, "ensure_project_admin_access", _admin),
            mock.patch.object(
                router, "get_user_record_by_identifier", _user_record
            ),
            mock.patch.object(router, "get_project_member_row", _member_row),
            mock.patch.object(router, "audit_project_member_change", _audit),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def call_remove(self, member_id: str) -> dict:
        return await router.remove_member_by_ref(
            "demo", member_id, object(), self.pool
        )

    async def test_unknown_identifier_is_404(self) -> None:
        self.known_user = False
        with self.assertRaises(HTTPException) as ctx:
            await self.call_remove("ghost-user")
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(deletes(self.pool), [])
        self.assertEqual(self.audits, [])

    async def test_non_member_uuid_is_404(self) -> None:
        self.target_role = None
        with self.assertRaises(HTTPException) as ctx:
            await self.call_remove(str(self.target_id))
        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(deletes(self.pool), [])

    async def test_last_admin_cannot_be_removed(self) -> None:
        self.actor_is_owner = True
        self.pool.admin_count = 1
        self.target_role = "admin"
        with self.assertRaises(HTTPException) as ctx:
            await self.call_remove(str(self.target_id))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(deletes(self.pool), [])
        self.assertEqual(self.audits, [])

    async def test_admin_removal_with_other_admins_succeeds(self) -> None:
        self.actor_is_owner = True
        self.pool.admin_count = 2
        self.target_role = "admin"
        body = await self.call_remove(str(self.target_id))
        self.assertEqual(body, {"ok": True})
        self.assertEqual(len(deletes(self.pool)), 1)
        self.assertEqual(len(self.audits), 1)

    async def test_owner_removal_stays_blocked(self) -> None:
        self.target_id = self.owner_id
        with self.assertRaises(HTTPException) as ctx:
            await self.call_remove(str(self.target_id))
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(deletes(self.pool), [])


if __name__ == "__main__":
    unittest.main()
