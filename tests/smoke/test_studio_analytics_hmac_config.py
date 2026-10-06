from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "configure_studio_runtime.py"
SPEC = importlib.util.spec_from_file_location("configure_studio_runtime", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


def values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


class StudioAnalyticsHmacConfigTest(unittest.TestCase):
    def test_provisions_studio_only_distinct_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = root / "server.env"
            studio = root / "studio.env"
            server.write_text(
                "STUDIO_GATEWAY_HMAC_SECRET=\nPROJECTS_API_HMAC_SECRET=\n",
                encoding="utf-8",
            )
            studio.write_text(
                "STUDIO_GATEWAY_HMAC_SECRET=\nPROJECTS_API_HMAC_SECRET=\n"
                "STUDIO_ANALYTICS_HMAC_SECRET=\n",
                encoding="utf-8",
            )

            self.assertTrue(runtime.ensure_internal_service_hmac_secrets(server, studio))
            server_values = values(server)
            studio_values = values(studio)

            analytics = studio_values[runtime.STUDIO_ANALYTICS_HMAC_KEY]
            self.assertRegex(analytics, r"^[0-9a-f]{64}$")
            self.assertNotIn(runtime.STUDIO_ANALYTICS_HMAC_KEY, server_values)
            self.assertNotEqual(analytics, server_values["STUDIO_GATEWAY_HMAC_SECRET"])
            self.assertNotEqual(analytics, server_values["PROJECTS_API_HMAC_SECRET"])

    def test_rejects_analytics_secret_reused_as_gateway_secret(self) -> None:
        shared = "ab" * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = root / "server.env"
            studio = root / "studio.env"
            server.write_text(
                f"STUDIO_GATEWAY_HMAC_SECRET={shared}\n"
                f"PROJECTS_API_HMAC_SECRET={'cd' * 32}\n",
                encoding="utf-8",
            )
            studio.write_text(
                f"STUDIO_GATEWAY_HMAC_SECRET={shared}\n"
                f"PROJECTS_API_HMAC_SECRET={'cd' * 32}\n"
                f"STUDIO_ANALYTICS_HMAC_SECRET={shared}\n",
                encoding="utf-8",
            )

            with self.assertRaises(runtime.RuntimeConfigError):
                runtime.ensure_internal_service_hmac_secrets(server, studio)


if __name__ == "__main__":
    unittest.main()
