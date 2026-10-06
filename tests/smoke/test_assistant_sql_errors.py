import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.assistant_sql_errors import SQL_FAILURES, assistant_sql_failure


class AssistantSqlErrorsTest(unittest.TestCase):
    def test_known_failures_have_fixed_codes_and_do_not_expose_postgres_values(self):
        for sqlstate, (status, code, _) in SQL_FAILURES.items():
            with self.subTest(sqlstate=sqlstate):
                error = assistant_sql_failure(SimpleNamespace(sqlstate=sqlstate, message="private-row-value", detail="private-row-value", hint="private-row-value"))
                self.assertEqual(error.status_code, status)
                self.assertEqual(error.detail["code"], code)
                self.assertEqual(error.detail["sqlstate"], sqlstate)
                self.assertNotIn("private-row-value", str(error.detail))
                self.assertIn("rolled back", error.detail["message"])

    def test_unknown_failure_is_explicit_and_does_not_echo_unknown_fields(self):
        error = assistant_sql_failure(SimpleNamespace(sqlstate="private-state", message="private-row-value"))
        self.assertEqual(error.status_code, 502)
        self.assertNotIn("private", str(error.detail))

    def test_type_error_is_not_a_gateway_failure_or_an_approval_requirement(self):
        error = assistant_sql_failure(SimpleNamespace(sqlstate="42883"))
        self.assertEqual(error.status_code, 422)
        self.assertEqual(error.detail["code"], "sql_operand_types")
