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

    def test_cache_uses_versions_metrics_and_configurable_ttls(self):
        source = (LUA / "security" / "get_service_key.lua").read_text(
            encoding="utf-8"
        )
        for contract in {
            "SERVICE_KEY_CACHE_TTL_SECONDS",
            "SERVICE_KEY_VERSION_CHECK_TTL_SECONDS",
            "project_key_version",
            'increment_metric("hit")',
            'increment_metric("miss")',
            'increment_metric("version_reload")',
        }:
            self.assertIn(contract, source)

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


if __name__ == "__main__":
    unittest.main()
