from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = (
    ROOT / "servidor" / "api-internal" / "app" / "routers" / "opaque_keys.py"
)
NGINX_PATH = ROOT / "studio" / "nginx" / "nginx.conf"
STEP_UP_LUA_PATH = (
    ROOT / "studio" / "nginx" / "lua" / "security" / "step_up_authenticate.lua"
)
DELETE_CHECK_PATH = (
    ROOT / "studio" / "nginx" / "lua" / "admin_api" / "projects_delete_check.lua"
)
COMPOSE_PATH = ROOT / "servidor" / "docker-compose-api.yml"
ENV_EXAMPLE_PATH = ROOT / "servidor" / ".env.example"


class OpaqueApiKeyStepUpPermissionContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.router = ROUTER_PATH.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.router)
        cls.nginx = NGINX_PATH.read_text(encoding="utf-8")
        cls.step_up_lua = STEP_UP_LUA_PATH.read_text(encoding="utf-8")
        cls.delete_check = DELETE_CHECK_PATH.read_text(encoding="utf-8")

    def function_source(self, name: str) -> str:
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name == name
            ):
                return ast.get_source_segment(self.router, node) or ""
        self.fail(f"function {name} not found")

    def test_members_receive_only_publishable_slots_and_reveals(self) -> None:
        slots = self.function_source("get_api_key_slots")
        reveals = self.function_source("get_api_key_reveals")
        for source in (slots, reveals):
            self.assertIn("_authorize_project_access", source)
            self.assertIn('== "publishable"', source)
        access = self.function_source("_authorize_project_access")
        self.assertIn("ensure_project_member_access", access)
        self.assertIn('role == "admin"', access)

    def test_publishable_claim_needs_membership_but_secret_needs_step_up(self) -> None:
        claim = self.function_source("claim_api_key")
        member_at = claim.index("ensure_project_member_access")
        kind_at = claim.index("key_kind")
        secret_at = claim.index('key_kind == "secret"')
        admin_at = claim.index("ensure_project_admin_access", secret_at)
        consume_at = claim.index("consume_step_up_grant", admin_at)
        reveal_at = claim.index("claim_key_reveal", consume_at)
        self.assertLess(member_at, kind_at)
        self.assertLess(secret_at, admin_at)
        self.assertLess(admin_at, consume_at)
        self.assertLess(consume_at, reveal_at)
        self.assertIn('action="reveal_secret_key"', claim)

    def test_secret_plaintext_creation_and_rotation_require_step_up(self) -> None:
        create = self.function_source("create_api_key_slot")
        rotate = self.function_source("rotate_api_key_slot")
        self.assertIn('body.kind == "secret"', create)
        self.assertIn('action="create_secret_key"', create)
        self.assertIn('slot_kind == "secret"', rotate)
        self.assertIn('action="rotate_secret_key"', rotate)
        for source in (create, rotate):
            self.assertIn("ensure_project_admin_access", source)
            self.assertIn('alias="X-Step-Up-Token"', source)

    def test_gateway_reauthenticates_current_identity_without_forwarding_cookie(self) -> None:
        self.assertIn("location = /api/security/step-up", self.nginx)
        self.assertIn("client_max_body_size 4k;", self.nginx)
        self.assertIn(
            "location = /internal/authelia-step-up-first-factor", self.nginx
        )
        self.assertIn(
            "proxy_pass https://$authelia_upstream/auth/api/firstfactor;",
            self.nginx,
        )
        self.assertIn('proxy_set_header Cookie "";', self.nginx)
        self.assertIn("proxy_hide_header Set-Cookie;", self.nginx)
        self.assertIn(
            'media_type:lower() ~= "application/json"', self.step_up_lua
        )
        self.assertIn("ngx.var.authelia_username", self.step_up_lua)
        self.assertIn("login_session.fingerprint()", self.step_up_lua)
        self.assertNotIn("ngx.log(ngx", self.step_up_lua.split("local password", 1)[1].split("password = nil", 1)[0])

    def test_global_delete_password_contract_is_removed(self) -> None:
        combined = "\n".join(
            [
                self.delete_check,
                COMPOSE_PATH.read_text(encoding="utf-8"),
                ENV_EXAMPLE_PATH.read_text(encoding="utf-8"),
            ]
        )
        self.assertNotIn("PROJECT_DELETE_PASSWORD", combined)
        self.assertNotIn("X-Delete-Password", combined)


if __name__ == "__main__":
    unittest.main()
