"""Guarda do delete_project_files contra containers vivos (LOG-11).

Remover o diretorio do projeto com containers ainda existentes corrompe
mounts e deixa lixo parcial: o handler do agent e o script recusam a
remocao enquanto houver container do projeto, incluindo daemon inacessivel.
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
    CommandContext,
    CommandOutcome,
    ProcessResult,
    RunningCommandState,
    handle_delete_project_files,
)
from hostagent.config import AgentConfig  # noqa: E402

DELETE_SCRIPT = ROOT / "servidor" / "generateProject" / "delete_project.sh"
COMMANDS_PATH = AGENT_ROOT / "hostagent" / "commands.py"
TENANT_UUID = "11111111-1111-4111-8111-111111111111"


def make_config(tmp: str) -> AgentConfig:
    base = Path(tmp)
    projects_root = base / "projects"
    (projects_root / "demo").mkdir(parents=True)
    (base / "backups").mkdir(parents=True)
    return AgentConfig(
        root=base,
        projects_root=projects_root,
        scripts_dir=base / "scripts",
        backups_root=base / "backups",
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


def make_ctx(config: AgentConfig) -> CommandContext:
    return CommandContext(
        config=config,
        state=RunningCommandState(),
        timeout_seconds=60,
        command="delete_project_files",
    )


class DeleteScriptGuardContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = DELETE_SCRIPT.read_text(encoding="utf-8")

    def test_script_lists_containers_before_rm(self) -> None:
        self.assertIn("docker ps -a", self.script)
        list_at = self.script.index("docker ps -a")
        rm_at = self.script.index('rm -rf "$PROJECT_DIR"')
        self.assertLess(list_at, rm_at)

    def test_script_refuses_when_project_containers_exist(self) -> None:
        self.assertIn("supabase-[a-z0-9]+-${PROJECT_ID}", self.script)
        self.assertIn("containers do projeto ainda existem", self.script)

    def test_script_fails_closed_when_docker_is_unavailable(self) -> None:
        self.assertIn("docker indisponivel", self.script)


class DeleteFilesGuardMappingTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = make_config(self.tmp.name)
        self.runner_calls: list = []

    async def fake_runner(self, *args: object, **kwargs: object):
        self.runner_calls.append((args, kwargs))
        return CommandOutcome(status="done", exit_code=0), ProcessResult(0, False, set())

    async def run_handler(self, ps: list[dict]) -> CommandOutcome:
        async def _ps() -> list[dict]:
            return ps

        with (
            mock.patch("hostagent.commands.docker_ps_all", _ps),
            mock.patch(
                "hostagent.commands._run_lifecycle_script", self.fake_runner
            ),
        ):
            return await handle_delete_project_files(
                make_ctx(self.config),
                "demo",
                {"tenant_uuid": TENANT_UUID},
            )

    async def test_living_containers_block_removal(self) -> None:
        outcome = await self.run_handler([{"Names": "supabase-nginx-demo"}])
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_code, "project_containers_present")
        self.assertIn("supabase-nginx-demo", outcome.message or "")
        self.assertEqual(self.runner_calls, [])

    async def test_unrelated_containers_do_not_block(self) -> None:
        outcome = await self.run_handler([{"Names": "supabase-nginx-other"}])
        self.assertEqual(outcome.status, "done")
        self.assertEqual(len(self.runner_calls), 1)
        self.assertTrue(outcome.result["backups_removed"] is False)

    async def test_docker_failure_blocks_removal(self) -> None:
        async def _boom() -> list[dict]:
            raise RuntimeError("docker ps falhou: 1")

        with (
            mock.patch("hostagent.commands.docker_ps_all", _boom),
            mock.patch(
                "hostagent.commands._run_lifecycle_script", self.fake_runner
            ),
        ):
            with self.assertRaises(RuntimeError):
                await handle_delete_project_files(
                    make_ctx(self.config),
                    "demo",
                    {"tenant_uuid": TENANT_UUID},
                )
        self.assertEqual(self.runner_calls, [])


if __name__ == "__main__":
    unittest.main()
