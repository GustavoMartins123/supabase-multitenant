from __future__ import annotations

import importlib
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

platform_capacity = importlib.import_module("app.platform_capacity")
assert_capacity_available = platform_capacity.assert_capacity_available
project_capacity = platform_capacity.project_capacity
read_capacity = platform_capacity.read_capacity

try:
    from fastapi import HTTPException
except ImportError:
    HTTPException = None


PUBLISHED = (
    "PLATFORM_PROJECT_CAPACITY=9\n"
    "PLATFORM_CAPACITY_BINDING=cpu\n"
    "PLATFORM_PROJECT_PROFILE=medium\n"
)


@unittest.skipIf(HTTPException is None, "fastapi ausente")
class CapacityEnforcementContract(unittest.TestCase):
    def _file(self, content: str) -> pathlib.Path:
        temp = tempfile.NamedTemporaryFile(
            "w", suffix=".env", delete=False, encoding="utf-8"
        )
        temp.write(content)
        temp.close()
        self.addCleanup(lambda: pathlib.Path(temp.name).unlink(missing_ok=True))
        return pathlib.Path(temp.name)

    def test_below_the_ceiling_is_allowed(self) -> None:
        path = self._file(PUBLISHED)
        for current in (0, 5, 8):
            with self.subTest(current=current):
                assert_capacity_available(current, capacity_file=path)

    def test_at_and_above_the_ceiling_is_refused(self) -> None:
        path = self._file(PUBLISHED)
        for current in (9, 10, 40):
            with self.subTest(current=current):
                with self.assertRaises(HTTPException) as ctx:
                    assert_capacity_available(current, capacity_file=path)
                self.assertEqual(409, ctx.exception.status_code)

    def test_refusal_says_what_to_do(self) -> None:
        path = self._file(PUBLISHED)
        with self.assertRaises(HTTPException) as ctx:
            assert_capacity_available(9, capacity_file=path)
        detail = ctx.exception.detail
        self.assertIn("9", detail)
        self.assertIn("cpu", detail)
        self.assertIn("medium", detail)
        self.assertIn("start.sh", detail)

    def test_missing_file_does_not_block(self) -> None:
        missing = pathlib.Path(tempfile.gettempdir()) / "nao-existe-capacity.env"
        self.assertIsNone(project_capacity(capacity_file=missing))
        assert_capacity_available(999, capacity_file=missing)

    def test_malformed_values_do_not_block(self) -> None:
        for content in (
            "PLATFORM_PROJECT_CAPACITY=abc\n",
            "PLATFORM_PROJECT_CAPACITY=\n",
            "PLATFORM_PROJECT_CAPACITY=0\n",
            "# so comentario\n",
        ):
            with self.subTest(content=content.strip()):
                path = self._file(content)
                assert_capacity_available(999, capacity_file=path)

    def test_reads_the_scalars_the_helper_publishes(self) -> None:
        path = self._file(PUBLISHED)
        values = read_capacity(capacity_file=path)
        self.assertEqual("9", values["PLATFORM_PROJECT_CAPACITY"])
        self.assertEqual("cpu", values["PLATFORM_CAPACITY_BINDING"])


class EnforcementWiringContract(unittest.TestCase):
    def test_every_insert_into_projects_checks_capacity(self) -> None:
        main = (APP / "app" / "main.py").read_text(encoding="utf-8")
        inserts = [
            index
            for index in range(len(main))
            if main.startswith("INSERT INTO projects(", index)
        ]
        self.assertGreaterEqual(len(inserts), 2, "esperado create e duplicate")

        checks = [
            index
            for index in range(len(main))
            if main.startswith("assert_capacity_available(", index)
        ]
        self.assertEqual(
            len(inserts),
            len(checks),
            "cada INSERT INTO projects precisa de uma verificacao de teto",
        )
        for insert_at in inserts:
            with self.subTest(insert_at=insert_at):
                preceding = [c for c in checks if c < insert_at]
                self.assertTrue(
                    preceding,
                    "INSERT INTO projects sem verificacao de teto antes dele",
                )

                self.assertLess(insert_at - preceding[-1], 1200)

    def test_creation_checks_capacity_inside_the_transaction(self) -> None:
        main = (APP / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("assert_capacity_available", main)
        endpoint = main.split('@app.post("/api/projects", status_code=202)', 1)[1]
        endpoint = endpoint.split("\n@app.", 1)[0]
        self.assertIn("async with conn.transaction():", endpoint)
        self.assertLess(
            endpoint.index("async with conn.transaction():"),
            endpoint.index("assert_capacity_available"),
        )

        self.assertLess(
            endpoint.index("assert_capacity_available"),
            endpoint.index("INSERT INTO projects"),
        )

    def test_capacity_file_is_published_and_mounted(self) -> None:
        helper = (ROOT / "servidor/generateProject/lib/platform_capacity.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("PLATFORM_PROJECT_CAPACITY=%s", helper)
        compose = (ROOT / "servidor" / "docker-compose-api.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("platform-capacity.env:/docker/platform-capacity.env:ro", compose)
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("platform_render_env", start)

    def test_shared_limits_are_reapplied_on_create_and_delete(self) -> None:
        for script in (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/duplicate_project_impl.sh",
            ROOT / "servidor/generateProject/delete_project.sh",
        ):
            with self.subTest(script=script.name):
                self.assertIn(
                    "platform_apply_shared_limits", script.read_text(encoding="utf-8")
                )


if __name__ == "__main__":
    unittest.main()
