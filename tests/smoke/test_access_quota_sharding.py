import ast
import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
ADMIN_DSN = os.environ.get("CONTROL_PLANE_TEST_DSN", "")
ROUTER = ROOT / "servidor/api-internal/app/routers/access_policy.py"


def usage_query():
    source = ROUTER.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "FROM access_quota_usage" in node.value:
            return node.value
    raise AssertionError("consulta de consumo ausente")


class AccessQuotaShardingTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        if not ADMIN_DSN:
            raise unittest.SkipTest("defina CONTROL_PLANE_TEST_DSN para rodar os testes de cota")
        cls.database = f"quota_test_{secrets.token_hex(6)}"
        cls.dsn = ADMIN_DSN.rsplit("/", 1)[0] + "/" + cls.database
        asyncio.run(cls._create_database())

    @classmethod
    def tearDownClass(cls):
        asyncio.run(cls._drop_database())

    @classmethod
    async def _create_database(cls):
        import asyncpg
        from app.schema_migrations import apply_migrations

        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            await conn.execute(f'CREATE DATABASE "{cls.database}"')
        finally:
            await conn.close()
        conn = await asyncpg.connect(cls.dsn)
        try:
            await apply_migrations(conn)
        finally:
            await conn.close()

    @classmethod
    async def _drop_database(cls):
        import asyncpg

        conn = await asyncpg.connect(ADMIN_DSN)
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{cls.database}" WITH (FORCE)')
        finally:
            await conn.close()

    async def asyncSetUp(self):
        import asyncpg

        self.pool = await asyncpg.create_pool(self.dsn, min_size=10, max_size=10)
        self.owner, self.project, self.slot = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO users(id,authelia_username) VALUES($1,$2)", self.owner, str(self.owner))
            await conn.execute(
                "INSERT INTO projects(id,tenant_uuid,name,display_name,owner_id,public_ref) VALUES($1,$1,$2,$2,$3,$4)",
                self.project, "p" + secrets.token_hex(4), self.owner, "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(20)),
            )
            await conn.execute(
                """INSERT INTO project_api_key_slots(id,project_id,name,kind,allowed_services,
                automatic_rotation_enabled,rotation_interval_days) VALUES($1,$2,'default','secret',$3,false,null)""",
                self.slot, self.project, ["rest"],
            )

    async def asyncTearDown(self):
        await self.pool.close()

    async def consume(self, conn=None):
        if conn is not None:
            return await conn.fetchval("SELECT consume_access_quota($1,$2,false)", self.project, self.slot)
        async with self.pool.acquire() as pooled:
            return await self.consume(pooled)

    async def admitted(self, scope_type, period="day"):
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT coalesce(sum(admitted),0) FROM access_quota_usage WHERE project_id=$1 AND scope_type=$2 AND period=$3",
                self.project, scope_type, period,
            )

    async def set_quota(self, table, key, quota):
        column = "project_id" if table == "project_access_policies" else "slot_id"
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE {table} SET policy=jsonb_set(policy,'{{request_quota}}',$2::jsonb), revision=revision+1 WHERE {column}=$1",
                key, json.dumps(quota),
            )

    async def test_unlimited_admission_does_not_wait_for_an_open_transaction(self):
        import asyncpg

        holder = await asyncpg.connect(self.dsn)
        others = []
        try:
            holder_shard = await holder.fetchval("SELECT 1 + pg_backend_pid() % 15")
            while True:
                other = await asyncpg.connect(self.dsn)
                others.append(other)
                if await other.fetchval("SELECT 1 + pg_backend_pid() % 15") != holder_shard:
                    break
            transaction = holder.transaction()
            await transaction.start()
            self.assertEqual(await self.consume(holder), 0)
            await other.execute("SET lock_timeout = '1s'")
            self.assertEqual(await self.consume(other), 0)
            await transaction.commit()
        finally:
            await holder.close()
            for connection in others:
                await connection.close()
        self.assertEqual(await self.admitted("project"), 2)
        self.assertEqual(await self.admitted("slot", "month"), 2)

    async def test_concurrent_unlimited_admissions_are_all_counted(self):
        results = await asyncio.gather(*(self.consume() for _ in range(200)))
        self.assertEqual(set(results), {0})
        for scope_type in ("project", "slot"):
            for period in ("day", "month"):
                with self.subTest(scope=scope_type, period=period):
                    self.assertEqual(await self.admitted(scope_type, period), 200)
        async with self.pool.acquire() as conn:
            shards = await conn.fetch("SELECT DISTINCT shard FROM access_quota_usage WHERE project_id=$1", self.project)
        self.assertTrue(all(1 <= row["shard"] <= 15 for row in shards))

    async def test_quota_counts_consumption_from_before_it_was_enabled(self):
        for _ in range(5):
            self.assertEqual(await self.consume(), 0)
        await self.set_quota("slot_access_policies", self.slot, {"period": "day", "limit": 7})
        results = [await self.consume() for _ in range(5)]
        self.assertEqual(results[:2], [0, 0])
        self.assertTrue(all(wait > 0 for wait in results[2:]))
        self.assertEqual(await self.admitted("slot"), 7)
        self.assertEqual(await self.admitted("slot", "month"), 7)

    async def test_concurrent_limited_admissions_never_exceed_the_limit(self):
        await self.set_quota("project_access_policies", self.project, {"period": "day", "limit": 10})
        results = await asyncio.gather(*(self.consume() for _ in range(40)))
        self.assertEqual(results.count(0), 10)
        self.assertEqual(await self.admitted("project"), 10)

    async def test_usage_query_reports_one_row_per_scope_and_period(self):
        await asyncio.gather(*(self.consume() for _ in range(30)))
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(usage_query(), self.project)
        keys = [(row["scope_type"], row["period"]) for row in rows]
        self.assertEqual(sorted(keys), [("project", "day"), ("project", "month"), ("slot", "day"), ("slot", "month")])
        self.assertTrue(all(row["admitted"] == 30 for row in rows))


if __name__ == "__main__":
    unittest.main()
