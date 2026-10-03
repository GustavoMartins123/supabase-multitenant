from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor" / "api-internal"))

from app.project_public_ref import (  # noqa: E402
    PublicProjectNotFound,
    generate_public_ref,
    resolve_public_project,
    validate_public_ref,
)


class PublicRefTest(unittest.TestCase):
    def test_independent_random_letters(self) -> None:
        refs = {generate_public_ref() for _ in range(2000)}
        self.assertEqual(len(refs), 2000)
        for ref in refs:
            self.assertRegex(ref, r"\A[a-z]{20}\Z")
            self.assertEqual(validate_public_ref(ref), ref)

    def test_uses_secure_choice_for_each_letter(self) -> None:
        with patch("app.project_public_ref.secrets.choice", return_value="z") as choice:
            self.assertEqual(generate_public_ref(), "z" * 20)
        self.assertEqual(choice.call_count, 20)
        for call in choice.call_args_list:
            self.assertEqual(call.args, ("abcdefghijklmnopqrstuvwxyz",))

    def test_noncanonical_input_is_not_normalized(self) -> None:
        for value in (
            None, 20, "", "meu_projeto", "a" * 19, "a" * 21, "A" * 20,
            "a" * 19 + "1", "a" * 19 + "_", "a" * 19 + "á",
            "a" * 20 + "\n", " " + "a" * 20, "a" * 20 + " ",
            "a" * 20 + "/rest/v1", "00000000-0000-4000-8000-000000000000",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_public_ref(value)


class PublicRefLookupTest(unittest.IsolatedAsyncioTestCase):
    async def test_lookup_uses_only_public_ref_and_parameter_binding(self) -> None:
        conn = AsyncMock()
        row = {"id": "internal", "name": "technical", "public_ref": "a" * 20}
        conn.fetchrow.return_value = row
        self.assertIs(await resolve_public_project(conn, "a" * 20), row)
        query, argument = conn.fetchrow.call_args.args
        self.assertIn("WHERE public_ref = $1", query)
        self.assertNotIn("WHERE name", query)
        self.assertNotIn(" OR ", query)
        self.assertNotIn("service_role", query)
        self.assertEqual(argument, "a" * 20)

    async def test_missing_ref_does_not_resolve_by_name_or_history(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        with self.assertRaises(PublicProjectNotFound):
            await resolve_public_project(conn, "b" * 20)
        conn.fetchrow.assert_awaited_once()

    async def test_invalid_ref_never_reaches_database(self) -> None:
        conn = AsyncMock()
        with self.assertRaises(ValueError):
            await resolve_public_project(conn, "technical_name")
        conn.fetchrow.assert_not_awaited()

    async def test_database_failure_is_propagated(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.side_effect = ConnectionError("database unavailable")
        with self.assertRaises(ConnectionError):
            await resolve_public_project(conn, "c" * 20)
        conn.fetchrow.assert_awaited_once()

    async def test_rotation_caller_can_lock_canonical_row(self) -> None:
        conn = AsyncMock()
        await resolve_public_project(conn, "d" * 20, for_update=True)
        self.assertTrue(conn.fetchrow.call_args.args[0].endswith(" FOR UPDATE"))


if __name__ == "__main__":
    unittest.main()
