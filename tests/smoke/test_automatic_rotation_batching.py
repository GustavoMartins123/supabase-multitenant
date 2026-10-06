"""Scan de rotacao automatica opaca em lotes (LOG-10).

Ate 100 transicoes precisam ser confirmadas em transacoes curtas (lotes),
nunca em uma unica transacao longa com N+1, e o lock do scan precisa ser
liberado mesmo em falha. Falha no meio preserva os lotes anteriores.
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

import app.automatic_opaque_key_rotation as sched  # noqa: E402


class FakeTransaction:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        if exc[0] is None:
            self._conn.committed += 1
        else:
            self._conn.rolled_back += 1
        return False


class FakeConn:
    def __init__(self, batches: list[list[dict]]) -> None:
        self.batches = list(batches)
        self.committed = 0
        self.rolled_back = 0
        self.locked = False
        self.max_fetch_limit = 0
        self.fetch_calls = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def fetchval(self, sql: str, *args: object) -> bool:
        assert "pg_try_advisory_lock" in sql, sql
        self.locked = True
        return True

    async def execute(self, sql: str, *args: object) -> str:
        if "pg_advisory_unlock" in sql:
            self.locked = False
            return "SELECT 1"
        return "DELETE 0"

    async def fetch(self, sql: str, *args: object) -> list[dict]:
        self.fetch_calls += 1
        self.max_fetch_limit = max(self.max_fetch_limit, int(args[-1]))
        if self.batches:
            return self.batches.pop(0)
        return []


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self._conn)


class FakeAcquire:
    def __init__(self, conn: FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> FakeConn:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


def due_row(index: int) -> dict:
    return {
        "project_id": uuid.uuid4(),
        "slot_id": uuid.uuid4(),
        "name": f"slot-{index}",
        "rotation_trigger": "automatic",
        "reveal_unclaimed": False,
    }


class ScanBatchingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.audits: list = []
        self.notifies: list = []

        async def _activate(conn: FakeConn, **kwargs: object):
            return uuid.uuid4(), 1

        async def _audit(conn: FakeConn, **kwargs: object) -> None:
            self.audits.append(kwargs)

        async def _notify(conn: FakeConn, **kwargs: object) -> None:
            self.notifies.append(kwargs)

        patches = [
            mock.patch.object(sched, "activate_pending_key", _activate),
            mock.patch.object(sched, "audit_studio_action", _audit),
            mock.patch.object(sched, "_notify_project_admins", _notify),
        ]
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()

    async def run_scan(self, batches: list[list[dict]]) -> tuple[int, FakeConn]:
        conn = FakeConn(batches)

        async def _pool() -> FakePool:
            return FakePool(conn)

        with mock.patch.object(sched, "get_pool", _pool):
            transitions = await sched.scan_automatic_opaque_key_rotations()
        return transitions, conn

    async def test_large_backlog_commits_in_small_batches(self) -> None:
        rows = [due_row(index) for index in range(25)]
        transitions, conn = await self.run_scan([rows[:10], rows[10:20], rows[20:]])
        self.assertEqual(transitions, 25)
        self.assertEqual(len(self.audits), 25)
        self.assertEqual(len(self.notifies), 25)
        self.assertLessEqual(conn.max_fetch_limit, sched.SCAN_BATCH_SIZE)
        self.assertGreaterEqual(conn.committed, 4)
        self.assertEqual(conn.rolled_back, 0)
        self.assertFalse(conn.locked)

    async def test_mid_scan_failure_keeps_earlier_batches(self) -> None:
        rows = [due_row(index) for index in range(12)]
        calls = {"count": 0}
        real_activate = sched.activate_pending_key

        async def _flaky(conn: FakeConn, **kwargs: object):
            calls["count"] += 1
            if calls["count"] > 11:
                raise RuntimeError("boom")
            return await real_activate(conn, **kwargs)

        with mock.patch.object(sched, "activate_pending_key", _flaky):
            conn = FakeConn([rows[:10], rows[10:]])

            async def _pool() -> FakePool:
                return FakePool(conn)

            with mock.patch.object(sched, "get_pool", _pool):
                with self.assertRaises(RuntimeError):
                    await sched.scan_automatic_opaque_key_rotations()
        self.assertEqual(conn.committed, 2)
        self.assertEqual(conn.rolled_back, 1)
        self.assertFalse(conn.locked)


if __name__ == "__main__":
    unittest.main()
