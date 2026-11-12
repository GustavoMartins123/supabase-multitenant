from pathlib import Path
import ast
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
from app.host_agent_protocol import ProjectNameValidator
from app.validation import is_protected_database, validate_new_project_name, validate_project_id
from fastapi import HTTPException


class ProjectNamesContractTest(unittest.TestCase):
    def test_names_are_not_routing_namespaces(self):
        for name in ("select", "default", "table", "admin", "internal", "phpmyadmin", "xmlrpc", "actuator"):
            with self.subTest(name=name):
                self.assertTrue(ProjectNameValidator.is_valid(name))
                self.assertEqual(validate_project_id(name), name)

    def test_unsafe_names_remain_rejected(self):
        for name in ("../admin", "a/b", "a.b", "ab", "x" * 41, "3name", "with space"):
            with self.subTest(name=name):
                self.assertFalse(ProjectNameValidator.is_valid(name))
                with self.assertRaises(HTTPException):
                    validate_project_id(name)

    def test_shell_and_flutter_keep_shape_without_blocklists(self):
        for path in ("servidor/generateProject/lib/generate_project_impl.sh",
                     "servidor/generateProject/lib/duplicate_project_impl.sh"):
            source = (ROOT / path).read_text(encoding="utf-8")
            self.assertIn("^[a-z_][a-z0-9_]{2,39}$", source)
            self.assertNotIn("RESERVED", source)
            self.assertNotIn("reservedWords", source)
        dart = (ROOT / "studio/seletor_de_projetos/lib/utils/project_name_validator.dart").read_text(encoding="utf-8")
        self.assertIn("RegExp(projectNamePattern)", dart)
        self.assertNotIn("reservedWords", dart)
        firewall = (ROOT / "servidor/traefik/middlewares.yml").read_text(encoding="utf-8")
        self.assertIn("malicious-paths:", firewall)
        self.assertIn("PathPrefix(`/phpmyadmin`)", firewall)


class InfrastructureNamespacesContractTest(unittest.TestCase):
    PLATFORM_COMPOSES = {
        "servidor/docker-compose.yml": "servidor",
        "servidor/docker-compose-api.yml": "servidor",
        "servidor/traefik/docker-compose.yml": "traefik",
        "studio/docker-compose.yml": "studio",
    }
    PROTECTED_DATABASES = (
        "postgres", "template0", "template1", "_supabase",
        "_supabase_storage", "_supabase_template", "meta_trap",
    )

    def reserved_names(self) -> list[str]:
        return sorted(ProjectNameValidator.RESERVED_NAMES) + [
            "_supabase", "_supabase_storage", "supabase_studio",
        ]

    def test_new_projects_cannot_take_reserved_names(self):
        for name in self.reserved_names():
            with self.subTest(name=name):
                with self.assertRaises(HTTPException) as ctx:
                    validate_new_project_name(name)
                self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(validate_new_project_name(" Meu_Projeto "), "meu_projeto")
        self.assertEqual(validate_new_project_name("default"), "default")

    def test_existing_projects_stay_addressable(self):
        for name in sorted(ProjectNameValidator.RESERVED_NAMES):
            with self.subTest(name=name):
                self.assertEqual(validate_project_id(name), name)

    def test_create_and_duplicate_endpoints_use_the_new_name_validator(self):
        source = (ROOT / "servidor/api-internal/app/routers/projects.py").read_text(encoding="utf-8")
        self.assertIn("name = validate_new_project_name(body.name)", source)
        self.assertIn("new_name = validate_new_project_name(body.new_name)", source)

    def test_platform_composes_pin_reserved_project_names(self):
        for path, expected in self.PLATFORM_COMPOSES.items():
            with self.subTest(path=path):
                source = (ROOT / path).read_text(encoding="utf-8")
                names = re.findall(r"^name:\s*(\S+)\s*$", source, flags=re.MULTILINE)
                self.assertEqual(names, [expected])
                self.assertTrue(ProjectNameValidator.is_reserved(expected))

    def test_shell_guard_refuses_internal_databases(self):
        guard = ROOT / "servidor/generateProject/lib/protected_databases.sh"
        script = 'source "$1"; shift; protected_database_assert_droppable "$1"'
        for db in self.PROTECTED_DATABASES + ("", "outro_banco"):
            with self.subTest(db=db):
                result = subprocess.run(
                    ["bash", "-c", script, "guard", str(guard), db],
                    capture_output=True, text=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
        result = subprocess.run(
            ["bash", "-c", script, "guard", str(guard), "_supabase_meu_projeto"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_project_database_drop_is_guarded(self):
        for path in ("servidor/generateProject/lib/generate_project_impl.sh",
                     "servidor/generateProject/lib/duplicate_project_impl.sh",
                     "servidor/generateProject/lib/restore_project_impl.sh"):
            with self.subTest(path=path):
                source = (ROOT / path).read_text(encoding="utf-8")
                self.assertIn('source "$SCRIPT_DIR/lib/protected_databases.sh"', source)
                self.assertIn("protected_database_assert_droppable", source)

    def test_python_deletion_refuses_internal_databases(self):
        for db in self.PROTECTED_DATABASES + ("outro_banco",):
            with self.subTest(db=db):
                self.assertTrue(is_protected_database(db))
        self.assertFalse(is_protected_database("_supabase_meu_projeto"))

        source = (ROOT / "servidor/api-internal/app/project_deletion.py").read_text(encoding="utf-8")
        functions = {
            node.name: ast.get_source_segment(source, node)
            for node in ast.parse(source).body
            if isinstance(node, ast.AsyncFunctionDef)
        }
        for helper in ("drain_database_connections", "drop_database_force"):
            with self.subTest(helper=helper):
                self.assertIn("assert_project_database_droppable(db_name)", functions[helper])


if __name__ == "__main__":
    unittest.main()
