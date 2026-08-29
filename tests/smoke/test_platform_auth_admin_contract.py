from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
API = ROOT / "servidor" / "api-internal" / "app"
LUA = ROOT / "studio" / "nginx" / "lua"


class AuthAdminProxyContract(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (API / "routers" / "platform_auth.py").read_text(
            encoding="utf-8"
        )

    def test_route_proxies_to_the_tenant_gotrue(self) -> None:
        self.assertIn(
            "/api/projects/internal/auth-admin/{project_name}/{gotrue_path:path}",
            self.source,
        )
        self.assertIn(
            'f"http://supabase-auth-{project_name}:"\n        f"{GOTRUE_INTERNAL_PORT}/',
            self.source,
        )
        self.assertIn("GOTRUE_INTERNAL_PORT = 9999", self.source)

    def test_internal_url_strips_the_public_auth_prefix(self) -> None:
        self.assertIn('GOTRUE_PUBLIC_PREFIX = "auth/v1/"', self.source)
        self.assertIn(
            "if internal_path.startswith(GOTRUE_PUBLIC_PREFIX):",
            self.source,
        )

    def test_proxy_uses_the_project_service_key(self) -> None:
        self.assertIn("SERVICE_ROLE_KEY_PROJETO", self.source)
        self.assertIn('headers["Authorization"] = f"Bearer {service_key}"', self.source)
        self.assertIn('headers["apikey"] = service_key', self.source)

    def test_proxy_never_forwards_internal_hmac_headers(self) -> None:
        for header in (
            "x-internal-signature",
            "x-internal-nonce",
            "x-internal-service",
            "x-internal-timestamp",
            "x-internal-version",
        ):
            with self.subTest(header=header):
                self.assertIn(f'"{header}"', self.source)

    def test_only_gotrue_admin_paths_are_allowed(self) -> None:
        self.assertIn('"auth/v1/admin/"', self.source)
        for path in ("auth/v1/invite", "auth/v1/recover", "auth/v1/otp"):
            with self.subTest(path=path):
                self.assertIn(f'"{path}"', self.source)

    def test_router_is_mounted_without_growing_the_monolith(self) -> None:
        main = (API / "main.py").read_text(encoding="utf-8")
        self.assertIn("from app.routers.platform_auth import router as platform_auth_router", main)
        self.assertIn("app.include_router(platform_auth_router)", main)
        self.assertLess(len(main.splitlines()), 5_000)


class StudioAuthLuaContract(unittest.TestCase):
    def setUp(self) -> None:
        self.lua = (LUA / "proxy_rewrites/auth.lua").read_text(encoding="utf-8")

    def test_signs_the_internal_route_with_the_gateway_hmac(self) -> None:
        self.assertIn("internal_hmac.apply_current_request", self.lua)
        self.assertIn("STUDIO_GATEWAY_HMAC_SECRET", self.lua)
        self.assertIn('"/api/projects/internal/auth-admin/"', self.lua)

    def test_rewritten_uri_keeps_the_leading_slash(self) -> None:
        self.assertIn('ngx.req.set_uri("/" .. gotrue_path, false)', self.lua)

    def test_signature_covers_path_and_query(self) -> None:
        self.assertIn("ngx.var.is_args", self.lua)
        self.assertIn("ngx.var.args", self.lua)

    def test_targets_the_projects_api_not_the_data_plane(self) -> None:
        self.assertIn(
            'ngx.var.server_path = server_domain .. "/api/projects/internal/auth-admin/" .. context.ref',
            self.lua,
        )

    def test_get_users_list_and_detail_are_supported(self) -> None:
        self.assertIn('method == "GET" and relative_path == "users"', self.lua)
        self.assertIn('method == "GET" and user_id', self.lua)
        self.assertIn('gotrue_path = "auth/v1/admin/users/" .. user_id', self.lua)

    def test_membership_gate_still_runs_before_anything_else(self) -> None:
        self.assertLess(
            self.lua.index('require("security.project_access").enforce'),
            self.lua.index("internal_hmac.apply_current_request"),
        )

    def test_service_key_is_still_injected(self) -> None:
        self.assertLess(
            self.lua.index("get_service_key(context.ref)"),
            self.lua.index("internal_hmac.apply_current_request"),
        )


class UsersListingReaderContract(unittest.TestCase):
    def setUp(self) -> None:
        self.main = (API / "main.py").read_text(encoding="utf-8")
        self.router = (API / "routers" / "platform_auth.py").read_text(
            encoding="utf-8"
        )

    def test_users_keyed_meta_queries_use_the_reader_dsn(self) -> None:
        connections = (API / "meta_connections.py").read_text(encoding="utf-8")
        self.assertIn("def get_project_reader_connection_string(", connections)
        reader_body = connections.split(
            "def get_project_reader_connection_string(", 1
        )[1].split("\ndef ", 1)[0]
        self.assertIn("platform_reader", reader_body)
        self.assertIn("PLATFORM_READER_DB_PASSWORD", reader_body)
        self.assertNotIn("meta_guest", reader_body)
        self.assertIn('meta_key.startswith("users")', self.main)
        self.assertIn("get_project_reader_connection_string(ref)", self.main)

    def test_dedicated_users_route_reads_via_platform_reader(self) -> None:
        self.assertIn("/api/projects/internal/auth-users/{project_name}", self.router)
        self.assertIn("FROM auth.users", self.router)
        self.assertIn('"platform_reader"', self.router)
        self.assertIn("ensure_project_admin_access", self.router)

    def test_meta_guest_trap_is_untouched(self) -> None:
        compose = (ROOT / "servidor" / "docker-compose-api.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("meta_trap", compose)
        self.assertIn("META_GUEST_PASSWORD", compose)


if __name__ == "__main__":
    unittest.main()
