from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


class PushWorkerResilienceContractTest(unittest.TestCase):
    def test_worker_has_durable_claims_retries_and_delivery_state(self) -> None:
        worker = read("servidor/api-internal/app/push_worker.py")

        for fragment in (
            "notification_deliveries",
            "PUSH_MAX_ATTEMPTS",
            "PUSH_NOTIFICATION_LEASE_SECONDS",
            "status = 'processando'",
            "FOR UPDATE SKIP LOCKED",
            "idempotency_key",
            "response.close()",
            "PUSH_MAX_TENANT_CONNECTIONS",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, worker)

        self.assertIn("notification resilience schema is missing", worker)
        self.assertNotIn("await asyncio.sleep(3600)", worker)

    def test_gateway_caches_success_and_bounds_outbound_requests(self) -> None:
        lua = read("studio/nginx/lua/send_push.lua")
        nginx = read("studio/nginx/nginx.conf")

        self.assertIn("push_idempotency", lua)
        self.assertIn("PUSH_IDEMPOTENCY_TTL_SECONDS", lua)
        self.assertIn("httpc:set_timeouts", lua)
        self.assertIn("lua_shared_dict push_idempotency", nginx)
        self.assertIn("lua_shared_dict push_oauth_tokens", nginx)

    def test_compose_exposes_resilience_controls_and_hardening(self) -> None:
        compose = read("servidor/docker-compose-api.yml")

        for fragment in (
            "PUSH_MAX_ATTEMPTS",
            "PUSH_NOTIFICATION_LEASE_SECONDS",
            "PUSH_MAX_TENANT_CONNECTIONS",
            "read_only: true",
            "no-new-privileges:true",
        ):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, compose)


if __name__ == "__main__":
    unittest.main()
