"""Persistencia do perfil de recursos via PUT /settings (LOG-07).

Trocar PROJECT_RESOURCE_PROFILE por um perfil nomeado precisa persistir
projects.resource_profile; capacidade personalizada precisa persistir
"custom" e marcar recreate dos servicos afetados. Mudanca sem recurso nao
pode tocar a coluna.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

import os

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

from app.schemas import UpdateSettings  # noqa: E402

import app.routers.project_lifecycle_ops as ops  # noqa: E402


class FakeAcquire:
    def __init__(self, conn: object) -> None:
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, *exc: object) -> bool:
        return False


class FakePool:
    def __init__(self) -> None:
        self.executes: list[tuple[str, tuple[object, ...]]] = []

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(object())

    async def execute(self, query: str, *args: object) -> str:
        self.executes.append((query, args))
        return "UPDATE 1"

    def profile_updates(self) -> list[tuple[str, tuple[object, ...]]]:
        return [
            (query, args)
            for query, args in self.executes
            if "SET resource_profile" in query
        ]


def write_env(path: Path, profile: str = "medium") -> None:
    path.write_text(
        "PROJECT_RESOURCE_PROFILE=%s\n"
        "FILE_SIZE_LIMIT=100\n"
        "PROJECT_MEM_LIMIT=512m\n"
        "PROJECT_CPUS=1.00\n"
        "PROJECT_PIDS_LIMIT=256\n" % profile,
        encoding="utf-8",
    )


class SettingsProfilePersistenceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env_path = Path(self.tmp.name) / ".env"
        write_env(self.env_path)
        self.user_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.pool = FakePool()
        self.pending: list[tuple[str, list[str]]] = []
        self.cleared: list[str] = []

    async def call_update(
        self,
        settings: dict[str, str],
        db_profile: str = "medium",
        resolve_stub: dict[str, str] | None = None,
    ) -> dict:
        async def _auth(*args: object, **kwargs: object) -> dict:
            return {"db_user_id": self.user_id}

        async def _row(*args: object, **kwargs: object) -> dict:
            return {
                "id": self.project_id,
                "name": "demo",
                "resource_profile": db_profile,
            }

        async def _admin(*args: object, **kwargs: object) -> None:
            return None

        patches = [
            mock.patch.object(ops, "resolve_authenticated_user", _auth),
            mock.patch.object(ops, "get_project_row", _row),
            mock.patch.object(ops, "ensure_project_admin_access", _admin),
            mock.patch.object(
                ops, "_get_project_env_path", lambda name: self.env_path
            ),
            mock.patch.object(
                ops, "_get_project_file_size_limit", lambda name: "100"
            ),
            mock.patch.object(
                ops, "_get_project_storage_limit_token", lambda name: "tok"
            ),
            mock.patch.object(
                ops,
                "_write_project_pending_settings",
                lambda name, affected: self.pending.append((name, affected)),
            ),
            mock.patch.object(
                ops,
                "_clear_project_pending_settings",
                lambda name: self.cleared.append(name),
            ),
        ]
        if resolve_stub is not None:
            patches.append(
                mock.patch.object(
                    ops, "resolve_resource_limits", lambda profile: resolve_stub
                )
            )
        for entered in patches:
            self.addCleanup(entered.stop)
            entered.start()
        return await ops.update_project_settings(
            "demo", UpdateSettings(settings=settings), object(), self.pool
        )

    async def test_named_profile_change_persists_in_database(self) -> None:
        body = await self.call_update(
            {"PROJECT_RESOURCE_PROFILE": "large"},
            db_profile="medium",
            resolve_stub={
                "PROJECT_MEM_LIMIT": "1024m",
                "PROJECT_CPUS": "2.00",
                "PROJECT_PIDS_LIMIT": "512",
            },
        )
        updates = self.pool.profile_updates()
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], ("large", "demo"))
        self.assertEqual(body["affected_services"], ["auth", "nginx", "rest"])
        self.assertIn("PROJECT_RESOURCE_PROFILE", body["updated_keys"])
        env = self.env_path.read_text(encoding="utf-8")
        self.assertIn("PROJECT_RESOURCE_PROFILE=large", env)

    async def test_custom_totals_persist_custom_and_request_recreate(self) -> None:
        body = await self.call_update(
            {
                "PROJECT_MEM_LIMIT": "1024m",
                "PROJECT_CPUS": "2.00",
                "PROJECT_PIDS_LIMIT": "512",
            },
            db_profile="medium",
        )
        updates = self.pool.profile_updates()
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][1], ("custom", "demo"))
        self.assertEqual(body["affected_services"], ["auth", "nginx", "rest"])
        env = self.env_path.read_text(encoding="utf-8")
        self.assertIn("PROJECT_RESOURCE_PROFILE=custom", env)

    async def test_non_resource_change_does_not_touch_profile(self) -> None:
        body = await self.call_update(
            {"JWT_EXPIRY": "3600"}, db_profile="medium"
        )
        self.assertEqual(self.pool.profile_updates(), [])
        self.assertEqual(body["affected_services"], ["auth", "rest"])


if __name__ == "__main__":
    unittest.main()
