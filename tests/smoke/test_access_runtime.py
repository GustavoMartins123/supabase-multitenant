import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "access_runtime", ROOT / "tools/configure_access_runtime.py"
)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class AccessRuntimeTests(unittest.TestCase):
    def fixture(self, folder, extra=""):
        root = Path(folder)
        (root / "traefik").mkdir()
        (root / "traefik/traefik.yml").write_text(
            'entryPoints:\n  web:\n    address: ":80"\n  websecure:\n    address: ":443"\n',
            encoding="utf-8",
        )
        env = root / ".env"
        env.write_text(
            "ACCESS_ADMISSION_SECRET=pass\nACCESS_RATE_REDIS_PASSWORD=pass\nACCESS_ADMIN_CIDRS=pass\n"
            + extra,
            encoding="utf-8",
        )
        return env

    def test_generation_preserves_secrets_and_matches_proxy_trust(self):
        with tempfile.TemporaryDirectory() as folder:
            env = self.fixture(folder, "ACCESS_TRUSTED_PROXY_CIDRS=192.0.2.1/32\n")
            runtime.configure(env, "192.0.2.10", "172.50.0.0/16")
            first = env.read_bytes()
            self.assertNotIn(b"=pass", first)
            self.assertIn(b"ACCESS_ADMIN_CIDRS=192.0.2.10/32,172.50.0.0/16", first)
            self.assertEqual(
                (Path(folder) / "traefik/traefik.runtime.yml")
                .read_text()
                .count('trustedIPs: ["192.0.2.1/32"]'),
                2,
            )
            runtime.configure(env, "192.0.2.11", "172.60.0.0/16")
            self.assertEqual(env.read_bytes(), first)

    def test_invalid_trust_and_template_fail_before_env_changes(self):
        for extra in (
            "ACCESS_TRUSTED_PROXY_CIDRS=0.0.0.0/0\n",
            "ACCESS_TRUSTED_PROXY_CIDRS=192.0.2.1/24\n",
            "ACCESS_TRUSTED_PROXY_CIDRS=::ffff:0:0/96\n",
            "ACCESS_TRUSTED_PROXY_CIDRS=::ffff:192.0.2.0/120\n",
            "ACCESS_TRUSTED_PROXY_CIDRS=192.0.2.1/32,\n",
        ):
            with tempfile.TemporaryDirectory() as folder:
                env = self.fixture(folder, extra)
                before = env.read_bytes()
                with self.assertRaises(ValueError):
                    runtime.configure(env, "192.0.2.10", "172.50.0.0/16")
                self.assertEqual(env.read_bytes(), before)
                self.assertFalse((Path(folder) / "traefik/traefik.runtime.yml").exists())
        with tempfile.TemporaryDirectory() as folder:
            env = self.fixture(folder)
            (Path(folder) / "traefik/traefik.yml").write_text("invalid", encoding="utf-8")
            before = env.read_bytes()
            with self.assertRaises(ValueError):
                runtime.configure(env, "192.0.2.10", "172.50.0.0/16")
            self.assertEqual(env.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
