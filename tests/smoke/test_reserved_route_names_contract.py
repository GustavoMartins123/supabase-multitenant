from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
from app.host_agent_protocol import ProjectNameValidator
from app.validation import validate_project_id
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


if __name__ == "__main__":
    unittest.main()
