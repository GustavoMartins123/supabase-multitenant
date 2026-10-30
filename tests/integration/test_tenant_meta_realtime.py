"""Regression coverage for Studio-owned triggers calling Realtime invoker helpers.

TENANT_META_REALTIME_TEST_DSN must point at a disposable PostgreSQL cluster with
permission to create databases and roles. No production tenant is used.
"""
from __future__ import annotations
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse
from uuid import uuid4
import asyncpg

ROOT = Path(os.environ['TENANT_META_TEST_ROOT']) if 'TENANT_META_TEST_ROOT' in os.environ else Path(__file__).resolve().parents[2]
DSN = os.getenv('TENANT_META_REALTIME_TEST_DSN')

@unittest.skipUnless(DSN, 'Set TENANT_META_REALTIME_TEST_DSN to a disposable cluster')
class TenantMetaRealtimeTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self, *, lazy):
        identity = uuid4().hex
        database = '_supabase_realtime_probe_' + identity[:12]
        role = 'tenant_meta_' + identity
        reader = 'tenant_ai_reader_' + identity
        password = 'e' * 64
        root = await asyncpg.connect(DSN)
        tenant = None
        admin = None
        created = False
        try:
            if not await root.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated')"):
                await root.execute('CREATE ROLE authenticated')
            await root.execute(f'CREATE DATABASE "{database}"')
            created = True
            source = urlparse(DSN)
            tenant = await asyncpg.connect(host=source.hostname, port=source.port or 5432,
                user=source.username, password=source.password, database=database)
            async def install_realtime():
                await tenant.execute("""CREATE SCHEMA IF NOT EXISTS realtime;
                    CREATE TABLE realtime.messages(payload text);
                    CREATE FUNCTION realtime.emit_probe(value text) RETURNS void
                    LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
                    BEGIN INSERT INTO realtime.messages VALUES(value);
                    EXCEPTION WHEN OTHERS THEN RAISE WARNING 'ErrorSendingBroadcastMessage: %',SQLERRM;
                    END $$;""")
            if not lazy:
                await install_realtime()
            template = (ROOT / 'servidor/api-internal/app/tenant_meta_role.sql').read_text()
            sql = template.replace(":'meta_role'", "'" + role + "'").replace(":'meta_password'", "'" + password + "'")
            async with tenant.transaction():
                await tenant.execute(sql)
            if lazy:
                await install_realtime()
            admin = await asyncpg.connect(host=source.hostname, port=source.port or 5432,
                user=role, password=password, database=database)
            await admin.execute("""CREATE TABLE public.probe(payload text);
                CREATE FUNCTION public.notify_probe() RETURNS trigger LANGUAGE plpgsql
                SECURITY DEFINER SET search_path=pg_catalog AS $$
                BEGIN PERFORM realtime.emit_probe(NEW.payload); RETURN NEW; END $$;
                CREATE TRIGGER notify AFTER INSERT ON public.probe FOR EACH ROW EXECUTE FUNCTION public.notify_probe();
                GRANT INSERT ON public.probe TO authenticated;""")
            marker = 'broadcast-' + identity
            async with tenant.transaction():
                await tenant.execute('SET LOCAL ROLE authenticated')
                await tenant.execute('INSERT INTO public.probe VALUES($1)', marker)
            self.assertEqual(await tenant.fetchval('SELECT payload FROM realtime.messages'), marker)
            self.assertEqual(tuple(await admin.fetchrow("SELECT rolsuper,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user")), (False,False,False))
            self.assertFalse(await tenant.fetchval("SELECT has_schema_privilege($1,'realtime','USAGE')", reader))
            self.assertFalse(await tenant.fetchval("SELECT has_table_privilege($1,'realtime.messages','INSERT')", reader))
        finally:
            if admin:
                await admin.close()
            if tenant:
                await tenant.close()
            if created:
                await root.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
            for name in (reader, role):
                await root.execute(f'DROP ROLE IF EXISTS "{name}"')
            await root.close()

    async def test_existing_realtime_table_after_owner_transfer(self):
        await self.scenario(lazy=False)

    async def test_realtime_table_created_after_provisioning(self):
        await self.scenario(lazy=True)

if __name__ == '__main__':
    unittest.main()
