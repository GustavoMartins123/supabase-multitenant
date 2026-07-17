from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "servidor" / "api-internal" / "app" / "main.py"
DEPENDENCIES_PATH = ROOT / "servidor" / "api-internal" / "app" / "dependencies.py"


class ProjectAccessAndDeletionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MAIN_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.dependencies_source = DEPENDENCIES_PATH.read_text(encoding="utf-8")
        cls.dependencies_tree = ast.parse(cls.dependencies_source)

    def function(self, name: str) -> ast.AsyncFunctionDef:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
                return node
        self.fail(f"async function {name} not found")

    def test_member_access_accepts_endpoint_specific_error_message(self) -> None:
        function = next(
            node
            for node in ast.walk(self.dependencies_tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "ensure_project_member_access"
        )
        keyword_only_args = [argument.arg for argument in function.args.kwonlyargs]
        self.assertIn("message", keyword_only_args)

    def test_deletion_terminates_supavisor_pools_before_dropping_database(self) -> None:
        function = self.function("_delete_project_impl")
        function_source = ast.get_source_segment(self.source, function) or ""
        terminate_at = function_source.index("_terminate_supavisor_pools(")
        delete_tenant_at = function_source.index(
            "_delete_tenant_api(\n        service_label=\"Supavisor\""
        )
        drop_database_at = function_source.index("_drop_database_force_or_fallback(")

        self.assertLess(terminate_at, delete_tenant_at)
        self.assertLess(delete_tenant_at, drop_database_at)
        self.assertIn("connections_drained", function_source)
        self.assertIn("if database_removed:", function_source)

    def test_final_verification_includes_supavisor_metadata(self) -> None:
        function = self.function("_delete_project_impl")
        function_source = ast.get_source_segment(self.source, function) or ""
        self.assertIn("_supavisor.tenants", function_source)
        self.assertIn("_supavisor.users", function_source)


if __name__ == "__main__":
    unittest.main()
