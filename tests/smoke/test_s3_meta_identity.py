"""Fail-closed por identidade nas s3-keys e no DSN do Meta (LOG-17/18).

S3: par SigV4 so e entregue quando PROJECT_UUID do .env pertence ao
projeto do control plane; .env trocado/divergente da 409.
Meta: query do DSN (sslmode etc.) sobrevive a troca de banco e hosts IPv6
sao reformatados com colchetes; ref invalida e rejeitada.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
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

import app.asgi as asgi  # noqa: E402
from app.meta_connections import (  # noqa: E402
    get_project_meta_connection_string,
    get_project_reader_connection_string,
)

PROJECT_UUID = "11111111-1111-4111-8111-111111111111"
ACCESS_KEY = "a" * 32
SECRET_KEY = "b" * 64


def write_env(path: Path, project_uuid: str | None) -> None:
    lines = [
        f"S3_PROTOCOL_ACCESS_KEY_ID={ACCESS_KEY}",
        f"S3_PROTOCOL_ACCESS_KEY_SECRET={SECRET_KEY}",
    ]
    if project_uuid is not None:
        lines.append(f"PROJECT_UUID={project_uuid}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class S3KeysIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(
            asgi, "PROJECTS_ROOT", Path(self.tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, project_uuid: str | None) -> tuple[str, str]:
        project_dir = Path(self.tmp.name) / "demo"
        project_dir.mkdir(exist_ok=True)
        write_env(project_dir / ".env", project_uuid)
        return asgi._read_project_s3_vector_keys(
            "demo",
            project_id=PROJECT_UUID,
            tenant_uuid=PROJECT_UUID,
        )

    def test_matching_identity_returns_keys(self) -> None:
        self.assertEqual(self.read(PROJECT_UUID), (ACCESS_KEY, SECRET_KEY))

    def test_matching_identity_is_case_insensitive(self) -> None:
        self.assertEqual(
            self.read(PROJECT_UUID.upper()), (ACCESS_KEY, SECRET_KEY)
        )

    def test_foreign_uuid_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.read("22222222-2222-4222-8222-222222222222")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_missing_uuid_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.read(None)
        self.assertEqual(ctx.exception.status_code, 409)


class MetaDsnTest(unittest.TestCase):
    def dsn(self, **overrides: str) -> dict[str, str]:
        env = {
            "META_ADMIN_DSN": (
                "postgresql://admin:secret@db.internal:5433/postgres"
                "?sslmode=require&connect_timeout=10"
            ),
            "PLATFORM_READER_DB_PASSWORD": "reader-secret",
        }
        env.update(overrides)
        return env

    def test_meta_preserves_query_and_switches_database(self) -> None:
        with mock.patch.dict(os.environ, self.dsn(), clear=False):
            out = get_project_meta_connection_string("demo")
        self.assertIn("/_supabase_demo", out)
        self.assertIn("sslmode=require", out)
        self.assertIn("connect_timeout=10", out)
        self.assertIn("admin:secret@", out)

    def test_reader_preserves_query_and_brackets_ipv6(self) -> None:
        with mock.patch.dict(
            os.environ,
            self.dsn(
                META_ADMIN_DSN=(
                    "postgresql://admin:secret@[fd00::10]:5433/postgres"
                    "?sslmode=require"
                )
            ),
            clear=False,
        ):
            out = get_project_reader_connection_string("demo")
        self.assertIn("/_supabase_demo", out)
        self.assertIn("sslmode=require", out)
        self.assertIn("platform_reader:reader-secret@[fd00::10]:5433", out)

    def test_invalid_ref_is_rejected(self) -> None:
        with mock.patch.dict(os.environ, self.dsn(), clear=False):
            with self.assertRaises(HTTPException) as ctx:
                get_project_meta_connection_string("../escape")
            self.assertEqual(ctx.exception.status_code, 400)
            with self.assertRaises(HTTPException) as ctx:
                get_project_reader_connection_string("UPPER SPACE")
            self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
