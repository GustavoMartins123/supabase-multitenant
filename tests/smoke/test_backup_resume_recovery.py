"""Resume apos quiesce em backup/restore (LOG-09).

Falha transitoria ao reativar o tenant Storage ou religar containers nao
pode deixar o projeto parado em silencio: o script tenta de novo com
backoff limitado, emite marker legivel por maquina e o agent converte o
marker em error_code/resultado distintos.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
sys.path.insert(0, str(AGENT_ROOT))

from hostagent.commands import (  # noqa: E402
    SERVICES_RESTART_FAILED_MARKER,
    STORAGE_RESUME_FAILED_MARKER,
    CommandContext,
    CommandOutcome,
    ProcessResult,
    RunningCommandState,
    handle_backup_project,
    handle_restore_project,
)
from hostagent.config import AgentConfig  # noqa: E402

BACKUP_SCRIPT = (
    ROOT / "servidor" / "generateProject" / "lib" / "backup_project_impl.sh"
)
COMMANDS_PATH = AGENT_ROOT / "hostagent" / "commands.py"

PROJECT_UUID = "11111111-1111-4111-8111-111111111111"
BACKUP_ID = "22222222-2222-4222-8222-222222222222"
SAFETY_ID = "33333333-3333-4333-8333-333333333333"


def make_config(tmp: str) -> AgentConfig:
    base = Path(tmp)
    projects_root = base / "projects"
    (projects_root / "demo").mkdir(parents=True)
    (projects_root / "demo" / ".env").write_text(
        f"PROJECT_UUID={PROJECT_UUID}\n", encoding="utf-8"
    )
    backups_root = base / "backups"
    backups_root.mkdir(parents=True)
    return AgentConfig(
        root=base,
        projects_root=projects_root,
        scripts_dir=base / "scripts",
        backups_root=backups_root,
        dsn="postgresql://u:p@localhost:5432/db",
        hmac_secret="x" * 32,
        worker_id="test-worker",
        poll_interval=2.0,
        heartbeat_interval=15.0,
        lease_seconds=60,
        state_refresh_interval=10.0,
        max_parallel_commands=3,
        shutdown_grace=300,
        schema_wait_timeout=180.0,
        db_command_timeout=30.0,
    )


def make_ctx(config: AgentConfig, command: str) -> CommandContext:
    return CommandContext(
        config=config,
        state=RunningCommandState(),
        timeout_seconds=60,
        command=command,
    )


def stub_runner(outcome: CommandOutcome, markers: set[str]):
    async def _run(*args: object, **kwargs: object):
        return outcome, ProcessResult(1, False, set(markers))

    return _run


class BackupScriptResumeContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = BACKUP_SCRIPT.read_text(encoding="utf-8")
        cls.commands = COMMANDS_PATH.read_text(encoding="utf-8")

    def test_resume_and_restart_retry_with_bounded_backoff(self) -> None:
        for fn in ("resume_storage_tenant", "restart_stopped"):
            body = self.script.split(f"{fn}() {{", 1)[1].split("\n}\n", 1)[0]
            self.assertIn("RESUME_MAX_ATTEMPTS", body)
            self.assertIn("sleep", body)
            self.assertIn("attempt=$((attempt + 1))", body)

    def test_failed_resume_emits_machine_readable_markers(self) -> None:
        on_error = self.script.split("on_error() {", 1)[1].split("\nexit ", 1)[0]
        self.assertIn("HOST_AGENT_STORAGE_RESUME_FAILED=1", on_error)
        self.assertIn("HOST_AGENT_SERVICES_RESTART_FAILED=1", on_error)

    def test_agent_watches_the_resume_markers(self) -> None:
        self.assertIn("STORAGE_RESUME_FAILED_MARKER", self.commands)
        self.assertIn("SERVICES_RESTART_FAILED_MARKER", self.commands)
        self.assertIn("backup_resume_failed", self.commands)

    def test_restore_watches_rollback_incomplete(self) -> None:
        self.assertIn('"ROLLBACK_INCOMPLETE"', self.commands)
        self.assertIn("restore_rollback_incomplete", self.commands)


class BackupResumeMappingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)

    async def run_backup(self, markers: set[str]) -> CommandOutcome:
        outcome = CommandOutcome(status="failed", error_code="backup_failed")
        with mock.patch(
            "hostagent.commands._run_lifecycle_script",
            new=stub_runner(outcome, markers),
        ):
            return await handle_backup_project(
                make_ctx(self.config, "backup_project"),
                "demo",
                {"backup_id": BACKUP_ID},
            )

    async def test_storage_resume_failure_gets_distinct_error(self) -> None:
        outcome = await self.run_backup({STORAGE_RESUME_FAILED_MARKER})
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_code, "backup_resume_failed")
        self.assertTrue(outcome.result["storage_resume_failed"])
        self.assertFalse(outcome.result["services_restart_failed"])
        self.assertIn("bloqueado", outcome.message)

    async def test_restart_failure_gets_distinct_error(self) -> None:
        outcome = await self.run_backup({SERVICES_RESTART_FAILED_MARKER})
        self.assertEqual(outcome.error_code, "backup_resume_failed")
        self.assertFalse(outcome.result["storage_resume_failed"])
        self.assertTrue(outcome.result["services_restart_failed"])
        self.assertIn("desligados", outcome.message)

    async def test_plain_failure_keeps_generic_error(self) -> None:
        outcome = await self.run_backup(set())
        self.assertEqual(outcome.error_code, "backup_failed")
        self.assertFalse(outcome.result["storage_resume_failed"])
        self.assertFalse(outcome.result["services_restart_failed"])


class RestoreRollbackMappingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)
        point = (
            self.config.backups_root / PROJECT_UUID / BACKUP_ID
        )
        point.mkdir(parents=True)
        (point / "manifest.json").write_text("{}", encoding="utf-8")

    async def run_restore(self, markers: set[str]) -> CommandOutcome:
        outcome = CommandOutcome(status="failed", error_code="restore_failed")
        with mock.patch(
            "hostagent.commands._run_lifecycle_script",
            new=stub_runner(outcome, markers),
        ):
            return await handle_restore_project(
                make_ctx(self.config, "restore_project"),
                "demo",
                {
                    "backup_id": BACKUP_ID,
                    "safety_backup_id": SAFETY_ID,
                },
            )

    async def test_incomplete_rollback_gets_distinct_error(self) -> None:
        outcome = await self.run_restore({"ROLLBACK_INCOMPLETE"})
        self.assertEqual(outcome.error_code, "restore_rollback_incomplete")
        self.assertTrue(outcome.result["rollback_incomplete"])
        self.assertIn("intervencao manual", outcome.message)

    async def test_complete_rollback_keeps_existing_mapping(self) -> None:
        outcome = await self.run_restore({"ROLLBACK_COMPLETE"})
        self.assertEqual(outcome.error_code, "restore_rolled_back")
        self.assertTrue(outcome.result["rolled_back"])
        self.assertFalse(outcome.result["rollback_incomplete"])


if __name__ == "__main__":
    unittest.main()
