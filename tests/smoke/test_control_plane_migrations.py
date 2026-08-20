"""Contratos das migrations versionadas do control plane.

O boot da Projects API nao pode alterar schema: ele apenas confere o ledger.
Estes testes travam essa fronteira sem tocar em banco nem em rede.
"""

from __future__ import annotations

import importlib
import pathlib
import re
import sys
import tempfile
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
APP = API_ROOT / "app"
MIGRATIONS = APP / "migrations"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _load_runner() -> types.ModuleType:
    """Importa o runner sem exigir o driver, e sem deixar stub para tras."""

    try:
        import asyncpg  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("asyncpg")
        stub.Pool = object
        stub.Connection = object
        stub.Record = dict
        stub.PostgresError = type("PostgresError", (Exception,), {})
        stub.connect = None
        stub.create_pool = None
        sys.modules["asyncpg"] = stub
        try:
            return importlib.import_module("app.schema_migrations")
        finally:
            sys.modules.pop("asyncpg", None)
    return importlib.import_module("app.schema_migrations")


schema_migrations = _load_runner()

APPLY_COMMAND = schema_migrations.APPLY_COMMAND
LEDGER_TABLE = schema_migrations.LEDGER_TABLE
MIGRATION_ADVISORY_LOCK_KEY = schema_migrations.MIGRATION_ADVISORY_LOCK_KEY
Migration = schema_migrations.Migration
SchemaMigrationError = schema_migrations.SchemaMigrationError
discover_migrations = schema_migrations.discover_migrations
_drifted = schema_migrations._drifted
_pending = schema_migrations._pending

SCHEMA_DDL = re.compile(
    r"\b(CREATE\s+TABLE|ALTER\s+TABLE|CREATE\s+(UNIQUE\s+)?INDEX"
    r"|CREATE\s+TRIGGER|CREATE\s+EXTENSION"
    r"|CREATE\s+OR\s+REPLACE\s+FUNCTION)\b",
    re.IGNORECASE,
)

CONTROL_PLANE_TABLES = (
    "users",
    "user_groups",
    "user_group_audit",
    "projects",
    "project_members",
    "project_members_audit",
    "project_key_envelopes",
    "project_api_key_slots",
    "project_api_keys",
    "project_api_key_reveals",
    "jobs",
    "host_agent_workers",
    "host_agent_commands",
    "project_container_state",
    "studio_project_tags",
    "studio_project_tag_assignments",
    "studio_project_notes",
    "studio_project_hints",
    "studio_project_thread_messages",
    "studio_project_notifications",
    "studio_audit_log",
    "project_name_history",
    "project_restore_points",
    "studio_step_up_grant_consumptions",
)


def _write_migrations(directory: pathlib.Path, names: dict[str, str]) -> None:
    for name, body in names.items():
        (directory / name).write_text(body, encoding="utf-8")


class MigrationCatalogTest(unittest.TestCase):
    def test_repository_catalog_is_a_contiguous_versioned_sequence(self) -> None:
        catalog = discover_migrations()
        self.assertGreaterEqual(len(catalog), 3)
        self.assertEqual(
            [migration.version for migration in catalog],
            [f"{index:04d}" for index in range(1, len(catalog) + 1)],
        )
        self.assertEqual(catalog[0].name, "control_plane_baseline")
        for migration in catalog:
            with self.subTest(migration=migration.label):
                self.assertEqual(len(migration.checksum), 64)
                self.assertTrue(migration.sql.strip())

    def test_checksum_follows_the_file_content(self) -> None:
        catalog = discover_migrations()
        with tempfile.TemporaryDirectory() as raw:
            directory = pathlib.Path(raw)
            _write_migrations(
                directory, {"0001_baseline.sql": catalog[0].sql}
            )
            self.assertEqual(
                discover_migrations(directory)[0].checksum,
                catalog[0].checksum,
            )
            _write_migrations(
                directory, {"0001_baseline.sql": catalog[0].sql + "\n-- x\n"}
            )
            self.assertNotEqual(
                discover_migrations(directory)[0].checksum,
                catalog[0].checksum,
            )

    def test_invalid_catalogs_are_rejected(self) -> None:
        cases = {
            "nome fora do padrao": {"baseline.sql": "SELECT 1;"},
            "buraco na sequencia": {
                "0001_a.sql": "SELECT 1;",
                "0003_b.sql": "SELECT 1;",
            },
            "arquivo vazio": {"0001_a.sql": "   \n"},
        }
        for label, files in cases.items():
            with self.subTest(case=label):
                with tempfile.TemporaryDirectory() as raw:
                    directory = pathlib.Path(raw)
                    _write_migrations(directory, files)
                    with self.assertRaises(SchemaMigrationError):
                        discover_migrations(directory)

    def test_empty_directory_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(SchemaMigrationError):
                discover_migrations(pathlib.Path(raw))


class LedgerContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = discover_migrations()
        self.runner = (APP / "schema_migrations.py").read_text(encoding="utf-8")

    def _migration(self, version: str, checksum: str) -> Migration:
        return Migration(
            version=version,
            name="x",
            path=pathlib.Path("x"),
            sql="SELECT 1;",
            checksum=checksum,
        )

    def test_pending_and_drift_are_computed_from_the_ledger(self) -> None:
        first = self._migration("0001", "a" * 64)
        second = self._migration("0002", "b" * 64)
        catalog = (first, second)
        self.assertEqual(_pending(catalog, {}), [first, second])
        self.assertEqual(
            _pending(catalog, {"0001": "a" * 64}), [second]
        )
        self.assertEqual(_drifted(catalog, {"0001": "a" * 64}), [])
        self.assertEqual(
            _drifted(catalog, {"0001": "c" * 64}), [first]
        )

    def test_ledger_is_dedicated_to_the_control_plane(self) -> None:
        self.assertEqual(LEDGER_TABLE, "control_plane_schema_migrations")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS {LEDGER_TABLE}", self.runner
        )
        for column in ("version", "checksum", "applied_at", "applied_by"):
            with self.subTest(column=column):
                self.assertIn(column, self.runner)

    def test_apply_serializes_with_an_advisory_lock_and_releases_it(self) -> None:
        self.assertIsInstance(MIGRATION_ADVISORY_LOCK_KEY, int)
        self.assertLess(MIGRATION_ADVISORY_LOCK_KEY, 2**63)
        apply_body = self.runner[
            self.runner.index("async def apply_migrations") :
            self.runner.index("async def verify_control_plane_schema")
        ]
        self.assertIn("pg_advisory_lock($1)", apply_body)
        self.assertIn("pg_advisory_unlock($1)", apply_body)
        self.assertIn("finally:", apply_body)
        self.assertIn("async with conn.transaction():", apply_body)

    def test_verification_never_writes_to_the_database(self) -> None:
        verify_body = self.runner[
            self.runner.index("async def verify_control_plane_schema") :
            self.runner.index("async def _connect_pool")
        ]
        self.assertNotIn("execute(", verify_body)
        self.assertIn("raise SchemaMigrationError", verify_body)
        self.assertIn("{APPLY_COMMAND}", verify_body)
        self.assertIn("unknown_versions", verify_body)
        self.assertEqual(APPLY_COMMAND, "python -m app.schema_migrations apply")


class StartupDoesNotMigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main = (APP / "main.py").read_text(encoding="utf-8")
        self.startup = self.main[
            self.main.index('@app.on_event("startup")') :
            self.main.index('@app.on_event("shutdown")')
        ]

    def test_startup_only_verifies_the_schema_version(self) -> None:
        self.assertIn("await verify_control_plane_schema(pool)", self.startup)
        self.assertNotIn("ensure_identity_schema", self.main)
        self.assertNotIn("ensure_jobs_schema", self.main)
        self.assertNotIn("ensure_host_agent_schema", self.main)
        self.assertNotIn("ensure_opaque_key_schema", self.main)
        self.assertNotIn("ensure_collaboration_schema", self.main)
        self.assertNotIn("ensure_restore_points_schema", self.main)
        self.assertNotIn("ensure_step_up_auth_schema", self.main)
        self.assertNotIn("ensure_project_secrets_schema", self.main)

    def test_runtime_process_does_not_provision_database_identities(self) -> None:
        self.assertNotIn("ensure_key_authorizer_role", self.main)
        self.assertNotIn("KEY_AUTHORIZER_DB_PASSWORD", self.main)
        roles = (APP / "control_plane_roles.py").read_text(encoding="utf-8")
        self.assertIn("ensure_key_authorizer_role", roles)
        self.assertIn(
            "from app.control_plane_roles import ensure_key_authorizer_role",
            (APP / "schema_migrations.py").read_text(encoding="utf-8"),
        )

    def test_no_application_module_carries_schema_ddl(self) -> None:
        offenders: list[str] = []
        for path in sorted(APP.rglob("*.py")):
            if path.name == "schema_migrations.py":
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if SCHEMA_DDL.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()}")
        self.assertEqual(
            offenders,
            [],
            "DDL de schema pertence a app/migrations:\n" + "\n".join(offenders),
        )

    def test_runner_ddl_is_limited_to_its_own_ledger(self) -> None:
        runner = (APP / "schema_migrations.py").read_text(encoding="utf-8")
        matches = [
            line.strip()
            for line in runner.splitlines()
            if SCHEMA_DDL.search(line)
        ]
        self.assertEqual(
            matches, ["CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} ("]
        )


class SchemaOwnershipTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog_sql = "\n".join(
            migration.sql for migration in discover_migrations()
        )
        self.bootstrap = (
            ROOT / "servidor/volumes/db/create_template.sh"
        ).read_text(encoding="utf-8")

    def test_every_control_plane_table_is_created_by_a_migration(self) -> None:
        for table in CONTROL_PLANE_TABLES:
            with self.subTest(table=table):
                self.assertIn(
                    f"CREATE TABLE IF NOT EXISTS {table}", self.catalog_sql
                )

    def test_historic_bootstrap_keeps_only_cluster_objects(self) -> None:
        for table in CONTROL_PLANE_TABLES:
            with self.subTest(table=table):
                self.assertNotIn(
                    f"CREATE TABLE IF NOT EXISTS {table}", self.bootstrap
                )
        self.assertNotIn("CREATE ROLE key_authorizer", self.bootstrap)
        self.assertNotIn("TO key_authorizer", self.bootstrap)
        self.assertIn("_supabase_template", self.bootstrap)
        self.assertIn("meta_guest", self.bootstrap)

    def test_legacy_installs_converge_to_the_canonical_jobs_table(self) -> None:
        self.assertIn("ALTER TABLE jobs ALTER COLUMN action SET NOT NULL", self.catalog_sql)
        self.assertIn("jobs_progress_check", self.catalog_sql)
        self.assertIn("jobs_total_steps_check", self.catalog_sql)
        self.assertIn("jobs_attempt_check", self.catalog_sql)

    def test_operator_tools_do_not_create_schema(self) -> None:
        secrets_tool = (APP / "migrate_project_secrets.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("async def assert_schema(", secrets_tool)
        self.assertIn("to_regclass('public.project_key_envelopes')", secrets_tool)


class DeployWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.compose = (
            ROOT / "servidor" / "docker-compose-api.yml"
        ).read_text(encoding="utf-8")
        self.start = (ROOT / "start.sh").read_text(encoding="utf-8")

    def _service(self, name: str) -> str:
        start = self.compose.index(f"\n  {name}:\n")
        remainder = self.compose[start + 1 :]
        following = re.search(r"\n  [a-z][a-z0-9-]*:\n", remainder)
        return remainder[: following.start()] if following else remainder

    def test_migrations_run_in_a_dedicated_one_shot_service(self) -> None:
        migrator = self._service("control-plane-migrations")
        self.assertIn(
            '["python", "-m", "app.schema_migrations", "apply"]', migrator
        )
        self.assertIn('restart: "no"', migrator)
        self.assertIn("KEY_AUTHORIZER_DB_PASSWORD", migrator)
        self.assertIn("${POSTGRES_USER}", migrator)
        self.assertIn("read_only: true", migrator)
        self.assertIn("no-new-privileges:true", migrator)

    def test_runtime_services_start_only_after_a_successful_migration(self) -> None:
        for service in ("projects-api", "key-authorizer"):
            with self.subTest(service=service):
                block = self._service(service)
                self.assertIn("depends_on:", block)
                self.assertIn("control-plane-migrations:", block)
                self.assertIn(
                    "condition: service_completed_successfully", block
                )

    def test_projects_api_no_longer_receives_the_role_password(self) -> None:
        self.assertNotIn(
            "KEY_AUTHORIZER_DB_PASSWORD", self._service("projects-api")
        )

    def test_start_script_migrates_before_the_api_comes_up(self) -> None:
        database = self.start.index("Aguardando o banco de dados ficar pronto")
        migrate = self.start.index("Aplicando migrations do control plane")
        api_up = self.start.index('"${API_COMPOSE[@]}" up --build -d')
        storage = self.start.index("Aguardando Storage compartilhado")
        self.assertLess(database, migrate)
        self.assertLess(migrate, api_up)
        self.assertLess(api_up, storage)


if __name__ == "__main__":
    unittest.main()
