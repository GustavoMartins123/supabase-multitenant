"""Contrato do host-agent: comandos fechados, HMAC, paths e sanitizacao.

Fixa as garantias do P0 estrutural: a Projects API nao executa Docker nem
shell; toda execucao fisica passa pelo host-agent com assinatura HMAC,
reautorizacao, confinamento de paths e saida sanitizada.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
API_ROOT = ROOT / "servidor" / "api-internal"

for path in (str(AGENT_ROOT), str(API_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from hostagent import host_agent_protocol as protocol
from hostagent.commands import COMMAND_HANDLERS
from hostagent.security import PathConfinementError, resolve_project_dir


class ProtocolCopiesAreIdenticalTest(unittest.TestCase):
    def test_api_and_agent_share_the_same_protocol_bytes(self) -> None:
        agent_copy = (AGENT_ROOT / "hostagent" / "host_agent_protocol.py").read_bytes()
        api_copy = (API_ROOT / "app" / "host_agent_protocol.py").read_bytes()
        self.assertEqual(
            agent_copy,
            api_copy,
            "As copias do host_agent_protocol.py divergiram; sincronize-as.",
        )


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
            ("duplicate_project", "copia", {
                "original_name": "meuprojeto",
                "copy_mode": "schema-only",
                "tenant_uuid": tenant_uuid,
            }),
            ("rename_project", "meuprojeto", {"new_name": "novo_nome"}),
            ("container_logs", "meuprojeto", {"service": "auth", "lines": 100}),
        ]
        for command, project, args in cases:
            with self.subTest(command=command):
                self.assertEqual(
                    protocol.validate_command_args(command, project, args), []
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
