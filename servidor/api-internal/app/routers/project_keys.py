from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.automatic_key_rotation import block_automatic_key_rotation
from app.automatic_opaque_key_rotation import scan_automatic_opaque_key_rotations
from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import (
    HostAgentError,
    run_command_for_job as run_host_agent_command_for_job,
)
from app.jobs import (
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
    set_job_status as _set_job_status,
)
from app.key_rotation import KeyRotationMetadataError, project_key_schedule
from app.main import (
    _scan_automatic_key_rotations,
)
from app.project_backgrounds import (
    _fail_job_from_command,
    _get_job_project_uuid,
    _job_progress_mirror,
    _rotate_project_key_background,
    _serialize_queued_job,
)
from app.opaque_key_service import cancel_project_automatic_pending_keys
from app.project_env_secrets import (
    read_project_secret_keys as _read_project_secret_keys,
)
from app.project_secret_service import store_project_secrets
from app.runtime_config import AUTOMATIC_KEY_ROTATION_LEAD_DAYS
from app.schemas import AutomaticKeyRotationUpdate
from app.service_key_cache import invalidate_service_key_cache
from app.validation import validate_project_id

router = APIRouter(tags=["project-keys"])


@router.put("/api/projects/{project_name}/automatic-key-rotation")
async def update_automatic_key_rotation(
    project_name: str,
    body: AutomaticKeyRotationUpdate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            await ensure_project_admin_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
                message=(
                    "Only project admin or system admin can configure "
                    "automatic key rotation"
                ),
            )
            old_enabled = bool(project_row["automatic_key_rotation_enabled"])
            updated = await conn.fetchrow(
                """
                UPDATE projects
                SET automatic_key_rotation_enabled = $2,
                    automatic_key_rotation_blocked_at = CASE
                        WHEN $2 THEN NULL
                        ELSE automatic_key_rotation_blocked_at
                    END,
                    automatic_key_rotation_last_error = CASE
                        WHEN $2 THEN NULL
                        ELSE automatic_key_rotation_last_error
                    END
                WHERE id = $1
                RETURNING automatic_key_rotation_enabled,
                          automatic_key_rotation_blocked_at,
                          automatic_key_rotation_last_error
                """,
                project_row["id"],
                body.enabled,
            )
            opaque_keyset_version = None
            if not body.enabled:
                opaque_keyset_version = (
                    await cancel_project_automatic_pending_keys(
                        conn, project_id=project_row["id"]
                    )
                )
            await audit_studio_action(
                conn,
                project_id=project_row["id"],
                actor_user_id=auth_user["db_user_id"],
                action="automatic_key_rotation_updated",
                target_type="project_keys",
                old_value={"enabled": old_enabled},
                new_value={
                    "enabled": body.enabled,
                    "opaque_api_keyset_version": opaque_keyset_version,
                },
            )

    if body.enabled:
        await _scan_automatic_key_rotations()
        await scan_automatic_opaque_key_rotations()
    return {
        "automatic_key_rotation_enabled": updated[
            "automatic_key_rotation_enabled"
        ],
        "automatic_key_rotation_blocked": (
            updated["automatic_key_rotation_blocked_at"] is not None
        ),
        "automatic_key_rotation_last_error": updated[
            "automatic_key_rotation_last_error"
        ],
        "automatic_key_rotation_lead_days": AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
    }


@router.post("/api/projects/{project_name}/rotate-key", status_code=202)
async def rotate_project_key(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Rotaciona anon/service_role via script. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            await ensure_project_admin_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
                message="Only project admin or system admin can rotate keys",
            )
            if project_row["opaque_gateway_ready_at"] is None:
                raise HTTPException(
                    409,
                    "Conclua a migracao do gateway opaco antes de rotacionar "
                    "os tokens internos",
                )
            await conn.execute(
                "SELECT id FROM projects WHERE id = $1 FOR UPDATE",
                project_row["id"],
            )
            active_rotation = await conn.fetchval(
                """
                SELECT job_id FROM jobs
                WHERE project_uuid = $1
                  AND action = 'rotate_key'
                  AND status IN ('queued', 'running')
                LIMIT 1
                """,
                project_row["id"],
            )
            if active_rotation is not None:
                raise HTTPException(
                    409,
                    "Ja existe uma rotacao de chaves ativa para este projeto",
                )
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Rotação de chaves enfileirada.",
                action="rotate_key",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "trigger": "manual",
                },
                total_steps=4,
                project_uuid=project_row["id"],
                connection=conn,
            )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _rotate_project_key_background(
            job_id,
            project_name,
            auth_user["db_user_id"],
            trigger="manual",
        ),
    )
    message = (
        "Rotação enfileirada."
        if position == 0
        else f"Rotação enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )
