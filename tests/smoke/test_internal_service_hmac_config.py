from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "configure_studio_runtime.py"
SPEC = importlib.util.spec_from_file_location("configure_studio_runtime", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
runtime_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime_config)


def env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.lstrip().startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        values[key] = value
    return values


class InternalServiceHmacConfigTest(unittest.TestCase):
    def make_envs(self, server: str, studio: str) -> tuple[Path, Path, tempfile.TemporaryDirectory[str]]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        server_env = root / "servidor.env"
        studio_env = root / "studio.env"
        server_env.write_text(server, encoding="utf-8")
        studio_env.write_text(studio, encoding="utf-8")
        server_env.chmod(0o600)
        studio_env.chmod(0o600)
        return server_env, studio_env, temp

    def test_generates_two_distinct_secrets_and_syncs_both_envs(self) -> None:
        server_env, studio_env, temp = self.make_envs(
            "STUDIO_GATEWAY_HMAC_SECRET=\nPROJECTS_API_HMAC_SECRET=\n",
            "STUDIO_GATEWAY_HMAC_SECRET=\nPROJECTS_API_HMAC_SECRET=\n",
        )
        self.addCleanup(temp.cleanup)

        changed = runtime_config.ensure_internal_service_hmac_secrets(
            server_env,
            studio_env,
        )
        self.assertTrue(changed)

        server = env_values(server_env)
        studio = env_values(studio_env)
        for key in runtime_config.INTERNAL_SERVICE_HMAC_KEYS:
            self.assertEqual(server[key], studio[key])
            self.assertRegex(server[key], r"^[0-9a-f]{64}$")
        self.assertNotEqual(
            server["STUDIO_GATEWAY_HMAC_SECRET"],
            server["PROJECTS_API_HMAC_SECRET"],
        )

    def test_existing_secret_on_one_side_is_copied_without_rotation(self) -> None:
        existing = "ab" * 32
        reverse = "cd" * 32
        server_env, studio_env, temp = self.make_envs(
            f"STUDIO_GATEWAY_HMAC_SECRET={existing}\nPROJECTS_API_HMAC_SECRET=\n",
            f"STUDIO_GATEWAY_HMAC_SECRET=\nPROJECTS_API_HMAC_SECRET={reverse}\n",
        )
        self.addCleanup(temp.cleanup)

        runtime_config.ensure_internal_service_hmac_secrets(server_env, studio_env)
        server = env_values(server_env)
        studio = env_values(studio_env)
        self.assertEqual(server["STUDIO_GATEWAY_HMAC_SECRET"], existing)
        self.assertEqual(studio["STUDIO_GATEWAY_HMAC_SECRET"], existing)
        self.assertEqual(server["PROJECTS_API_HMAC_SECRET"], reverse)
        self.assertEqual(studio["PROJECTS_API_HMAC_SECRET"], reverse)

    def test_divergent_explicit_values_fail_closed(self) -> None:
        server_env, studio_env, temp = self.make_envs(
            f"STUDIO_GATEWAY_HMAC_SECRET={'aa' * 32}\nPROJECTS_API_HMAC_SECRET={'cc' * 32}\n",
            f"STUDIO_GATEWAY_HMAC_SECRET={'bb' * 32}\nPROJECTS_API_HMAC_SECRET={'cc' * 32}\n",
        )
        self.addCleanup(temp.cleanup)

        with self.assertRaises(runtime_config.RuntimeConfigError):
            runtime_config.ensure_internal_service_hmac_secrets(server_env, studio_env)


if __name__ == "__main__":
    unittest.main()
