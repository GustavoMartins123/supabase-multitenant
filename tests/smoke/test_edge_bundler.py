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
