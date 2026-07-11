from __future__ import annotations

import asyncio
import datetime as dt
import sys
import types
import unittest
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[2] / "servidor" / "api-internal"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")
    asyncpg_stub.Connection = object
    sys.modules["asyncpg"] = asyncpg_stub

from app.project_telemetry import (
    TelemetryValidationError,
    fetch_project_user_telemetry,
    resolve_telemetry_period,
)


UTC = dt.timezone.utc


class FakeConnection:
    def __init__(self, rows):
        self.rows = rows
        self.query = ""
        self.arguments = ()

    async def fetch(self, query, *arguments):
        self.query = query
        self.arguments = arguments
        return self.rows


class ProjectTelemetryTest(unittest.TestCase):
    def test_predefined_period_is_resolved_in_utc(self) -> None:
        now = dt.datetime(2026, 7, 11, 18, 0, tzinfo=UTC)
        period = resolve_telemetry_period("7d", now=now)
        self.assertEqual(period.start, now - dt.timedelta(days=7))
        self.assertEqual(period.end, now)

    def test_custom_period_rejects_invalid_or_excessive_ranges(self) -> None:
        now = dt.datetime(2026, 7, 11, 18, 0, tzinfo=UTC)
        with self.assertRaises(TelemetryValidationError):
            resolve_telemetry_period("custom", now=now)
        with self.assertRaises(TelemetryValidationError):
            resolve_telemetry_period(
                "custom",
                start=now,
                end=now,
                now=now,
            )
        with self.assertRaises(TelemetryValidationError):
            resolve_telemetry_period(
                "custom",
                start=now - dt.timedelta(days=367),
                end=now,
                now=now,
            )

    def test_query_is_scoped_to_auth_schema_and_selected_period(self) -> None:
        period = resolve_telemetry_period(
            "24h",
            now=dt.datetime(2026, 7, 11, 18, 0, tzinfo=UTC),
        )
        connection = FakeConnection(
            [
                {
                    "user_id": "user-1",
                    "email": "user@example.test",
                    "phone": None,
                    "last_login_at": period.end - dt.timedelta(hours=1),
                    "session_count": 3,
                }
            ]
        )

        result = asyncio.run(fetch_project_user_telemetry(connection, period))

        self.assertIn("FROM auth.sessions", connection.query)
        self.assertIn("FROM auth.users", connection.query)
        self.assertEqual(connection.arguments, (period.start, period.end))
        self.assertEqual(result["active_users"], 1)
        self.assertEqual(result["total_sessions"], 3)
        self.assertEqual(result["users"][0]["user_id"], "user-1")

    def test_route_contract_requires_project_admin_or_owner(self) -> None:
        main_source = (APP_ROOT / "app" / "main.py").read_text(encoding="utf-8")
        route_start = main_source.index(
            '@app.get("/api/projects/{project_name}/telemetry/users")'
        )
        route_end = main_source.index("\n@app.api_route(", route_start)
        route_source = main_source[route_start:route_end]
        self.assertIn('project_role != "admin"', route_source)
        self.assertIn("is_owner", route_source)
        self.assertIn('auth_user["is_global_admin"]', route_source)
        self.assertIn('response.headers["Cache-Control"] = "no-store"', route_source)


if __name__ == "__main__":
    unittest.main()
