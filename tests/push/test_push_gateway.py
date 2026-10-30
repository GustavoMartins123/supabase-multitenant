"""Real multi-worker OpenResty/TLS tests, using isolated mocked Google transport.
Run only with PUSH_TEST_GATEWAY=https://localhost:8443 and its ephemeral CA.
"""

import asyncio
import os
import json
import time
import sys
from pathlib import Path
import ssl
import unittest

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.internal_hmac import build_internal_hmac_headers


@unittest.skipUnless(
    os.getenv("PUSH_TEST_GATEWAY"), "requires isolated OpenResty test server"
)
class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.url = os.environ["PUSH_TEST_GATEWAY"]
        ctx = ssl.create_default_context(cafile=os.environ["PUSH_TEST_CA"])
        self.client = httpx.AsyncClient(verify=ctx, trust_env=False, timeout=10)
        await self.client.get(self.url + "/test/reset")

    async def asyncTearDown(self):
        await self.client.aclose()

    async def post(self, token="good", key="op", project="a", auth=True):
        url = self.url + "/api/internal/push"
        body = json.dumps(
            {
                "token": token,
                "body": "hello",
                "project": project,
                "idempotency_key": key,
            }
        ).encode()
        return await self.client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                **(
                    build_internal_hmac_headers(
                        "internal-test-secret", "POST", url, body
                    )
                    if auth
                    else {}
                ),
            },
        )

    async def state(self):
        return (await self.client.get(self.url + "/test/state")).json()

    async def test_auth_required(self):
        response = await self.post(auth=False)
        self.assertEqual(response.status_code, 401)
        self.assertEqual((await self.state())["fcm"], 0)
        url = self.url + "/api/internal/push"
        body = b"{}"
        headers = build_internal_hmac_headers("internal-test-secret", "POST", url, body)
        headers["X-Internal-Signature"] = "0" * 64
        response = await self.client.post(url, content=body, headers=headers)
        self.assertEqual(response.status_code, 403)

    async def test_tls_trusted_and_untrusted(self):
        self.assertEqual((await self.post()).status_code, 200)
        async with httpx.AsyncClient(trust_env=False) as untrusted:
            with self.assertRaises(httpx.ConnectError):
                await untrusted.get(self.url + "/test/state")

    async def test_duplicate_internal_auth_headers_rejected(self):
        url = self.url + "/api/internal/push"
        body = b"{}"
        headers = build_internal_hmac_headers("internal-test-secret", "POST", url, body)
        response = await self.client.post(
            url,
            content=body,
            headers=[
                *headers.items(),
                ("X-Internal-Timestamp", headers["X-Internal-Timestamp"]),
            ],
        )
        self.assertEqual(response.status_code, 401)

    async def test_hmac_replay_and_body_tampering(self):
        url = self.url + "/api/internal/push"
        body = json.dumps(
            {
                "token": "good",
                "body": "hello",
                "project": "a",
                "idempotency_key": "replay",
            }
        ).encode()
        headers = build_internal_hmac_headers("internal-test-secret", "POST", url, body)
        self.assertEqual(
            (await self.client.post(url, content=body, headers=headers)).status_code,
            200,
        )
        self.assertEqual(
            (await self.client.post(url, content=body, headers=headers)).status_code,
            401,
        )
        headers = build_internal_hmac_headers("internal-test-secret", "POST", url, body)
        self.assertEqual(
            (
                await self.client.post(url, content=body + b" ", headers=headers)
            ).status_code,
            403,
        )

    async def test_future_timestamp_nonce_is_retained_for_full_window(self):
        url = self.url + "/api/internal/push"
        body = json.dumps(
            {
                "token": "good",
                "body": "hello",
                "project": "a",
                "idempotency_key": "future",
            }
        ).encode()
        headers = build_internal_hmac_headers(
            "internal-test-secret",
            "POST",
            url,
            body,
            timestamp=int(time.time()) + 30,
            nonce="future-nonce",
        )
        self.assertEqual(
            (await self.client.post(url, content=body, headers=headers)).status_code,
            200,
        )
        state = (
            await self.client.get(self.url + "/test/state?nonce=future-nonce")
        ).json()
        self.assertGreater(state["nonce_ttl"], 70)
        self.assertEqual(
            (await self.client.post(url, content=body, headers=headers)).status_code,
            401,
        )

    async def test_original_oauth_concurrency_comparison(self):
        # Cold TLS handshakes can otherwise serialize arrivals enough to mask
        # the renewal race. Same 500ms mocked OAuth latency before and after.
        await self.client.get(self.url + "/test/oauth-delay")

        async def legacy(i):
            url = self.url + "/test/legacy-push"
            body = json.dumps(
                {
                    "token": "good",
                    "body": "hello",
                    "project": "a",
                    "idempotency_key": f"legacy-{i}",
                }
            ).encode()
            return await self.client.post(
                url,
                content=body,
                headers=build_internal_hmac_headers(
                    "internal-test-secret", "POST", url, body
                ),
            )

        responses = await asyncio.gather(*(legacy(i) for i in range(24)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        before = (await self.state())["oauth"]
        self.assertGreater(before, 1)
        await self.client.get(self.url + "/test/reset")
        await self.client.get(self.url + "/test/oauth-delay")
        responses = await asyncio.gather(
            *(self.post(key=f"new-{i}") for i in range(24))
        )
        self.assertTrue(all(r.status_code == 200 for r in responses))
        after = (await self.state())["oauth"]
        self.assertEqual(after, 1)
        print(
            f"OAUTH_BEFORE_AFTER requests=24 oauth_latency_ms=500 before={before} after={after} baseline=dc02ebb"
        )

    async def test_lua_resty_http_tls(self):
        trusted = (await self.client.get(self.url + "/test/lua-tls")).json()
        self.assertTrue(trusted["verified"], trusted)
        self.assertFalse(
            (await self.client.get(self.url + "/test/lua-tls?mode=untrusted")).json()[
                "verified"
            ]
        )

        self.assertFalse(
            (await self.client.get(self.url + "/test/lua-tls?mode=wronghost")).json()[
                "verified"
            ]
        )

    async def test_multiworker_oauth_single_refresh(self):
        responses = await asyncio.gather(*(self.post(key=f"op-{i}") for i in range(24)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        state = await self.state()
        self.assertEqual(state["oauth"], 1)
        self.assertEqual(state["fcm"], 24)
        pids = set()
        # A fresh client per request creates connections distributed across workers.
        for _ in range(16):
            async with httpx.AsyncClient(
                verify=ssl.create_default_context(
                    cafile=os.environ["PUSH_TEST_CA"]
                ),
                trust_env=False,
            ) as c:
                pids.add((await c.get(self.url + "/test/state")).json()["pid"])
        self.assertGreater(len(pids), 1)
        print(
            f"OPENRESTY_CONCURRENCY requests=24 oauth_calls=1 workers_observed={len(pids)}"
        )

    async def test_duplicate_delivery_single_fcm_request(self):
        responses = await asyncio.gather(*(self.post() for _ in range(12)))
        self.assertTrue(all(r.status_code == 200 for r in responses))
        self.assertEqual((await self.state())["fcm"], 1)

    async def test_cache_cannot_alias_tenants_or_payload(self):
        await self.post(project="a")
        await self.post(project="b")
        await self.post(token="other")
        self.assertEqual((await self.state())["fcm"], 3)
        self.assertEqual((await self.state())["oauth"], 1)

    async def test_structured_unregistered_and_no_secret_reflection(self):
        response = await self.post(token="unregistered")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()["error"]["details"][0]["errorCode"], "UNREGISTERED"
        )
        self.assertNotIn("secret-fcm-token", response.text)
        self.assertEqual((await self.post(token="invalid")).status_code, 400)

    async def test_retry_after_forwarded_and_network_sanitized(self):
        response = await self.post(token="rate")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "120")
        response = await self.post(token="network")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["push_category"], "NETWORK_FAILURE")
        self.assertNotIn("secret", response.text)

    async def test_oauth_failure_cooldown_and_safe_logs(self):
        await self.client.get(self.url + "/test/oauth-fail")
        responses = await asyncio.gather(*(self.post(key=f"op-{i}") for i in range(6)))
        self.assertTrue(all(r.status_code == 503 for r in responses))
        self.assertEqual((await self.state())["oauth"], 1)
        logs = (await self.client.get(self.url + "/test/inspect-logs")).text
        for secret in (
            "secret-oauth-access",
            "secret-fcm-token",
            "internal-test-secret",
            "BEGIN PRIVATE KEY",
        ):
            self.assertNotIn(secret, logs)

    async def test_project_cannot_choose_path_or_firebase(self):
        self.assertEqual((await self.post(project="../../other")).status_code, 400)
        self.assertEqual((await self.state())["fcm"], 0)
        self.assertEqual((await self.post(project="arbitrary-tenant")).status_code, 200)
        # Mock asserts the URL always uses shared-test from the single service account.


if __name__ == "__main__":
    unittest.main()
