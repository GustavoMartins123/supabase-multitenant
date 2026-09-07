from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

import asyncpg

from app.database import get_pool
from app.dependencies import (
    ensure_project_member_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.jobs import (
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
    set_job_status as _set_job_status,
)
from app.key_rotation import project_key_schedule
from app.project_backgrounds import (
    _delete_project_background,
    _duplicate_and_store_keys,
    _fail_job_from_command,
    _get_job_project_uuid,
    _get_project_file_size_limit,
    _get_project_storage_limit_token,
    _job_progress_mirror,
    _provision_and_store_keys,
    _serialize_queued_job,
    rollback_project_from_db,
)
from app.opaque_key_service import bootstrap_project_opaque_keys
from app.project_deletion import (
    ProjectDeletionError,
    build_global_delete_token,
    build_realtime_delete_token,
    delete_realtime_tenant,
    delete_supavisor_tenant,
    drain_database_connections,
    drop_database_force,
    drop_supabase_replication_slots,
    global_admin_connection,
    load_project_environment,
    terminate_supavisor_pools,
)
from app.project_env_secrets import (
    PROJECTS_ROOT,
    read_project_secret_keys as _read_project_secret_keys,
)
from app.project_identity import (
    ProjectIdentityError,
    get_job_project_identity as _get_job_project_identity,
    parse_tenant_uuid,
)
from app.project_secret_service import store_project_secrets
from app.runtime_config import (
    AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
    KEY_EXPIRY_WARNING_DAYS,
    NGINX_HMAC_SECRET,
    USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
)
from app.schemas import DuplicateProject, NewProject
from app.step_up_auth import consume_step_up_grant
from app.validation import validate_project_id

router = APIRouter(tags=["projects"])


class ProjectListItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    project_uuid: str
    tenant_uuid: str | None
    name: str
    display_name: str | None
    file_size_limit: str
    storage_limit_token: str
    internal_token_expires_at: int | None
    internal_token_expired: bool
    internal_token_expiring_soon: bool
    internal_token_expiry_warning_days: int
    automatic_key_rotation_enabled: bool
    automatic_key_rotation_lead_days: int
    automatic_key_rotation_due_at: int | None
    automatic_key_rotation_blocked: bool
    automatic_key_rotation_last_error: str | None
    last_key_rotation_at: str | None
    opaque_api_keys_status: str
    opaque_api_key_slot_count: int


class QueuedJobResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    project: str
    project_uuid: str | None
    tenant_uuid: str | None
    created_by: str | None
    action: str
    status: str
    message: str | None
    progress: int | None
    current_step: str | None
    total_steps: int | None
    started_at: str | None
    finished_at: str | None
    error_code: str | None
    is_idempotent: bool
    retryable: bool
    retry_of: str | None
    attempt: int
    created_at: str | None
    updated_at: str | None
    queue_position: int


@router.get("/api/projects", response_model=list[ProjectListItem])
async def list_projects(
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("""
                SELECT p.id, p.tenant_uuid, p.name, p.display_name,
                       p.automatic_key_rotation_enabled,
                       p.automatic_key_rotation_blocked_at,
                       p.automatic_key_rotation_last_error,
                       p.last_key_rotation_at, p.key_expires_at,
                       p.opaque_keys_prepared_at,
                       p.opaque_keys_activated_at,
                       p.opaque_gateway_cutover_started_at,
                       p.opaque_gateway_ready_at,
                       (
                           SELECT count(*)
                           FROM project_api_key_slots s
                           WHERE s.project_id = p.id AND s.status = 'active'
                       ) AS opaque_key_slot_count
                FROM projects p
                WHERE p.anon_key IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM project_members m
                      WHERE m.project_id = p.id
                        AND m.user_id = $1
                  )
                ORDER BY p.name
            """, auth_user["db_user_id"])
            result = []
            for r in rows:
                key_expires_at = (
                    int(r["key_expires_at"].timestamp())
                    if r["key_expires_at"] is not None
                    else None
                )
                seconds_remaining = (
                    key_expires_at - int(time.time())
                    if key_expires_at is not None
                    else None
                )
                result.append({
                    "project_uuid": str(r["id"]),
                    "tenant_uuid": (
                        str(r["tenant_uuid"]) if r["tenant_uuid"] else None
                    ),
                    "name": r["name"],
                    "display_name": r["display_name"],
                    "file_size_limit": _get_project_file_size_limit(r["name"]),
                    "storage_limit_token": _get_project_storage_limit_token(r["name"]),
                    "internal_token_expires_at": key_expires_at,
                    "internal_token_expired": (
                        seconds_remaining is not None and seconds_remaining <= 0
                    ),
                    "internal_token_expiring_soon": (
                        seconds_remaining is not None
                        and seconds_remaining <= KEY_EXPIRY_WARNING_DAYS * 86400
                    ),
                    "internal_token_expiry_warning_days": KEY_EXPIRY_WARNING_DAYS,
                    "automatic_key_rotation_enabled": r[
                        "automatic_key_rotation_enabled"
                    ],
                    "automatic_key_rotation_lead_days": (
                        AUTOMATIC_KEY_ROTATION_LEAD_DAYS
                    ),
                    "automatic_key_rotation_due_at": (
                        key_expires_at - AUTOMATIC_KEY_ROTATION_LEAD_DAYS * 86400
                        if key_expires_at is not None
                        else None
                    ),
                    "automatic_key_rotation_blocked": (
                        r["automatic_key_rotation_blocked_at"] is not None
                    ),
                    "automatic_key_rotation_last_error": r[
                        "automatic_key_rotation_last_error"
                    ],
                    "last_key_rotation_at": (
                        r["last_key_rotation_at"].isoformat()
                        if r["last_key_rotation_at"]
                        else None
                    ),
                    "opaque_api_keys_status": (
                        "active"
                        if r["opaque_gateway_ready_at"] is not None
                        else "gateway_recovery_required"
                        if (
                            r["opaque_gateway_cutover_started_at"] is not None
                            or r["opaque_keys_activated_at"] is not None
                        )
                        else "prepared"
                        if r["opaque_keys_prepared_at"] is not None
                        else "legacy"
                    ),
                    "opaque_api_key_slot_count": int(
                        r["opaque_key_slot_count"]
                    ),
                })
    return result


@router.post("/api/projects", status_code=202, response_model=QueuedJobResponse)
async def create_project(
    body: NewProject,
    request: Request,
    pool=Depends(get_pool),
):
    name = validate_project_id(body.name)

    if not name:
        raise HTTPException(400, "name required")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"project-name:{name}",
            )
            existing = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1",
                name
            )
            if existing:
                raise HTTPException(status_code=409, detail="Project already exists")
            project_id = uuid.uuid4()
            try:
                await conn.execute(
                    """
                    INSERT INTO projects(id, tenant_uuid, name, owner_id, resource_profile)
                    VALUES($1, $1, $2, $3, $4)
                    """,
                    project_id,
                    name,
                    auth_user["db_user_id"],
                    body.resource_profile,
                )
                await conn.execute(
                        """
                        INSERT INTO project_members(project_id, user_id, role)
                        VALUES($1, $2, 'admin')
                        """,
                        project_id, auth_user["db_user_id"]
                    )
            except asyncpg.UniqueViolationError:
                raise HTTPException(status_code=409, detail="Project already exists")
            job_id = await _create_project_job(
                pool,
                name,
                auth_user["db_user_id"],
                action="create",
                payload={
                    "project_name": name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "tenant_uuid": str(project_id),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )

    position = await _enqueue_project_action(
        name,
        job_id,
        lambda: _provision_and_store_keys(
            job_id, name, auth_user["db_user_id"]
        ),
    )
    message = (
        "Criação enfileirada."
        if position == 0
        else f"Criação enfileirada. Existem {position} ações antes desta na fila para {name}."
    )
    return await _serialize_queued_job(pool, job_id, position, message)


@router.post("/api/projects/duplicate", status_code=202, response_model=QueuedJobResponse)
async def duplicate_project(
    body: DuplicateProject,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Duplica um projeto existente.
    - Valida acesso do usuário ao projeto original
    - Cria registro no banco
    - Dispara job em background para executar script de duplicação
    """
    original = validate_project_id(body.original_name)
    new_name = validate_project_id(body.new_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"project-name:{new_name}",
            )
            project_row = await get_project_row(conn, original)
            await ensure_project_member_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
            )

            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM projects WHERE name = $1)",
                new_name
            )
            if exists:
                raise HTTPException(409, "Nome de projeto já existe")

            project_id = uuid.uuid4()
            try:
                await conn.execute(
                    """
                    INSERT INTO projects(id, tenant_uuid, name, owner_id,
                                         resource_profile)
                    SELECT $1, $1, $2, $3, resource_profile
                    FROM projects WHERE id = $4
                    """,
                    project_id,
                    new_name,
                    auth_user["db_user_id"],
                    project_row["id"],
                )

                await conn.execute("""
                    INSERT INTO project_members(project_id, user_id, role)
                    VALUES($1, $2, 'admin')
                """, project_id, auth_user["db_user_id"])
            except asyncpg.UniqueViolationError:
                raise HTTPException(409, "Nome de projeto já existe")

            job_id = await _create_project_job(
                pool,
                new_name,
                auth_user["db_user_id"],
                action="duplicate",
                payload={
                    "original_name": original,
                    "new_name": new_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "copy_data": body.copy_data,
                    "tenant_uuid": str(project_id),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )

    position = await _enqueue_project_action(
        new_name,
        job_id,
        lambda: _duplicate_and_store_keys(
            job_id,
            original,
            new_name,
            auth_user["db_user_id"],
            body.copy_data,
        ),
    )

    message = (
        "Duplicação enfileirada."
        if position == 0
        else f"Duplicação enfileirada. Existem {position} ações antes desta na fila para {new_name}."
    )
    return await _serialize_queued_job(pool, job_id, position, message)

@router.delete("/api/projects/{project_name}", response_model=QueuedJobResponse)
async def delete_project(
    project_name: str,
    request: Request,
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "Admin required")

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await conn.fetchrow(
                """
                SELECT id, tenant_uuid
                FROM projects
                WHERE name = $1
                FOR UPDATE
                """,
                project_name,
            )
            if not project_row:
                raise HTTPException(404, "Project not found")
            await consume_step_up_grant(
                conn,
                token=x_step_up_token,
                secret=NGINX_HMAC_SECRET,
                max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
                auth_user=auth_user,
                action="delete_project",
                project_id=project_row["id"],
                project_ref=project_name,
                resource_id=project_name,
            )

    project_id = project_row["id"]
    tenant_uuid = parse_tenant_uuid(project_row["tenant_uuid"])
    if tenant_uuid is None:
        raise HTTPException(
            409,
            "Project tenant UUID is missing; run the canonical migration first",
        )

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Exclusão enfileirada.",
        action="delete",
        payload={
            "project_name": project_name,
            "tenant_uuid": str(tenant_uuid),
        },
        total_steps=8,
        project_uuid=project_id,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _delete_project_background(job_id, project_name),
    )
    message = (
        "Exclusão enfileirada. Será executada quando não houver outras ações "
        "em andamento para este projeto."
        if position == 0
        else f"Exclusão enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )
