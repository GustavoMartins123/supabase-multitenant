"""Unit and contract tests for Phase 0 infrastructure security hardening (SEC-03 & SEC-05)."""
from __future__ import annotations

import ast
import os
import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / "servidor"


class Phase0InfraSecuritySmokeTests(unittest.TestCase):
    def test_sec03_realtime_admin_requires_global_api_jwt_secret(self) -> None:
        router = (SERVER_ROOT / "volumes/realtime/router.ex").read_text(encoding="utf-8")
        for removed in (
            "tenant_auth_context",
            "tenant_context_from_existing_tenant",
            "tenant_context_from_payload",
            "validate_tenant_claims",
            "Realtime.Crypto",
        ):
            self.assertNotIn(removed, router)
        self.assertIn("authorize_any(token, secrets)", router)

        # Deletion control-plane helper must sign Realtime admin JWT with global JWT_SECRET.
        source = (SERVER_ROOT / "api-internal/app/project_deletion.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "build_realtime_delete_token")
        fn_src = ast.get_source_segment(source, fn) or ""
        self.assertIn('build_global_delete_token("supabase")', fn_src)

        import base64
        fernet_key = base64.urlsafe_b64encode(b"a" * 32).decode("ascii")
        fernet_key2 = base64.urlsafe_b64encode(b"b" * 32).decode("ascii")
        isolated_env = {
            **os.environ,
            "DB_DSN": "postgres://u:p@127.0.0.1:5432/db",
            "META_ADMIN_DSN": "postgres://u:p@127.0.0.1:5432/db",
            "PROJECT_SECRETS_MASTER_KEY": fernet_key,
            "PG_META_CRYPTO_KEY": "pgmeta-test-key",
            "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": fernet_key2,
            "NGINX_HMAC_SECRET": "nginx-hmac-secret",
            "STUDIO_GATEWAY_HMAC_SECRET": "studio-gateway-hmac",
            "PROJECTS_API_HMAC_SECRET": "projects-api-hmac",
            "LOGFLARE_PRIVATE_ACCESS_TOKEN": "logflare-token",
            "HOST_AGENT_HMAC_SECRET": "host-agent-hmac",
            "JWT_SECRET": "global-secret-for-realtime-admin",
            "PROJECTS_DIR": "/tmp/nonexistent",
            "DOCKER_SCRIPTS_DIR": "/tmp/nonexistent",
            "PYTHONPATH": str(SERVER_ROOT / "api-internal"),
        }
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import hmac, hashlib, base64; from app import project_deletion; "
                "tok = project_deletion.build_realtime_delete_token({'PROJECT_UUID': 'u1', 'ANON_KEY_PROJETO': 'tenant-anon'}); "
                "assert tok != 'tenant-anon'; "
                "h, b, sig = tok.split('.'); "
                "exp = base64.urlsafe_b64encode(hmac.new(b'global-secret-for-realtime-admin', f'{h}.{b}'.encode(), hashlib.sha256).digest()).rstrip(b'=').decode(); "
                "assert hmac.compare_digest(sig, exp)",
            ],
            env=isolated_env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

        for rel in (
            "generateProject/lib/generate_project_impl.sh",
            "generateProject/lib/duplicate_project_impl.sh",
            "generateProject/lib/restore_project_impl.sh",
        ):
            text = (SERVER_ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn('realtime-dev.supabase-realtime POST "/api/tenants/$PROJECT_UUID/shutdown" "$ANON_KEY_PROJETO"', text)

    def test_sec05_pg_net_revoked_and_imgproxy_signed_and_isolated(self) -> None:
        webhooks = (SERVER_ROOT / "volumes/db/webhooks.sql").read_text(encoding="utf-8")
        self.assertIn("REVOKE ALL ON SCHEMA net FROM PUBLIC, anon, authenticated;", webhooks)
        self.assertIn("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA net FROM PUBLIC, anon, authenticated;", webhooks)
        self.assertIn("REVOKE ALL ON FUNCTION supabase_functions.http_request() FROM PUBLIC, anon, authenticated;", webhooks)
        self.assertNotIn("GRANT EXECUTE ON FUNCTION net.http_get(url text, params jsonb, headers jsonb, timeout_milliseconds integer) TO supabase_functions_admin, postgres, anon", webhooks)
        self.assertNotIn("GRANT EXECUTE ON FUNCTION supabase_functions.http_request() TO postgres, anon", webhooks)

        compose = (SERVER_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        imgproxy_block = compose.split("\n  imgproxy:", 1)[1].split("\n  storage-data-plane:", 1)[0]
        self.assertIn("imgproxy-internal", imgproxy_block)
        self.assertNotIn("storage-control", imgproxy_block)
        self.assertIn("IMGPROXY_KEY:", imgproxy_block)
        self.assertIn("IMGPROXY_SALT:", imgproxy_block)
        self.assertIn("IMGPROXY_ALLOWED_SOURCES:", imgproxy_block)

        storage_block = compose.split("\n  storage:", 1)[1].split("\n  imgproxy:", 1)[0]
        self.assertIn("--require /etc/storage/imgproxy-signer.cjs", storage_block)
        self.assertIn("./volumes/storage-proxy/imgproxy-signer.cjs:/etc/storage/imgproxy-signer.cjs:ro,z", storage_block)
        self.assertIn("imgproxy-internal", storage_block)

        signer = SERVER_ROOT / "volumes/storage-proxy/imgproxy-signer.cjs"
        script = """
const assert = require("node:assert/strict");
const s = require(process.argv[1]);
const env = {
  IMGPROXY_URL: "http://imgproxy:5001",
  IMGPROXY_KEY: "11".repeat(32),
  IMGPROXY_SALT: "22".repeat(32),
  IMGPROXY_LOCAL_FILESYSTEM_ROOT: "/var/lib/storage",
};
const rebased = s.signImgproxyUrl("http://imgproxy:5001/public/width:50/plain/local:////var/lib/storage/objects/t1/b1/a.png", env);
assert.ok(rebased.endsWith("/width:50/plain/local:///objects/t1/b1/a.png"));
assert.ok(s.signImgproxyUrl("http://imgproxy:5001/public/width:50/plain/local:////var/lib/storage/objects/t1/b1/100%off.png", env).endsWith("/100%off.png"));
for (const bad of [
  "http://imgproxy:5001/public/width:50/plain/local:////etc/passwd",
  "http://imgproxy:5001/public/width:50/plain/local:////var/lib/storage/../../etc/passwd",
  "http://imgproxy:5001/public/width:50/plain/local:////var/lib/storage/%2e%2e/etc/passwd",
]) {
  assert.throws(() => s.signImgproxyUrl(bad, env));
}
"""
        subprocess.run(["node", "-e", script, str(signer)], check=True)


if __name__ == "__main__":
    unittest.main()
