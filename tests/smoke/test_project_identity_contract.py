from __future__ import annotations

import sys
import tempfile
import types
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")
    asyncpg_stub.Pool = object
    sys.modules["asyncpg"] = asyncpg_stub

from app.project_identity import (  # noqa: E402
    ProjectIdentityConflict,
    ProjectIdentityError,
    get_job_project_identity,
    parse_tenant_uuid,
    read_project_tenant_uuid,
    reconcile_project_tenant_uuids,
)


class _FakePool:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.updates: list[tuple[uuid.UUID, uuid.UUID]] = []
        self.query = ""

    async def fetch(self, query: str) -> list[dict]:
        self.query = query
        return self.rows

    async def executemany(self, _query: str, updates) -> None:
        self.updates.extend(updates)


class _FakeJobPool:
    def __init__(self, row: dict | None) -> None:
        self.row = row
        self.executions: list[tuple[uuid.UUID, uuid.UUID]] = []

    async def fetchrow(self, _query: str, _job_id: uuid.UUID):
        return self.row

    async def execute(
        self,
        _query: str,
        project_id: uuid.UUID,
        tenant_uuid: uuid.UUID,
    ) -> None:
        self.executions.append((project_id, tenant_uuid))


class ProjectJobIdentityTest(unittest.IsolatedAsyncioTestCase):
    async def test_job_backfills_mapping_from_its_durable_payload(self) -> None:
        project_id = uuid.uuid4()
        tenant_uuid = uuid.uuid4()
        pool = _FakeJobPool(
            {
                "project_uuid": project_id,
                "payload": {"tenant_uuid": str(tenant_uuid)},
                "tenant_uuid": None,
                "command_tenant_uuid": None,
            }
        )

        resolved = await get_job_project_identity(pool, str(uuid.uuid4()))

        self.assertEqual(resolved, (project_id, tenant_uuid))
        self.assertEqual(pool.executions, [(project_id, tenant_uuid)])

    async def test_job_rejects_divergent_persisted_and_command_identity(self) -> None:
        project_id = uuid.uuid4()
        pool = _FakeJobPool(
            {
                "project_uuid": project_id,
                "payload": {},
                "tenant_uuid": uuid.uuid4(),
                "command_tenant_uuid": str(uuid.uuid4()),
            }
        )

        with self.assertRaises(ProjectIdentityError):
            await get_job_project_identity(pool, str(uuid.uuid4()))

        self.assertEqual(pool.executions, [])


class ProjectIdentityMigrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_legacy_project_is_backfilled_from_env(self) -> None:
        project_id = uuid.uuid4()
        legacy_tenant = uuid.uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir)
            project_dir = projects_root / "legado"
            project_dir.mkdir()
            (project_dir / ".env").write_text(
                f"PROJECT_UUID={legacy_tenant}\n",
                encoding="utf-8",
            )
            pool = _FakePool(
                [
                    {
                        "id": project_id,
                        "name": "legado",
                        "tenant_uuid": None,
                        "is_provisioned": True,
                        "command_tenant_uuid": None,
                    }
                ]
            )

            result = await reconcile_project_tenant_uuids(pool, projects_root)

        self.assertEqual(pool.updates, [(project_id, legacy_tenant)])
        self.assertEqual(result.migrated, 1)
        self.assertEqual(result.unresolved, ())

    async def test_pending_project_adopts_its_canonical_id(self) -> None:
        project_id = uuid.uuid4()
        pool = _FakePool(
            [
                {
                    "id": project_id,
                    "name": "pendente",
                    "tenant_uuid": None,
                    "is_provisioned": False,
                    "command_tenant_uuid": None,
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            result = await reconcile_project_tenant_uuids(pool, Path(temp_dir))

        self.assertEqual(pool.updates, [(project_id, project_id)])
        self.assertEqual(result.migrated, 1)

    async def test_conflicting_env_and_command_fail_before_updates(self) -> None:
        project_id = uuid.uuid4()
        env_tenant = uuid.uuid4()
        command_tenant = uuid.uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir)
            project_dir = projects_root / "conflito"
            project_dir.mkdir()
            (project_dir / ".env").write_text(
                f"PROJECT_UUID={env_tenant}\n",
                encoding="utf-8",
            )
            pool = _FakePool(
                [
                    {
                        "id": project_id,
                        "name": "conflito",
                        "tenant_uuid": None,
                        "is_provisioned": True,
                        "command_tenant_uuid": str(command_tenant),
                    }
                ]
            )

            with self.assertRaises(ProjectIdentityConflict):
                await reconcile_project_tenant_uuids(pool, projects_root)

        self.assertEqual(pool.updates, [])

    async def test_project_with_artifacts_but_no_identity_stays_unresolved(self) -> None:
        project_id = uuid.uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            projects_root = Path(temp_dir)
            (projects_root / "incompleto").mkdir()
            pool = _FakePool(
                [
                    {
                        "id": project_id,
                        "name": "incompleto",
                        "tenant_uuid": None,
                        "is_provisioned": False,
                        "command_tenant_uuid": None,
                    }
                ]
            )

            result = await reconcile_project_tenant_uuids(pool, projects_root)

        self.assertEqual(pool.updates, [])
        self.assertEqual(result.unresolved, ("incompleto",))

    def test_env_reader_is_confined_and_validates_uuid(self) -> None:
        tenant_uuid = uuid.uuid4()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            project = root / "seguro"
            project.mkdir()
            (project / ".env").write_text(
                f"PROJECT_UUID={tenant_uuid}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                read_project_tenant_uuid(root, "seguro"),
                tenant_uuid,
            )
            self.assertIsNone(read_project_tenant_uuid(root, "../escape"))
            self.assertIsNone(parse_tenant_uuid("nao-e-uuid"))


class ProjectIdentitySourceContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.schema = (API_ROOT / "app" / "database_schema.py").read_text(
            encoding="utf-8"
        )

    def test_new_projects_use_one_uuid_for_project_and_tenant(self) -> None:
        self.assertGreaterEqual(
            self.main.count("VALUES($1, $1, $2, $3)"),
            2,
        )
        self.assertGreaterEqual(
            self.main.count('"tenant_uuid": str(project_id)'),
            2,
        )

    def test_background_workers_never_generate_the_tenant_uuid(self) -> None:
        duplicate = self.main.split("async def _duplicate_and_store_keys", 1)[1]
        duplicate = duplicate.split("def _base64url_no_padding", 1)[0]
        create = self.main.split("async def _provision_and_store_keys", 1)[1]
        create = create.split("async def get_project_containers", 1)[0]
        self.assertNotIn("uuid.uuid4()", duplicate)
        self.assertNotIn("uuid.uuid4()", create)
        self.assertIn("_get_job_project_identity", duplicate)
        self.assertIn("_get_job_project_identity", create)

    def test_schema_persists_unique_tenant_mapping_with_insert_guard(self) -> None:
        self.assertIn("ADD COLUMN IF NOT EXISTS tenant_uuid UUID", self.schema)
        self.assertIn("idx_projects_tenant_uuid_unique", self.schema)
        self.assertIn("projects_default_tenant_uuid", self.schema)
        self.assertIn("reconcile_project_tenant_uuids", self.main)


if __name__ == "__main__":
    unittest.main()
