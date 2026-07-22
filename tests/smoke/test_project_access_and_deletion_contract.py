from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAIN_PATH = ROOT / "servidor" / "api-internal" / "app" / "main.py"
DEPENDENCIES_PATH = ROOT / "servidor" / "api-internal" / "app" / "dependencies.py"
DELETION_PATH = ROOT / "servidor" / "api-internal" / "app" / "project_deletion.py"
HOST_PROTOCOL_PATH = (
    ROOT / "servidor" / "api-internal" / "app" / "host_agent_protocol.py"
)
NGINX_PATH = ROOT / "studio" / "nginx" / "nginx.conf"


class ProjectAccessAndDeletionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MAIN_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.dependencies_source = DEPENDENCIES_PATH.read_text(encoding="utf-8")
        cls.dependencies_tree = ast.parse(cls.dependencies_source)
        cls.deletion_source = DELETION_PATH.read_text(encoding="utf-8")
        cls.host_protocol_source = HOST_PROTOCOL_PATH.read_text(encoding="utf-8")
        cls.nginx_source = NGINX_PATH.read_text(encoding="utf-8")

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
        terminate_at = function_source.index("terminate_supavisor_pools(")
        delete_tenant_at = function_source.index("delete_supavisor_tenant(")
        drop_database_at = function_source.index("drop_database_force(")

        self.assertLess(terminate_at, delete_tenant_at)
        self.assertLess(delete_tenant_at, drop_database_at)
        self.assertIn("drain_database_connections", function_source)
        self.assertNotIn("partial_success", function_source)

    def test_deletion_has_one_canonical_tenant_cleanup_path(self) -> None:
        self.assertNotIn("fallback", self.deletion_source.lower())
        self.assertNotIn("run_host_agent_command", self.deletion_source)
        self.assertIn("follow_redirects=False", self.deletion_source)
        self.assertIn("DROP DATABASE IF EXISTS", self.deletion_source)
        self.assertIn("WITH (FORCE)", self.deletion_source)

        for removed_command in (
            "terminate_supavisor_tenant",
            "delete_supavisor_tenant",
            "delete_realtime_tenant",
        ):
            self.assertNotIn(f'\"{removed_command}\"', self.host_protocol_source)

    def test_final_verification_includes_supavisor_metadata(self) -> None:
        function = self.function("_delete_project_impl")
        function_source = ast.get_source_segment(self.source, function) or ""
        self.assertIn("_supavisor.tenants", function_source)
        self.assertIn("_supavisor.users", function_source)

    def test_whole_project_deletion_remains_global_admin_only(self) -> None:
        function = self.function("delete_project")
        function_source = ast.get_source_segment(self.source, function) or ""
        self.assertIn('if not auth_user["is_global_admin"]', function_source)
        self.assertIn('alias="X-Delete-Password"', function_source)
        self.assertIn("hmac.compare_digest", function_source)
        self.assertNotIn("ensure_project_owner_access", function_source)

    def test_admin_projects_info_uses_one_canonical_path(self) -> None:
        self.assertIn('@app.post("/api/admin/projects-info")', self.source)
        self.assertIn(
            "proxy_pass $server_domain/api/admin/projects-info;",
            self.nginx_source,
        )
        self.assertNotIn("/api/projects/admin/projects-info", self.nginx_source)


if __name__ == "__main__":
    unittest.main()
