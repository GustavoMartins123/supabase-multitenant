from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
LUA = ROOT / "studio" / "nginx" / "lua"


class StudioSlugContextContractTest(unittest.TestCase):
    def test_flutter_opens_the_real_project_path_without_setting_a_cookie(self) -> None:
        project_list = (ROOT / "studio/seletor_de_projetos/lib/project_list_page.dart").read_text(
            encoding="utf-8"
        )
        admin = (ROOT / "studio/seletor_de_projetos/lib/userProjectsAdminScreen.dart").read_text(
            encoding="utf-8"
        )
        settings = (
            ROOT
            / "studio/seletor_de_projetos/lib/widgets/project_settings/env_settings_section.dart"
        ).read_text(encoding="utf-8")

        for source in (project_list, admin):
            self.assertRegex(source, r"/project/\$(?:ref|refKey)")
            self.assertNotIn("/project/default", source)
            self.assertNotIn("/set-project", source)
        self.assertNotIn("/set-project", settings)

    def test_slug_resolver_prefers_path_and_uses_only_same_origin_referer(self) -> None:
        resolver = (LUA / "project_context/project_ref_resolver.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn('STUDIO_PROJECT_CONTEXT_MODE") or "slug"', resolver)
        self.assertIn('"^/project/([^/]+)"', resolver)
        self.assertIn('"^/api/platform/projects/([^/]+)"', resolver)
        self.assertIn("ref_from_same_origin_referer", resolver)
        self.assertIn("scheme:lower() ~= request_scheme", resolver)
        self.assertIn("authority:lower() ~= request_authority:lower()", resolver)
        self.assertIn("local path_ref, has_path_ref = ref_from_path", resolver)
        self.assertIn('return path_ref or "default"', resolver)
        slug_branch = resolver.split('if context_mode == "slug" then', 1)[1].split(
            'if context_mode == "hybrid" then', 1
        )[0]
        self.assertNotIn("resolve_cookie()", slug_branch)
        hybrid_branch = resolver.split('if context_mode == "hybrid" then', 1)[1].split(
            "return resolve_cookie()\nend", 1
        )[0]
        self.assertIn('raw_path_ref == "default"', hybrid_branch)
        self.assertIn("return resolve_cookie()", hybrid_branch)

    def test_internal_context_authorizes_membership_and_never_returns_service_role(self) -> None:
        internal = (API_ROOT / "app/routers/internal.py").read_text(encoding="utf-8")
        start = internal.index("async def get_studio_project_context(")
        end = internal.index('@router.get("/api/projects/internal/enc-key/', start)
        endpoint = internal[start:end]

        self.assertIn("resolve_authenticated_user(request, pool)", endpoint)
        self.assertIn("ensure_project_member_access(", endpoint)
        self.assertIn('column="anon_key"', endpoint)
        self.assertIn('"tenant_uuid"', endpoint)
        self.assertIn('"file_size_limit"', endpoint)
        self.assertNotIn("service_role", endpoint)

    def test_service_role_is_loaded_only_after_the_membership_gate(self) -> None:
        for name in (
            "inject_service_key.lua",
            "inject_service_key_apikey.lua",
            "inject_service_key_storage.lua",
            "inject_service_key_graphql.lua",
        ):
            with self.subTest(name=name):
                source = (LUA / "security" / name).read_text(encoding="utf-8")
                self.assertLess(
                    source.index('require("security.project_access").enforce'),
                    source.index('require("security.get_service_key")'),
                )

    def test_browser_compatibility_responses_expose_only_the_anon_key(self) -> None:
        response = (LUA / "studio_compat/project_context_response.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn("context.anon_key", response)
        self.assertIn('jwt_secret = ""', response)
        self.assertIn('serviceApiKey = ""', response)
        self.assertNotIn("context.service_role", response)

    def test_ai_and_unscoped_s3_are_bound_to_the_tab_context(self) -> None:
        sql_ai = (LUA / "api/ai_sql_generate_handler.lua").read_text(encoding="utf-8")
        code_ai = (LUA / "api/ai_code_complete_handler.lua").read_text(encoding="utf-8")
        upload_guard = (LUA / "security/upload_route_guard.lua").read_text(encoding="utf-8")

        self.assertIn("studio_request.projectRef", sql_ai)
        self.assertIn("project_access", sql_ai)
        self.assertIn("if requested_ref ~= nil", sql_ai)
        self.assertIn("requested_ref ~= tab_ref", sql_ai)
        self.assertIn("request.projectRef", code_ai)
        self.assertIn("project_access", code_ai)
        self.assertIn("if requested_ref ~= nil", code_ai)
        self.assertIn("requested_ref ~= tab_ref", code_ai)
        self.assertIn('uri == "/api/get-s3-keys"', upload_guard)
        self.assertIn("project_ref_resolver", upload_guard)

    def test_ai_chat_history_is_namespaced_and_does_not_use_a_global_cookie(self) -> None:
        handler = (LUA / "api/ai_sql_generate_handler.lua").read_text(encoding="utf-8")
        generator = (LUA / "ai_sql_generate.lua").read_text(encoding="utf-8")
        schema = (ROOT / "studio/postgres/init.sql").read_text(encoding="utf-8")
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")

        self.assertIn('user_id .. ":" .. project_ref .. ":" .. client_chat_id', handler)
        self.assertIn("studio_request.chatId = session_hash", handler)
        self.assertIn("local session_id = studio_request.chatId", generator)
        self.assertNotIn("cookie_ai_chat_session", generator)
        self.assertIn("AND user_id = p_user_id", schema)
        self.assertIn("AND project_ref = p_project_ref", schema)
        self.assertIn("ON CONFLICT (id) DO NOTHING", schema)
        self.assertIn("ai_chat_session=; Path=/; HttpOnly; Secure;", nginx)

    def test_studio_image_remains_pinned_while_gateway_supplies_dynamic_context(self) -> None:
        env = (ROOT / "studio/.env.example").read_text(encoding="utf-8")
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        gateway_dockerfile = (ROOT / "studio/Dockerfile").read_text(encoding="utf-8")

        self.assertIn("supabase/studio:2026.06.29-sha-20290c7", env)
        self.assertIn("image: ${STUDIO_IMAGE}", compose)
        self.assertIn("studio_compat/project_context_response.lua", nginx)
        self.assertIn("STUDIO_PROJECT_CONTEXT_MODE=slug", env)
        self.assertIn("COPY nginx/lua/ /usr/local/openresty/lualib/", gateway_dockerfile)

    def test_nginx_gates_dynamic_routes_before_generic_fallbacks(self) -> None:
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")

        detail = nginx.index(
            'location ~ "^/api/platform/projects/[a-z_][a-z0-9_]{2,39}/?$"'
        )
        generic_platform = nginx.index("location ~* ^/api/platform/projects/ {")
        api_keys = nginx.index(
            'location ~ "^/api/v1/projects/[a-z_][a-z0-9_]{2,39}/api-keys'
        )
        generic_v1 = nginx.index("location ~ ^/api/v1/projects/ {")
        self.assertLess(detail, generic_platform)
        self.assertLess(api_keys, generic_v1)

        run_lints_start = nginx.index("/run-lints$")
        run_lints_end = nginx.index("}", run_lints_start)
        run_lints = nginx[run_lints_start:run_lints_end]
        self.assertIn("studio_project_access.lua", run_lints)
        self.assertIn("return_empty_json.lua", run_lints)

        mcp_start = nginx.index("location = /api/mcp")
        mcp_end = nginx.index("}", mcp_start)
        mcp = nginx[mcp_start:mcp_end]
        self.assertIn("studio_project_access.lua", mcp)
        self.assertIn("mcp_disabled.lua", mcp)

    def test_privileged_routes_fail_closed_without_a_project_ref_or_service_key(self) -> None:
        for relative in (
            "proxy_rewrites/auth.lua",
            "security/inject_service_key.lua",
            "security/inject_service_key_storage.lua",
            "security/inject_service_key_graphql.lua",
            "security/pg_meta_access.lua",
        ):
            with self.subTest(relative=relative):
                source = (LUA / relative).read_text(encoding="utf-8")
                gate = source.index('require("security.project_access").enforce')
                key = source.index('require("security.get_service_key")')
                unavailable = source.index("project_service_unavailable")
                self.assertLess(gate, key)
                self.assertLess(key, unavailable)


class ProjectFileSizeLimitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(API_ROOT))
        from app.project_settings import get_project_file_size_limit

        cls.get_limit = staticmethod(get_project_file_size_limit)

    def test_limit_is_read_server_side_and_has_a_safe_default(self) -> None:
        root = pathlib.Path("/projects")
        with mock.patch(
            "app.project_settings.dotenv_values",
            return_value={"FILE_SIZE_LIMIT": "123456"},
        ) as dotenv_values:
            self.assertEqual(
                self.get_limit("alpha", projects_root=root),
                "123456",
            )
            dotenv_values.assert_called_once_with(root / "alpha" / ".env")

        with mock.patch(
            "app.project_settings.dotenv_values",
            side_effect=OSError("missing"),
        ):
            self.assertEqual(
                self.get_limit("missing", projects_root=root),
                "524288000",
            )


if __name__ == "__main__":
    unittest.main()
