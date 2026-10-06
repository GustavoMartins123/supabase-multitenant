from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


class OutboundTlsContractTests(unittest.TestCase):
    def test_no_client_disables_certificate_validation(self) -> None:
        lua_sources = "\n".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in (ROOT / "studio/nginx/lua").rglob("*.lua")
        )
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        runtime = (ROOT / "servidor/api-internal/app/runtime_config.py").read_text(
            encoding="utf-8"
        )
        push_worker = (ROOT / "servidor/api-internal/app/push_worker.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ssl_verify = false", lua_sources)
        self.assertNotIn("NODE_TLS_REJECT_UNAUTHORIZED", compose)
        self.assertNotIn("check_hostname = False", runtime)
        self.assertNotIn("ssl.CERT_NONE", push_worker)

    def test_public_hosts_always_verify_and_internal_tls_is_fail_closed(self) -> None:
        helper = (ROOT / "studio/nginx/lua/utils/outbound_tls.lua").read_text(
            encoding="utf-8"
        )
        entrypoint = (ROOT / "studio/nginx/docker-entrypoint.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("options.ssl_verify = true", helper)
        self.assertIn("options.ssl_server_name = hostname(url)", helper)
        self.assertIn('https://*)', entrypoint)
        self.assertIn("SERVICE_KEY_VERIFY_TLS deve permanecer ativo", entrypoint)
        self.assertIn("-checkhost nginx", entrypoint)
        self.assertIn("studio-ca-bundle.pem", entrypoint)
        self.assertIn("ca-certificates.crt", entrypoint)

    def test_lua_and_node_share_a_configurable_ca(self) -> None:
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        example = (ROOT / "studio/.env.example").read_text(encoding="utf-8")
        runtime = (ROOT / "tools/configure_studio_runtime.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("STUDIO_CA_CERT_PATH", example)
        self.assertGreaterEqual(compose.count("STUDIO_CA_CERT_PATH"), 2)
        self.assertIn("NODE_EXTRA_CA_CERTS", compose)
        self.assertIn('"DNS:nginx"', runtime)

    def test_backend_proxy_and_lua_share_the_explicit_certificate_identity(self) -> None:
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        helper = (ROOT / "studio/nginx/lua/utils/outbound_tls.lua").read_text(encoding="utf-8")
        self.assertIn("env STUDIO_BACKEND_TLS_NAME;", nginx)
        self.assertIn("proxy_ssl_name $backend_tls_name;", nginx)
        self.assertNotIn("proxy_ssl_name        $server_hostname;", nginx)
        self.assertIn("options.ssl_server_name = M.backend_name()", helper)
        self.assertIn('assert(configured_verify == "true"', helper)
        self.assertIn("STUDIO_BACKEND_TLS_NAME must specify", helper)

    def test_google_and_fcm_use_the_public_policy(self) -> None:
        source = (ROOT / "studio/nginx/lua/send_push.lua").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("outbound_tls.apply_public"), 2)


if __name__ == "__main__":
    unittest.main()
