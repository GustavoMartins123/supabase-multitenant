"""Consulta de telemetria do Auth isolada por database de projeto."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import asyncpg


UTC = dt.timezone.utc
MAX_CUSTOM_RANGE = dt.timedelta(days=366)


class TelemetryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class TelemetryPeriod:
    key: str
    start: dt.datetime
    end: dt.datetime


def _as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def resolve_telemetry_period(
    period: str,
    *,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    now: dt.datetime | None = None,
) -> TelemetryPeriod:
    current = _as_utc(now or dt.datetime.now(UTC))
    normalized = period.strip().lower()
    durations = {
        "24h": dt.timedelta(hours=24),
        "7d": dt.timedelta(days=7),
        "30d": dt.timedelta(days=30),
    }

    if normalized in durations:
        if start is not None or end is not None:
            raise TelemetryValidationError(
                "start/end somente podem ser usados com period=custom"
            )
        return TelemetryPeriod(
            key=normalized,
            start=current - durations[normalized],
            end=current,
        )

    if normalized != "custom":
        raise TelemetryValidationError(
            "period deve ser 24h, 7d, 30d ou custom"
        )
    if start is None or end is None:
        raise TelemetryValidationError(
            "start e end sao obrigatorios para period=custom"
        )

    range_start = _as_utc(start)
    range_end = _as_utc(end)
    if range_start >= range_end:
        raise TelemetryValidationError("start deve ser anterior a end")
    if range_end - range_start > MAX_CUSTOM_RANGE:
        raise TelemetryValidationError(
            "intervalo customizado nao pode ultrapassar 366 dias"
        )
    if range_end > current + dt.timedelta(minutes=5):
        raise TelemetryValidationError("end nao pode estar no futuro")

    return TelemetryPeriod(key="custom", start=range_start, end=range_end)


async def fetch_project_user_telemetry(
    conn: asyncpg.Connection,
    telemetry_period: TelemetryPeriod,
) -> dict[str, Any]:
    rows = await conn.fetch(
        """
        WITH period_sessions AS (
            SELECT
                user_id,
                count(*)::bigint AS session_count,
                max(created_at) AS last_session_at
            FROM auth.sessions
            WHERE created_at >= $1
              AND created_at < $2
            GROUP BY user_id
        )
        SELECT
            users.id::text AS user_id,
            users.email,
            users.phone,
            GREATEST(
                users.last_sign_in_at,
                period_sessions.last_session_at
            ) AS last_login_at,
            COALESCE(period_sessions.session_count, 0)::bigint AS session_count
        FROM auth.users AS users
        LEFT JOIN period_sessions ON period_sessions.user_id = users.id
        WHERE period_sessions.user_id IS NOT NULL
           OR (
                users.last_sign_in_at >= $1
                AND users.last_sign_in_at < $2
           )
        ORDER BY last_login_at DESC NULLS LAST, users.id
        """,
        telemetry_period.start,
        telemetry_period.end,
    )

    users = [
        {
            "user_id": row["user_id"],
            "email": row["email"],
            "phone": row["phone"],
            "last_login_at": row["last_login_at"],
            "session_count": int(row["session_count"] or 0),
        }
        for row in rows
    ]
    return {
        "period": telemetry_period.key,
        "start": telemetry_period.start,
        "end": telemetry_period.end,
        "active_users": len(users),
        "total_sessions": sum(user["session_count"] for user in users),
        "users": users,
        "source": "auth.users+auth.sessions",
        "sessions_are_current_records": True,
    }
