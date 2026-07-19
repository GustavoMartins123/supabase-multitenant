"""Contrato do host-agent: comandos fechados, HMAC, paths e sanitizacao.

Fixa as garantias do P0 estrutural: a Projects API nao executa Docker nem
shell; toda execucao fisica passa pelo host-agent com assinatura HMAC,
reautorizacao, confinamento de paths e saida sanitizada.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
API_ROOT = ROOT / "servidor" / "api-internal"

for path in (str(AGENT_ROOT), str(API_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from hostagent import host_agent_protocol as protocol
from hostagent.commands import COMMAND_HANDLERS
from hostagent.security import PathConfinementError, resolve_project_dir

try:
    import asyncpg as _asyncpg  # noqa: F401
except ModuleNotFoundError:
    asyncpg_stub = types.ModuleType("asyncpg")

    class _PostgresError(Exception):
        pass

    asyncpg_stub.PostgresError = _PostgresError
    asyncpg_stub.connect = None
    sys.modules["asyncpg"] = asyncpg_stub
    try:
        from hostagent import db as agent_db
    finally:
        sys.modules.pop("asyncpg", None)
else:
    from hostagent import db as agent_db


class ProtocolCopiesAreIdenticalTest(unittest.TestCase):
    def test_api_and_agent_share_the_same_protocol_bytes(self) -> None:
        agent_copy = (AGENT_ROOT / "hostagent" / "host_agent_protocol.py").read_bytes()
        api_copy = (API_ROOT / "app" / "host_agent_protocol.py").read_bytes()
        self.assertEqual(
            agent_copy,
            api_copy,
            "As copias do host_agent_protocol.py divergiram; sincronize-as.",
        )


class SystemdInstallerContractTest(unittest.TestCase):
    def test_unit_quotes_paths_that_may_contain_spaces(self) -> None:
        template = (
            AGENT_ROOT / "supabase-host-agent.service"
        ).read_text(encoding="utf-8")
        self.assertIn('Environment="HOST_AGENT_ROOT=__SERVIDOR_DIR__"', template)
        self.assertIn(
            'ExecStart="__AGENT_DIR__/.venv/bin/python" '
            '-m hostagent --root "__SERVIDOR_DIR__"',
            template,
        )
        self.assertIn(
            'ExecStartPre="__AGENT_DIR__/.venv/bin/python" '
            '-m hostagent --root "__SERVIDOR_DIR__" --wait-for-schema',
            template,
        )
        self.assertIn("TimeoutStartSec=0", template)
        self.assertIn("WorkingDirectory=__AGENT_DIR__", template)

    def test_installer_shell_syntax_and_systemd_escaping(self) -> None:
        installer = AGENT_ROOT / "install.sh"
        bash = shutil.which("bash") or "bash"
        if os.name == "nt":
            git_bash = (
                pathlib.Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
                / "Git"
                / "bin"
                / "bash.exe"
            )
            if git_bash.is_file():
                bash = str(git_bash)
        subprocess.run([bash, "-n", str(installer)], check=True)
        source = installer.read_text(encoding="utf-8")
        self.assertIn("escape_systemd_value", source)
        self.assertIn("escape_sed_replacement", source)
        self.assertIn('render_unit "$SERVIDOR_DIR" "$AGENT_DIR" "$UNIT_PATH"', source)
        self.assertIn("HOST_AGENT_INSTALL_SCHEMA_WAIT_TIMEOUT", source)
        self.assertIn("--wait-for-schema", source)

        with tempfile.TemporaryDirectory(prefix="host agent % & ") as temp_dir:
            root = pathlib.Path(temp_dir)
            servidor_dir = root / "servidor com espaco"
            agent_dir = AGENT_ROOT
            rendered = root / "rendered.service"
            servidor_dir.mkdir()
            subprocess.run(
                [
                    bash,
                    "-c",
                    'source "$1"; render_unit "$2" "$3" "$4"',
                    "bash",
                    str(installer),
                    str(servidor_dir),
                    str(agent_dir),
                    str(rendered),
                ],
                check=True,
            )
            unit = rendered.read_text(encoding="utf-8")
            escaped_servidor = (
                str(servidor_dir).replace("\\", "\\\\").replace("%", "%%")
            )
            escaped_workdir = (
                str(agent_dir).replace("\\", "\\\\").replace("%", "%%")
            )
            self.assertIn(
                f'Environment="HOST_AGENT_ROOT={escaped_servidor}"',
                unit,
            )
            self.assertIn(f'--root "{escaped_servidor}"', unit)
            self.assertIn(f"WorkingDirectory={escaped_workdir}", unit)


class SchemaReadinessTest(unittest.IsolatedAsyncioTestCase):
    async def test_schema_probe_checks_all_agent_tables_and_closes_connection(
        self,
    ) -> None:
        connection = mock.AsyncMock()
        connection.fetchval.return_value = True

        with mock.patch.object(
            agent_db.asyncpg,
            "connect",
            new=mock.AsyncMock(return_value=connection),
        ) as connect:
            ready = await agent_db.host_agent_schema_ready("postgresql://db")

        self.assertTrue(ready)
        connect.assert_awaited_once_with("postgresql://db", timeout=5)
        query = connection.fetchval.await_args.args[0]
        self.assertIn("host_agent_workers", query)
        self.assertIn("host_agent_commands", query)
        self.assertIn("project_container_state", query)
        connection.close.assert_awaited_once()

    async def test_schema_wait_retries_until_api_schema_is_ready(self) -> None:
        probe = mock.AsyncMock(side_effect=[False, True])
        with (
            mock.patch.object(agent_db, "host_agent_schema_ready", probe),
            mock.patch.object(agent_db.asyncio, "sleep", new=mock.AsyncMock()),
        ):
            await agent_db.wait_for_host_agent_schema(
                "postgresql://db",
                timeout=1,
                poll_interval=0.1,
            )

        self.assertEqual(probe.await_count, 2)

    async def test_zero_timeout_still_probes_once_then_fails(self) -> None:
        probe = mock.AsyncMock(return_value=False)
        with mock.patch.object(agent_db, "host_agent_schema_ready", probe):
            with self.assertRaises(agent_db.HostAgentSchemaTimeout):
                await agent_db.wait_for_host_agent_schema(
                    "postgresql://db",
                    timeout=0,
                )

        probe.assert_awaited_once_with("postgresql://db")


class ClosedCommandSetTest(unittest.TestCase):
    def test_registry_matches_protocol_and_every_command_has_timeout(self) -> None:
        self.assertEqual(set(COMMAND_HANDLERS), protocol.HOST_AGENT_COMMANDS)
        for command in protocol.HOST_AGENT_COMMANDS:
            self.assertGreater(protocol.COMMAND_TIMEOUTS[command], 0)

    def test_initial_command_order_is_covered(self) -> None:
        expected = {
            "start_project",
            "stop_project",
            "restart_project",
            "recreate_services",
            "create_project",
            "duplicate_project",
            "delete_project_containers",
            "delete_project_files",
            "rotate_keys",
            "rename_project",
        }
        self.assertLessEqual(expected, protocol.HOST_AGENT_COMMANDS)

    def test_unknown_command_is_rejected(self) -> None:
        errors = protocol.validate_command_args("run_shell", "meuprojeto", {})
        self.assertEqual(errors, ["unknown_command:run_shell"])

    def test_args_validation_rejects_injection_shapes(self) -> None:
        cases = [
            ("start_project", "meu-projeto; rm -rf /", {}),
            ("start_project", "../escape", {}),
            ("create_project", "meuprojeto", {"tenant_uuid": "x; whoami"}),
            ("create_project", "meuprojeto", {
                "tenant_uuid": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
                "recover_stale": "true",
            }),
            ("create_project", "meuprojeto", {
                "tenant_uuid": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
                "stale_tenant_uuids": ["../escape"],
            }),
            ("recreate_services", "meuprojeto", {"services": ["auth", "traefik"]}),
            ("recreate_services", "meuprojeto", {"services": []}),
            ("rename_project", "meuprojeto", {"new_name": "meuprojeto"}),
            ("duplicate_project", "novo", {
                "original_name": "ok",
                "copy_mode": "everything",
                "tenant_uuid": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
            }),
            ("container_logs", "meuprojeto", {"service": "auth", "lines": 100000}),
            ("container_logs", "meuprojeto", {"service": "auth/../db", "lines": 10}),
            ("start_project", "meuprojeto", {"extra": True}),
            ("backup_project", "meuprojeto", {"backup_id": "../escape"}),
            ("backup_project", "meuprojeto", {}),
            ("restore_project", "meuprojeto", {
                "backup_id": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
                "safety_backup_id": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
            }),
            ("restore_project", "meuprojeto", {
                "backup_id": "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
            }),
            ("delete_restore_point", "meuprojeto", {"backup_id": "x; rm -rf /"}),
            ("delete_project_files", "meuprojeto", {"project_uuid": "nao-e-uuid"}),
        ]
        for command, project, args in cases:
            with self.subTest(command=command, project=project, args=args):
                self.assertTrue(protocol.validate_command_args(command, project, args))

    def test_args_validation_accepts_legitimate_payloads(self) -> None:
        tenant_uuid = "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa"
        cases = [
            ("start_project", "meuprojeto", {}),
            ("recreate_services", "meuprojeto", {"services": ["auth", "nginx"]}),
            ("create_project", "meuprojeto", {"tenant_uuid": tenant_uuid}),
            ("create_project", "meuprojeto", {
                "tenant_uuid": tenant_uuid,
                "recover_stale": True,
                "stale_tenant_uuids": [
                    "1b671a64-40d5-491e-99b0-da01ff1f3341"
                ],
            }),
            ("duplicate_project", "copia", {
                "original_name": "meuprojeto",
                "copy_mode": "schema-only",
                "tenant_uuid": tenant_uuid,
            }),
            ("rename_project", "meuprojeto", {"new_name": "novo_nome"}),
            ("container_logs", "meuprojeto", {"service": "auth", "lines": 100}),
            ("backup_project", "meuprojeto", {"backup_id": tenant_uuid}),
            ("restore_project", "meuprojeto", {
                "backup_id": tenant_uuid,
                "safety_backup_id": "1b671a64-40d5-491e-99b0-da01ff1f3341",
            }),
            ("delete_restore_point", "meuprojeto", {"backup_id": tenant_uuid}),
            ("delete_project_files", "meuprojeto", {}),
            ("delete_project_files", "meuprojeto", {"project_uuid": tenant_uuid}),
        ]
        for command, project, args in cases:
            with self.subTest(command=command):
                self.assertEqual(
                    protocol.validate_command_args(command, project, args), []
                )


class LeaseSqlTypingTest(unittest.TestCase):
    def test_lease_duration_has_an_explicit_integer_type(self) -> None:
        source = (
            AGENT_ROOT / "hostagent" / "db.py"
        ).read_text(encoding="utf-8")
        self.assertIn("lease_seconds = $3::integer", source)
        self.assertEqual(
            source.count("make_interval(secs => $3::integer)"),
            2,
            "Lease e heartbeat devem tipar a duracao como integer.",
        )


class HmacSignatureTest(unittest.TestCase):
    FIELDS = dict(
        command_id="9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa",
        command="start_project",
        project="meuprojeto",
        project_uuid="1b671a64-40d5-491e-99b0-da01ff1f3341",
        requested_by="2b671a64-40d5-491e-99b0-da01ff1f3342",
        args={},
        issued_at=1_752_000_000,
    )

    def test_roundtrip(self) -> None:
        signature = protocol.command_signature("segredo", **self.FIELDS)
        self.assertTrue(
            protocol.verify_command_signature("segredo", signature, **self.FIELDS)
        )

    def test_tampering_any_field_breaks_the_signature(self) -> None:
        signature = protocol.command_signature("segredo", **self.FIELDS)
        tampered_cases = {
            "command": "delete_project_files",
            "project": "outro",
            "requested_by": "3b671a64-40d5-491e-99b0-da01ff1f3343",
            "args": {"services": ["nginx"]},
            "issued_at": 1_752_000_001,
        }
        for field, value in tampered_cases.items():
            with self.subTest(field=field):
                fields = {**self.FIELDS, field: value}
                self.assertFalse(
                    protocol.verify_command_signature("segredo", signature, **fields)
                )

    def test_wrong_secret_or_empty_signature_fails(self) -> None:
        signature = protocol.command_signature("segredo", **self.FIELDS)
        self.assertFalse(
            protocol.verify_command_signature("outro-segredo", signature, **self.FIELDS)
        )
        self.assertFalse(
            protocol.verify_command_signature("segredo", None, **self.FIELDS)
        )

    def test_intent_expires_after_protocol_window(self) -> None:
        now = 1_752_000_000
        self.assertFalse(
            protocol.intent_is_expired(
                now - protocol.MAX_INTENT_AGE_SECONDS,
                now=now,
            )
        )
        self.assertTrue(
            protocol.intent_is_expired(
                now - protocol.MAX_INTENT_AGE_SECONDS - 1,
                now=now,
            )
        )
        self.assertTrue(protocol.intent_is_expired("invalid", now=now))


class SanitizeOutputTest(unittest.TestCase):
    def test_redacts_jwt_password_uri_and_bearer(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.c2lnbmF0dXJl"
        raw = "\n".join(
            (
                f"ANON_KEY_PROJETO={jwt}",
                "POSTGRES_PASSWORD=supersecreta123",
                "postgres://supabase_admin:supersecreta123@172.50.200.10:6755/postgres",
                "Authorization: Bearer abcdef123456",
                "linha normal permanece",
            )
        )
        cleaned = protocol.sanitize_output(raw)
        self.assertNotIn(jwt, cleaned)
        self.assertNotIn("supersecreta123", cleaned)
        self.assertNotIn("abcdef123456", cleaned)
        self.assertIn("linha normal permanece", cleaned)
        self.assertIn("[REDACTED", cleaned)

    def test_limits_tail_size(self) -> None:
        cleaned = protocol.sanitize_output("x" * 100_000)
        self.assertLessEqual(len(cleaned), protocol.OUTPUT_TAIL_LIMIT)


class AuthorizationMatrixTest(unittest.TestCase):
    BASE = dict(
        user_exists=True,
        user_active=True,
        is_global_admin=False,
        is_owner=False,
        member_role=None,
        project_row_exists=True,
        project_uuid_matches=True,
    )

    def check(self, command: str, **overrides):
        return protocol.evaluate_authorization(command, **{**self.BASE, **overrides})

    def test_requester_must_exist_and_be_active(self) -> None:
        self.assertEqual(
            self.check("start_project", user_exists=False), "requester_unknown"
        )
        self.assertEqual(
            self.check("start_project", user_active=False), "requester_inactive"
        )

    def test_delete_flow_requires_global_admin(self) -> None:
        for command in sorted(protocol.GLOBAL_ADMIN_COMMANDS):
            with self.subTest(command=command):
                self.assertEqual(
                    self.check(command, is_owner=True, member_role="admin"),
                    "global_admin_required",
                )
                self.assertIsNone(self.check(command, is_global_admin=True))

    def test_lifecycle_requires_owner_admin_or_global_admin(self) -> None:
        self.assertEqual(self.check("start_project"), "project_admin_required")
        self.assertEqual(
            self.check("start_project", member_role="member"),
            "project_admin_required",
        )
        self.assertIsNone(self.check("start_project", is_owner=True))
        self.assertIsNone(self.check("start_project", member_role="admin"))
        self.assertIsNone(self.check("start_project", is_global_admin=True))

    def test_restore_point_commands_allow_any_project_member(self) -> None:
        for command in sorted(protocol.PROJECT_MEMBER_COMMANDS):
            with self.subTest(command=command):
                self.assertEqual(self.check(command), "project_member_required")
                self.assertIsNone(self.check(command, member_role="member"))
                self.assertIsNone(self.check(command, member_role="admin"))
                self.assertIsNone(self.check(command, is_owner=True))
                self.assertIsNone(self.check(command, is_global_admin=True))

    def test_project_row_and_uuid_are_revalidated(self) -> None:
        self.assertEqual(
            self.check("start_project", is_owner=True, project_row_exists=False),
            "project_not_found",
        )
        self.assertEqual(
            self.check("start_project", is_owner=True, project_uuid_matches=False),
            "project_uuid_mismatch",
        )
        # O fluxo de delete remove a linha do projeto antes da limpeza fisica.
        self.assertIsNone(
            self.check(
                "delete_project_files",
                is_global_admin=True,
                project_row_exists=False,
            )
        )


class PathConfinementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.projects_root = pathlib.Path(self._tmp.name) / "projects"
        self.projects_root.mkdir()
        (self.projects_root / "meuprojeto").mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_valid_project_resolves_inside_root(self) -> None:
        resolved = resolve_project_dir(self.projects_root, "meuprojeto", must_exist=True)
        self.assertEqual(resolved.parent, self.projects_root.resolve())

    def test_invalid_names_are_rejected(self) -> None:
        for name in ("../fora", "a/b", "nome com espaco", "select", "..", "nome.ponto"):
            with self.subTest(name=name):
                with self.assertRaises(PathConfinementError):
                    resolve_project_dir(self.projects_root, name)

    def test_symlink_component_is_rejected(self) -> None:
        outside = pathlib.Path(self._tmp.name) / "fora"
        outside.mkdir()
        link = self.projects_root / "linkado"
        try:
            os.symlink(outside, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("sem permissao para criar symlink neste ambiente")
        with self.assertRaises(PathConfinementError) as ctx:
            resolve_project_dir(self.projects_root, "linkado")
        self.assertEqual(ctx.exception.code, "symlink_rejected")


class ApiNoLongerExecutesDockerOrShellTest(unittest.TestCase):
    FORBIDDEN = re.compile(
        r"create_subprocess|subprocess\.run|os\.system|os\.popen"
        r"|[\"']docker[\"']|docker exec"
    )

    def test_api_source_has_no_subprocess_or_docker_calls(self) -> None:
        app_dir = API_ROOT / "app"
        offenders: list[str] = []
        for source in sorted(app_dir.glob("*.py")):
            for number, line in enumerate(
                source.read_text(encoding="utf-8").splitlines(), start=1
            ):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if self.FORBIDDEN.search(stripped):
                    offenders.append(f"{source.name}:{number}: {stripped}")
        self.assertEqual(
            offenders,
            [],
            "A Projects API nao pode executar Docker/shell diretamente:\n"
            + "\n".join(offenders),
        )

    def test_main_delegates_lifecycle_to_host_agent(self) -> None:
        main_source = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("run_host_agent_command_for_job", main_source)
        self.assertIn("ensure_host_agent_schema", main_source)


if __name__ == "__main__":
    unittest.main()
