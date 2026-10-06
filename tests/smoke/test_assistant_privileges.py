import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.assistant_privileges import PrivilegeChange, PrivilegeChangeBody, privilege_sql
from app.assistant_sql import SqlPolicyError, inspect_sql


class AssistantPrivilegesTest(unittest.TestCase):
    def change(self, **fields):
        return {"operation": "grant", "tables": ["clientes", "Pedidos"], "role": "authenticated", "privileges": ["SELECT", "UPDATE"], "label": "Application access", **fields}

    def test_exact_sql_is_generated_only_from_structured_app_privileges(self):
        self.assertEqual(privilege_sql(PrivilegeChange(**self.change())), 'GRANT SELECT, UPDATE ON TABLE public."clientes", public."Pedidos" TO "authenticated";')
        self.assertEqual(privilege_sql(PrivilegeChange(**self.change(operation="revoke", role="anon"))), 'REVOKE SELECT, UPDATE ON TABLE public."clientes", public."Pedidos" FROM "anon" RESTRICT;')

    def test_broad_privileges_roles_schemas_and_arbitrary_sql_are_rejected(self):
        for fields in (
            {"role": "PUBLIC"}, {"role": "postgres"}, {"role": "service_role"},
            {"privileges": ["ALL"]}, {"privileges": ["TRUNCATE"]}, {"privileges": ["TRIGGER"]}, {"privileges": ["REFERENCES"]},
            {"tables": ["auth.users"]}, {"tables": ['items"; DROP TABLE public.items;--']}, {"tables": ["x" * 64]},
            {"tables": []}, {"tables": ["a"] * 21}, {"tables": ["a", "a"]}, {"privileges": ["SELECT", "SELECT"]},
            {"sql": "GRANT ALL TO PUBLIC"}, {"grant_option": True}, {"cascade": True}, {"operation": "alter"},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                PrivilegeChange(**self.change(**fields))

    def test_execution_cannot_omit_confirmation_or_use_another_tool(self):
        execution = {"chat_id": "00000000-0000-4000-8000-000000000001", "call_id": "call", "approval_id": "approval", "sql_hash": "a" * 64, "tool": "manage_table_privileges"}
        for change in ({"approval_id": None}, {"approval_id": ""}, {"tool": "execute_sql"}, {"tool": "execute_destructive_sql"}):
            with self.assertRaises(ValidationError):
                PrivilegeChangeBody(**self.change(), permission="full", execution={**execution, **change})
        with self.assertRaises(ValidationError):
            PrivilegeChangeBody(**self.change(), permission="read", execution=execution)

    def test_general_sql_tools_still_reject_grant_and_revoke(self):
        for operation in ("grant", "revoke"):
            with self.assertRaises(SqlPolicyError):
                inspect_sql(privilege_sql(PrivilegeChange(**self.change(operation=operation))))
