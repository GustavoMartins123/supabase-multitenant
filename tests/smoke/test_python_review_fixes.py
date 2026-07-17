"""Regressões dos achados registrados em issues-review-python.md."""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
API_APP = ROOT / "servidor" / "api-internal" / "app"


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class InternalTlsHardeningTest(unittest.TestCase):
    def test_python_integrations_verify_the_internal_ca_by_default(self) -> None:
        runtime = read("servidor/api-internal/app/runtime_config.py")
        worker = read("servidor/api-internal/app/push_worker.py")
        cache_client = read("servidor/api-internal/app/service_key_cache.py")
        snippets_client = read("servidor/api-internal/app/snippets_migration.py")

        self.assertIn('"STUDIO_CACHE_INVALIDATION_VERIFY_TLS", "true"', runtime)
        self.assertIn('"/docker/push-certs/ca.pem"', runtime)
        self.assertIn("context.check_hostname = False", runtime)
        self.assertIn("verify=build_studio_cache_ssl_context()", cache_client)
        self.assertIn("verify=build_studio_cache_ssl_context()", snippets_client)

        self.assertIn('os.getenv("PUSH_VERIFY_TLS", "true")', worker)
        self.assertIn("ssl.create_default_context(cafile=PUSH_CA_FILE)", worker)
        self.assertNotIn("ssl._create_unverified_context", worker)

    def test_openresty_service_key_client_verifies_tls_by_default(self) -> None:
        nginx = read("studio/nginx/nginx.conf")
        lua = read("studio/nginx/lua/security/get_service_key.lua")
        self.assertIn("lua_ssl_trusted_certificate /config/ssl/ca.pem;", nginx)
        self.assertIn('os.getenv("SERVICE_KEY_VERIFY_TLS") or "true"', lua)
        self.assertIn("ssl_verify = verify_tls", lua)
        self.assertIn("ssl_server_name = hostname", lua)


class PushWorkerConfigurationTest(unittest.TestCase):
    def test_push_url_fails_fast_and_project_prefix_is_removed_once(self) -> None:
        worker = read("servidor/api-internal/app/push_worker.py")
        self.assertIn('API_URL = os.getenv("PUSH_API_URL")', worker)
        self.assertIn("Missing PUSH_API_URL environment variable", worker)
        self.assertNotIn("<SEU_IP>:4000", worker)
        self.assertGreaterEqual(
            worker.count('removeprefix("_supabase_")'),
            2,
        )
        self.assertNotIn('replace("_supabase_", "")', worker)


class PublicErrorContractTest(unittest.TestCase):
    def test_internal_exception_details_are_not_persisted(self) -> None:
        main = read("servidor/api-internal/app/main.py")
        agent = read("servidor/host-agent/hostagent/agent.py")

        forbidden = (
            "message=str(exc)",
            "str(exc)[:2000]",
            'error=str(exc)',
            '"exception": str(exc)',
            'message=f"Falha inesperada',
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, main)
        self.assertNotIn('message=f"Falha interna do host-agent: {exc}"', agent)


class SignedContractHardeningTest(unittest.TestCase):
    def test_host_agent_revalidates_intent_age(self) -> None:
        agent = read("servidor/host-agent/hostagent/agent.py")
        protocol = read("servidor/api-internal/app/host_agent_protocol.py")
        self.assertIn("MAX_INTENT_AGE_SECONDS = 24 * 60 * 60", protocol)
        self.assertIn('intent_is_expired(record["issued_at"])', agent)
        self.assertIn('"intent_expired"', agent)

    def test_push_v2_signs_the_query_string_on_both_sides(self) -> None:
        signer = read("servidor/api-internal/app/internal_hmac.py")
        verifier = read("studio/nginx/lua/security/check_push_worker.lua")
        self.assertIn('"push-v2"', signer)
        self.assertIn("parsed.query", signer)
        self.assertIn('"push-v2"', verifier)
        self.assertIn("ngx.var.request_uri", verifier)
        self.assertNotIn('"push-v1"', signer)
        self.assertNotIn('"push-v1"', verifier)


class HealthAndRouterArchitectureTest(unittest.TestCase):
    def test_healthz_bypasses_auth_and_is_used_by_compose(self) -> None:
        main = read("servidor/api-internal/app/main.py")
        health = read("servidor/api-internal/app/routers/health.py")
        compose = read("servidor/docker-compose-api.yml")
        self.assertIn('@router.get("/healthz"', health)
        self.assertIn('request.url.path == "/healthz"', main)
        self.assertIn("127.0.0.1:18000/healthz", compose)

    def test_large_domains_use_dedicated_routers_and_dependencies(self) -> None:
        main = read("servidor/api-internal/app/main.py")
        collaboration = read(
            "servidor/api-internal/app/routers/collaboration.py"
        )
        internal = read("servidor/api-internal/app/routers/internal.py")
        lifecycle = read("servidor/api-internal/app/routers/lifecycle.py")
        dependencies = read("servidor/api-internal/app/dependencies.py")

        self.assertIn('APIRouter(tags=["collaboration"])', collaboration)
        self.assertIn('APIRouter(tags=["internal"])', internal)
        self.assertIn('APIRouter(tags=["lifecycle"])', lifecycle)
        self.assertIn("async def resolve_authenticated_user", dependencies)
        self.assertNotIn(
            '@app.get("/api/projects/{project_name}/collaboration")',
            main,
        )
        self.assertLess(len(main.splitlines()), 5_000)
        direct_routes = re.findall(
            r"^@app\.(?:get|post|put|patch|delete|api_route)",
            main,
            flags=re.MULTILINE,
        )
        self.assertLessEqual(len(direct_routes), 35)


if __name__ == "__main__":
    unittest.main()
