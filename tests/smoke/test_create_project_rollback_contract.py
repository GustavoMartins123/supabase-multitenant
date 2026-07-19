from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
GENERATE_IMPL = (
    ROOT / "servidor" / "generateProject" / "lib" / "generate_project_impl.sh"
)
DUPLICATE_IMPL = (
    ROOT / "servidor" / "generateProject" / "lib" / "duplicate_project_impl.sh"
)
COMMANDS = ROOT / "servidor" / "host-agent" / "hostagent" / "commands.py"
API_MAIN = ROOT / "servidor" / "api-internal" / "app" / "main.py"


class CreateRollbackContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.generate = GENERATE_IMPL.read_text(encoding="utf-8")
        self.duplicate = DUPLICATE_IMPL.read_text(encoding="utf-8")

    def test_drop_database_is_not_batched_with_terminate(self) -> None:
        broken_shape = (
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = '$CREATED_DB' AND pid <> pg_backend_pid(); "
            "DROP DATABASE"
        )
        self.assertNotIn(broken_shape, self.generate)
        self.assertNotIn("; DROP DATABASE IF EXISTS $NEW_DB;", self.duplicate)
        self.assertIn('"DROP DATABASE IF EXISTS \\"$db\\";"', self.generate)
        self.assertIn('"DROP DATABASE IF EXISTS \\"$NEW_DB\\";"', self.duplicate)

    def test_rollback_is_verified_and_reported(self) -> None:
        self.assertIn("HOST_AGENT_ROLLBACK_COMPLETE=1", self.generate)
        self.assertIn("HOST_AGENT_ROLLBACK_FAILED=1", self.generate)
        self.assertIn("SELECT count(*) FROM pg_database", self.generate)
        self.assertIn("pg_drop_replication_slot", self.generate)
        self.assertIn("ALLOW_CONNECTIONS false", self.generate)

    def test_failed_create_can_recover_known_stale_state(self) -> None:
        self.assertIn("cleanup_stale_state", self.generate)
        self.assertIn("STALE_TENANT_UUIDS", self.generate)
        self.assertIn("HOST_AGENT_STALE_STATE_RECOVERED=1", self.generate)

    def test_create_emits_incremental_progress_markers(self) -> None:
        source = COMMANDS.read_text(encoding="utf-8")
        expected = {
            "files_rendered",
            "database_created",
            "realtime_created",
            "supavisor_created",
            "services_started",
            "storage_verified",
        }
        for marker in expected:
            with self.subTest(marker=marker):
                self.assertIn(f"HOST_AGENT_PROGRESS=create:{marker}", self.generate)
                self.assertIn(f'"HOST_AGENT_PROGRESS=create:{marker}"', source)

    def test_running_create_reattaches_after_api_restart(self) -> None:
        source = API_MAIN.read_text(encoding="utf-8")
        self.assertIn(
            'RECOVERABLE_RUNNING_ACTIONS = IDEMPOTENT_ACTIONS | {"create"}',
            source,
        )
        self.assertIn("reuse_terminal=True", source)


if __name__ == "__main__":
    unittest.main()
