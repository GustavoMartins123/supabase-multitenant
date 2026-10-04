from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import configure_studio_runtime as runtime


@unittest.skipUnless(shutil.which("openssl"), "requires openssl")
class SetupTlsProvisioningTests(unittest.TestCase):
    def test_studio_and_traefik_leaves_share_a_ca_and_verify_the_published_ip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            for name, _ in runtime.AUTHELIA_RUNTIME_SEEDS:
                shutil.copyfile(
                    runtime.CONFIG_TEMPLATE.parent / f"{name}.example",
                    root / "config" / f"{name}.example",
                )
            with mock.patch.object(runtime, "ensure_internal_service_hmac_secrets", return_value=False):
                runtime.configure_runtime(
                    studio_origin="https://192.0.2.10:9091",
                    target=root / "config/configuration.runtime.yml",
                    ssl_root=root / "ssl",
                    secrets_root=root / "secrets",
                    server_env=root / "missing.env",
                    server_host="192.0.2.10",
                    server_dns_host="supabase-backend.internal",
                    server_tls_root=root / "traefik",
                )
            for leaf in (root / "ssl/server.pem", root / "traefik/tls.crt"):
                result = subprocess.run(
                    ["openssl", "verify", "-CAfile", str(root / "ssl/ca.pem"),
                     "-verify_ip", "192.0.2.10", str(leaf)],
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "traefik/tls.key").is_file())
            self.assertFalse((root / "traefik/server.key").exists())
            self.assertFalse((root / "traefik/ca.key").exists())
            result = subprocess.run(
                ["openssl", "verify", "-CAfile", str(root / "ssl/ca.pem"),
                 "-verify_hostname", "supabase-backend.internal", str(root / "traefik/tls.crt")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            assistant = root / "assistant"
            for name in ("MASTER_KEY", "GATEWAY_KEY"):
                self.assertRegex((assistant / name).read_text().strip(), r"^[0-9a-f]{64}$")
            self.assertNotEqual((assistant / "MASTER_KEY").read_bytes(), (assistant / "GATEWAY_KEY").read_bytes())
            for hostname, expected in (("studio-assistant", 0), ("nginx", 2), ("authelia", 2)):
                result = subprocess.run(["openssl", "verify", "-CAfile", str(root / "ssl/ca.pem"),
                                         "-verify_hostname", hostname, str(assistant / "tls/server.pem")], capture_output=True)
                self.assertEqual(result.returncode, expected)
            previous = {name: (assistant / name).read_bytes() for name in ("MASTER_KEY", "GATEWAY_KEY")}
            with mock.patch.object(runtime, "ensure_internal_service_hmac_secrets", return_value=False):
                runtime.configure_runtime(studio_origin="https://192.0.2.10:9091", force=True, rotate_secrets=True,
                                          target=root / "config/configuration.runtime.yml", ssl_root=root / "ssl",
                                          secrets_root=root / "secrets", server_env=root / "missing.env")
            self.assertEqual(previous, {name: (assistant / name).read_bytes() for name in previous})

    def test_internal_dns_identity_rejects_literal_ips_and_configuration_injection(self):
        for identity in ("192.0.2.10", "backend.internal\nDNS:other.internal", "backend.internal:443"):
            with self.subTest(identity=identity), self.assertRaises(runtime.RuntimeConfigError):
                runtime.certificate_sans("192.0.2.10", identity)


if __name__ == "__main__":
    unittest.main()
