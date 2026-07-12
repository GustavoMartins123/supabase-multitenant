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

    def test_authenticated_requests_update_sampled_last_seen_only(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/main.py"
        ).read_text(encoding="utf-8")
        start = source.index("async def resolve_authenticated_user(")
        end = source.index("async def ensure_project_member_access(", start)
        block = source[start:end]
        self.assertIn("SET last_seen_at = now(), updated_at = now()", block)
        self.assertIn("last_seen_at < now() - interval '5 minutes'", block)
        self.assertNotIn("SET last_login_at = now()", block)

    def test_identity_schema_exposes_last_seen_at(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/database_schema.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ", source)
        self.assertIn("idx_users_last_seen_at", source)


if __name__ == "__main__":
    unittest.main()
