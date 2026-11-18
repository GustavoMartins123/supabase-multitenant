"""Contract and SSRF-boundary tests for Edge Function dependency validation and bundling service."""
from __future__ import annotations

import base64
import http.client
import importlib.util
import json
import os
import pathlib
import socket
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import AsyncMock, patch

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
sys.path.insert(0, str(ROOT / "servidor/edge-bundler"))

from app import edge_bundler
import policy as bundler_policy
import server as bundler_server


class EdgeBundlerSmokeTests(unittest.TestCase):
    def test_dependency_policy_allows_npm_jsr_node_and_blocks_remote_or_escaping_uris(self) -> None:
        files = [
            {"name": "deno.json", "content": '{"imports":{"@std/fmt/bytes":"jsr:@std/fmt@1/bytes"}}'},
            {"name": "index.ts", "content": '// comment https://ignored.example\nimport ms from "npm:ms@2.1.3";\nimport { format } from "@std/fmt/bytes";\nimport { Buffer } from "node:buffer";\n'},
        ]
        summary = edge_bundler.inspect_dependencies(files)
        self.assertEqual(summary, bundler_policy.inspect_dependencies(files))
        self.assertEqual(summary["npm"], ["npm:ms@2.1.3"])
        self.assertEqual(summary["jsr"], ["jsr:@std/fmt@1/bytes"])
        self.assertTrue(summary["requires_bundle"])

        for spec in ("https://evil.example/x.ts", "http://127.0.0.1/x.ts", "file:///etc/passwd", "data:text/plain,x", "../escape.ts", "/abs/path.ts"):
            with self.assertRaises(edge_bundler.DependencyPolicyError, msg=spec):
                edge_bundler.inspect_dependencies([{"name": "index.ts", "content": f'import x from "{spec}";'}])
            with self.assertRaises(bundler_policy.DependencyPolicyError, msg=spec):
                bundler_policy.inspect_dependencies([{"name": "index.ts", "content": f'import x from "{spec}";'}])

    def test_connect_proxy_rejects_private_ips_disallowed_hosts_and_non_443(self) -> None:
        self.assertFalse(bundler_server._is_public_global_ip("127.0.0.1"))
        self.assertFalse(bundler_server._is_public_global_ip("10.0.0.1"))
        self.assertFalse(bundler_server._is_public_global_ip("172.16.0.1"))
        self.assertFalse(bundler_server._is_public_global_ip("192.168.1.1"))
        self.assertFalse(bundler_server._is_public_global_ip("169.254.169.254"))
        self.assertFalse(bundler_server._is_public_global_ip("::ffff:127.0.0.1"))
        self.assertTrue(bundler_server._is_public_global_ip("104.16.25.34"))

        orig_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, port, *args, **kwargs):
            if host == "registry.npmjs.org":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
            return orig_getaddrinfo(host, port, *args, **kwargs)

        with bundler_server._RegistryConnectProxy(frozenset({"registry.npmjs.org"})) as proxy_url:
            port = int(proxy_url.rsplit(":", 1)[1])
            for target in ("localhost:443", "evil.example.com:443", "registry.npmjs.org:80"):
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                    resp = sock.recv(1024).decode()
                    self.assertTrue(resp.startswith("HTTP/1.1 403"), (target, resp))
            with patch.object(bundler_server.socket, "getaddrinfo", side_effect=fake_getaddrinfo):
                with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
                    sock.sendall(b"CONNECT registry.npmjs.org:443 HTTP/1.1\r\nHost: registry.npmjs.org:443\r\n\r\n")
                    resp = sock.recv(1024).decode()
                    self.assertTrue(resp.startswith("HTTP/1.1 403"), resp)

    def test_bundler_http_server_enforces_hmac_and_rpc_client_validates_eszip(self) -> None:
        import asyncio

        srv = ThreadingHTTPServer(("127.0.0.1", 0), bundler_server.BundlerHandler)
        port = srv.server_port
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        fake_eszip = b"ESZIP2.3\x00\x00\x00\x04unit"
        try:
            with patch.dict(os.environ, {"EDGE_BUNDLER_HMAC_SECRET": "test-secret", "EDGE_BUNDLER_URL": f"http://127.0.0.1:{port}"}):
                # Missing HMAC signature is rejected with 401.
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request("POST", "/bundle", body=b'{"files":[{"name":"index.ts","content":"Deno.serve(() => new Response())"}]}', headers={"Content-Type": "application/json"})
                self.assertEqual(conn.getresponse().status, 401)
                conn.close()

                # Signed client RPC decodes valid ESZIP and rejects disallowed import locally before HTTP call.
                files = [{"name": "index.ts", "content": 'import ms from "npm:ms@2.1.3"; Deno.serve(() => new Response(String(ms("1m"))));'}]
                with patch.object(bundler_server, "compile_function_eszip", return_value=fake_eszip):
                    out = asyncio.run(edge_bundler.bundle_function_eszip(files))
                self.assertEqual(out, fake_eszip)

                with self.assertRaises(edge_bundler.DependencyPolicyError):
                    asyncio.run(edge_bundler.bundle_function_eszip([{"name": "index.ts", "content": 'import x from "https://evil.example/a.ts";'}]))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=2)

    def test_private_registry_validation_runtime_config_proxy_and_redaction(self) -> None:
        import asyncio
        from datetime import datetime, timedelta, timezone
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "internal-ca")])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        ca_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

        # URL & token & CA validation contract matches between api-internal and edge-bundler policy.
        self.assertEqual(edge_bundler.validate_registry_name(" corp-npm_1 "), "corp-npm_1")
        with self.assertRaises(edge_bundler.DependencyPolicyError):
            edge_bundler.validate_registry_name("-bad-start")
        for mod in (edge_bundler, bundler_policy):
            with self.assertRaises(mod.DependencyPolicyError):
                mod.validate_registry_url("http://npm.example.com")
            with self.assertRaises(mod.DependencyPolicyError):
                mod.validate_registry_url("https://user:pass@npm.example.com")
            with self.assertRaises(mod.DependencyPolicyError):
                mod.validate_registry_url("https://10.0.0.5/npm", allow_private_network=False)
            with self.assertRaises(mod.DependencyPolicyError):
                mod.validate_registry_url("https://npm.corp.internal:8080/npm", allow_private_network=False)
            with self.assertRaises(mod.DependencyPolicyError):
                mod.validate_registry_url("https://npm.corp.internal:80/npm", allow_private_network=True)
            self.assertEqual(
                mod.validate_registry_url("https://npm.corp.internal:8443/pkg", allow_private_network=True),
                ("https://npm.corp.internal:8443/pkg/", "npm.corp.internal", 8443, "/pkg/"),
            )
            with self.assertRaises(mod.DependencyPolicyError):
                mod.normalize_ca_pem("not a pem certificate")
            self.assertTrue(mod.normalize_ca_pem(ca_pem).startswith("-----BEGIN CERTIFICATE-----"))

        regs = [
            {
                "kind": "npm",
                "scope": "@corp",
                "registry_url": "https://npm.corp.internal:8443/npm",
                "auth_type": "bearer",
                "token": "synthetic-npm-token",
                "allow_private_network": True,
                "ca_pem": ca_pem,
            },
            {
                "kind": "npm",
                "scope": "",
                "registry_url": "https://artifactory.example.com/npm",
                "auth_type": "basic",
                "token": "reader:pw_basic_456",
                "allow_private_network": False,
                "ca_pem": "",
            },
            {
                "kind": "jsr",
                "scope": "",
                "registry_url": "https://jsr.corp.internal:9443",
                "auth_type": "bearer",
                "token": "tok_secret_jsr_789",
                "allow_private_network": True,
                "ca_pem": ca_pem,
            },
        ]
        normalized = edge_bundler.validate_registries_payload(regs)
        self.assertEqual(len(normalized), 3)

        # Duplicate active slots or missing credentials must be rejected.
        with self.assertRaises(edge_bundler.DependencyPolicyError):
            edge_bundler.validate_registries_payload([regs[0], {**regs[0], "registry_url": "https://other.example.com"}])
        with self.assertRaises(edge_bundler.DependencyPolicyError):
            edge_bundler.validate_registries_payload([{**regs[1], "token": ""}])

        # _prepare_registry_runtime writes $HOME/.npmrc, JSR_URL, DENO_AUTH_TOKENS, combined SSL_CERT_FILE.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root_path = pathlib.Path(td)
            home_dir = root_path / "home"
            home_dir.mkdir()
            endpoints, env_extra, isolate_cache = bundler_server._prepare_registry_runtime(root_path, home_dir, normalized)
            self.assertTrue(isolate_cache)
            self.assertTrue(endpoints[("npm.corp.internal", 8443)])
            self.assertFalse(endpoints[("artifactory.example.com", 443)])
            self.assertTrue(endpoints[("jsr.corp.internal", 9443)])
            npmrc = (home_dir / ".npmrc").read_text(encoding="utf-8")
            self.assertIn("@corp:registry=https://npm.corp.internal:8443/npm/", npmrc)
            self.assertIn("//npm.corp.internal:8443/npm/:_authToken=synthetic-npm-token", npmrc)
            self.assertIn("registry=https://artifactory.example.com/npm/", npmrc)
            basic_b64 = base64.b64encode(b"reader:pw_basic_456").decode("ascii")
            self.assertIn(f"//artifactory.example.com/npm/:_auth={basic_b64}", npmrc)
            self.assertEqual(env_extra["JSR_URL"], "https://jsr.corp.internal:9443")
            self.assertEqual(env_extra["DENO_AUTH_TOKENS"], "tok_secret_jsr_789@jsr.corp.internal:9443")
            self.assertEqual(env_extra["DENO_TLS_CA_STORE"], "system")
            ca_bundle = pathlib.Path(env_extra["SSL_CERT_FILE"]).read_text(encoding="utf-8")
            self.assertEqual(ca_bundle.count("-----BEGIN CERTIFICATE-----"), ca_bundle_count := ca_bundle.count("-----END CERTIFICATE-----"))
            self.assertGreaterEqual(ca_bundle_count, 1)

            # Credential redaction hides both bearer tokens and basic base64 credentials.
            leaked = f"auth failed: synthetic-npm-token {basic_b64} reader:pw_basic_456"
            redacted = bundler_server._redact_credentials(leaked, normalized)
            self.assertNotIn("synthetic-npm-token", redacted)
            self.assertNotIn(basic_b64, redacted)
            self.assertNotIn("pw_basic_456", redacted)

        # _is_allowed_ip & _RegistryConnectProxy per-endpoint allow_private enforcement.
        self.assertFalse(bundler_server._is_allowed_ip("10.0.0.1", allow_private=False))
        self.assertTrue(bundler_server._is_allowed_ip("10.0.0.1", allow_private=True))
        self.assertFalse(bundler_server._is_allowed_ip("169.254.169.254", allow_private=True))
        self.assertFalse(bundler_server._is_allowed_ip("127.0.0.1", allow_private=True))
        with patch.dict(os.environ, {"EDGE_BUNDLER_ALLOW_LOOPBACK_FOR_TESTS": "1"}):
            self.assertTrue(bundler_server._is_allowed_ip("127.0.0.1", allow_private=True))
            self.assertFalse(bundler_server._is_allowed_ip("127.0.0.1", allow_private=False))

        orig_getaddrinfo = socket.getaddrinfo

        def resolve_mock(host, port, *args, **kwargs):
            mapping = {
                "npm.corp.internal": "169.254.169.254",
                "artifactory.example.com": "10.0.0.5",
            }
            if host in mapping:
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], port))]
            return orig_getaddrinfo(host, port, *args, **kwargs)

        with bundler_server._RegistryConnectProxy({("npm.corp.internal", 8443): True, ("artifactory.example.com", 443): False}) as proxy_url:
            pport = int(proxy_url.rsplit(":", 1)[1])
            with patch.object(bundler_server.socket, "getaddrinfo", side_effect=resolve_mock):
                for target in ("npm.corp.internal:8443", "artifactory.example.com:443", "npm.corp.internal:443"):
                    with socket.create_connection(("127.0.0.1", pport), timeout=5) as sock:
                        sock.sendall(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
                        resp = sock.recv(1024).decode()
                        self.assertTrue(resp.startswith("HTTP/1.1 403"), (target, resp))

        # Bundler HTTP RPC forwards registries and surfaces redacted error output.
        srv = ThreadingHTTPServer(("127.0.0.1", 0), bundler_server.BundlerHandler)
        bport = srv.server_port
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        fake_eszip = b"ESZIP2.3\x00\x00\x00\x04priv"
        seen: list[list[dict]] = []
        try:
            with patch.dict(os.environ, {"EDGE_BUNDLER_HMAC_SECRET": "test-secret", "EDGE_BUNDLER_URL": f"http://127.0.0.1:{bport}"}):
                files = [{"name": "index.ts", "content": 'import x from "npm:@corp/pkg@1.0.0"; Deno.serve(() => new Response(String(x)));'}]

                def fake_compile(f, registries=None):
                    seen.append(list(registries or []))
                    return fake_eszip

                with patch.object(bundler_server, "compile_function_eszip", side_effect=fake_compile):
                    out = asyncio.run(edge_bundler.bundle_function_eszip(files, registries=[regs[0]]))
                self.assertEqual(out, fake_eszip)
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0][0]["registry_url"], "https://npm.corp.internal:8443/npm/")
                self.assertEqual(seen[0][0]["token"], "synthetic-npm-token")
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=2)

    def test_bundler_fails_closed_without_shared_secret(self) -> None:
        import asyncio

        srv = ThreadingHTTPServer(("127.0.0.1", 0), bundler_server.BundlerHandler)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {"EDGE_BUNDLER_HMAC_SECRET": "", "EDGE_BUNDLER_URL": f"http://127.0.0.1:{srv.server_port}"}):
                self.assertFalse(bundler_server._verify_hmac(b"{}", str(int(time.time())), "0" * 64, ""))
                with patch.object(bundler_server, "compile_function_eszip", side_effect=AssertionError("unauthenticated bundle")):
                    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
                    conn.request("POST", "/bundle", body=b'{"files":[{"name":"index.ts","content":"x"}]}', headers={"Content-Type": "application/json"})
                    self.assertEqual(conn.getresponse().status, 503)
                    conn.close()
                files = [{"name": "index.ts", "content": 'import ms from "npm:ms@2.1.3"; Deno.serve(() => new Response(""));'}]
                with patch.object(edge_bundler.httpx, "AsyncClient", side_effect=AssertionError("network used without secret")):
                    with self.assertRaisesRegex(edge_bundler.BundleBuildError, "EDGE_BUNDLER_HMAC_SECRET"):
                        asyncio.run(edge_bundler.bundle_function_eszip(files))
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
