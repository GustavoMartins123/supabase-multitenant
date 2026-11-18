"""Hardening de _write_env_whitelisted e _normalize_setting_value (SEC-02)."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

from fastapi import HTTPException

ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import project_settings as ps  # noqa: E402


class ProjectSettingsHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = pathlib.Path(self.tmp.name)

    def test_write_env_whitelisted_enforces_0o600_and_atomic_preservation(self) -> None:
        env_path = self.base / ".env"
        env_path.write_text(
            "# header\nJWT_EXPIRY=3600\nJWT_SECRET_PROJETO=keep-secret\n",
            encoding="utf-8",
        )
        os.chmod(env_path, 0o644)

        ps._write_env_whitelisted(
            env_path,
            {"JWT_EXPIRY": "7200", "DISABLE_SIGNUP": "true"},
        )

        mode = env_path.stat().st_mode & 0o777
        self.assertEqual(mode, 0o600)
        content = env_path.read_text(encoding="utf-8")
        self.assertIn("# header\n", content)
        self.assertIn("JWT_EXPIRY=7200\n", content)
        self.assertIn("DISABLE_SIGNUP=true\n", content)
        self.assertIn("JWT_SECRET_PROJETO=keep-secret\n", content)
        self.assertEqual(list(self.base.glob(".*.tmp")), [])

    def test_write_env_whitelisted_rejects_newline_carriage_return_and_nul(self) -> None:
        env_path = self.base / ".env"
        original = "JWT_EXPIRY=3600\nJWT_SECRET_PROJETO=immutable\n"
        env_path.write_text(original, encoding="utf-8")

        for injected in (
            "3600\nJWT_SECRET_PROJETO=hack",
            "3600\rJWT_SECRET_PROJETO=hack",
            "3600\x00JWT_SECRET_PROJETO=hack",
            "true\n",
        ):
            with self.subTest(injected=injected):
                with self.assertRaises(ValueError):
                    ps._write_env_whitelisted(env_path, {"JWT_EXPIRY": injected})
                self.assertEqual(env_path.read_text(encoding="utf-8"), original)

    def test_write_env_whitelisted_rejects_invalid_keys(self) -> None:
        env_path = self.base / ".env"
        env_path.write_text("JWT_EXPIRY=3600\n", encoding="utf-8")

        for bad_key in ("jwt_expiry", "1BAD", "BAD-KEY", "BAD=KEY", "BAD\nKEY", ""):
            with self.subTest(bad_key=bad_key):
                with self.assertRaises(ValueError):
                    ps._write_env_whitelisted(env_path, {bad_key: "100"})

    def test_write_and_read_env_whitelisted_reject_symlinks(self) -> None:
        victim = self.base / "victim.env"
        victim.write_text("JWT_EXPIRY=3600\n", encoding="utf-8")

        file_link = self.base / "link.env"
        file_link.symlink_to(victim)
        with self.assertRaises(ValueError):
            ps._write_env_whitelisted(file_link, {"JWT_EXPIRY": "7200"})
        with self.assertRaises(ValueError):
            ps._read_env_whitelisted(file_link)
        self.assertEqual(victim.read_text(encoding="utf-8"), "JWT_EXPIRY=3600\n")

        real_dir = self.base / "real_project"
        real_dir.mkdir()
        real_env = real_dir / ".env"
        real_env.write_text("JWT_EXPIRY=3600\n", encoding="utf-8")
        dir_link = self.base / "linked_project"
        dir_link.symlink_to(real_dir)
        with self.assertRaises(ValueError):
            ps._write_env_whitelisted(dir_link / ".env", {"JWT_EXPIRY": "7200"})
        with self.assertRaises(ValueError):
            ps._read_env_whitelisted(dir_link / ".env")
        self.assertEqual(real_env.read_text(encoding="utf-8"), "JWT_EXPIRY=3600\n")

    def test_normalize_setting_value_rejects_trailing_newline_and_system_schemas(self) -> None:
        for raw in ("true\n", "\rtrue", "3600\x00"):
            with self.subTest(raw=raw), self.assertRaises(HTTPException):
                ps._normalize_setting_value("DISABLE_SIGNUP", raw)

        for forbidden in (
            "pg_catalog",
            "public,information_schema",
            "_supavisor",
            "_realtime",
            "_analytics",
            "pg_toast_temp_1",
        ):
            with self.subTest(forbidden=forbidden), self.assertRaises(HTTPException):
                ps._normalize_setting_value("PGRST_DB_SCHEMAS", forbidden)

        self.assertEqual(
            ps._normalize_setting_value(
                "PGRST_DB_SCHEMAS", "public, storage, graphql_public, extensions, app_v1"
            ),
            "public,storage,graphql_public,extensions,app_v1",
        )


if __name__ == "__main__":
    unittest.main()
