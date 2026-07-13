from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class GlobalAdminVisibilityContractTest(unittest.TestCase):
    def test_global_admin_listing_includes_other_global_admins(self) -> None:
        users_list = (
            ROOT / "studio" / "nginx" / "lua" / "admin_api" / "users_list.lua"
        ).read_text(encoding="utf-8")
        model = (
            ROOT
            / "studio"
            / "seletor_de_projetos"
            / "lib"
            / "models"
            / "user_models.dart"
        ).read_text(encoding="utf-8")
        page = (
            ROOT
            / "studio"
            / "seletor_de_projetos"
            / "lib"
            / "admin_users_page.dart"
        ).read_text(encoding="utf-8")

        self.assertNotIn("not user.is_admin", users_list)
        self.assertIn("is_admin = user.is_admin == true", users_list)
        self.assertIn("final bool isAdmin", model)
        self.assertIn("!user.isAdmin", page)


class SupabaseAnalyticsContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server_compose = (ROOT / "servidor" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.studio_compose = (ROOT / "studio" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.vector = (
            ROOT / "servidor" / "volumes" / "logs" / "vector.yml"
        ).read_text(encoding="utf-8")

    def test_analytics_uses_official_pinned_images_and_private_network(self) -> None:
        self.assertIn("image: supabase/logflare:1.43.1", self.server_compose)
        self.assertIn("image: timberio/vector:0.53.0-alpine", self.server_compose)
        analytics_block = self.server_compose.split("  analytics:", 1)[1].split(
            "\n  vector:", 1
        )[0]
        self.assertNotIn("ports:", analytics_block)
        self.assertIn('LOGFLARE_SINGLE_TENANT: "true"', analytics_block)
        self.assertIn('LOGFLARE_SUPABASE_MODE: "true"', analytics_block)
        self.assertIn("POSTGRES_BACKEND_SCHEMA: _analytics", analytics_block)

    def test_vector_forwards_supabase_sources_to_logflare(self) -> None:
        for source_name in {
            "gotrue.logs.prod",
            "postgREST.logs.prod",
            "storage.logs.prod.2",
            "realtime.logs.prod",
            "deno-relay-logs",
            "postgres.logs",
            "edge_logs",
        }:
            self.assertIn(f"source_name={source_name}", self.vector)
        self.assertNotIn("source_name=cloudflare.logs.prod", self.vector)
        self.assertIn("metadata.tenant_project", self.vector)
        self.assertNotIn("PG_URI", self.server_compose)

    def test_setup_generates_distinct_tokens_and_studio_is_admin_only(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        nginx = (ROOT / "studio" / "nginx" / "nginx.conf").read_text(
            encoding="utf-8"
        )
        self.assertIn("LOGFLARE_PUBLIC_ACCESS_TOKEN=$(generate_logflare_api_key)", setup)
        self.assertIn("LOGFLARE_PRIVATE_ACCESS_TOKEN=$(generate_logflare_api_key)", setup)
        self.assertIn(".analytics.env", self.server_compose)
        self.assertIn(".analytics.env", self.studio_compose)
        root_env = (ROOT / "servidor" / ".env.example").read_text(
            encoding="utf-8"
        )
        analytics_env = (
            ROOT / "servidor" / ".analytics.env.example"
        ).read_text(encoding="utf-8")
        self.assertNotIn("LOGFLARE_PRIVATE_ACCESS_TOKEN", root_env)
        self.assertIn("LOGFLARE_PUBLIC_ACCESS_TOKEN", analytics_env)
        self.assertIn("LOGFLARE_PRIVATE_ACCESS_TOKEN", analytics_env)
        self.assertIn("LOGFLARE_DB_ENCRYPTION_KEY", analytics_env)
        studio_root_env = (ROOT / "studio" / ".env.example").read_text(
            encoding="utf-8"
        )
        studio_analytics_env = (
            ROOT / "studio" / ".analytics.env.example"
        ).read_text(encoding="utf-8")
        self.assertNotIn("LOGFLARE_PRIVATE_ACCESS_TOKEN", studio_root_env)
        self.assertIn("LOGFLARE_PRIVATE_ACCESS_TOKEN", studio_analytics_env)
        self.assertIn("analytics-internal", self.server_compose)
        self.assertNotIn("analytics-internal", self.studio_compose)
        self.assertIn(
            "LOGFLARE_URL: https://nginx:443/_internal/logflare",
            self.studio_compose,
        )
        analytics_route = nginx.index(
            "^/api/platform/projects/[^/]+/analytics(?:/|$)"
        )
        generic_route = nginx.index("location ~* ^/api/platform/projects/ {")
        self.assertLess(analytics_route, generic_route)
        self.assertIn(
            "security/check_admin.lua",
            nginx[analytics_route:generic_route],
        )

    def test_legacy_direct_postgres_pipeline_is_not_wired(self) -> None:
        self.assertNotIn("vector_logs.sql", self.server_compose)
        self.assertFalse(
            (ROOT / "servidor" / "volumes" / "db" / "vector_logs.sql").exists()
        )


if __name__ == "__main__":
    unittest.main()
