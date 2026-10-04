"""Real PostgreSQL negative tests; use an isolated Docker cluster, never production."""
from __future__ import annotations

import os
import hashlib
import secrets
import sys
import unittest
import uuid
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.control_plane_roles import ensure_tenant_meta_roles
from app.tenant_meta_identity import tenant_meta_credentials, tenant_assistant_reader_credentials

DSN = os.environ.get("TENANT_SQL_TEST_ADMIN_DSN", "")


@unittest.skipUnless(DSN, "TENANT_SQL_TEST_ADMIN_DSN required (disposable cluster)")
class TenantSqlIsolationTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        self.asyncpg = asyncpg
        self.suffix = secrets.token_hex(4)
        self.master = "m" * 48
        self.refs = ["seca_" + self.suffix, "secb_" + self.suffix]
        self.ids = [uuid.uuid4(), uuid.uuid4()]
        self.cp = "seccp_" + self.suffix
        self.shared = "secshared_" + self.suffix
        self.admin = await asyncpg.connect(DSN)
        self.connections = []
        await self.admin.execute(f'CREATE ROLE "{self.shared}" LOGIN PASSWORD \'shared-test-only\'')
        for name in [self.cp] + ["_supabase_" + ref for ref in self.refs]:
            await self.admin.execute(f'CREATE DATABASE "{name}"')
        self.pool = await asyncpg.create_pool(self.dsn(self.cp), min_size=1, max_size=2)
        await self.pool.execute("CREATE TABLE projects(name text, tenant_uuid uuid)")
        for ref, identity in zip(self.refs, self.ids):
            await self.pool.execute("INSERT INTO projects VALUES($1,$2)", ref, identity)
            conn = await asyncpg.connect(self.dsn("_supabase_" + ref))
            try:
                await conn.execute(f'''CREATE SCHEMA auth AUTHORIZATION "{self.shared}";
                    CREATE TABLE auth.users(id integer);
                    ALTER TABLE auth.users OWNER TO "{self.shared}";
                    CREATE TABLE public.existing(id integer);
                    CREATE TYPE public.mood AS ENUM ('ok');
                    CREATE FUNCTION public.who() RETURNS text LANGUAGE sql SECURITY DEFINER AS 'SELECT current_user::text';''')
            finally:
                await conn.close()
        await ensure_tenant_meta_roles(self.pool, admin_dsn=self.dsn(self.cp), password=self.master)
        self.role, password = tenant_meta_credentials(self.ids[0], self.master)
        self.tenant = await asyncpg.connect(self.dsn("_supabase_" + self.refs[0], self.role, password))
        self.connections.append(self.tenant)
        # Explicit grant only for our simulated Auth service in tenant B.
        await self.admin.execute(f'GRANT CONNECT ON DATABASE "_supabase_{self.refs[1]}" TO "{self.shared}"')
        self.other_service = await asyncpg.connect(self.dsn("_supabase_" + self.refs[1], self.shared, "shared-test-only"))
        self.connections.append(self.other_service)

    def dsn(self, database, role=None, password=None):
        dsn = urlsplit(DSN)
        if role:
            host = f"[{dsn.hostname}]" if ":" in dsn.hostname else dsn.hostname
            dsn = dsn._replace(netloc=f"{role}:{password}@{host}:{dsn.port or 5432}")
        return urlunsplit(dsn._replace(path="/" + database))

    async def asyncTearDown(self):
        for conn in self.connections:
            await conn.close()
        await self.pool.close()
        for database in [self.cp] + ["_supabase_" + ref for ref in self.refs]:
            await self.admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        for identity in self.ids:
            role, _ = tenant_meta_credentials(identity, self.master)
            await self.admin.execute(f'DROP ROLE "{role}"')
            reader, _ = tenant_assistant_reader_credentials(identity, self.master)
            await self.admin.execute(f'DROP ROLE "{reader}"')
        await self.admin.execute(f'DROP ROLE "{self.shared}"')
        await self.admin.close()

    async def test_sql_administration_is_local_and_cross_tenant_authority_is_denied(self):
        pg = self.asyncpg
        await self.tenant.execute("CREATE TABLE public.created(id integer); ALTER TABLE public.existing ADD COLUMN note text; INSERT INTO auth.users VALUES (1); ALTER TYPE public.mood ADD VALUE 'good'")
        self.assertEqual(await self.tenant.fetchval("SELECT public.who()"), self.role)
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM pg_auth_members WHERE member=current_user::regrole"), 0)
        pid = await self.other_service.fetchval("SELECT pg_backend_pid()")
        for sql in (
            f'GRANT CONNECT ON DATABASE "_supabase_{self.refs[1]}" TO "{self.role}"',
            f'ALTER DATABASE "_supabase_{self.refs[1]}" RENAME TO stolen',
            f'ALTER ROLE "{self.shared}" PASSWORD \'stolen\'',
            f'SET ROLE "{self.shared}"',
            f'SELECT pg_terminate_backend({pid})',
            "CREATE ROLE stolen SUPERUSER",
            "COPY (SELECT 1) TO PROGRAM 'true'",
        ):
            with self.subTest(sql=sql):
                with self.assertRaises(pg.InsufficientPrivilegeError):
                    await self.tenant.execute(sql)
        _, password = tenant_meta_credentials(self.ids[0], self.master)
        for database in [self.cp, "_supabase_" + self.refs[1], "template1"]:
            with self.subTest(database=database):
                with self.assertRaises(pg.InsufficientPrivilegeError):
                    await pg.connect(self.dsn(database, self.role, password))
        self.assertEqual(await self.other_service.fetchval("SELECT 1"), 1)

    async def test_assistant_reader_cannot_write_escalate_read_auth_or_connect_other_tenants(self):
        role, password = tenant_assistant_reader_credentials(self.ids[0], self.master)
        reader = await self.asyncpg.connect(self.dsn("_supabase_" + self.refs[0], role, password))
        self.connections.append(reader)
        self.assertEqual(await reader.fetchval("SHOW default_transaction_read_only"), "on")
        self.assertEqual(await reader.fetchval("SELECT count(*) FROM public.existing"), 0)
        self.assertEqual(await reader.fetchval("SELECT count(*) FROM pg_auth_members WHERE member=current_user::regrole"), 0)
        await reader.execute("SET default_transaction_read_only=off")
        for query in ("INSERT INTO public.existing VALUES (1)", "CREATE TABLE public.stolen(id integer)",
                      "SELECT * FROM auth.users", f'SET ROLE "{self.role}"'):
            with self.subTest(query=query):
                with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
                    await reader.execute(query)
        for database in (self.cp, "_supabase_" + self.refs[1], "template1"):
            with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
                await self.asyncpg.connect(self.dsn(database, role, password))
        await self.tenant.execute("CREATE TABLE public.future_table(id integer)")
        self.assertEqual(await reader.fetchval("SELECT count(*) FROM public.future_table"), 0)

    async def rls_fixture(self):
        from app.assistant_security import AUTH_IDENTITY_SQL
        connection = await self.asyncpg.connect(self.dsn("_supabase_" + self.refs[0]))
        self.connections.append(connection)
        await connection.execute("""DO $$ BEGIN
            IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
            IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
            END $$;
            GRANT USAGE ON SCHEMA public, auth TO anon, authenticated;""")
        for name, source in AUTH_IDENTITY_SQL.items():
            return_type = "uuid" if name == "uid" else "jsonb"
            await connection.execute(f"CREATE FUNCTION auth.{name}() RETURNS {return_type} LANGUAGE sql STABLE AS $fn${source}$fn$")
        return connection

    async def test_rls_isolation_and_security_inspection_use_real_application_roles(self):
        from app.assistant_security import inspect_table_security
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException

        client = await self.rls_fixture()
        owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
        for sql in (
            "CREATE TABLE public.orders(id integer PRIMARY KEY, user_id uuid NOT NULL, total integer)",
            "ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY own_rows ON public.orders TO authenticated USING(user_id=(SELECT auth.uid())) WITH CHECK(user_id=auth.uid())",
        ):
            await execute_assistant_sql(self.tenant, self.sql_execution(sql))
        await self.tenant.execute("INSERT INTO public.orders VALUES(1,$1,10),(2,$2,20)", owner_a, owner_b)
        await client.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.orders TO anon, authenticated")
        await client.execute("SET ROLE authenticated")
        await client.fetchval("SELECT set_config('request.jwt.claims',$1,false)", json.dumps({"sub": str(owner_a)}))
        self.assertEqual(await client.fetchval("SELECT array_agg(id) FROM public.orders"), [1])
        self.assertEqual(await client.execute("UPDATE public.orders SET total=99 WHERE id=2"), "UPDATE 0")
        self.assertEqual(await client.execute("DELETE FROM public.orders WHERE id=2"), "DELETE 0")
        with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
            await client.execute("INSERT INTO public.orders VALUES(3,$1,30)", owner_b)
        with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
            await client.execute("UPDATE public.orders SET user_id=$1 WHERE id=1", owner_b)
        await client.execute("RESET ROLE; SET ROLE anon")
        await client.execute("SELECT set_config('request.jwt.claims','{}',false)")
        self.assertEqual(await client.fetchval("SELECT count(*) FROM public.orders"), 0)
        with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
            await client.execute("INSERT INTO public.orders VALUES(3,$1,30)", owner_a)
        await client.execute("RESET ROLE")
        reader_role, password = tenant_assistant_reader_credentials(self.ids[0], self.master)
        reader = await self.asyncpg.connect(self.dsn("_supabase_" + self.refs[0], reader_role, password))
        self.connections.append(reader)
        snapshot = (await inspect_table_security(reader, ["orders"]))[0]
        self.assertTrue(snapshot["rls_enabled"])
        self.assertFalse(snapshot["rls_forced"])
        self.assertEqual(snapshot["policies"][0]["roles"], ["authenticated"])
        self.assertTrue(snapshot["effective_privileges"]["anon"]["select"])
        self.assertFalse(snapshot["effective_privileges"]["authenticated"]["bypass_rls"])
        for sql in (
            "CREATE TABLE public.teams(id integer, team_id uuid)",
            "ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY team_access ON public.teams FOR SELECT TO authenticated USING(team_id=(auth.jwt()->'app_metadata'->>'team_id')::uuid)",
        ):
            await execute_assistant_sql(self.tenant, self.sql_execution(sql))
        await self.tenant.execute("INSERT INTO public.teams VALUES(1,$1),(2,$2)", owner_a, owner_b)
        await client.execute("GRANT SELECT ON public.teams TO authenticated; SET ROLE authenticated")
        await client.fetchval("SELECT set_config('request.jwt.claims',$1,false)", json.dumps({"sub": str(owner_a), "app_metadata": {"team_id": str(owner_a)}}))
        self.assertEqual(await client.fetchval("SELECT array_agg(id) FROM public.teams"), [1])
        await client.execute("RESET ROLE")
        for sql in (
            "ALTER POLICY own_rows ON public.orders TO anon USING(true)",
            "ALTER TABLE public.orders DISABLE ROW LEVEL SECURITY", "DROP POLICY own_rows ON public.orders",
            "ALTER TABLE public.orders NO FORCE ROW LEVEL SECURITY",
        ):
            with self.assertRaises(HTTPException) as error:
                await execute_assistant_sql(self.tenant, self.sql_execution(sql))
            self.assertEqual(error.exception.status_code, 409)
        await execute_assistant_sql(self.tenant, self.sql_execution("ALTER POLICY own_rows ON public.orders USING(user_id=auth.uid())", destructive=True))
        await execute_assistant_sql(self.tenant, self.sql_execution("DROP POLICY own_rows ON public.orders", destructive=True))
        await client.execute("SET ROLE authenticated")
        self.assertEqual(await client.fetchval("SELECT count(*) FROM public.orders"), 0)
        await client.execute("RESET ROLE")

    async def test_rls_rejects_tampered_identity_and_cross_schema_policies(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        client = await self.rls_fixture()
        await self.tenant.execute("CREATE TABLE public.orders(user_id uuid)")
        await client.execute("CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$SELECT '00000000-0000-4000-8000-000000000001'::uuid$$")
        with self.assertRaises(HTTPException) as error:
            await execute_assistant_sql(self.tenant, self.sql_execution("CREATE POLICY own ON public.orders TO authenticated USING(user_id=auth.uid())"))
        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM pg_policies WHERE tablename='orders'"), 0)
        for sql in ("CREATE POLICY leak ON auth.users TO authenticated USING(true)",
                    "CREATE POLICY leak ON public.orders TO postgres USING(true)"):
            with self.assertRaises(HTTPException):
                await execute_assistant_sql(self.tenant, self.sql_execution(sql, destructive=True))

    async def test_invalid_numeric_ownership_policy_has_safe_diagnostics_and_rolls_back(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from app.assistant_sql_errors import assistant_sql_failure
        await self.rls_fixture()
        await self.tenant.execute("CREATE TABLE public.orders(cliente_id bigint); ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY")
        with self.assertRaises(self.asyncpg.UndefinedFunctionError) as failure:
            await execute_assistant_sql(self.tenant, self.sql_execution("CREATE POLICY own ON public.orders TO authenticated USING(cliente_id=auth.uid())"))
        error = assistant_sql_failure(failure.exception)
        self.assertEqual(error.status_code, 422)
        self.assertEqual(error.detail["sqlstate"], "42883")
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM pg_policies WHERE tablename='orders'"), 0)
        self.assertTrue(await self.tenant.fetchval("SELECT relrowsecurity FROM pg_class WHERE oid='public.orders'::regclass"))
        self.assertEqual(await self.tenant.fetchval("SELECT 1"), 1)

    def privilege_change(self, operation="grant", tables=None, privileges=None, role="authenticated"):
        from app.assistant_privileges import PrivilegeChange, PrivilegeChangeBody, privilege_sql
        change = PrivilegeChange(operation=operation, tables=tables if tables is not None else ["orders"],
                                 role=role, privileges=privileges if privileges is not None else ["SELECT"], label="Application privileges")
        return PrivilegeChangeBody(**change.model_dump(), permission="full", execution={
            "chat_id": uuid.uuid4(), "call_id": str(uuid.uuid4()), "approval_id": str(uuid.uuid4()),
            "tool": "manage_table_privileges", "sql_hash": hashlib.sha256(privilege_sql(change).encode()).hexdigest(),
        })

    async def test_confirmed_grants_enable_real_rls_reads_and_revoke_preserves_policies(self):
        from app.assistant_privileges import execute_privilege_change
        from app.assistant_sql_execution import execute_assistant_sql
        client = await self.rls_fixture()
        owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
        await self.tenant.execute("CREATE TABLE public.orders(id integer,user_id uuid); ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY")
        await execute_assistant_sql(self.tenant, self.sql_execution("CREATE POLICY own ON public.orders TO authenticated USING(user_id=auth.uid()) WITH CHECK(user_id=auth.uid())"))
        await self.tenant.execute("INSERT INTO public.orders VALUES(1,$1),(2,$2)", owner_a, owner_b)
        result = await execute_privilege_change(self.tenant, self.privilege_change())
        self.assertTrue(result["effective_privileges"][0]["privileges"]["select"])
        self.assertTrue(result["effective_privileges"][0]["rls_enabled"])
        self.assertFalse(await client.fetchval("SELECT has_table_privilege('authenticated','public.orders','INSERT')"))
        self.assertFalse(await client.fetchval("SELECT has_table_privilege('anon','public.orders','SELECT')"))
        await client.execute("SET ROLE authenticated")
        await client.fetchval("SELECT set_config('request.jwt.claims',$1,false)", json.dumps({"sub":str(owner_a)}))
        self.assertEqual(await client.fetchval("SELECT array_agg(id) FROM public.orders"), [1])
        await client.execute("RESET ROLE")
        result = await execute_privilege_change(self.tenant, self.privilege_change(operation="revoke"))
        self.assertFalse(result["effective_privileges"][0]["privileges"]["select"])
        self.assertTrue(result["effective_privileges"][0]["rls_enabled"])
        self.assertEqual(await client.fetchval("SELECT count(*) FROM pg_policies WHERE tablename='orders'"), 1)
        await client.execute("SET ROLE authenticated")
        with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
            await client.fetchval("SELECT count(*) FROM public.orders")
        await client.execute("RESET ROLE")

    async def test_privilege_changes_reject_tampering_foreign_ownership_and_non_tables_atomically(self):
        from app.assistant_privileges import execute_privilege_change
        from fastapi import HTTPException
        client = await self.rls_fixture()
        await self.tenant.execute("CREATE TABLE public.orders(id integer); CREATE VIEW public.orders_view AS SELECT 1 AS id")
        await client.execute("CREATE TABLE public.foreign_owned(id integer)")
        body = self.privilege_change(); body.execution.sql_hash = "0" * 64
        with self.assertRaises(HTTPException) as failure:
            await execute_privilege_change(self.tenant, body)
        self.assertEqual(failure.exception.status_code, 403)
        for other in ("missing", "foreign_owned", "orders_view"):
            with self.assertRaises(HTTPException):
                await execute_privilege_change(self.tenant, self.privilege_change(tables=["orders", other]))
            self.assertFalse(await client.fetchval("SELECT has_table_privilege('authenticated','public.orders','SELECT')"))

    async def test_revocation_reports_remaining_column_or_public_access_without_claiming_denial(self):
        from app.assistant_privileges import execute_privilege_change
        client = await self.rls_fixture()
        await self.tenant.execute("CREATE TABLE public.orders(id integer); GRANT SELECT(id) ON public.orders TO authenticated")
        result = await execute_privilege_change(self.tenant, self.privilege_change(operation="revoke"))
        self.assertFalse(result["effective_privileges"][0]["privileges"]["select"])
        self.assertFalse(result["effective_privileges"][0]["privileges"]["column_select"])
        await self.tenant.execute("GRANT SELECT(id) ON public.orders TO PUBLIC")
        result = await execute_privilege_change(self.tenant, self.privilege_change(operation="revoke"))
        self.assertFalse(result["effective_privileges"][0]["privileges"]["select"])
        self.assertTrue(result["effective_privileges"][0]["privileges"]["column_select"])
        await self.tenant.execute("GRANT SELECT ON public.orders TO PUBLIC")
        result = await execute_privilege_change(self.tenant, self.privilege_change(operation="revoke"))
        self.assertTrue(result["effective_privileges"][0]["privileges"]["select"])

    async def test_privilege_deadline_rolls_back_and_releases_the_connection(self):
        import asyncio
        from app import assistant_privileges
        from unittest import mock
        client = await self.rls_fixture()
        await self.tenant.execute("CREATE TABLE public.orders(id integer)")
        lock = client.transaction()
        await lock.start()
        try:
            await client.execute("LOCK TABLE public.orders IN ACCESS EXCLUSIVE MODE")
            original_timeout = asyncio.timeout
            with mock.patch.object(assistant_privileges.asyncio, "timeout", side_effect=lambda _: original_timeout(0.05)):
                with self.assertRaises(TimeoutError):
                    await assistant_privileges.execute_privilege_change(self.tenant, self.privilege_change())
        finally:
            await lock.rollback()
        self.assertFalse(self.tenant.is_in_transaction())
        self.assertFalse(await self.tenant.fetchval("SELECT has_table_privilege('authenticated','public.orders','SELECT')"))

    async def test_real_tenant_pools_reuse_reset_and_bound_database_sessions(self):
        import asyncio
        from app.tenant_pools import TenantPoolManager, TenantPoolUnavailable

        manager = TenantPoolManager(size_per_role=1, acquire_timeout=.1, idle_seconds=.2)
        reader, reader_password = tenant_assistant_reader_credentials(self.ids[0], self.master)
        admin, admin_password = tenant_meta_credentials(self.ids[0], self.master)
        database = "_supabase_" + self.refs[0]
        dsns = {"reader": self.dsn(database, reader, reader_password),
                "admin": self.dsn(database, admin, admin_password)}
        try:
            async with manager.connection(self.ids[0], dsns, "reader") as first:
                reader_pid = first.get_server_pid()
                self.assertEqual(await first.fetchval("SELECT current_user"), reader)
                await first.execute("SET search_path=pg_catalog; SET default_transaction_read_only=off")
                with self.assertRaises(TenantPoolUnavailable):
                    async with manager.connection(self.ids[0], dsns, "reader"):
                        self.fail("Reader connection overflow")
                async with manager.connection(self.ids[0], dsns, "admin") as second:
                    self.assertNotEqual(second.get_server_pid(), reader_pid)
                    self.assertEqual(await second.fetchval("SELECT current_user"), admin)
            async with manager.connection(self.ids[0], dsns, "reader") as reused:
                self.assertEqual(reused.get_server_pid(), reader_pid)
                self.assertEqual(await reused.fetchval("SHOW default_transaction_read_only"), "on")
                self.assertEqual(await reused.fetchval("SHOW search_path"), '"$user", public')
                for query in ("INSERT INTO public.existing VALUES (1)", "SELECT * FROM auth.users", f'SET ROLE "{admin}"'):
                    with self.assertRaises(self.asyncpg.PostgresError):
                        await reused.execute(query)
            async with manager.connection(self.ids[0], dsns, "admin") as connection:
                await connection.execute("BEGIN; CREATE TABLE public.pool_rollback(id integer)")
            async with manager.connection(self.ids[0], dsns, "admin") as connection:
                self.assertFalse(connection.is_in_transaction())
                self.assertIsNone(await connection.fetchval("SELECT to_regclass('public.pool_rollback')"))
            started = asyncio.Event()

            async def cancelled_query():
                async with manager.connection(self.ids[0], dsns, "reader") as connection:
                    started.set()
                    await connection.execute("SELECT pg_sleep(10)")

            task = asyncio.create_task(cancelled_query())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            async with manager.connection(self.ids[0], dsns, "reader") as connection:
                self.assertEqual(await connection.fetchval("SELECT 1"), 1)
            await asyncio.sleep(.3)
            async with manager.connection(self.ids[0], dsns, "reader") as after_idle:
                self.assertNotEqual(after_idle.get_server_pid(), reader_pid)
        finally:
            await manager.close()

    async def test_uuid_identity_survives_rename_and_does_not_follow_slug_reuse(self):
        _, password = tenant_meta_credentials(self.ids[0], self.master)
        await self.tenant.close()
        new_name = "_supabase_secr_" + self.suffix
        old_name = "_supabase_" + self.refs[0]
        await self.admin.execute(f'ALTER DATABASE "{old_name}" RENAME TO "{new_name}"')
        try:
            conn = await self.asyncpg.connect(self.dsn(new_name, self.role, password))
            await conn.close()
            await self.admin.execute(f'CREATE DATABASE "{old_name}"')
            await self.admin.execute(f'REVOKE CONNECT ON DATABASE "{old_name}" FROM PUBLIC')
            with self.assertRaises(self.asyncpg.InsufficientPrivilegeError):
                await self.asyncpg.connect(self.dsn(old_name, self.role, password))
            await self.admin.execute(f'DROP DATABASE "{old_name}"')
        finally:
            await self.admin.execute(f'ALTER DATABASE "{new_name}" RENAME TO "{old_name}"')

    def sql_execution(self, sql, *, destructive=False):
        from app.assistant_sql_execution import ExecuteSqlBody
        return ExecuteSqlBody(sql=sql, label="Synthetic SQL", permission="full", execution={
            "chat_id": uuid.uuid4(), "call_id": "synthetic-call",
            **({"approval_id": "synthetic-approval"} if destructive else {}),
            "sql_hash": hashlib.sha256(sql.encode()).hexdigest(),
            "tool": "execute_destructive_sql" if destructive else "execute_sql",
        })

    async def test_assistant_full_creates_inserts_updates_but_never_deletes_without_confirmation(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        for sql in ("CREATE TABLE public.items(id integer PRIMARY KEY, title text)",
                    "INSERT INTO public.items VALUES (1,'one')", "UPDATE public.items SET title='two' WHERE id=1"):
            await execute_assistant_sql(self.tenant, self.sql_execution(sql))
        self.assertEqual(await self.tenant.fetchval("SELECT title FROM public.items WHERE id=1"), "two")
        for sql in ("DELETE FROM public.items WHERE id=1", "DELETE FROM public.items WHERE false",
                    "WITH gone AS (DELETE FROM public.items RETURNING id) SELECT 1",
                    "TRUNCATE public.items", "DROP TABLE public.items", "ALTER TABLE public.items DROP COLUMN title"):
            with self.subTest(sql=sql):
                with self.assertRaises(HTTPException) as error:
                    await execute_assistant_sql(self.tenant, self.sql_execution(sql))
                self.assertEqual(error.exception.status_code, 409)
                self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 1)
        await execute_assistant_sql(self.tenant, self.sql_execution("DELETE FROM public.items WHERE id=1", destructive=True))
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 0)

    async def test_assistant_sql_rolls_back_errors_oversized_results_and_rejects_changed_authority(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        await self.tenant.execute("CREATE TABLE public.items(id integer PRIMARY KEY)")
        for sql in ("INSERT INTO public.items SELECT * FROM generate_series(1,60) RETURNING *",
                    "UPDATE public.items SET id=1; DELETE FROM public.items"):
            with self.assertRaises(HTTPException):
                await execute_assistant_sql(self.tenant, self.sql_execution(sql))
            self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 0)
        body = self.sql_execution("INSERT INTO public.items VALUES (1)")
        body.sql = "DELETE FROM public.items"
        with self.assertRaises(HTTPException) as error:
            await execute_assistant_sql(self.tenant, body)
        self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(self.asyncpg.UniqueViolationError):
            await execute_assistant_sql(self.tenant, self.sql_execution("INSERT INTO public.items VALUES (1),(1)"))
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 0)

    async def test_assistant_blocks_views_auth_cluster_commands_and_indirect_deletion(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        await self.tenant.execute("""CREATE TABLE public.items(id integer PRIMARY KEY);
            INSERT INTO public.items VALUES (1);
            CREATE VIEW public.items_view AS SELECT * FROM public.items;
            CREATE FUNCTION public.erase_on_update() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN DELETE FROM public.items; RETURN NULL; END $$;
            CREATE TRIGGER erase AFTER UPDATE ON public.items FOR EACH STATEMENT EXECUTE FUNCTION public.erase_on_update();""")
        for sql in ("SELECT * FROM public.items_view", "DELETE FROM auth.users",
                    "CREATE ROLE stolen", "SELECT public.erase_on_update()"):
            with self.subTest(sql=sql):
                with self.assertRaises(HTTPException):
                    await execute_assistant_sql(self.tenant, self.sql_execution(sql, destructive=True))
        with self.assertRaises(HTTPException) as error:
            await execute_assistant_sql(self.tenant, self.sql_execution("UPDATE public.items SET id=2"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 1)
        await execute_assistant_sql(self.tenant, self.sql_execution("UPDATE public.items SET id=2", destructive=True))
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.items"), 0)

    async def test_assistant_requires_explicit_deletion_for_default_and_check_side_effects(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        await self.tenant.execute("""CREATE TABLE public.guard(id integer);
            CREATE FUNCTION public.erase_guard() RETURNS integer LANGUAGE plpgsql AS
                $$ BEGIN DELETE FROM public.guard; RETURN 1; END $$;
            CREATE TABLE public.defaulted(id integer DEFAULT public.erase_guard());
            CREATE TABLE public.checked(id integer CHECK (public.erase_guard()=1));""")
        for sql in ("INSERT INTO public.defaulted DEFAULT VALUES", "INSERT INTO public.checked VALUES(1)"):
            await self.tenant.execute("INSERT INTO public.guard VALUES(1)")
            with self.assertRaises(HTTPException) as error:
                await execute_assistant_sql(self.tenant, self.sql_execution(sql))
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.guard"), 1)
            await execute_assistant_sql(self.tenant, self.sql_execution(sql, destructive=True))
            self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.guard"), 0)

    async def test_foreign_key_index_and_inserts_are_not_destructive(self):
        from app.assistant_sql_execution import execute_assistant_sql
        queries = (
            "CREATE TABLE public.clientes(id bigint PRIMARY KEY)",
            "INSERT INTO public.clientes VALUES (1)",
            """CREATE TABLE public.pedidos (
                id bigint PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
                cliente_id bigint NOT NULL REFERENCES public.clientes(id),
                valor_total numeric(12,2) NOT NULL DEFAULT 0,
                status text NOT NULL DEFAULT 'aberto', criado_em timestamptz NOT NULL DEFAULT now())""",
            "CREATE INDEX idx_pedidos_cliente_id ON public.pedidos(cliente_id)",
            "INSERT INTO public.pedidos(cliente_id) VALUES(1)",
            "UPDATE public.pedidos SET valor_total=20 WHERE id=1",
            "ALTER TABLE public.pedidos ENABLE ROW LEVEL SECURITY",
        )
        for sql in queries:
            with self.subTest(sql=sql):
                plan, _ = await execute_assistant_sql(self.tenant, self.sql_execution(sql))
                self.assertFalse(plan.destructive)
        self.assertIsNotNone(await self.tenant.fetchval("SELECT to_regclass('public.idx_pedidos_cliente_id')"))
        self.assertEqual(await self.tenant.fetchval("SELECT valor_total FROM public.pedidos WHERE id=1"), 20)

    async def test_index_does_not_fire_row_triggers_or_defaults_but_update_cascade_requires_confirmation(self):
        from app.assistant_sql_execution import execute_assistant_sql
        from fastapi import HTTPException
        await self.tenant.execute("""CREATE TABLE public.parent(id integer PRIMARY KEY);
            CREATE TABLE public.child(id integer REFERENCES public.parent(id) ON UPDATE CASCADE);
            CREATE TABLE public.guard(id integer);
            INSERT INTO public.parent VALUES (1);
            INSERT INTO public.child VALUES (1);
            INSERT INTO public.guard VALUES (1);
            CREATE FUNCTION public.erase_guard_trigger() RETURNS trigger LANGUAGE plpgsql AS
                $$ BEGIN DELETE FROM public.guard; RETURN NEW; END $$;
            CREATE TRIGGER erase AFTER UPDATE ON public.child FOR EACH ROW EXECUTE FUNCTION public.erase_guard_trigger();""")
        await execute_assistant_sql(self.tenant, self.sql_execution("CREATE INDEX child_id_idx ON public.child(id)"))
        await execute_assistant_sql(self.tenant, self.sql_execution("INSERT INTO public.child VALUES (1)"))
        with self.assertRaises(HTTPException) as error:
            await execute_assistant_sql(self.tenant, self.sql_execution("UPDATE public.parent SET id=2"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.guard"), 1)
        await execute_assistant_sql(self.tenant, self.sql_execution("UPDATE public.parent SET id=2", destructive=True))
        self.assertEqual(await self.tenant.fetchval("SELECT count(*) FROM public.guard"), 0)
