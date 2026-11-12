import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
import uuid

ROOT = Path(__file__).resolve().parents[2]
AUTHORIZER = ROOT / "servidor/key-authorizer"
SECRET = "4" * 64
PUBLIC_REF = "abcdefghijklmnopqrst"
POLICY = {
    "geo_mode": "unrestricted",
    "allowed_countries": None,
    "allowed_networks": [],
    "rate_limit": None,
    "request_quota": None,
}
SLOT_POLICY = {**POLICY, "geo_mode": "inherit"}


def _ensure_redis_module():
    try:
        import redis.asyncio  # noqa: F401
        import redis.exceptions  # noqa: F401
    except ModuleNotFoundError:
        package = types.ModuleType("redis")
        asyncio_module = types.ModuleType("redis.asyncio")
        exceptions_module = types.ModuleType("redis.exceptions")
        asyncio_module.Redis = object
        exceptions_module.RedisError = type("RedisError", (Exception,), {})
        package.asyncio, package.exceptions = asyncio_module, exceptions_module
        sys.modules.update(
            {"redis": package, "redis.asyncio": asyncio_module, "redis.exceptions": exceptions_module}
        )


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_ensure_redis_module()
_load("access_policy", ROOT / "servidor/api-internal/app/access_policy.py")
_load("opaque_keys", ROOT / "servidor/api-internal/app/opaque_keys.py")
admission = _load("admission", AUTHORIZER / "admission.py")
with mock.patch.dict(os.environ, {"DB_DSN": "postgresql://unused", "ACCESS_ADMISSION_SECRET": SECRET}):
    authorizer = _load("key_authorizer_pool_discipline_app", AUTHORIZER / "app.py")


class FakeConnection:
    def __init__(self, pool):
        self.pool = pool
        self.executed = []

    async def fetchrow(self, query, *args):
        await asyncio.sleep(0)
        if "project_access_policies" in query:
            return {"policy": POLICY, "revision": 1}
        if "slot_access_policies" in query:
            return None if self.pool.slot_policy_missing else {"policy": SLOT_POLICY, "revision": 2}
        return None

    async def fetchval(self, query, *args):
        await asyncio.sleep(0)
        self.pool.quota_calls += 1
        return 0

    async def execute(self, query, *args):
        await asyncio.sleep(0)
        self.executed.append(query)


class FakePool:
    def __init__(self, size):
        self.slots = asyncio.Semaphore(size)
        self.held = 0
        self.peak = 0
        self.quota_calls = 0
        self.slot_policy_missing = False
        self.connection = FakeConnection(self)

    def acquire(self):
        return _Acquire(self)


class _Acquire:
    def __init__(self, pool):
        self.pool = pool

    async def __aenter__(self):
        await self.pool.slots.acquire()
        self.pool.held += 1
        self.pool.peak = max(self.pool.peak, self.pool.held)
        return self.pool.connection

    async def __aexit__(self, *exc):
        self.pool.held -= 1
        self.pool.slots.release()


class FakeRedis:
    def __init__(self, pool, epoch):
        self.pool = pool
        self.store = {"access:epoch": epoch}
        self.held_during_io = []

    async def get(self, key):
        self.held_during_io.append(self.pool.held)
        return self.store.get(key)

    async def getdel(self, key):
        self.held_during_io.append(self.pool.held)
        return self.store.pop(key, None)

    async def set(self, key, value, ex=None, nx=False):
        self.held_during_io.append(self.pool.held)
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def eval(self, script, numkeys, *args):
        self.held_during_io.append(self.pool.held)
        return [1, 0]


class PoolDisciplineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import httpx

        self.epoch = str(uuid.uuid4())
        self.pool = FakePool(size=2)
        self.redis = FakeRedis(self.pool, self.epoch)
        self.engine = admission.AdmissionEngine(self.pool, self.redis, "192.0.2.10/32")
        self.engine.epoch = self.epoch
        self.project = {"id": uuid.uuid4(), "public_ref": PUBLIC_REF, "api_keyset_version": 3}
        self.key = {
            "id": uuid.uuid4(),
            "slot_id": uuid.uuid4(),
            "administrative": False,
            "functions_internal": False,
        }

        async def project_identity(conn, name, token):
            await conn.fetchrow("SELECT id FROM projects WHERE name=$1", name)
            return self.project

        async def key_identity(conn, project, body, service, missing, required):
            await conn.fetchrow("SELECT k.id FROM project_api_keys k", project["id"])
            return self.key, types.SimpleNamespace(role="anon"), False

        for target, value in (
            ("_pool", self.pool),
            ("_engine", self.engine),
            ("project_identity", project_identity),
            ("key_identity", key_identity),
        ):
            patcher = mock.patch.object(authorizer, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=authorizer.app), base_url="http://key-authorizer"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        await self.engine.http.aclose()

    def body(self):
        return admission.AdmissionRequest(
            project_ref="projeto", gateway_token="a" * 64, uri="/" + PUBLIC_REF + "/rest/v1/items",
            method="GET", client_ip="127.0.0.1", api_key="sb_publishable_test", authorization="",
        )

    def ticket(self):
        ticket = os.urandom(32).hex()[:43]
        value = admission.ticket_binding(self.body(), self.project["id"], str(self.key["id"]))
        value.update({"epoch": self.epoch, "revisions": [1, 2]})
        self.redis.store["access:ticket:" + ticket] = json.dumps(value)
        return ticket

    def authorize(self, ticket):
        body = self.body()
        return self.client.get("/v1/authorize", headers={
            "x-gateway-admission": ticket,
            "x-project-ref": body.project_ref,
            "x-project-gateway-token": body.gateway_token,
            "x-admission-uri": body.uri,
            "x-admission-method": body.method,
            "x-api-key-header": body.api_key,
            "x-original-authorization": body.authorization,
            "x-gateway-request-uri": "/rest/v1/items",
            "x-gateway-request-method": body.method,
            "x-target-service": "rest",
        })

    async def test_concurrent_authorize_never_deadlocks_a_full_pool(self):
        tickets = [self.ticket() for _ in range(25)]
        responses = await asyncio.wait_for(
            asyncio.gather(*(self.authorize(ticket) for ticket in tickets)), timeout=5
        )
        self.assertEqual([response.status_code for response in responses], [204] * 25)
        self.assertTrue(all(r.headers["X-Opaque-Key-Id"] == str(self.key["id"]) for r in responses))
        self.assertLessEqual(self.pool.peak, 2)
        self.assertEqual(self.pool.held, 0)
        self.assertEqual(sum("last_used_at" in q for q in self.pool.connection.executed), 25)
        self.assertFalse([k for k in self.redis.store if k.startswith("access:ticket:")])

    async def test_redis_redemption_runs_without_a_held_connection(self):
        response = await self.authorize(self.ticket())
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(set(self.redis.held_during_io), {0})

    async def test_policy_lookup_failure_does_not_burn_the_ticket(self):
        ticket = self.ticket()
        self.pool.slot_policy_missing = True
        response = await self.authorize(ticket)
        self.assertEqual(response.status_code, 503)
        self.assertIn("access:ticket:" + ticket, self.redis.store)

    async def test_issue_releases_the_connection_during_geoip_and_redis(self):
        observed = []

        async def geographic(policies, ip):
            observed.append(self.pool.held)

        with mock.patch.object(self.engine, "geographic", geographic):
            ticket = await self.engine.issue(self.body(), self.key, self.project, "rest")
        self.assertEqual(len(ticket), 43)
        self.assertEqual(observed, [0])
        self.assertEqual(set(self.redis.held_during_io), {0})
        self.assertEqual(self.pool.quota_calls, 1)
        self.assertEqual(self.pool.held, 0)

    async def test_preflight_admission_never_touches_the_pool(self):
        body = self.body().model_dump()
        body["method"] = "OPTIONS"
        for project_ref, gateway_token in ((body["project_ref"], body["gateway_token"]), ("", "")):
            payload = {**body, "project_ref": project_ref, "gateway_token": gateway_token}
            with self.subTest(discovery=project_ref == ""):
                response = await self.client.post(
                    "/v1/admit", json=payload, headers={"x-admission-secret": SECRET}
                )
                self.assertEqual(response.status_code, 204, response.text)
                self.assertNotIn("X-Gateway-Admission", response.headers)
        self.assertEqual(self.pool.peak, 0)
        denied = await self.client.post("/v1/admit", json=body, headers={"x-admission-secret": "5" * 64})
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
