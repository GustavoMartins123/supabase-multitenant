"""Real PostgreSQL negative tests; use an isolated Docker cluster, never production."""
from __future__ import annotations

import os
import secrets
import sys
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.control_plane_roles import ensure_tenant_meta_roles
from app.tenant_meta_identity import tenant_meta_credentials

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
