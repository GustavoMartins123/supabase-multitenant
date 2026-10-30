"""Unit and isolated PostgreSQL regression tests. No FCM traffic.

PUSH_TEST_DSN must point ONLY to an ephemeral PostgreSQL server; this suite
creates/drops databases named push_test_<uuid>, never existing tenant DBs.
"""

import asyncio
import importlib
import io
import json
import logging
import os
from pathlib import Path
import ssl
import sys
import time
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
with patch.dict(
    os.environ,
    {
        "DB_DSN": "postgres://test@localhost/postgres",
        "PUSH_API_URL": "https://push.test/api/internal/push",
        "INTERNAL_HMAC_SECRET": "internal-test-secret",
        "PUSH_CA_FILE": "",
        "PUSH_VERIFY_TLS": "true",
    },
):
    w = importlib.import_module("app.push_worker")


def fcm(code, status=404, message="sensitive-fcm-token"):
    return {
        "error": {
            "code": status,
            "message": message,
            "status": "NOT_FOUND",
            "details": [{"@type": w.FCM_ERROR_TYPE, "errorCode": code}],
        }
    }


class ResultTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_contract_and_success(self):
        def handler(request):
            from app.internal_hmac import verify_internal_hmac_signature

            self.assertEqual(request.headers["X-Internal-Service"], "push-worker")
            self.assertNotIn("X-Push-Worker-Token", request.headers)
            self.assertTrue(
                verify_internal_hmac_signature(
                    "internal-test-secret",
                    service="push-worker",
                    method="POST",
                    target=request.url.raw_path.decode(),
                    body=request.content,
                    timestamp=int(request.headers["X-Internal-Timestamp"]),
                    nonce=request.headers["X-Internal-Nonce"],
                    signature=request.headers["X-Internal-Signature"],
                    version="push-v2",
                )
            )
            self.assertEqual(json.loads(request.content)["project"], "tenant-a")
            return httpx.Response(200, json={"name": "projects/shared/messages/1"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await w.send_to_api(
                "device", "hello", "tenant-a", "safe-operation", client
            )
        self.assertTrue(result.succeeded)
        self.assertEqual(result.operation_id, "safe-operation")

    async def test_hmac_retry_nonce_and_exact_query_body(self):
        from app.internal_hmac import verify_internal_hmac_signature

        nonces = []

        def handler(req):
            nonces.append(req.headers["X-Internal-Nonce"])
            self.assertEqual(
                req.url.raw_path.decode(), "/api/internal/push?trace=a%2Fb"
            )
            self.assertTrue(
                verify_internal_hmac_signature(
                    "internal-test-secret",
                    service="push-worker",
                    method="POST",
                    target=req.url.raw_path.decode(),
                    body=req.content,
                    timestamp=int(req.headers["X-Internal-Timestamp"]),
                    nonce=req.headers["X-Internal-Nonce"],
                    signature=req.headers["X-Internal-Signature"],
                    version="push-v2",
                )
            )
            return httpx.Response(503, json={})

        with patch.object(
            w, "API_URL", "https://push.test/api/internal/push?trace=a%2Fb"
        ):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                for _ in range(2):
                    result = await w.send_to_api(
                        "token", "ação", "a", "same-operation", client
                    )
                    self.assertTrue(result.retryable)
        self.assertNotEqual(nonces[0], nonces[1])

    def test_structured_categories(self):
        cases = [
            (404, fcm("UNREGISTERED"), "UNREGISTERED", False),
            (404, {"error": {"message": "NotRegistered"}}, "UNKNOWN_ERROR", False),
            (400, fcm("INVALID_ARGUMENT", 400), "INVALID_REQUEST", False),
            (403, fcm("SENDER_ID_MISMATCH", 403), "SENDER_ID_MISMATCH", False),
            (401, {}, "AUTH_ERROR", False),
            (502, {"push_category": "AUTH_ERROR"}, "AUTH_ERROR", False),
            (429, {}, "RATE_LIMITED", True),
        ]
        cases += [
            (s, {}, "TEMPORARY_FAILURE", True) for s in (408, 425, 500, 502, 503, 504)
        ]
        for status, payload, category, retry in cases:
            with self.subTest(status=status, category=category):
                result = w.classify_response(status, payload)
                self.assertEqual((result.category, result.retryable), (category, retry))
                self.assertNotIn("sensitive", result.detail)
        self.assertNotEqual(
            w.classify_response(
                404,
                {
                    "error": {
                        "details": [{"@type": "other", "errorCode": "UNREGISTERED"}]
                    }
                },
            ).category,
            "UNREGISTERED",
        )

    def test_malformed_errors_are_safe(self):
        for body in (
            None,
            [],
            "raw-token",
            {"error": []},
            {"error": {"details": None}},
            {"error": {"details": [None]}},
        ):
            self.assertEqual(
                w.classify_response(500, body).category, "TEMPORARY_FAILURE"
            )

    async def test_network_timeout_and_lost_response(self):
        for exc in (
            httpx.ReadTimeout("secret"),
            httpx.ConnectError("secret"),
            httpx.ReadError("accepted but response lost"),
        ):
            with self.subTest(error=type(exc).__name__):
                client = AsyncMock()
                client.post.side_effect = exc
                result = await w.send_to_api("secret-token", "body", "a", "op", client)
                self.assertEqual(result.category, "NETWORK_FAILURE")
                self.assertTrue(result.retryable)
                self.assertNotIn("secret", result.detail)

    async def test_tls_failure_is_not_retried(self):
        exc = httpx.ConnectError("certificate secret")
        exc.__cause__ = ssl.SSLCertVerificationError("bad certificate")
        client = AsyncMock()
        client.post.side_effect = exc
        result = await w.send_to_api("token", "body", "a", "op", client)
        self.assertFalse(result.retryable)

    def test_retry_after_and_jitter(self):
        self.assertEqual(w.parse_retry_after("120"), 120)
        self.assertIsNone(w.parse_retry_after("inf"))
        self.assertIsNone(w.parse_retry_after("bad"))
        self.assertIsNotNone(w.parse_retry_after("Wed, 21 Oct 2037 07:28:00 GMT"))
        with patch.object(w.random, "uniform", return_value=31):
            self.assertEqual(
                w.retry_delay(1, w.PushResult("RATE_LIMITED", retry_after=7200)), 7200
            )
            self.assertEqual(w.retry_delay(1, w.PushResult("TEMPORARY_FAILURE")), 31)

    def test_tls_cannot_be_disabled(self):
        with patch.object(w, "PUSH_VERIFY_TLS", False):
            with self.assertRaises(RuntimeError):
                w.build_ssl_context()
        ctx = w.build_ssl_context()
        self.assertTrue(ctx.check_hostname)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_tenant_key_and_database_are_distinct(self):
        self.assertNotEqual(
            w.idempotency_key("a", "same", "token"),
            w.idempotency_key("b", "same", "token"),
        )
        self.assertTrue(
            w.get_tenant_dsn("postgres://user@host/base", "_supabase_a").endswith(
                "/_supabase_a"
            )
        )
        self.assertNotIn(
            "/base", w.get_tenant_dsn("postgres://user@host/base", "_supabase_b")
        )

    async def test_dynamic_add_remove_only_target_worker(self):
        active = {}
        started = []

        async def poll(name, *args):
            started.append(name)
            await asyncio.Event().wait()

        with patch.object(w, "poll_tenant", side_effect=poll):
            await w.reconcile_workers(active, {"a", "b"}, None, None, None)
            await asyncio.sleep(0)
            a, b = active["a"], active["b"]
            await w.reconcile_workers(active, {"b", "c"}, None, None, None)
            await asyncio.sleep(0)
            self.assertTrue(a.cancelled())
            self.assertIs(active["b"], b)
            self.assertEqual(set(started), {"a", "b", "c"})
            await w.reconcile_workers(active, set(), None, None, None)


BASE_SCHEMA = """
CREATE TABLE public.push_tokens(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid,
 token text NOT NULL UNIQUE,platform text,created_at timestamptz DEFAULT now());
CREATE TABLE public.notifications(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid,
 body text NOT NULL,created_at timestamptz DEFAULT now(),status text DEFAULT 'pendente');
CREATE FUNCTION public.notify_new_push() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN PERFORM pg_notify('new_push',''); RETURN NEW; END $$;
CREATE TRIGGER trigger_new_push AFTER INSERT ON public.notifications FOR EACH STATEMENT EXECUTE FUNCTION public.notify_new_push();
"""


@unittest.skipUnless(os.getenv("PUSH_TEST_DSN"), "requires isolated PostgreSQL")
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.admin = await asyncpg.connect(os.environ["PUSH_TEST_DSN"])
        self.connections = []
        self.databases = []
        self.a = await self.database()
        self.b = await self.database()
        self.uid = uuid.uuid4()
        self.settings = patch.multiple(
            w,
            PUSH_RETRY_BASE_SECONDS=60,
            PUSH_MAX_RETRY_SECONDS=3600,
            PUSH_HTTP_CONCURRENCY=4,
            PUSH_MAX_ATTEMPTS=3,
        )
        self.settings.start()

    async def database(self, fresh_setup=False):
        name = "push_test_" + uuid.uuid4().hex
        await self.admin.execute(f'CREATE DATABASE "{name}"')
        self.databases.append(name)
        conn = await asyncpg.connect(
            w.get_tenant_dsn(os.environ["PUSH_TEST_DSN"], name)
        )
        self.connections.append(conn)
        if fresh_setup:
            await conn.execute("""CREATE SCHEMA auth;
                CREATE TABLE auth.users(id uuid PRIMARY KEY);
                CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$;""")
            await conn.execute((ROOT / "servidor/sql/push/00_base.sql").read_text())
        else:
            await conn.execute(BASE_SCHEMA)
        await conn.execute(
            (
                ROOT / "servidor/migrations/push/20261014_01_delivery_fencing.sql"
            ).read_text()
        )
        await w.validate_notification_schema(conn)
        return conn

    async def test_fresh_tenant_setup_creates_all_push_tables(self):
        conn = await self.database(fresh_setup=True)
        await conn.execute("INSERT INTO auth.users(id) VALUES($1)", self.uid)
        nid = await self.add(conn)
        _, summary = await self.run_notification(
            conn, {"good": (200, {})}, "fresh-tenant"
        )
        self.assertEqual(summary["sent_count"], 1)
        self.assertEqual(await self.status(conn, nid), "enviado")
        self.assertTrue(
            await conn.fetchval(
                "SELECT relrowsecurity FROM pg_class WHERE oid='notification_deliveries'::regclass"
            )
        )

    async def asyncTearDown(self):
        self.settings.stop()
        for conn in self.connections:
            await conn.close()
        for name in self.databases:
            await self.admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await self.admin.close()

    async def add(self, conn, tokens=("good",)):
        for token in tokens:
            await conn.execute(
                "INSERT INTO push_tokens(user_id,token,platform) VALUES($1,$2,'android') ON CONFLICT(token) DO NOTHING",
                self.uid,
                token,
            )
        return await conn.fetchval(
            "INSERT INTO notifications(user_id,body) VALUES($1,'hello') RETURNING id",
            self.uid,
        )

    async def run_notification(self, conn, responses, tenant="a", hook=None):
        requests = []

        async def handler(req):
            data = json.loads(req.content)
            requests.append(data["token"])
            self.assertFalse(conn.is_in_transaction(), "HTTP performed in transaction")
            if hook:
                await hook(data)
            result = responses[data["token"]]
            if isinstance(result, Exception):
                raise result
            return httpx.Response(
                result[0], json=result[1], headers=result[2] if len(result) > 2 else {}
            )

        rows = await w.claim_notifications(conn)
        if not rows:
            return [], None
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            summary = await w.process_notification(conn, tenant, rows[0], client)
        return requests, summary

    async def status(self, conn, nid):
        return await conn.fetchval("SELECT status FROM notifications WHERE id=$1", nid)

    async def test_valid_all_devices_and_no_resend(self):
        nid = await self.add(self.a, ("a", "b", "c"))
        sent, summary = await self.run_notification(
            self.a, {t: (200, {}) for t in ("a", "b", "c")}
        )
        self.assertEqual(summary["sent_count"], 3)
        self.assertEqual(await self.status(self.a, nid), "enviado")
        self.assertEqual(
            await self.a.fetchval(
                "SELECT count(*) FROM notification_deliveries WHERE delivered_at IS NOT NULL"
            ),
            3,
        )
        self.assertEqual(await w.claim_notifications(self.a), [])

    async def test_all_unregistered_and_other_devices_and_tenants(self):
        nid = await self.add(self.a, ("invalid",))
        await self.a.execute(
            "INSERT INTO push_tokens(user_id,token,platform) VALUES($1,'other-user','ios')",
            uuid.uuid4(),
        )
        await self.add(self.b, ("invalid",))
        await self.run_notification(self.a, {"invalid": (404, fcm("UNREGISTERED"))})
        self.assertEqual(await self.status(self.a, nid), "erro")
        self.assertEqual(
            await self.a.fetchval("SELECT array_agg(token) FROM push_tokens"),
            ["other-user"],
        )
        self.assertEqual(await self.b.fetchval("SELECT count(*) FROM push_tokens"), 1)
        self.assertEqual(
            await self.b.fetchval("SELECT count(*) FROM notification_deliveries"), 0
        )

    async def test_one_valid_four_invalid(self):
        tokens = ("good", "bad1", "bad2", "bad3", "bad4")
        nid = await self.add(self.a, tokens)
        _, summary = await self.run_notification(
            self.a,
            {
                t: (200, {}) if t == "good" else (404, fcm("UNREGISTERED"))
                for t in tokens
            },
        )
        self.assertEqual((summary["sent_count"], summary["error_count"]), (1, 4))
        self.assertEqual(await self.status(self.a, nid), "enviado_parcial")
        self.assertEqual(
            await self.a.fetchval("SELECT array_agg(token) FROM push_tokens"), ["good"]
        )

    async def test_failure_categories_never_remove_tokens(self):
        cases = [
            (500, {}),
            (503, {}),
            (429, {}),
            (502, {}),
            (504, {}),
            (403, fcm("SENDER_ID_MISMATCH", 403)),
            (502, {"push_category": "AUTH_ERROR"}),
            (400, fcm("INVALID_ARGUMENT", 400)),
            (404, {"error": {"message": "NotRegistered"}}),
            httpx.ReadTimeout("timeout"),
        ]
        for index, result in enumerate(cases):
            with self.subTest(result=str(result)):
                token = "token" + str(index)
                nid = await self.add(self.a, (token,))
                # Other tokens are also recipients; isolate this notification's user.
                uid = uuid.uuid4()
                await self.a.execute(
                    "UPDATE push_tokens SET user_id=$1 WHERE token=$2", uid, token
                )
                await self.a.execute(
                    "UPDATE notifications SET user_id=$1 WHERE id=$2", uid, nid
                )
                await self.run_notification(self.a, {token: result})
                self.assertTrue(
                    await self.a.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM push_tokens WHERE token=$1)", token
                    )
                )
                # Avoid earlier scheduled notifications being eligible in next subcase.
                await self.a.execute(
                    "UPDATE notifications SET available_at=now()+interval '1 day' WHERE status='pendente'"
                )

    async def test_token_updated_during_send_not_deleted(self):
        db = await self.a.fetchval("SELECT current_database()")
        app_conn = await asyncpg.connect(
            w.get_tenant_dsn(os.environ["PUSH_TEST_DSN"], db)
        )
        self.connections.append(app_conn)
        for same_value in (False, True):
            with self.subTest(same_value=same_value):
                token = "old" + str(same_value)
                await self.add(self.a, (token,))

                async def hook(data):
                    if data["token"] == token:
                        await app_conn.execute(
                            "UPDATE push_tokens SET token=$2 WHERE token=$1",
                            token,
                            token if same_value else "new",
                        )

                responses = {
                    t: (404, fcm("UNREGISTERED"))
                    for t in await self.a.fetch("SELECT token FROM push_tokens")
                    for t in [t["token"]]
                }
                await self.run_notification(self.a, responses, hook=hook)
                self.assertTrue(
                    await self.a.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM push_tokens WHERE token=$1)",
                        token if same_value else "new",
                    )
                )

    async def test_partial_retry_preserves_success_and_retry_after(self):
        nid = await self.add(self.a, ("good", "retry"))
        _, summary = await self.run_notification(
            self.a, {"good": (200, {}), "retry": (503, {}, {"Retry-After": "120"})}
        )
        self.assertEqual(await self.status(self.a, nid), "pendente")
        self.assertEqual(summary["open_count"], 1)
        delay = await self.a.fetchval(
            "SELECT EXTRACT(EPOCH FROM available_at-now()) FROM notification_deliveries WHERE token='retry'"
        )
        self.assertGreater(delay, 119)
        await self.a.execute(
            "UPDATE notification_deliveries SET available_at=now() WHERE status='pendente'"
        )
        await self.a.execute(
            "UPDATE notifications SET available_at=now() WHERE id=$1", nid
        )
        sent, _ = await self.run_notification(self.a, {"retry": (200, {})})
        self.assertEqual(sent, ["retry"])
        self.assertEqual(await self.status(self.a, nid), "enviado")

    async def test_retry_limit_terminal(self):
        nid = await self.add(self.a)
        for attempt in range(3):
            sent, _ = await self.run_notification(self.a, {"good": (500, {})})
            self.assertEqual(sent, ["good"])
            await self.a.execute("UPDATE notifications SET available_at=now()")
            await self.a.execute(
                "UPDATE notification_deliveries SET available_at=now()"
            )
        self.assertEqual(await self.status(self.a, nid), "erro")
        self.assertEqual(await w.claim_notifications(self.a), [])

    async def test_no_tokens_snapshot_is_terminal(self):
        nid = await self.add(self.a, ())
        sent, summary = await self.run_notification(self.a, {})
        self.assertEqual(sent, [])
        self.assertEqual(await self.status(self.a, nid), "sem_token")
        self.assertEqual(summary["devices"], 0)

    async def test_two_instances_claim_once_and_fencing(self):
        nid = await self.add(self.a)
        db = await self.a.fetchval("SELECT current_database()")
        other = await asyncpg.connect(
            w.get_tenant_dsn(os.environ["PUSH_TEST_DSN"], db)
        )
        self.connections.append(other)
        claims = await asyncio.gather(
            w.claim_notifications(self.a), w.claim_notifications(other)
        )
        self.assertEqual(sum(len(c) for c in claims), 1)
        row = next(c[0] for c in claims if c)
        await w.create_delivery_rows(self.a, row)
        deliveries = await w.claim_deliveries(self.a, row)
        await self.a.execute(
            "UPDATE notifications SET locked_at=now()-interval '1 day' WHERE id=$1", nid
        )
        recovered = (await w.claim_notifications(other))[0]
        self.assertNotEqual(row["claim_id"], recovered["claim_id"])
        with self.assertRaises(w.ClaimLost):
            await w.record_delivery(
                self.a,
                row,
                deliveries[0],
                w.classify_response(404, fcm("UNREGISTERED")),
            )
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)
        with self.assertRaises(w.ClaimLost):
            await w.finalize_notification(self.a, row)
        client = AsyncMock()
        client.post.return_value = httpx.Response(200, json={})
        await w.process_notification(other, "a", recovered, client)
        self.assertEqual(await self.status(self.a, nid), "enviado")

    async def test_crash_after_claim_recovers_and_attempt_limit(self):
        nid = await self.add(self.a)
        for attempt in range(3):
            row = (await w.claim_notifications(self.a))[0]
            await w.create_delivery_rows(self.a, row)
            d = await w.claim_deliveries(self.a, row)
            self.assertEqual(d[0]["attempts"], attempt + 1)
            await self.a.execute(
                "UPDATE notifications SET locked_at=now()-interval '1 day'"
            )
        sent, _ = await self.run_notification(self.a, {"good": (200, {})})
        self.assertEqual(sent, [])
        self.assertEqual(await self.status(self.a, nid), "erro")

    async def test_restart_after_success_only_retries_unconfirmed(self):
        nid = await self.add(self.a, ("good", "retry"))
        row = (await w.claim_notifications(self.a))[0]
        await w.create_delivery_rows(self.a, row)
        deliveries = await w.claim_deliveries(self.a, row)
        first = next(d for d in deliveries if d["token"] == "good")
        await w.record_delivery(self.a, row, first, w.classify_response(200, {}))
        await self.a.execute(
            "UPDATE notifications SET locked_at=now()-interval '1 day'"
        )
        sent, _ = await self.run_notification(self.a, {"retry": (200, {})})
        self.assertEqual(sent, ["retry"])
        self.assertEqual(await self.status(self.a, nid), "enviado")

    async def test_two_tenants_concurrently_and_one_fails(self):
        na = await self.add(self.a)
        nb = await self.add(self.b)
        await asyncio.gather(
            self.run_notification(self.a, {"good": httpx.ConnectError("offline")}, "a"),
            self.run_notification(self.b, {"good": (200, {})}, "b"),
        )
        self.assertEqual(await self.status(self.a, na), "pendente")
        self.assertEqual(await self.status(self.b, nb), "enviado")
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)

    async def test_listen_notify_and_due_wakeup(self):
        event = asyncio.Event()
        await self.a.add_listener("new_push", lambda *args: event.set())
        await self.add(self.a)
        await asyncio.wait_for(event.wait(), 2)
        await self.a.execute(
            "UPDATE notifications SET available_at=now()+interval '2 seconds'"
        )
        self.assertLessEqual(await w.next_wakeup(self.a), 2)

    async def test_migration_repeatable_preserves_history(self):
        nid = await self.add(self.a)
        await self.a.execute(
            "UPDATE notifications SET status='enviado' WHERE id=$1", nid
        )
        await self.a.execute(
            (
                ROOT / "servidor/migrations/push/20261014_01_delivery_fencing.sql"
            ).read_text()
        )
        self.assertEqual(await self.status(self.a, nid), "enviado")
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)

    async def test_legacy_delivery_cannot_delete_without_snapshot(self):
        nid = await self.add(self.a)
        await self.a.execute(
            "INSERT INTO notification_deliveries(notification_id,token) VALUES($1,'good')",
            nid,
        )
        await self.a.execute("UPDATE notifications SET deliveries_initialized_at=now()")
        await self.run_notification(self.a, {"good": (404, fcm("UNREGISTERED"))})
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)

    async def test_bounded_concurrency_and_synthetic_comparison(self):
        tokens = tuple(f"device-{i}" for i in range(8))
        await self.add(self.a, tokens)
        inflight = peak = 0

        async def hook(data):
            nonlocal inflight, peak
            inflight += 1
            peak = max(peak, inflight)
            await asyncio.sleep(0.04)
            inflight -= 1

        start = time.monotonic()
        await self.run_notification(self.a, {t: (200, {}) for t in tokens}, hook=hook)
        parallel = time.monotonic() - start
        start = time.monotonic()
        for _ in tokens:
            await asyncio.sleep(0.04)
        sequential = time.monotonic() - start
        self.assertEqual(peak, 4)
        self.assertLess(parallel, sequential)
        print(
            f"SYNTHETIC_BENCHMARK devices=8 latency_ms=40 sequential_ms={sequential * 1000:.1f} parallel_ms={parallel * 1000:.1f} peak={peak}"
        )

    async def test_safe_logs(self):
        await self.add(self.a, ("sensitive-fcm-token",))
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        w.log.addHandler(handler)
        old = w.log.level
        w.log.setLevel(logging.INFO)
        try:
            await self.run_notification(
                self.a, {"sensitive-fcm-token": (404, fcm("UNREGISTERED"))}
            )
        finally:
            w.log.removeHandler(handler)
            w.log.setLevel(old)
        text = stream.getvalue()
        self.assertIn('"tokens_invalidated":1', text)
        for secret in ("sensitive-fcm-token", "internal-test-secret", "hello"):
            self.assertNotIn(secret, text)

    async def test_heartbeat_keeps_claim_during_long_http(self):
        await self.add(self.a)
        db = await self.a.fetchval("SELECT current_database()")
        competitor = await asyncpg.connect(
            w.get_tenant_dsn(os.environ["PUSH_TEST_DSN"], db)
        )
        self.connections.append(competitor)

        async def hook(data):
            await asyncio.sleep(0.14)
            self.assertEqual(await w.claim_notifications(competitor), [])
            await asyncio.sleep(0.06)

        with patch.object(w, "PUSH_NOTIFICATION_LEASE_SECONDS", 0.09):
            _, summary = await self.run_notification(
                self.a, {"good": (200, {})}, hook=hook
            )
        self.assertEqual(summary["sent_count"], 1)

    async def test_excessive_retry_after_is_terminal_without_early_retry(self):
        nid = await self.add(self.a)
        await self.run_notification(
            self.a, {"good": (429, {}, {"Retry-After": "10000000000000000"})}
        )
        self.assertEqual(await self.status(self.a, nid), "erro")
        self.assertEqual(await w.claim_notifications(self.a), [])

    async def test_lost_fcm_response_uses_documented_at_least_once_policy(self):
        nid = await self.add(self.a)
        accepted = []

        async def hook(data):
            # Upstream may have accepted, but the client cannot prove delivery.
            accepted.append(data["idempotency_key"])

        await self.run_notification(
            self.a,
            {"good": httpx.ReadError("response lost after acceptance")},
            hook=hook,
        )
        self.assertEqual(await self.status(self.a, nid), "pendente")
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)
        await self.a.execute("UPDATE notifications SET available_at=now()")
        await self.a.execute("UPDATE notification_deliveries SET available_at=now()")
        await self.run_notification(self.a, {"good": (200, {})}, hook=hook)
        self.assertEqual(await self.status(self.a, nid), "enviado")
        self.assertEqual(len(accepted), 2)
        self.assertEqual(accepted[0], accepted[1])

    async def test_migration_refuses_nonunique_tokens_without_data_loss(self):
        await self.add(self.a)
        await self.a.execute(
            "ALTER TABLE push_tokens DROP CONSTRAINT push_tokens_token_key"
        )
        with self.assertRaises(asyncpg.RaiseError):
            await self.a.execute(
                (
                    ROOT / "servidor/migrations/push/20261014_01_delivery_fencing.sql"
                ).read_text()
            )
        await self.a.execute("ROLLBACK")
        self.assertEqual(await self.a.fetchval("SELECT count(*) FROM push_tokens"), 1)

    @unittest.skipUnless(
        os.getenv("PUSH_TEST_GATEWAY"), "requires isolated OpenResty test server"
    )
    async def test_worker_to_real_gateway_and_postgres(self):
        nid = await self.add(self.a, ("good", "unregistered"))
        context = ssl.create_default_context(cafile=os.environ["PUSH_TEST_CA"])
        with patch.multiple(
            w,
            API_URL=os.environ["PUSH_TEST_GATEWAY"] + "/api/internal/push",
            SSL_CONTEXT=context,
        ):
            async with w.http_client() as client:
                row = (await w.claim_notifications(self.a))[0]
                summary = await w.process_notification(self.a, "tenant-a", row, client)
        self.assertEqual((summary["sent_count"], summary["error_count"]), (1, 1))
        self.assertEqual(await self.status(self.a, nid), "enviado_parcial")
        self.assertEqual(
            await self.a.fetchval("SELECT array_agg(token) FROM push_tokens"), ["good"]
        )

    async def test_connection_recovery_keeps_tenant_identity(self):
        da = await self.a.fetchval("SELECT current_database()")
        db = await self.b.fetchval("SELECT current_database()")

        async def handler(req):
            return httpx.Response(200, json={})

        async def wait_status(conn, nid):
            async def wait():
                while await self.status(conn, nid) != "enviado":
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(wait(), 3)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with patch.multiple(
                w,
                BASE_DSN=os.environ["PUSH_TEST_DSN"],
                PUSH_SCHEMA_RETRY_SECONDS=0.02,
                PUSH_IDLE_WAKEUP_SECONDS=0.02,
            ):
                slots = asyncio.Semaphore(2)
                tasks = [
                    asyncio.create_task(w.poll_tenant(d, slots, client))
                    for d in (da, db)
                ]
                try:
                    na = await self.add(self.a)
                    nb = await self.add(self.b)
                    await asyncio.gather(
                        wait_status(self.a, na), wait_status(self.b, nb)
                    )
                    pid = await self.admin.fetchval(
                        "SELECT pid FROM pg_stat_activity WHERE datname=$1 AND application_name='supabase-push-worker'",
                        da,
                    )
                    self.assertIsNotNone(pid)
                    await self.admin.execute("SELECT pg_terminate_backend($1)", pid)
                    na2 = await self.add(self.a, ("after-reconnect",))
                    await wait_status(self.a, na2)
                    newpid = await self.admin.fetchval(
                        "SELECT pid FROM pg_stat_activity WHERE datname=$1 AND application_name='supabase-push-worker'",
                        da,
                    )
                    self.assertNotEqual(pid, newpid)
                    self.assertEqual(
                        await self.b.fetchval("SELECT count(*) FROM notifications"), 1
                    )
                    self.assertEqual(
                        await self.b.fetchval("SELECT count(*) FROM push_tokens"), 1
                    )
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
