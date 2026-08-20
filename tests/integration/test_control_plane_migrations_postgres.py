"""Migrations do control plane contra um Postgres real.

Opt-in e destrutivo apenas em databases proprios: o teste cria dois databases
temporarios a partir do DSN administrativo informado, aplica as migrations e
remove tudo no final. Nenhum objeto do control plane em uso e tocado.

    export RUN_MIGRATIONS_INTEGRATION=1
    export MIGRATIONS_ADMIN_DSN=postgres://supabase_admin:...@127.0.0.1:5432/postgres
    python -m unittest tests.integration.test_control_plane_migrations_postgres -v

Rode dentro da imagem da Projects API ou em um host com `asyncpg` instalado.
"""

from __future__ import annotations

import os
import pathlib
import secrets
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# Estado minimo de uma instalacao que nasceu antes das migrations versionadas:
# `jobs` com seis colunas, `project_members.role` sem NOT NULL e `projects` sem
# tenant_uuid nem versionamento de chaves.
LEGACY_BOOTSTRAP = """
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE users (
    id UUID PRIMARY KEY,
    authelia_username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    source TEXT NOT NULL DEFAULT 'authelia',
    last_login_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    anon_key TEXT,
    service_role TEXT,
    config_token TEXT
);

CREATE TABLE project_members (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT,
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE jobs (
    job_id UUID PRIMARY KEY,
    project TEXT NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    message TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO users(id, authelia_username)
VALUES ('11111111-2222-4333-8444-555555555555', 'legacy_admin');

INSERT INTO projects(id, name, owner_id, anon_key)
VALUES (
    '99999999-8888-4777-8666-555555555555',
    'legacy_project',
    '11111111-2222-4333-8444-555555555555',
    'legacy-anon'
);

INSERT INTO project_members(project_id, user_id, role)
VALUES (
    '99999999-8888-4777-8666-555555555555',
    '11111111-2222-4333-8444-555555555555',
    NULL
);

INSERT INTO jobs(job_id, project, owner_id, status, updated_at)
VALUES (
    '77777777-6666-4555-8444-333333333333',
    'legacy_project',
    '11111111-2222-4333-8444-555555555555',
    'done',
    NULL
);
"""

SCHEMA_SNAPSHOT = """
SELECT 'COL '||table_name||'.'||column_name||' '||data_type
       ||' null='||is_nullable||' def='||coalesce(column_default, '-')
FROM information_schema.columns WHERE table_schema = 'public'
UNION ALL
SELECT 'IDX '||indexdef FROM pg_indexes WHERE schemaname = 'public'
UNION ALL
SELECT 'CON '||conrelid::regclass::text||' '||conname||' '
       ||pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
UNION ALL
SELECT 'TRG '||tgrelid::regclass::text||' '||tgname
FROM pg_trigger WHERE NOT tgisinternal
ORDER BY 1
"""


@unittest.skipUnless(
    os.getenv("RUN_MIGRATIONS_INTEGRATION") == "1",
    "defina RUN_MIGRATIONS_INTEGRATION=1 para exercitar um Postgres real",
)
class ControlPlaneMigrationsIntegrationTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin_dsn = os.getenv("MIGRATIONS_ADMIN_DSN", "").strip()
        if not cls.admin_dsn:
            raise unittest.SkipTest("MIGRATIONS_ADMIN_DSN e obrigatorio")
        try:
            import asyncpg  # noqa: F401
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise unittest.SkipTest("asyncpg nao esta instalado") from exc
        from app import schema_migrations

        cls.runner = schema_migrations
        cls.suffix = secrets.token_hex(4)

    async def asyncSetUp(self) -> None:
        import asyncpg

        self.asyncpg = asyncpg
        self.databases: list[str] = []
        self.admin = await asyncpg.connect(self.admin_dsn)
        self.addAsyncCleanup(self._drop_databases)

    async def _drop_databases(self) -> None:
        for name in self.databases:
            await self.admin.execute(f'DROP DATABASE IF EXISTS "{name}"')
        await self.admin.close()

    def _database_dsn(self, name: str) -> str:
        import urllib.parse

        parsed = urllib.parse.urlparse(self.admin_dsn)
        return urllib.parse.urlunparse(parsed._replace(path=f"/{name}"))

    async def _create_database(self, label: str):
        name = f"cp_migrations_{label}_{self.suffix}"
        await self.admin.execute(f'CREATE DATABASE "{name}"')
        self.databases.append(name)
        connection = await self.asyncpg.connect(self._database_dsn(name))
        self.addAsyncCleanup(connection.close)
        return connection

    async def _snapshot(self, connection) -> list[str]:
        return [row[0] for row in await connection.fetch(SCHEMA_SNAPSHOT)]

    async def test_clean_install_applies_every_version_once(self) -> None:
        connection = await self._create_database("clean")
        catalog = self.runner.discover_migrations()

        applied = await self.runner.apply_migrations(connection)
        self.assertEqual(
            [migration.version for migration in applied],
            [migration.version for migration in catalog],
        )

        ledger = await self.runner.read_ledger(connection)
        self.assertEqual(
            sorted(ledger), [migration.version for migration in catalog]
        )
        for migration in catalog:
            self.assertEqual(ledger[migration.version], migration.checksum)

        self.assertEqual(await self.runner.apply_migrations(connection), [])

    async def test_existing_install_converges_to_the_clean_schema(self) -> None:
        legacy = await self._create_database("legacy")
        await legacy.execute(LEGACY_BOOTSTRAP)
        clean = await self._create_database("target")

        await self.runner.apply_migrations(legacy)
        await self.runner.apply_migrations(clean)

        self.assertEqual(await self._snapshot(legacy), await self._snapshot(clean))

        self.assertEqual(
            await legacy.fetchval(
                "SELECT action FROM jobs WHERE job_id = $1",
                "77777777-6666-4555-8444-333333333333",
            ),
            "unknown",
        )
        self.assertIsNotNone(
            await legacy.fetchval(
                "SELECT updated_at FROM jobs WHERE job_id = $1",
                "77777777-6666-4555-8444-333333333333",
            )
        )
        self.assertEqual(
            await legacy.fetchval("SELECT role FROM project_members"), "member"
        )
        self.assertEqual(
            await legacy.fetchval(
                "SELECT project_uuid::text FROM jobs WHERE project = 'legacy_project'"
            ),
            "99999999-8888-4777-8666-555555555555",
        )

    async def test_new_rows_inherit_the_migrated_defaults(self) -> None:
        connection = await self._create_database("defaults")
        await self.runner.apply_migrations(connection)

        await connection.execute(
            "INSERT INTO users(id, authelia_username) VALUES($1, $2)",
            "22222222-3333-4444-8555-666666666666",
            "novo_admin",
        )
        project_id = await connection.fetchval(
            """
            INSERT INTO projects(name, owner_id) VALUES($1, $2)
            RETURNING id::text
            """,
            "projeto_novo",
            "22222222-3333-4444-8555-666666666666",
        )
        self.assertEqual(
            await connection.fetchval(
                "SELECT tenant_uuid::text FROM projects WHERE id = $1::uuid",
                project_id,
            ),
            project_id,
        )
        with self.assertRaises(self.asyncpg.PostgresError):
            await connection.execute(
                """
                INSERT INTO project_members(project_id, user_id, role)
                VALUES($1::uuid, $2::uuid, 'owner')
                """,
                project_id,
                "22222222-3333-4444-8555-666666666666",
            )

    async def test_edited_migration_is_refused(self) -> None:
        connection = await self._create_database("drift")
        catalog = self.runner.discover_migrations()
        await self.runner.apply_migrations(connection)

        edited = self.runner.Migration(
            version=catalog[-1].version,
            name=catalog[-1].name,
            path=catalog[-1].path,
            sql=catalog[-1].sql + "\n-- editada depois de aplicada\n",
            checksum="0" * 64,
        )
        with self.assertRaises(self.runner.SchemaMigrationError):
            await self.runner.apply_migrations(
                connection, migrations=catalog[:-1] + (edited,)
            )


if __name__ == "__main__":
    unittest.main()
