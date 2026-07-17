from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StudioApiTransportAndActivityTests(unittest.TestCase):
    def test_studio_nginx_has_no_direct_projects_api_origin(self) -> None:
        root = ROOT / "studio/nginx"
        violations = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if "projects-api:18000" in source or "PROJECTS_API_INTERNAL_URL" in source:
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations)

    def test_user_sync_requires_server_domain_without_network_fallback(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_sync.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('local API_ORIGIN = (os.getenv("SERVER_DOMAIN") or "")', source)
        self.assertIn('return nil, "SERVER_DOMAIN ausente"', source)
        self.assertEqual(1, source.count("httpc:request_uri("))
        self.assertNotIn("for _, origin", source)

    def test_every_lua_api_client_requires_server_domain(self) -> None:
        root = ROOT / "studio/nginx/lua"
        violations = []
        for path in root.rglob("*.lua"):
            source = path.read_text(encoding="utf-8")
            if 'SERVER_DOMAIN") or "http://' in source:
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual([], violations)

        helper = (root / "cache/project_db_helper.lua").read_text(encoding="utf-8")
        self.assertIn('return {}, "SERVER_DOMAIN ausente"', helper)

    def test_authenticated_requests_distinguish_login_from_activity(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/dependencies.py"
        ).read_text(encoding="utf-8")
        start = source.index("async def resolve_authenticated_user(")
        end = source.index("async def get_user_record_by_identifier(", start)
        block = source[start:end]
        self.assertIn("SET last_seen_at = now(), updated_at = now()", block)
        self.assertIn("last_seen_at < now() - interval '5 minutes'", block)
        self.assertIn("SET last_login_at = now()", block)
        self.assertIn("last_login_session_hash IS DISTINCT FROM $2", block)
        self.assertIn('token_claims.get("login_session")', block)

    def test_identity_schema_exposes_last_seen_at(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/database_schema.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ", source)
        self.assertIn("ADD COLUMN IF NOT EXISTS last_login_session_hash TEXT", source)
        self.assertIn("idx_users_last_seen_at", source)

    def test_gateway_signs_authelia_session_fingerprint(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/project_context/user_context_headers.lua"
        ).read_text(encoding="utf-8")
        self.assertIn("ngx.var.cookie_authelia_session", source)
        self.assertIn('digest.new("sha256")', source)
        self.assertIn("sha256_bin(session_cookie)", source)
        self.assertIn("login_session = login_session_fingerprint()", source)


if __name__ == "__main__":
    unittest.main()
