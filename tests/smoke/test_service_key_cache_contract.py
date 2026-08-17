import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal" / "app"
LUA = ROOT / "studio" / "nginx" / "lua"


class ServiceKeyCacheContractTest(unittest.TestCase):
    def test_rotation_versions_key_before_invalidating_cache(self):
        main = (APP / "main.py").read_text(encoding="utf-8")
        rotation = main[main.index("async def _rotate_project_key_background"):]
        store = rotation.index("await store_project_secrets")
        bump = rotation.index("SET project_key_version = project_key_version + 1")
        invalidate = rotation.index("await invalidate_service_key_cache")
        self.assertLess(store, bump)
        self.assertLess(bump, invalidate)

    def test_cache_requires_canonical_version_check_and_fails_closed(self):
        source = (LUA / "security" / "get_service_key.lua").read_text(
            encoding="utf-8"
        )
        for contract in {
            "SERVICE_KEY_CACHE_TTL_SECONDS",
            "project_key_version",
            'increment_metric("hit")',
            'increment_metric("miss")',
            'increment_metric("version_reload")',
            'return nil, "version_check_failed"',
            "Service key bloqueada por falha na verificacao de versao",
            "STUDIO_GATEWAY_HMAC_SECRET",
            '"studio-gateway"',
            "internal_hmac.sign_headers",
        }:
            self.assertIn(contract, source)
        self.assertNotIn("fallback_version", source)
        self.assertNotIn("checked_version", source)
        self.assertNotIn("SERVICE_KEY_VERSION_CHECK_TTL_SECONDS", source)
        self.assertNotIn('X-Shared-Token', source)

    def test_rotation_handler_does_not_invalidate_before_job_finishes(self):
        source = (LUA / "admin_api" / "project_rotate_key.lua").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("ngx.shared.service_keys:delete", source)

    def test_internal_invalidation_route_and_version_column_exist(self):
        nginx = (ROOT / "studio" / "nginx" / "nginx.conf").read_text(
            encoding="utf-8"
        )
        schema = (APP / "database_schema.py").read_text(encoding="utf-8")
        self.assertIn("/internal/cache/service-key/", nginx)
        self.assertIn("service_key_metrics", nginx)
        self.assertIn("project_key_version BIGINT", schema)

    def test_projects_api_to_studio_calls_use_service_hmac_not_shared_token(self):
        cache_client = (APP / "service_key_cache.py").read_text(encoding="utf-8")
        snippet_client = (APP / "snippets_migration.py").read_text(encoding="utf-8")
        for source in (cache_client, snippet_client):
            self.assertIn("PROJECTS_API_HMAC_SECRET", source)
            self.assertIn("build_internal_hmac_headers", source)
            self.assertIn('service="projects-api"', source)
            self.assertNotIn('"X-Shared-Token"', source)

        cache_handler = (LUA / "cache" / "invalidate_service_key.lua").read_text(
            encoding="utf-8"
        )
        snippet_handler = (LUA / "admin_api" / "snippets_rename.lua").read_text(
            encoding="utf-8"
        )
        for source in (cache_handler, snippet_handler):
            self.assertIn("PROJECTS_API_HMAC_SECRET", source)
            self.assertIn("verify_current_request", source)
            self.assertIn('"projects-api"', source)
            self.assertNotIn("security.shared_token", source)

    def test_studio_to_projects_api_has_outer_hmac_authentication(self):
        asgi = (APP / "asgi.py").read_text(encoding="utf-8")
        auth = (APP / "internal_service_auth.py").read_text(encoding="utf-8")
        signer = (LUA / "security" / "projects_api_signer.lua").read_text(
            encoding="utf-8"
        )
        upload_guard = (LUA / "security" / "upload_route_guard.lua").read_text(
            encoding="utf-8"
        )

        self.assertIn("InternalServiceAuthenticationMiddleware", asgi)
        self.assertIn("app.add_middleware", asgi)
        self.assertIn("X-Internal-Version", auth)
        self.assertIn("X-Internal-Caller", auth)
        self.assertIn("Replayed internal HMAC signature", auth)
        self.assertIn("INTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN", auth)
        self.assertIn('SERVICE = "studio-gateway"', signer)
        self.assertIn("clear_untrusted_internal_headers", signer)
        self.assertIn("projects_api_signer.maybe_sign", upload_guard)

    def test_direct_user_sync_is_hmac_authenticated(self):
        source = (LUA / "admin_api" / "user_sync.lua").read_text(
            encoding="utf-8"
        )
        self.assertIn("STUDIO_GATEWAY_HMAC_SECRET", source)
        self.assertIn("internal_hmac.sign_headers", source)
        self.assertIn('"studio-gateway"', source)
        self.assertNotIn("NGINX_SHARED_TOKEN", source)


if __name__ == "__main__":
    unittest.main()
