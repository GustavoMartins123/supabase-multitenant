from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError


ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
sys.path.insert(0, str(API_ROOT))

schemas = importlib.import_module("app.schemas")


class RoleSchemaContractTest(unittest.TestCase):
    def test_project_member_roles_are_closed(self) -> None:
        self.assertEqual(
            schemas.AddMember(user_id="user", role="admin").role,
            "admin",
        )
        self.assertEqual(schemas.AddMember(user_id="user").role, "member")
        with self.assertRaises(ValidationError):
            schemas.AddMember(user_id="user", role="owner")


if __name__ == "__main__":
    unittest.main()
