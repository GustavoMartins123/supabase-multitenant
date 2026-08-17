from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools/migrate_internal_hmac_v1.py"
spec = importlib.util.spec_from_file_location("migrate_internal_hmac_v1", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class InternalHmacMigrationTest(unittest.TestCase):
    def _files(self, root: Path, server: str, studio: str) -> tuple[Path, Path]:
        server_path = root / "server.env"
        studio_path = root / "studio.env"
        server_path.write_text(server, encoding="utf-8")
        studio_path.write_text(studio, encoding="utf-8")
        return server_path, studio_path

    def test_generates_distinct_keys_and_removes_old_assignments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server, studio = self._files(
                Path(tmp),
                "NGINX_SHARED_TOKEN=old\nINTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN=true\n",
                "NGINX_SHARED_TOKEN=old\n",
            )
            self.assertTrue(module.migrate(server, studio))
            server_text = server.read_text(encoding="utf-8")
            studio_text = studio.read_text(encoding="utf-8")
            for key in module.REMOVED_KEYS:
                self.assertNotIn(key, server_text + studio_text)
            values = []
            for key in module.SERVICE_KEYS:
                server_value = module._value(server_text, key)
                studio_value = module._value(studio_text, key)
                self.assertEqual(server_value, studio_value)
                self.assertTrue(server_value)
                values.append(server_value)
            self.assertNotEqual(values[0], values[1])
            self.assertTrue(server.with_name(server.name + ".pre-internal-hmac-v1").exists())

    def test_preserves_existing_explicit_key_without_rotation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            existing = "a" * 64
            server, studio = self._files(
                Path(tmp),
                f"STUDIO_GATEWAY_HMAC_SECRET={existing}\n",
                "",
            )
            module.migrate(server, studio)
            self.assertEqual(existing, module._value(server.read_text(), "STUDIO_GATEWAY_HMAC_SECRET"))
            self.assertEqual(existing, module._value(studio.read_text(), "STUDIO_GATEWAY_HMAC_SECRET"))

    def test_fails_on_divergent_explicit_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            server, studio = self._files(
                Path(tmp),
                "STUDIO_GATEWAY_HMAC_SECRET=" + "a" * 64 + "\n",
                "STUDIO_GATEWAY_HMAC_SECRET=" + "b" * 64 + "\n",
            )
            with self.assertRaises(module.MigrationError):
                module.migrate(server, studio)


if __name__ == "__main__":
    unittest.main()
