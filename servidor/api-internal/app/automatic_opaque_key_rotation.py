"""Durable scheduler for time-based opaque API-key cutovers."""

from __future__ import annotations

import asyncio
import uuid

from app.control_plane_service import (
    audit_studio_action,
    create_studio_notification,
)
from app.database import get_pool
from app.opaque_key_service import (
    activate_pending_key,
    prepare_slot_rotation,
)
from app.runtime_config import (
    AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS,
    AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
)


AUTOMATIC_OPAQUE_KEY_ROTATION_LOCK_NAME = (
    "supabase-multitenant:auto-opaque-key-rotation:v1"
)
MAX_TRANSITIONS_PER_SCAN = 100

_automatic_opaque_key_rotation_task: asyncio.Task[None] | None = None


async def _notify_project_admins(
    conn,
    *,
    project_id: uuid.UUID,
    kind: str,
    target_id: str,
    payload: dict,
) -> None:
    recipients = await conn.fetch(
        """
        SELECT owner_id AS user_id
        FROM projects
        WHERE id = $1
        UNION
        SELECT user_id
        FROM project_members
        WHERE project_id = $1 AND role = 'admin'
        """,
        project_id,
    )
    for recipient in recipients:
        await create_studio_notification(
            conn,
            project_id=project_id,
            target_user_id=recipient["user_id"],
            actor_user_id=None,
            kind=kind,
            target_type="project_api_key",
            target_id=target_id,
            payload=payload,
        )


async def scan_automatic_opaque_key_rotations() -> int:
    """Prepare, cut over, and explicitly block invalid automatic schedules."""

    pool = await get_pool()
    transitions = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            owns_scan = await conn.fetchval(
                "SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))",
                AUTOMATIC_OPAQUE_KEY_ROTATION_LOCK_NAME,
            )
            if not owns_scan:
                return 0

            due = await conn.fetch(
                """
                SELECT s.project_id, s.id AS slot_id, s.name,
                       k.id AS pending_key_id, k.rotation_trigger,
                       EXISTS (
                           SELECT 1 FROM project_api_key_reveals r
                           WHERE r.key_id = k.id AND r.expires_at > now()
                       ) AS reveal_unclaimed
                FROM project_api_key_slots s
                JOIN projects p ON p.id = s.project_id
                JOIN project_api_keys k ON k.slot_id = s.id
                WHERE p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND s.status = 'active'
                  AND k.status = 'pending'
                  AND k.confirmed_at IS NOT NULL
                  AND k.activate_at <= now()
                  AND k.expires_at > now()
                ORDER BY k.activate_at, s.id
                FOR UPDATE OF s, k SKIP LOCKED
                LIMIT $1
                """,
                MAX_TRANSITIONS_PER_SCAN,
            )
            for row in due:
                key_id, version = await activate_pending_key(
                    conn,
                    project_id=row["project_id"],
                    slot_id=row["slot_id"],
                )
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=None,
                    action=(
                        "opaque_api_key_automatically_activated"
                        if row["rotation_trigger"] == "automatic"
                        else "opaque_api_key_scheduled_rotation_activated"
                    ),
                    target_type="project_api_key",
                    target_id=str(key_id),
                    new_value={
                        "slot_id": str(row["slot_id"]),
                        "slot_name": row["name"],
                        "reveal_was_unclaimed": row["reveal_unclaimed"],
                        "api_keyset_version": version,
                    },
                )
                await _notify_project_admins(
                    conn,
                    project_id=row["project_id"],
                    kind=(
                        "opaque_api_key_automatically_activated"
                        if row["rotation_trigger"] == "automatic"
                        else "opaque_api_key_scheduled_rotation_activated"
                    ),
                    target_id=str(key_id),
                    payload={
                        "slot_id": str(row["slot_id"]),
                        "slot_name": row["name"],
                        "reveal_was_unclaimed": row["reveal_unclaimed"],
                    },
                )
                transitions += 1

            remaining = MAX_TRANSITIONS_PER_SCAN - transitions
            if remaining <= 0:
                return transitions

            unconfirmed = await conn.fetch(
                """
                SELECT s.project_id, s.id AS slot_id, s.name,
                       k.id AS pending_key_id
                FROM project_api_key_slots s
                JOIN projects p ON p.id = s.project_id
                JOIN project_api_keys k ON k.slot_id = s.id
                WHERE p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND s.status = 'active'
                  AND s.automatic_rotation_blocked_at IS NULL
                  AND k.status = 'pending'
                  AND k.confirmed_at IS NULL
                  AND k.activate_at <= now()
                ORDER BY k.activate_at, s.id
                FOR UPDATE OF s, k SKIP LOCKED
                LIMIT $1
                """,
                remaining,
            )
            for row in unconfirmed:
                error_code = "pending_replacement_not_confirmed_before_cutover"
                await conn.execute(
                    """
                    UPDATE project_api_key_slots
                    SET automatic_rotation_blocked_at = now(),
                        automatic_rotation_last_error = $2,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    row["slot_id"],
                    error_code,
                )
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=None,
                    action="opaque_api_key_automatic_rotation_blocked",
                    target_type="project_api_key_slot",
                    target_id=str(row["slot_id"]),
                    new_value={
                        "error_code": error_code,
                        "pending_key_id": str(row["pending_key_id"]),
                    },
                )
                await _notify_project_admins(
                    conn,
                    project_id=row["project_id"],
                    kind="opaque_api_key_automatic_rotation_blocked",
                    target_id=str(row["slot_id"]),
                    payload={
                        "slot_name": row["name"],
                        "pending_key_id": str(row["pending_key_id"]),
                        "error_code": error_code,
                    },
                )
                transitions += 1

            remaining = MAX_TRANSITIONS_PER_SCAN - transitions
            if remaining <= 0:
                return transitions

            expired_pending = await conn.fetch(
                """
                SELECT s.project_id, s.id AS slot_id, s.name,
                       k.id AS pending_key_id
                FROM project_api_key_slots s
                JOIN projects p ON p.id = s.project_id
                JOIN project_api_keys k ON k.slot_id = s.id
                WHERE p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND s.status = 'active'
                  AND s.automatic_rotation_blocked_at IS NULL
                  AND k.status = 'pending'
                  AND k.expires_at <= now()
                ORDER BY k.expires_at, s.id
                FOR UPDATE OF s, k SKIP LOCKED
                LIMIT $1
                """,
                remaining,
            )
            for row in expired_pending:
                error_code = "pending_replacement_expired_before_activation"
                await conn.execute(
                    """
                    UPDATE project_api_key_slots
                    SET automatic_rotation_blocked_at = now(),
                        automatic_rotation_last_error = $2,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    row["slot_id"],
                    error_code,
                )
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=None,
                    action="opaque_api_key_automatic_rotation_blocked",
                    target_type="project_api_key_slot",
                    target_id=str(row["slot_id"]),
                    new_value={
                        "error_code": error_code,
                        "pending_key_id": str(row["pending_key_id"]),
                    },
                )
                await _notify_project_admins(
                    conn,
                    project_id=row["project_id"],
                    kind="opaque_api_key_automatic_rotation_blocked",
                    target_id=str(row["slot_id"]),
                    payload={
                        "slot_name": row["name"],
                        "pending_key_id": str(row["pending_key_id"]),
                        "error_code": error_code,
                    },
                )
                transitions += 1

            remaining = MAX_TRANSITIONS_PER_SCAN - transitions
            if remaining <= 0:
                return transitions

            expired = await conn.fetch(
                """
                SELECT s.project_id, s.id AS slot_id, s.name, k.id AS key_id
                FROM project_api_key_slots s
                JOIN projects p ON p.id = s.project_id
                JOIN project_api_keys k ON k.slot_id = s.id
                WHERE p.automatic_key_rotation_enabled
                  AND p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND s.automatic_rotation_enabled
                  AND s.status = 'active'
                  AND s.automatic_rotation_blocked_at IS NULL
                  AND k.status = 'active'
                  AND k.expires_at <= now()
                  AND NOT EXISTS (
                      SELECT 1 FROM project_api_keys pending
                      WHERE pending.slot_id = s.id
                        AND pending.status = 'pending'
                  )
                ORDER BY k.expires_at, s.id
                FOR UPDATE OF s, k SKIP LOCKED
                LIMIT $1
                """,
                remaining,
            )
            for row in expired:
                error_code = "active_key_expired_without_pending_replacement"
                await conn.execute(
                    """
                    UPDATE project_api_key_slots
                    SET automatic_rotation_blocked_at = now(),
                        automatic_rotation_last_error = $2,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    row["slot_id"],
                    error_code,
                )
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=None,
                    action="opaque_api_key_automatic_rotation_blocked",
                    target_type="project_api_key_slot",
                    target_id=str(row["slot_id"]),
                    new_value={"error_code": error_code},
                )
                await _notify_project_admins(
                    conn,
                    project_id=row["project_id"],
                    kind="opaque_api_key_automatic_rotation_blocked",
                    target_id=str(row["slot_id"]),
                    payload={
                        "slot_name": row["name"],
                        "error_code": error_code,
                    },
                )
                transitions += 1

            remaining = MAX_TRANSITIONS_PER_SCAN - transitions
            if remaining <= 0:
                return transitions

            candidates = await conn.fetch(
                """
                SELECT s.project_id, s.id AS slot_id, s.name,
                       k.id AS active_key_id, k.expires_at
                FROM project_api_key_slots s
                JOIN projects p ON p.id = s.project_id
                JOIN project_api_keys k ON k.slot_id = s.id
                WHERE p.automatic_key_rotation_enabled
                  AND p.opaque_keys_activated_at IS NOT NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND s.automatic_rotation_enabled
                  AND s.status = 'active'
                  AND s.automatic_rotation_blocked_at IS NULL
                  AND k.status = 'active'
                  AND k.expires_at > now()
                  AND k.expires_at <= now() + make_interval(days => $1)
                  AND NOT EXISTS (
                      SELECT 1 FROM project_api_keys pending
                      WHERE pending.slot_id = s.id
                        AND pending.status = 'pending'
                  )
                ORDER BY k.expires_at, s.id
                FOR UPDATE OF s, k SKIP LOCKED
                LIMIT $2
                """,
                AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
                remaining,
            )
            for row in candidates:
                issued, version = await prepare_slot_rotation(
                    conn,
                    project_id=row["project_id"],
                    slot_id=row["slot_id"],
                    activate_at=row["expires_at"],
                    retain_reveal=True,
                    rotation_trigger="automatic",
                )
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=None,
                    action="opaque_api_key_automatic_rotation_prepared",
                    target_type="project_api_key",
                    target_id=str(issued.key_id),
                    new_value={
                        "slot_id": str(row["slot_id"]),
                        "slot_name": row["name"],
                        "activate_at": issued.activate_at.isoformat(),
                        "token_hint": issued.token_hint,
                        "api_keyset_version": version,
                    },
                )
                await _notify_project_admins(
                    conn,
                    project_id=row["project_id"],
                    kind="opaque_api_key_automatic_rotation_prepared",
                    target_id=str(issued.key_id),
                    payload={
                        "slot_id": str(row["slot_id"]),
                        "slot_name": row["name"],
                        "activate_at": issued.activate_at.isoformat(),
                        "token_hint": issued.token_hint,
                    },
                )
                transitions += 1

    return transitions


async def _automatic_opaque_key_rotation_loop() -> None:
    while True:
        try:
            await scan_automatic_opaque_key_rotations()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[automatic-opaque-key-rotation] scan failed: {exc}")
        await asyncio.sleep(AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS)


async def start_automatic_opaque_key_rotation() -> None:
    global _automatic_opaque_key_rotation_task
    if _automatic_opaque_key_rotation_task is not None:
        raise RuntimeError("automatic opaque-key rotation scheduler already started")
    await scan_automatic_opaque_key_rotations()
    _automatic_opaque_key_rotation_task = asyncio.create_task(
        _automatic_opaque_key_rotation_loop(),
        name="automatic-opaque-key-rotation",
    )


async def stop_automatic_opaque_key_rotation() -> None:
    global _automatic_opaque_key_rotation_task
    if _automatic_opaque_key_rotation_task is None:
        return
    _automatic_opaque_key_rotation_task.cancel()
    try:
        await _automatic_opaque_key_rotation_task
    except asyncio.CancelledError:
        pass
    _automatic_opaque_key_rotation_task = None
