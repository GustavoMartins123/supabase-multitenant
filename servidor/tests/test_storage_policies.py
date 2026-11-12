"""Storage policies keep their transaction, owner and tenant isolation."""

from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import uuid

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-internal"))
from app import storage_policies as policies
from app.control_plane_roles import ensure_tenant_meta_roles
from app.tenant_meta_identity import tenant_meta_credentials, tenant_storage_policy_key


MANUAL_SQL = """BEGIN;
INSERT INTO storage.buckets(id,name,public) VALUES ('Manual','Manual',false)
ON CONFLICT(id) DO UPDATE SET public=false;
DROP POLICY IF EXISTS manuais_leitura_autenticada ON storage.objects;
CREATE POLICY manuais_leitura_autenticada ON storage.objects FOR SELECT TO authenticated
USING(bucket_id='Manual' AND name IN ('Manual_IDR_Campo.pdf','Manual_Aplicativo_IDR_Campo.pdf') AND (SELECT auth.uid()) IS NOT NULL);
DROP POLICY IF EXISTS manuais_restringir_leitura_autenticada ON storage.objects;
CREATE POLICY manuais_restringir_leitura_autenticada ON storage.objects AS RESTRICTIVE FOR SELECT TO authenticated
USING(bucket_id<>'Manual' OR (name IN ('Manual_IDR_Campo.pdf','Manual_Aplicativo_IDR_Campo.pdf') AND (SELECT auth.uid()) IS NOT NULL));
DROP POLICY IF EXISTS manuais_bloquear_leitura_anonima ON storage.objects;
CREATE POLICY manuais_bloquear_leitura_anonima ON storage.objects AS RESTRICTIVE FOR SELECT TO anon USING(bucket_id<>'Manual');
DROP POLICY IF EXISTS manuais_bloquear_envio ON storage.objects;
CREATE POLICY manuais_bloquear_envio ON storage.objects AS RESTRICTIVE FOR INSERT TO anon,authenticated WITH CHECK(bucket_id<>'Manual');
DROP POLICY IF EXISTS manuais_bloquear_alteracao ON storage.objects;
CREATE POLICY manuais_bloquear_alteracao ON storage.objects AS RESTRICTIVE FOR UPDATE TO anon,authenticated USING(bucket_id<>'Manual') WITH CHECK(bucket_id<>'Manual');
DROP POLICY IF EXISTS manuais_bloquear_exclusao ON storage.objects;
CREATE POLICY manuais_bloquear_exclusao ON storage.objects AS RESTRICTIVE FOR DELETE TO anon,authenticated USING(bucket_id<>'Manual');
COMMIT;"""


class PolicyParsingTests(unittest.TestCase):
    def test_whole_script_delegates_only_policy_statements(self):
        prepared = policies.prepare_policy_statements(MANUAL_SQL)
        self.assertEqual(sum(delegated for _, delegated in prepared), 12)
        rewritten = policies.rewrite_policy_statements(
            prepared, uuid.uuid4(), key=b"a" * 32, now=100
        )
        self.assertTrue(rewritten.startswith("BEGIN;"))
        self.assertTrue(rewritten.endswith("COMMIT;"))
        self.assertIn("INSERT INTO storage.buckets", rewritten)
        self.assertEqual(rewritten.count("studio_storage_guard.execute_policy("), 12)

    def test_other_sql_keeps_the_regular_tenant_path(self):
        for sql in (
            "SELECT 1",
            "CREATE POLICY p ON public.items TO authenticated USING(true)",
            "ALTER TABLE storage.objects DISABLE ROW LEVEL SECURITY",
            "not sql",
        ):
            self.assertIsNone(policies.prepare_policy_statements(sql))

    def test_privileged_policy_expressions_and_targets_are_rejected(self):
        for sql in (
            "CREATE POLICY p ON storage.secrets TO authenticated USING(true)",
            "CREATE POLICY p ON storage.objects USING(true)",
            "CREATE POLICY p ON storage.objects TO postgres USING(true)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(public.escalate())",
            "CREATE POLICY p ON storage.objects TO authenticated USING(set_config('role','postgres',false) IS NOT NULL)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(name='x'::public.secret_domain)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(EXISTS(WITH x AS(DELETE FROM public.items RETURNING id) SELECT 1 FROM x))",
            "DROP POLICY p ON storage.objects CASCADE",
        ):
            with self.subTest(sql=sql), self.assertRaises(policies.StoragePolicyError):
                policies.prepare_policy_statements(sql)


@unittest.skipUnless(
    os.getenv("STUDIO_POLICY_TEST_DSN"), "Disposable PostgreSQL required"
)
class PolicyDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dsn = os.environ["STUDIO_POLICY_TEST_DSN"]
        self.admin = await asyncpg.connect(self.dsn)
        self.project = {
            "name": "policy_" + uuid.uuid4().hex[:12],
            "tenant_uuid": uuid.uuid4(),
        }
        self.database = "_supabase_" + self.project["name"]
        self.control_database = "policycp_" + uuid.uuid4().hex[:12]
        self.master = "m" * 48
        await self.admin.execute("""DO $$ BEGIN
            IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='supabase_storage_admin') THEN
                CREATE ROLE supabase_storage_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'storage-test-only';
                CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE;
                CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
                CREATE ROLE service_role NOLOGIN BYPASSRLS;
            END IF; END $$;""")
        await self.admin.execute('CREATE DATABASE "' + self.database + '"')
        await self.admin.execute('CREATE DATABASE "' + self.control_database + '"')
        self.control = await asyncpg.create_pool(self.dsn, database=self.control_database, min_size=1, max_size=2)
        await self.control.execute('CREATE TABLE projects(name text,tenant_uuid uuid)')
        await self.control.execute('INSERT INTO projects VALUES($1,$2)', self.project['name'], self.project['tenant_uuid'])
        self.owner = await asyncpg.connect(self.dsn, database=self.database)
        await self.owner.execute("""CREATE SCHEMA auth;
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                'SELECT nullif(current_setting(''request.jwt.claim.sub'',true),'''')::uuid';
            GRANT USAGE ON SCHEMA auth TO authenticated,anon;
            CREATE SCHEMA storage AUTHORIZATION supabase_storage_admin;
            CREATE TABLE storage.buckets(id text PRIMARY KEY,name text,public boolean);
            CREATE TABLE storage.objects(id int PRIMARY KEY,bucket_id text,name text);
            ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
            ALTER TABLE storage.objects OWNER TO supabase_storage_admin;
            ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
            GRANT USAGE ON SCHEMA storage TO anon,authenticated,service_role;
            GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA storage TO anon,authenticated,service_role;
            CREATE POLICY generic_access ON storage.objects TO anon,authenticated USING(true) WITH CHECK(true);
            INSERT INTO storage.objects VALUES(1,'Manual','Manual_IDR_Campo.pdf'),
                (2,'Manual','Manual_Aplicativo_IDR_Campo.pdf'),(3,'Manual','Outro.pdf'),(4,'other','other.pdf');""")
        await self.owner.execute(
            'GRANT CONNECT ON DATABASE "'
            + self.database
            + '" TO supabase_storage_admin'
        )
        self.environment = patch.dict(os.environ, {"META_ADMIN_DSN": "postgresql://platform_meta_admin:" + self.master + "@db/postgres"})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        await self.provision()
        self.role, password = tenant_meta_credentials(self.project["tenant_uuid"], self.master)
        self.tenant = await asyncpg.connect(
            self.dsn, database=self.database, user=self.role, password=password
        )

    async def provision(self):
        await ensure_tenant_meta_roles(self.control, admin_dsn=self.dsn, password=self.master)

    async def asyncTearDown(self):
        await self.tenant.close()
        await self.owner.close()
        await self.admin.execute('DROP DATABASE "' + self.database + '" WITH (FORCE)')
        await self.control.close()
        await self.admin.execute('DROP DATABASE "' + self.control_database + '" WITH (FORCE)')
        for prefix in ("tenant_storage_policy_", "tenant_ai_reader_", "tenant_meta_"):
            await self.admin.execute('DROP ROLE "' + prefix + self.project['tenant_uuid'].hex + '"')
        await self.admin.close()

    def rewritten(self, sql=MANUAL_SQL, **kwargs):
        return policies.rewrite_policy_statements(
            policies.prepare_policy_statements(sql),
            self.project["tenant_uuid"],
            **kwargs,
        )

    async def visible(self, role, uid):
        async with self.owner.transaction():
            await self.owner.execute(
                "SELECT set_config('request.jwt.claim.sub',$1,true)", uid or ""
            )
            await self.owner.execute('SET LOCAL ROLE "' + role + '"')
            return await self.owner.fetch(
                "SELECT name FROM storage.objects ORDER BY id"
            )

    async def test_original_manual_script_and_restrictive_rls_work(self):
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(MANUAL_SQL)
        await self.tenant.execute("ROLLBACK")
        await self.tenant.execute(self.rewritten())
        self.assertFalse(
            await self.tenant.fetchval(
                "SELECT public FROM storage.buckets WHERE id='Manual'"
            )
        )
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND policyname LIKE 'manuais_%'"
            ),
            6,
        )
        def names(rows):
            return [row["name"] for row in rows]
        self.assertEqual(
            names(await self.visible("authenticated", str(uuid.uuid4()))),
            ["Manual_IDR_Campo.pdf", "Manual_Aplicativo_IDR_Campo.pdf", "other.pdf"],
        )
        self.assertEqual(
            names(await self.visible("authenticated", None)), ["other.pdf"]
        )
        self.assertEqual(names(await self.visible("anon", None)), ["other.pdf"])
        self.assertEqual(len(await self.visible("service_role", None)), 4)
        async with self.owner.transaction():
            await self.owner.execute("SET LOCAL ROLE authenticated")
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                async with self.owner.transaction():
                    await self.owner.execute(
                        "INSERT INTO storage.objects VALUES(5,'Manual','upload.pdf')"
                    )
            self.assertEqual(
                await self.owner.execute(
                    "DELETE FROM storage.objects WHERE bucket_id='Manual'"
                ),
                "DELETE 0",
            )

    async def test_failure_rolls_back_bucket_and_policies_together(self):
        broken = MANUAL_SQL.replace("COMMIT;", "SELECT 1/0; COMMIT;")
        with self.assertRaises(asyncpg.DivisionByZeroError):
            await self.tenant.execute(self.rewritten(broken))
        await self.tenant.execute("ROLLBACK")
        self.assertEqual(
            await self.tenant.fetchval("SELECT count(*) FROM storage.buckets"), 0
        )
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT count(*) FROM pg_policies WHERE policyname LIKE 'manuais_%'"
            ),
            0,
        )

    async def test_tokens_cannot_change_sql_scope_or_expiry(self):
        for sql in (
            "SELECT studio_storage_guard.execute_policy('ALTER ROLE supabase_storage_admin PASSWORD ''stolen''', $1, $2)",
            "SELECT studio_storage_guard.execute_policy('DROP POLICY generic_access ON storage.objects', $1, $2)",
        ):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(sql, int(time.time()) + 60, "0" * 64)
        for kwargs in (
            {"now": time.time() - 120},
            {"key": b"b" * 32},
            {"role": "tenant_meta_" + uuid.uuid4().hex},
        ):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(self.rewritten(**kwargs))
            await self.tenant.execute("ROLLBACK")
        for sql in (
            "SELECT * FROM studio_storage_guard.authorities",
            "SET ROLE supabase_storage_admin",
            'SET ROLE "'
            + self.role.replace("tenant_meta_", "tenant_storage_policy_")
            + '"',
            "ALTER ROLE " + self.role + " SUPERUSER",
        ):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(sql)

    @asynccontextmanager
    async def legacy_clone(self):
        clone = {"name": "legacy_" + uuid.uuid4().hex[:12], "tenant_uuid": uuid.uuid4()}
        database = "_supabase_" + clone["name"]
        await self.tenant.close()
        await self.owner.close()
        await self.admin.execute(f'CREATE DATABASE "{database}" TEMPLATE "{self.database}"')
        self.owner = await asyncpg.connect(self.dsn, database=self.database)
        _, password = tenant_meta_credentials(self.project["tenant_uuid"], self.master)
        self.tenant = await asyncpg.connect(self.dsn, database=self.database, user=self.role, password=password)
        await self.control.execute("INSERT INTO projects VALUES($1,$2)", clone["name"], clone["tenant_uuid"])
        try:
            yield clone, database
        finally:
            await self.control.execute("DELETE FROM projects WHERE name=$1", clone["name"])
            await self.admin.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            for prefix in ("tenant_storage_policy_", "tenant_ai_reader_", "tenant_meta_"):
                await self.admin.execute(f'DROP ROLE IF EXISTS "{prefix}{clone["tenant_uuid"].hex}"')

    async def source_delegation(self):
        return await self.owner.fetchrow("""SELECT role_name, signing_key,
            (SELECT proowner FROM pg_proc WHERE oid='studio_storage_guard.execute_policy(text,bigint,text)'::regprocedure) AS owner
            FROM studio_storage_guard.authorities""")

    async def test_legacy_clone_rebinds_storage_delegation_without_changing_source(self):
        original = await self.source_delegation()
        source_helper = self.role.replace("tenant_meta_", "tenant_storage_policy_")
        async with self.legacy_clone() as (clone, database):
            await self.provision()
            await self.provision()
            role, password = tenant_meta_credentials(clone["tenant_uuid"], self.master)
            tenant = await asyncpg.connect(self.dsn, database=database, user=role, password=password)
            owner = await asyncpg.connect(self.dsn, database=database)
            try:
                authority = await owner.fetchrow("SELECT role_name, signing_key FROM studio_storage_guard.authorities")
                self.assertEqual(authority["role_name"], role)
                self.assertEqual(authority["signing_key"], tenant_storage_policy_key(clone["tenant_uuid"], self.master))
                self.assertNotEqual(authority["signing_key"], original["signing_key"])
                await tenant.execute(policies.rewrite_policy_statements(policies.prepare_policy_statements(MANUAL_SQL), clone["tenant_uuid"]))
                self.assertEqual(await owner.fetchval("SELECT count(*) FROM storage.objects"), 4)
                self.assertEqual(await owner.fetchval("SELECT count(*) FROM pg_policies WHERE schemaname='storage' AND policyname='generic_access'"), 1)
                self.assertEqual(
                    await owner.fetchval("SELECT proowner::regrole::text FROM pg_proc WHERE oid='studio_storage_guard.execute_policy(text,bigint,text)'::regprocedure"),
                    role.replace("tenant_meta_", "tenant_storage_policy_"),
                )
                for old_role in (self.role, source_helper):
                    self.assertFalse(await owner.fetchval("SELECT has_schema_privilege($1,'studio_storage_guard','USAGE')", old_role))
                    self.assertFalse(await owner.fetchval("SELECT has_function_privilege($1,'studio_storage_guard.execute_policy(text,bigint,text)','EXECUTE')", old_role))
                with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                    await tenant.execute(self.rewritten())
                await tenant.execute("ROLLBACK")
            finally:
                await tenant.close()
                await owner.close()
        self.assertEqual(await self.source_delegation(), original)

    async def test_legacy_clone_rejects_login_enabled_delegation_owner(self):
        helper = self.role.replace("tenant_meta_", "tenant_storage_policy_")
        async with self.legacy_clone() as (clone, database):
            await self.admin.execute(f'ALTER ROLE "{helper}" LOGIN')
            try:
                with self.assertRaisesRegex(asyncpg.RaiseError, "Untrusted Storage policy delegation schema"):
                    await self.provision()
                owner = await asyncpg.connect(self.dsn, database=database)
                try:
                    self.assertEqual(await owner.fetchval("SELECT role_name FROM studio_storage_guard.authorities"), self.role)
                finally:
                    await owner.close()
            finally:
                await self.admin.execute(f'ALTER ROLE "{helper}" NOLOGIN')

    async def test_legacy_clone_rejects_other_functions_owned_by_source_helper(self):
        helper = self.role.replace("tenant_meta_", "tenant_storage_policy_")
        async with self.legacy_clone() as (clone, database):
            owner = await asyncpg.connect(self.dsn, database=database)
            try:
                await owner.execute(
                    "CREATE FUNCTION studio_storage_guard.execute_policy(text) RETURNS void LANGUAGE plpgsql AS 'BEGIN RETURN; END'; "
                    f'ALTER FUNCTION studio_storage_guard.execute_policy(text) OWNER TO "{helper}"'
                )
                with self.assertRaisesRegex(asyncpg.RaiseError, "Untrusted Storage policy delegation schema"):
                    await self.provision()
                self.assertEqual(await owner.fetchval("SELECT role_name FROM studio_storage_guard.authorities"), self.role)
            finally:
                await owner.close()

    async def test_storage_owner_and_migrations_stay_unchanged(self):
        await self.provision()
        await self.tenant.execute(self.rewritten())
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT relowner::regrole::text FROM pg_class WHERE oid='storage.objects'::regclass"
            ),
            "supabase_storage_admin",
        )
        storage = await asyncpg.connect(
            self.dsn,
            database=self.database,
            user="supabase_storage_admin",
            password="storage-test-only",
        )
        try:
            await storage.execute(
                "ALTER TABLE storage.objects ADD COLUMN migration_probe text"
            )
        finally:
            await storage.close()
        attributes = await self.admin.fetchrow(
            "SELECT rolcanlogin,rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=$1",
            self.role.replace("tenant_meta_", "tenant_storage_policy_"),
        )
        self.assertTrue(all(value is False for value in attributes.values()))
