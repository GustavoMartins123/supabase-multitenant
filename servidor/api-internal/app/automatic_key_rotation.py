"""Agendamento duravel da rotacao automatica das API keys de projeto."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Awaitable, Callable

from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.jobs import create_project_job
from app.key_rotation import project_key_schedule
from app.project_secret_service import decrypt_project_secret
from app.runtime_config import (
    AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS,
    AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
    AUTOMATIC_KEY_ROTATION_MAX_CONCURRENT,
)


AUTOMATIC_KEY_ROTATION_LOCK_NAME = "supabase-multitenant:auto-key-rotation:v1"
JobRunner = Callable[[], Awaitable[None]]
EnqueueAction = Callable[[str, str, JobRunner], Awaitable[int]]
RotationRunner = Callable[..., Awaitable[None]]

_automatic_key_rotation_task: asyncio.Task[None] | None = None


async def block_automatic_key_rotation(
    project_name: str,
    *,
    error_code: str,
    detail: str,
    job_id: str | None = None,
) -> None:
    """Interrompe novas tentativas automaticas ate intervencao explicita."""
    pool = await get_pool()
    safe_detail = detail.strip()[:500] or error_code
    async with pool.acquire() as conn:
        async with conn.transaction():
            project_id = await conn.fetchval(
                """
                UPDATE projects
                SET automatic_key_rotation_blocked_at = now(),
                    automatic_key_rotation_last_error = $2
                WHERE name = $1
                  AND automatic_key_rotation_enabled
                RETURNING id
                """,
                project_name,
                f"{error_code}: {safe_detail}",
            )
            if project_id is not None:
                await audit_studio_action(
                    conn,
                    project_id=project_id,
                    actor_user_id=None,
                    action="automatic_key_rotation_blocked",
                    target_type="project_keys",
                    target_id=job_id,
                    new_value={
                        "error_code": error_code,
                        "detail": safe_detail,
                    },
                )


async def scan_automatic_key_rotations(
    *,
    enqueue_action: EnqueueAction,
    rotation_runner: RotationRunner,
) -> int:
    """Cria no maximo um job devido por projeto, com lideranca no Postgres."""
    pool = await get_pool()
    claimed: list[tuple[str, str]] = []

    async with pool.acquire() as conn:
        async with conn.transaction():
            owns_scan = await conn.fetchval(
                "SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))",
                AUTOMATIC_KEY_ROTATION_LOCK_NAME,
            )
            if not owns_scan:
                return 0

            active_automatic = await conn.fetchval(
                """
                SELECT count(*)
                FROM jobs
                WHERE action = 'rotate_key'
                  AND status IN ('queued', 'running')
                  AND payload->>'trigger' = 'automatic'
                """
            )
            capacity = max(
                0,
                AUTOMATIC_KEY_ROTATION_MAX_CONCURRENT
                - int(active_automatic or 0),
            )
            if capacity == 0:
                return 0

            candidates = await conn.fetch(
                """
                SELECT p.id, p.name, p.anon_key, p.service_role,
                       p.key_expires_at
                FROM projects p
                WHERE p.automatic_key_rotation_enabled
                  AND p.automatic_key_rotation_blocked_at IS NULL
                  AND p.opaque_gateway_ready_at IS NOT NULL
                  AND p.anon_key IS NOT NULL
                  AND p.service_role IS NOT NULL
                  AND (
                      p.key_expires_at IS NULL
                      OR p.key_expires_at <= now() + make_interval(days => $1)
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM jobs j
                      WHERE j.project_uuid = p.id
                        AND j.status IN ('queued', 'running')
                  )
                ORDER BY p.key_expires_at ASC NULLS FIRST, p.name ASC
                FOR UPDATE OF p SKIP LOCKED
                LIMIT $2
                """,
                AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
                max(50, capacity * 10),
            )

            for project in candidates:
                if len(claimed) >= capacity:
                    break
                expires_at = project["key_expires_at"]
                if expires_at is None:
                    try:
                        anon_key = await decrypt_project_secret(
                            conn,
                            project_id=project["id"],
                            column="anon_key",
                            ciphertext=project["anon_key"],
                        )
                        service_role = await decrypt_project_secret(
                            conn,
                            project_id=project["id"],
                            column="service_role",
                            ciphertext=project["service_role"],
                        )
                        schedule = project_key_schedule(
                            anon_key,
                            service_role,
                            lead_days=AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
                        )
                    except Exception as exc:
                        safe_error = str(exc).strip()[:500] or "metadata invalida"
                        await conn.execute(
                            """
                            UPDATE projects
                            SET automatic_key_rotation_blocked_at = now(),
                                automatic_key_rotation_last_error = $2
                            WHERE id = $1
                            """,
                            project["id"],
                            f"invalid_key_metadata: {safe_error}",
                        )
                        await audit_studio_action(
                            conn,
                            project_id=project["id"],
                            actor_user_id=None,
                            action="automatic_key_rotation_blocked",
                            target_type="project_keys",
                            new_value={
                                "error_code": "invalid_key_metadata",
                                "detail": safe_error,
                            },
                        )
                        continue
                    expires_at = schedule.expires_at
                    await conn.execute(
                        "UPDATE projects SET key_expires_at = $2 WHERE id = $1",
                        project["id"],
                        expires_at,
                    )

                rotate_at = expires_at - dt.timedelta(
                    days=AUTOMATIC_KEY_ROTATION_LEAD_DAYS
                )
                if rotate_at > dt.datetime.now(dt.timezone.utc):
                    continue

                job_id = await create_project_job(
                    pool,
                    project["name"],
                    None,
                    message="Rotacao automatica de chaves enfileirada.",
                    action="rotate_key",
                    payload={
                        "project_name": project["name"],
                        "trigger": "automatic",
                    },
                    total_steps=4,
                    project_uuid=project["id"],
                    connection=conn,
                )
                claimed.append((project["name"], job_id))

    for project_name, job_id in claimed:
        try:
            await enqueue_action(
                project_name,
                job_id,
                lambda job_id=job_id, project_name=project_name: rotation_runner(
                    job_id,
                    project_name,
                    None,
                    trigger="automatic",
                ),
            )
        except Exception as exc:
            await block_automatic_key_rotation(
                project_name,
                error_code="automatic_rotation_enqueue_failed",
                detail=str(exc),
                job_id=job_id,
            )
    return len(claimed)


async def _automatic_key_rotation_loop(
    *,
    enqueue_action: EnqueueAction,
    rotation_runner: RotationRunner,
) -> None:
    while True:
        try:
            await scan_automatic_key_rotations(
                enqueue_action=enqueue_action,
                rotation_runner=rotation_runner,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[automatic-key-rotation] scan failed: {exc}")
        await asyncio.sleep(AUTOMATIC_KEY_ROTATION_CHECK_INTERVAL_SECONDS)


async def start_automatic_key_rotation(
    *,
    enqueue_action: EnqueueAction,
    rotation_runner: RotationRunner,
) -> None:
    global _automatic_key_rotation_task
    if _automatic_key_rotation_task is not None:
        raise RuntimeError("automatic key rotation scheduler already started")
    await scan_automatic_key_rotations(
        enqueue_action=enqueue_action,
        rotation_runner=rotation_runner,
    )
    _automatic_key_rotation_task = asyncio.create_task(
        _automatic_key_rotation_loop(
            enqueue_action=enqueue_action,
            rotation_runner=rotation_runner,
        ),
        name="automatic-key-rotation",
    )


async def stop_automatic_key_rotation() -> None:
    global _automatic_key_rotation_task
    if _automatic_key_rotation_task is None:
        return
    _automatic_key_rotation_task.cancel()
    try:
        await _automatic_key_rotation_task
    except asyncio.CancelledError:
        pass
    _automatic_key_rotation_task = None
