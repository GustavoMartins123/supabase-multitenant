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


MEDIA_CATALOG_MIGRATION_SQL = r"""BEGIN;
CREATE TABLE IF NOT EXISTS public.midia_arquivo (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    bucket text NOT NULL,
    storage_path text NOT NULL,
    nome text NOT NULL,
    id_projeto uuid NOT NULL,
    id_atividade uuid NOT NULL,
    id_celula uuid NOT NULL,
    tipo_midia text NOT NULL,
    sequencia integer NOT NULL,
    recorded_by text NOT NULL,
    CONSTRAINT midia_arquivo_pkey PRIMARY KEY (id),
    CONSTRAINT midia_arquivo_bucket_path_key UNIQUE (bucket, storage_path)
);

CREATE OR REPLACE FUNCTION public.midia_arquivo_registrar(
    p_bucket text,
    p_name text
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
SET row_security TO 'off'
AS $function$
DECLARE
    v_parts text[];
    v_nome text;
    v_ext text;
    v_base text;
    v_seq int;
BEGIN
    IF p_bucket NOT IN ('midias', 'aplicativos') THEN RETURN; END IF;
    v_parts := string_to_array(p_name, '/');
    IF array_length(v_parts, 1) <> 4 THEN RETURN; END IF;
    v_nome := v_parts[4];
    v_ext := lower(substring(v_nome from '\.([a-zA-Z0-9]+)$'));
    v_base := substring(v_nome from 1 for length(v_nome) - length(v_ext) - 1);
    v_seq := substring(v_base from '([0-9]+)$')::int;
    INSERT INTO public.midia_arquivo (
        bucket, storage_path, nome, id_projeto, id_atividade, id_celula,
        tipo_midia, sequencia, recorded_by
    ) VALUES (
        p_bucket, p_name, v_nome, v_parts[1]::uuid, v_parts[2]::uuid, v_parts[3]::uuid,
        'foto', v_seq, current_user
    )
    ON CONFLICT (bucket, storage_path) DO UPDATE SET
        nome = EXCLUDED.nome,
        sequencia = EXCLUDED.sequencia,
        recorded_by = EXCLUDED.recorded_by;
END;
$function$;

CREATE OR REPLACE FUNCTION public.midia_arquivo_catalogar()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
SET row_security TO 'off'
AS $function$
BEGIN
    IF TG_OP = 'DELETE' THEN
        DELETE FROM public.midia_arquivo
         WHERE bucket = OLD.bucket_id AND storage_path = OLD.name;
        RETURN NULL;
    END IF;
    IF TG_OP = 'UPDATE'
       AND (OLD.bucket_id IS DISTINCT FROM NEW.bucket_id
            OR OLD.name IS DISTINCT FROM NEW.name) THEN
        DELETE FROM public.midia_arquivo
         WHERE bucket = OLD.bucket_id AND storage_path = OLD.name;
    END IF;
    PERFORM public.midia_arquivo_registrar(NEW.bucket_id, NEW.name);
    RETURN NULL;
END;
$function$;

GRANT EXECUTE ON FUNCTION public.midia_arquivo_catalogar() TO supabase_storage_admin;

SET ROLE supabase_storage_admin;
DROP TRIGGER IF EXISTS trg_catalogar_midia_arquivo ON storage.objects;
CREATE TRIGGER trg_catalogar_midia_arquivo
    AFTER INSERT OR DELETE OR UPDATE ON storage.objects
    FOR EACH ROW EXECUTE FUNCTION public.midia_arquivo_catalogar();
RESET ROLE;

DO $do$
DECLARE
    v_rec record;
BEGIN
    FOR v_rec IN
        SELECT bucket_id, name FROM storage.objects WHERE bucket_id IN ('midias', 'aplicativos')
    LOOP
        PERFORM public.midia_arquivo_registrar(v_rec.bucket_id, v_rec.name);
    END LOOP;
END
$do$;

REVOKE EXECUTE ON FUNCTION public.midia_arquivo_registrar(text, text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.midia_arquivo_catalogar() FROM PUBLIC, anon, authenticated;
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

    def test_media_catalog_migration_with_set_role_and_triggers_is_delegated(self):
        prepared = policies.prepare_policy_statements(MEDIA_CATALOG_MIGRATION_SQL)
        self.assertIsNotNone(prepared)
        self.assertEqual(sum(delegated for _, delegated in prepared), 2)
        rewritten = policies.rewrite_policy_statements(
            prepared, uuid.uuid4(), key=b"a" * 32, now=100
        )
        self.assertTrue(rewritten.startswith("BEGIN;"))
        self.assertTrue(rewritten.endswith("COMMIT;"))
        self.assertNotIn("SET ROLE", rewritten)
        self.assertNotIn("RESET ROLE", rewritten)
        self.assertEqual(rewritten.count("studio_storage_guard.execute_policy("), 2)

    def test_storage_policy_project_helpers_and_auth_triggers_and_indexes_are_allowed(self):
        for sql in (
            "CREATE POLICY p ON storage.objects FOR SELECT TO authenticated USING (bucket_id='midias' AND public.can_read_atividade(id) AND auth.role() = 'authenticated')",
            "DROP TRIGGER IF EXISTS trg_x ON storage.objects; CREATE TRIGGER trg_x AFTER INSERT ON storage.objects FOR EACH ROW WHEN (NEW.bucket_id = 'midias') EXECUTE FUNCTION public.on_obj()",
            "ALTER TABLE storage.objects DISABLE TRIGGER trg_x; ALTER TABLE storage.objects ENABLE TRIGGER trg_x",
            "SET ROLE supabase_auth_admin; DROP TRIGGER IF EXISTS trg_user ON auth.users; CREATE TRIGGER trg_user AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user(); RESET ROLE",
            "CREATE INDEX IF NOT EXISTS idx_obj_bucket_lower ON storage.objects (bucket_id, lower(name)) WHERE bucket_id = 'midias'",
            "DROP INDEX IF EXISTS storage.idx_obj_bucket_lower",
            "CREATE INDEX IF NOT EXISTS idx_auth_email_lower ON auth.users (lower(email))",
            "DROP INDEX IF EXISTS auth.idx_auth_email_lower",
        ):
            with self.subTest(sql=sql):
                prepared = policies.prepare_policy_statements(sql)
                self.assertIsNotNone(prepared)
                self.assertTrue(any(delegated for _, delegated in prepared))

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
            "CREATE POLICY p ON storage.objects TO authenticated USING(net.http_get('http://internal') IS NOT NULL)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(studio_storage_guard.execute_policy('x',1,'a') IS NULL)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(set_config('role','postgres',false) IS NOT NULL)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(name='x'::public.secret_domain)",
            "CREATE POLICY p ON storage.objects TO authenticated USING(EXISTS(WITH x AS(DELETE FROM public.items RETURNING id) SELECT 1 FROM x))",
            "DROP POLICY p ON storage.objects CASCADE",
        ):
            with self.subTest(sql=sql), self.assertRaises(policies.StoragePolicyError):
                policies.prepare_policy_statements(sql)

    def test_unsafe_triggers_indexes_set_role_and_password_changes_are_rejected(self):
        for sql in (
            "ALTER ROLE current_user PASSWORD 'broken'",
            "ALTER ROLE supabase_storage_admin PASSWORD 'stolen'",
            "ALTER USER tenant_meta_00000000000000000000000000000000 WITH PASSWORD 'x'",
            "ALTER ROLE current_user SET statement_timeout = '0'",
            "CREATE ROLE hacker LOGIN PASSWORD 'x'",
            "CREATE USER hacker WITH PASSWORD 'x'",
            "DROP ROLE anon",
            "GRANT supabase_storage_admin TO current_user",
            "SET SESSION AUTHORIZATION postgres",
            "SET ROLE postgres",
            "SET ROLE supabase_storage_admin",
            "SET ROLE supabase_storage_admin; DROP TABLE storage.objects; RESET ROLE",
            "SET ROLE supabase_storage_admin; CREATE TRIGGER t AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.f(); RESET ROLE",
            "ALTER TABLE public.items OWNER TO supabase_storage_admin",
            "DROP SCHEMA studio_storage_guard",
            "DROP SCHEMA studio_trigger_guard",
            "DO $$ BEGIN EXECUTE 'ALTER ROLE current_user PASSWORD ''x'''; END $$",
            "DO $$ BEGIN EXECUTE format('ALTER ROLE %I PASSWORD %L', current_user, 'x'); END $$",
            "DO $$ BEGIN SET ROLE supabase_storage_admin; END $$",
            "CREATE FUNCTION public.pwn() RETURNS void LANGUAGE plpgsql AS $$ BEGIN ALTER ROLE current_user PASSWORD 'x'; END $$",
            "CREATE CONSTRAINT TRIGGER t AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION public.f()",
            "CREATE TRIGGER t AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION storage.internal_fn()",
            "CREATE TRIGGER t AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION unqualified_fn()",
            "CREATE TRIGGER t AFTER INSERT ON storage.objects FOR EACH ROW WHEN (public.evil()) EXECUTE FUNCTION public.f()",
            "DROP TRIGGER t ON storage.objects CASCADE",
            "ALTER TABLE storage.objects DISABLE TRIGGER ALL",
            "CREATE INDEX CONCURRENTLY idx_c ON storage.objects (name)",
            "CREATE INDEX idx_e ON storage.objects (public.evil(name))",
            "CREATE INDEX ON storage.objects (name)",
            "DROP INDEX storage.idx_c CASCADE",
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
                CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'auth-test-only';
                CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
                CREATE ROLE service_role NOLOGIN BYPASSRLS;
            END IF; END $$;""")
        await self.admin.execute('CREATE DATABASE "' + self.database + '"')
        await self.admin.execute('CREATE DATABASE "' + self.control_database + '"')
        self.control = await asyncpg.create_pool(self.dsn, database=self.control_database, min_size=1, max_size=2)
        await self.control.execute('CREATE TABLE projects(name text,tenant_uuid uuid)')
        await self.control.execute('INSERT INTO projects VALUES($1,$2)', self.project['name'], self.project['tenant_uuid'])
        self.owner = await asyncpg.connect(self.dsn, database=self.database)
        await self.owner.execute("""CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;
            CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS
                'SELECT nullif(current_setting(''request.jwt.claim.sub'',true),'''')::uuid';
            CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS
                'SELECT coalesce(nullif(current_setting(''request.jwt.claim.role'',true),''''), current_user)';
            CREATE TABLE auth.users(id uuid PRIMARY KEY,email text);
            ALTER TABLE auth.users OWNER TO supabase_auth_admin;
            CREATE FUNCTION auth.builtin_user_guard() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END';
            ALTER FUNCTION auth.builtin_user_guard() OWNER TO supabase_auth_admin;
            CREATE TRIGGER auth_builtin_trigger AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION auth.builtin_user_guard();
            CREATE INDEX auth_builtin_email_idx ON auth.users(email);
            GRANT USAGE ON SCHEMA auth TO authenticated,anon;
            CREATE SCHEMA storage AUTHORIZATION supabase_storage_admin;
            CREATE TABLE storage.buckets(id text PRIMARY KEY,name text,public boolean);
            CREATE TABLE storage.objects(id int PRIMARY KEY,bucket_id text,name text);
            ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
            ALTER TABLE storage.objects OWNER TO supabase_storage_admin;
            CREATE FUNCTION storage.builtin_object_guard() RETURNS trigger LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END';
            ALTER FUNCTION storage.builtin_object_guard() OWNER TO supabase_storage_admin;
            CREATE TRIGGER storage_builtin_trigger AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION storage.builtin_object_guard();
            CREATE INDEX storage_builtin_bucket_idx ON storage.objects(bucket_id);
            ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;
            GRANT USAGE ON SCHEMA storage TO anon,authenticated,service_role;
            GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA storage TO anon,authenticated,service_role;
            CREATE POLICY generic_access ON storage.objects TO anon,authenticated USING(true) WITH CHECK(true);
            INSERT INTO storage.objects VALUES(1,'Manual','Manual_IDR_Campo.pdf'),
                (2,'Manual','Manual_Aplicativo_IDR_Campo.pdf'),(3,'Manual','Outro.pdf'),(4,'other','other.pdf');""")
        await self.owner.execute(
            'GRANT CONNECT ON DATABASE "'
            + self.database
            + '" TO supabase_storage_admin, supabase_auth_admin'
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

    async def test_media_catalog_migration_runs_idempotently_and_trigger_executes_as_tenant(self):
        proj_id = str(uuid.uuid4())
        act_id = str(uuid.uuid4())
        cell_id = str(uuid.uuid4())
        initial_path = f"{proj_id}/{act_id}/{cell_id}/{cell_id}-1.jpg"
        live_path = f"{proj_id}/{act_id}/{cell_id}/{cell_id}-2.jpg"
        renamed_path = f"{proj_id}/{act_id}/{cell_id}/{cell_id}-3.jpg"

        await self.owner.execute(
            "INSERT INTO storage.objects VALUES(10,'midias',$1)", initial_path
        )

        await self.tenant.execute(self.rewritten(MEDIA_CATALOG_MIGRATION_SQL))
        await self.tenant.execute(self.rewritten(MEDIA_CATALOG_MIGRATION_SQL))

        backfilled = await self.tenant.fetchrow(
            "SELECT sequencia, recorded_by FROM public.midia_arquivo WHERE storage_path=$1",
            initial_path,
        )
        self.assertEqual(backfilled["sequencia"], 1)
        self.assertEqual(backfilled["recorded_by"], self.role)

        storage = await asyncpg.connect(
            self.dsn,
            database=self.database,
            user="supabase_storage_admin",
            password="storage-test-only",
        )
        try:
            await storage.execute(
                "INSERT INTO storage.objects VALUES(11,'midias',$1)", live_path
            )
            inserted = await self.tenant.fetchrow(
                "SELECT sequencia, recorded_by FROM public.midia_arquivo WHERE storage_path=$1",
                live_path,
            )
            self.assertEqual(inserted["sequencia"], 2)
            self.assertEqual(inserted["recorded_by"], self.role)

            await storage.execute(
                "UPDATE storage.objects SET name=$1 WHERE id=11", renamed_path
            )
            self.assertIsNone(
                await self.tenant.fetchval(
                    "SELECT 1 FROM public.midia_arquivo WHERE storage_path=$1",
                    live_path,
                )
            )
            self.assertEqual(
                await self.tenant.fetchval(
                    "SELECT sequencia FROM public.midia_arquivo WHERE storage_path=$1",
                    renamed_path,
                ),
                3,
            )

            await storage.execute("DELETE FROM storage.objects WHERE id=11")
            self.assertIsNone(
                await self.tenant.fetchval(
                    "SELECT 1 FROM public.midia_arquivo WHERE storage_path=$1",
                    renamed_path,
                )
            )
        finally:
            await storage.close()

    async def test_trigger_security_definer_enforced_and_downgrade_blocked_and_builtins_protected(self):
        await self.tenant.execute("""
            CREATE FUNCTION public.invoker_trg() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RETURN NEW; END $$;
            GRANT EXECUTE ON FUNCTION public.invoker_trg() TO supabase_storage_admin;
        """)
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                self.rewritten(
                    "CREATE TRIGGER trg_bad AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION public.invoker_trg();"
                )
            )

        await self.tenant.execute("""
            CREATE FUNCTION public.definer_trg() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
            BEGIN RETURN NEW; END $$;
            GRANT EXECUTE ON FUNCTION public.definer_trg() TO supabase_storage_admin;
        """)
        await self.tenant.execute(
            self.rewritten(
                "CREATE TRIGGER trg_good AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION public.definer_trg();"
            )
        )
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute("ALTER FUNCTION public.definer_trg() SECURITY INVOKER")
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                "CREATE OR REPLACE FUNCTION public.definer_trg() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$"
            )
        await self.tenant.execute(
            "CREATE OR REPLACE FUNCTION public.definer_trg() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$ BEGIN RETURN NEW; END $$"
        )
        await self.tenant.execute(
            self.rewritten("ALTER TABLE storage.objects DISABLE TRIGGER trg_good; ALTER TABLE storage.objects ENABLE TRIGGER trg_good; DROP TRIGGER trg_good ON storage.objects;")
        )

        for sql in (
            "DROP TRIGGER storage_builtin_trigger ON storage.objects",
            "ALTER TABLE storage.objects DISABLE TRIGGER storage_builtin_trigger",
            "CREATE OR REPLACE TRIGGER storage_builtin_trigger AFTER INSERT ON storage.objects FOR EACH ROW EXECUTE FUNCTION public.definer_trg()",
            "DROP TRIGGER auth_builtin_trigger ON auth.users",
            "ALTER TABLE auth.users DISABLE TRIGGER auth_builtin_trigger",
        ):
            with self.subTest(sql=sql), self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(self.rewritten(sql))

    async def test_auth_users_trigger_and_storage_policy_project_helpers_and_managed_indexes(self):
        await self.tenant.execute("""
            CREATE TABLE public.user_profiles(user_id uuid PRIMARY KEY, email text, created_by text);
            CREATE FUNCTION public.handle_new_user() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
            BEGIN
                INSERT INTO public.user_profiles VALUES (NEW.id, NEW.email, current_user);
                RETURN NEW;
            END $$;
            GRANT EXECUTE ON FUNCTION public.handle_new_user() TO supabase_auth_admin;
        """)
        await self.tenant.execute(
            self.rewritten(
                "SET ROLE supabase_auth_admin; DROP TRIGGER IF EXISTS trg_on_auth_user ON auth.users; CREATE TRIGGER trg_on_auth_user AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.handle_new_user(); RESET ROLE;"
            )
        )
        auth_conn = await asyncpg.connect(
            self.dsn,
            database=self.database,
            user="supabase_auth_admin",
            password="auth-test-only",
        )
        user_id = uuid.uuid4()
        try:
            await auth_conn.execute(
                "INSERT INTO auth.users VALUES($1, 'dev@example.com')", user_id
            )
        finally:
            await auth_conn.close()
        profile = await self.tenant.fetchrow(
            "SELECT email, created_by FROM public.user_profiles WHERE user_id=$1", user_id
        )
        self.assertEqual(profile["email"], "dev@example.com")
        self.assertEqual(profile["created_by"], self.role)

        await self.tenant.execute("""
            CREATE FUNCTION public.allow_manual_only(b text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
            SELECT b = 'Manual' $$;
            GRANT EXECUTE ON FUNCTION public.allow_manual_only(text) TO authenticated;
        """)
        await self.tenant.execute(
            self.rewritten(
                "CREATE POLICY helper_restrict ON storage.objects AS RESTRICTIVE FOR SELECT TO authenticated USING (public.allow_manual_only(bucket_id))"
            )
        )
        self.assertEqual(
            [r["name"] for r in await self.visible("authenticated", str(uuid.uuid4()))],
            ["Manual_IDR_Campo.pdf", "Manual_Aplicativo_IDR_Campo.pdf", "Outro.pdf"],
        )

        await self.owner.execute("""
            CREATE FUNCTION public.superuser_helper() RETURNS boolean LANGUAGE sql SECURITY DEFINER AS 'SELECT true';
            GRANT EXECUTE ON FUNCTION public.superuser_helper() TO authenticated;
        """)
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                self.rewritten(
                    "CREATE POLICY bad_priv_helper ON storage.objects FOR SELECT TO authenticated USING (public.superuser_helper())"
                )
            )

        await self.tenant.execute(
            self.rewritten(
                "CREATE INDEX IF NOT EXISTS idx_custom_obj_name ON storage.objects (bucket_id, lower(name));"
                "CREATE INDEX IF NOT EXISTS idx_custom_auth_email ON auth.users (lower(email));"
            )
        )
        await self.tenant.execute(
            self.rewritten(
                "DROP INDEX IF EXISTS storage.idx_custom_obj_name;"
                "DROP INDEX IF EXISTS auth.idx_custom_auth_email;"
            )
        )
        await self.tenant.execute(
            self.rewritten(
                "CREATE INDEX IF NOT EXISTS storage_builtin_bucket_idx ON storage.objects (bucket_id);"
            )
        )
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                self.rewritten("DROP INDEX storage.storage_builtin_bucket_idx;")
            )
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                self.rewritten("DROP INDEX auth.auth_builtin_email_idx;")
            )

        import hashlib
        import hmac as _hmac
        bad_stmt = "ALTER ROLE supabase_storage_admin PASSWORD 'stolen'"
        exp = int(time.time()) + 60
        proof = _hmac.new(
            tenant_storage_policy_key(self.project["tenant_uuid"], self.master),
            f"{self.role}\n{exp}\n{bad_stmt}".encode(),
            hashlib.sha256,
        ).hexdigest()
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                "SELECT studio_storage_guard.execute_policy($1, $2, $3)",
                bad_stmt,
                exp,
                proof,
            )
