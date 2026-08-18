from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class LogflareInternalHardeningContractTest(unittest.TestCase):
    def test_studio_server_signs_only_internal_analytics(self) -> None:
        hook = (ROOT / "studio/studio-slug/logflare-hmac-hook.cjs").read_text(
            encoding="utf-8"
        )
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        dockerfile = (ROOT / "studio/studio-slug/Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn("const SERVICE = 'studio-server'", hook)
        self.assertIn("STUDIO_ANALYTICS_HMAC_SECRET", hook)
        self.assertIn("crypto.createHmac('sha256'", hook)
        self.assertIn("headers.delete(name)", hook)
        self.assertIn("'authorization'", hook)
        self.assertIn("'x-api-key'", hook)
        self.assertIn("'cookie'", hook)
        self.assertIn("STUDIO_ANALYTICS_HMAC_SECRET:", compose)
        self.assertIn(
            'LOGFLARE_PRIVATE_ACCESS_TOKEN: "internal-proxy-authenticated"',
            compose,
        )
        self.assertIn("--require=/usr/local/lib/studio-logflare-hmac.cjs", compose)
        self.assertIn(
            "COPY logflare-hmac-hook.cjs /usr/local/lib/studio-logflare-hmac.cjs",
            dockerfile,
        )

    def test_gateway_verifies_before_resigning(self) -> None:
        upload_guard = (
            ROOT / "studio/nginx/lua/security/upload_route_guard.lua"
        ).read_text(encoding="utf-8")
        ingress_guard = (
            ROOT / "studio/nginx/lua/security/logflare_internal_guard.lua"
        ).read_text(encoding="utf-8")
        signer = (
            ROOT / "studio/nginx/lua/security/projects_api_signer.lua"
        ).read_text(encoding="utf-8")

        verify_at = upload_guard.index("logflare_internal_guard.check()")
        sign_at = upload_guard.index("projects_api_signer.maybe_sign()")
        self.assertLess(verify_at, sign_at)
        self.assertIn('SERVICE = "studio-server"', ingress_guard)
        self.assertIn("internal_hmac.verify_current_request(", ingress_guard)
        self.assertIn('ngx.req.clear_header(name)', ingress_guard)
        self.assertIn('"Authorization"', ingress_guard)
        self.assertIn('"X-API-KEY"', ingress_guard)
        self.assertIn('"Cookie"', ingress_guard)
        self.assertIn('"X-User-Token"', ingress_guard)
        self.assertIn('"/_internal/logflare/', signer)
        self.assertIn('"/api/internal/analytics/', signer)

    def test_nginx_proxy_never_forwards_caller_credentials(self) -> None:
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        start = nginx.index("location ~ ^/_internal/logflare/")
        end = nginx.index("location ~* ^/api/platform/projects/ {", start)
        block = nginx[start:end]

        self.assertIn("client_max_body_size 256k", block)
        self.assertIn('proxy_set_header Authorization ""', block)
        self.assertIn('proxy_set_header X-API-KEY ""', block)
        self.assertIn('proxy_set_header Cookie ""', block)
        self.assertNotIn("$http_authorization", block)
        self.assertNotIn("$http_x_api_key", block)

    def test_ingress_has_explicit_allowlist_and_limits(self) -> None:
        guard = (
            ROOT / "studio/nginx/lua/security/logflare_internal_guard.lua"
        ).read_text(encoding="utf-8")
        for expected in (
            'path == "api/backends"',
            'path == "api/sources"',
            'path == "api/rules"',
            '^api/endpoints/query/',
            '^api/backends/',
            "MAX_BODY_BYTES = 256 * 1024",
            "MAX_QUERY_BYTES = 16 * 1024",
            "MAX_HEADER_BYTES = 16 * 1024",
            "MAX_HEADERS = 64",
            "Transfer-Encoding",
            "Content-Length is required",
            "application/json",
        ):
            self.assertIn(expected, guard)

    def test_projects_api_uses_gateway_identity_not_caller_logflare_token(self) -> None:
        internal = (
            ROOT / "servidor/api-internal/app/routers/internal.py"
        ).read_text(encoding="utf-8")
        start = internal.index('"/api/internal/analytics/{analytics_path:path}"')
        end = internal.index('@router.post("/api/projects/internal/users/sync")')
        block = internal[start:end]

        self.assertIn('internal_service", None) != "studio-gateway"', block)
        self.assertIn("_analytics_allowed_methods", block)
        self.assertIn('"x-api-key": LOGFLARE_PRIVATE_ACCESS_TOKEN', block)
        self.assertNotIn('request.headers.get("x-api-key")', block)
        self.assertNotIn('request.headers.get("authorization")', block)
        self.assertIn("256 * 1024", block)
        self.assertIn("16 * 1024", block)

    def test_new_secret_is_explicit_and_migratable(self) -> None:
        env_example = (ROOT / "studio/.env.example").read_text(encoding="utf-8")
        entrypoint = (ROOT / "studio/nginx/docker-entrypoint.sh").read_text(
            encoding="utf-8"
        )
        configurator = (ROOT / "tools/configure_studio_runtime.py").read_text(
            encoding="utf-8"
        )
        migration = (ROOT / "tools/migrate_studio_analytics_hmac.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("STUDIO_ANALYTICS_HMAC_SECRET=", env_example)
        self.assertIn("migrate_studio_analytics_hmac.py", entrypoint)
        self.assertIn("STUDIO_ANALYTICS_HMAC_KEY", configurator)
        self.assertIn("secrets.token_hex(32)", configurator)
        self.assertIn(".pre-studio-analytics-hmac", migration)
        self.assertIn("--dry-run", migration)


if __name__ == "__main__":
    unittest.main()
