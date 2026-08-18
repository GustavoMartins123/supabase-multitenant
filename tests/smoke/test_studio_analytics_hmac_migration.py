from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "migrate_studio_analytics_hmac.py"
SPEC = importlib.util.spec_from_file_location("migrate_studio_analytics_hmac", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


class StudioAnalyticsHmacMigrationTest(unittest.TestCase):
    def env(self, content: str) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / ".env"
        path.write_text(content, encoding="utf-8")
        path.chmod(0o644)
        return path, temp

    def test_generates_secret_atomically_and_is_idempotent(self) -> None:
        path, temp = self.env(
            f"STUDIO_GATEWAY_HMAC_SECRET={'aa' * 32}\n"
            f"PROJECTS_API_HMAC_SECRET={'bb' * 32}\n"
        )
        self.addCleanup(temp.cleanup)

        self.assertTrue(migration.migrate(path))
        content = path.read_text(encoding="utf-8")
        value = migration._value(content, migration.KEY)
        self.assertRegex(value, r"^[0-9a-f]{64}$")
        self.assertNotEqual(value, "aa" * 32)
        self.assertNotEqual(value, "bb" * 32)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertTrue(path.with_name(".env.pre-studio-analytics-hmac").exists())
        self.assertFalse(migration.migrate(path))

    def test_dry_run_does_not_write(self) -> None:
        path, temp = self.env("")
        self.addCleanup(temp.cleanup)
        before = path.read_text(encoding="utf-8")
        self.assertTrue(migration.migrate(path, dry_run=True))
        self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_rejects_shared_or_invalid_secret(self) -> None:
        shared = "cc" * 32
        path, temp = self.env(
            f"STUDIO_GATEWAY_HMAC_SECRET={shared}\n"
            f"STUDIO_ANALYTICS_HMAC_SECRET={shared}\n"
        )
        self.addCleanup(temp.cleanup)
        with self.assertRaises(migration.MigrationError):
            migration.migrate(path)

        path2, temp2 = self.env("STUDIO_ANALYTICS_HMAC_SECRET=short\n")
        self.addCleanup(temp2.cleanup)
        with self.assertRaises(migration.MigrationError):
            migration.migrate(path2)


if __name__ == "__main__":
    unittest.main()
