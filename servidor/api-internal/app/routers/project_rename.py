import json
import uuid
from typing import Any

import asyncpg
from pydantic import BaseModel, ConfigDict

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from app.schemas import ProjectRenameRequest, ProjectDisplayNameUpdate
from app.project_secret_service import decrypt_project_secret
from app.jobs import (
    action_queue,
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
)
from app.validation import validate_project_ref
from app.project_public_ref import generate_public_ref
from app.control_plane_service import (
    audit_studio_action,
)
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    get_public_project_row,
    resolve_authenticated_user,
)
from app.main import _RENAME_HISTORY_ACTIONS
from app.project_backgrounds import (
    _rename_project_background,
    _serialize_queued_job,
    _update_rename_history,
)

router = APIRouter(tags=["project-rename"])


def _audit_object(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    decoded = json.loads(value)
    if not isinstance(decoded, dict):
        raise RuntimeError("Audit value must be a JSON object")
    return decoded


class RenameProjectResponse(BaseModel):
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
    old_ref: str
    new_ref: str


class UpdateDisplayNameResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    display_name: str
    status: str


class ProjectConfigTokenResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    config_token: str


class ProjectQueueInFlightJob(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    status: str
    message: str | None
    action: str
    progress: int | None
    current_step: str | None
    total_steps: int | None
    updated_at: str


class ProjectQueueStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    is_busy: bool
    current_job_id: str | None
    queued: int
    in_flight: list[ProjectQueueInFlightJob]
    message: str


class RenameHistoryEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    action: str
    actor_user_id: str | None
    actor_name: str
    target_id: str | None
    old_value: dict[str, Any] | None
    new_value: dict[str, Any] | None
    created_at: str


class RenameHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    job_id: str
    actor_user_id: str | None
    actor_name: str
    old_ref: str
    new_ref: str
    status: str
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


class ProjectRenameHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    requested_ref: str
    events: list[RenameHistoryEvent]
    renames: list[RenameHistoryEntry]


@router.post(
    "/api/projects/{project_ref}/rename", status_code=202, response_model=RenameProjectResponse
)
async def rename_project(
    project_ref: str,
    body: ProjectRenameRequest,
    request: Request,
    pool=Depends(get_pool),
):
    project_ref = validate_project_ref(project_ref)
    auth_user = await resolve_authenticated_user(request, pool)
    new_ref = generate_public_ref()
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_public_project_row(conn, project_ref)
                await ensure_project_admin_access(
                    conn, project_id=project["id"], auth_user=auth_user
                )
                if not project["tenant_uuid"]:
                    raise HTTPException(409, "Canonical tenant UUID is required")
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", str(project["id"])
                )
                expected_id = project["id"]
                project = await get_public_project_row(conn, project_ref, for_update=True)
                if project["id"] != expected_id:
                    raise HTTPException(409, "Canonical project identity changed")
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                    "project-ref:" + new_ref,
                )
                if new_ref == project_ref or await conn.fetchval(
                    "SELECT 1 FROM projects WHERE public_ref=$1", new_ref
                ):
                    raise HTTPException(409, "Generated public reference collision")
                if await conn.fetchval(
                    "SELECT 1 FROM project_reference_history WHERE project_id=$1 AND status IN ('queued','running')",
                    project["id"],
                ):
                    raise HTTPException(409, "A public reference rotation is already active")
                job_id = await _create_project_job(
                    pool,
                    project["name"],
                    auth_user["db_user_id"],
                    action="rename",
                    message="Rotacao da referencia publica enfileirada.",
                    total_steps=4,
                    project_uuid=project["id"],
                    connection=conn,
                    payload={
                        "old_ref": project_ref,
                        "new_ref": new_ref,
                        "actor_user_id": str(auth_user["db_user_id"]),
                    },
                )
                history_id = await conn.fetchval(
                    "INSERT INTO project_reference_history(project_id,job_id,actor_user_id,old_ref,new_ref) VALUES($1,$2,$3,$4,$5) RETURNING id",
                    project["id"],
                    uuid.UUID(str(job_id)),
                    auth_user["db_user_id"],
                    project_ref,
                    new_ref,
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="project_rename_started",
                    target_type="project",
                    target_id=project_ref,
                    old_value={"ref": project_ref, "path": "/" + project_ref},
                    new_value={"ref": new_ref, "path": "/" + new_ref},
                )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "Public reference reservation conflicted") from exc
    try:
        position = await _enqueue_project_action(
            project["name"],
            job_id,
            lambda: _rename_project_background(
                job_id, project["id"], history_id, project_ref, new_ref, auth_user["db_user_id"]
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "UPDATE jobs SET status='failed', error_code='queue_submit_failed', finished_at=now(), updated_at=now() WHERE job_id=$1",
                    uuid.UUID(str(job_id)),
                )
                await _update_rename_history(
                    conn, history_id, "failed", error="queue_submit_failed"
                )
        raise HTTPException(503, "Could not enqueue public reference rotation") from exc
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(
            pool,
            job_id,
            position,
            "Rotacao da URL enfileirada; dados e nomes internos permanecem iguais.",
            extra={"project": project_ref, "old_ref": project_ref, "new_ref": new_ref},
        ),
    )


@router.patch("/api/projects/{project_ref}/display-name", response_model=UpdateDisplayNameResponse)
async def update_project_display_name(
    project_ref: str,
    body: ProjectDisplayNameUpdate,
    request: Request,
    pool=Depends(get_pool),
):
    """Atualiza apenas o display_name do projeto (sem migrar infraestrutura)."""
    project_ref = validate_project_ref(project_ref)
    new_display = body.display_name.strip()
    if not new_display:
        raise HTTPException(400, "display_name não pode ser vazio")

    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_public_project_row(conn, project_ref, for_update=True)
            project_id = project_row["id"]
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admin do projeto ou admin global pode alterar o display_name",
            )
            current_display = await conn.fetchval(
                "SELECT display_name FROM projects WHERE id = $1",
                project_id,
            )
            if current_display == new_display:
                return {
                    "project": project_ref,
                    "display_name": new_display,
                    "status": "noop",
                }
            await conn.execute(
                "UPDATE projects SET display_name = $1 WHERE id = $2",
                new_display,
                project_id,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_display_name_changed",
                target_type="project",
                target_id=project_ref,
                old_value={"display_name": current_display},
                new_value={"display_name": new_display},
            )

    return {
        "project": project_ref,
        "display_name": new_display,
        "status": "updated",
    }


@router.get("/api/projects/{project_ref}/config-token", response_model=ProjectConfigTokenResponse)
async def get_project_config_token(
    project_ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Entrega o token compartilhado aos membros do projeto e registra a leitura."""
    project_ref = validate_project_ref(project_ref)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_public_project_row(conn, project_ref)
            await ensure_project_member_access(
                conn,
                project_id=project["id"],
                auth_user=auth_user,
                message="Apenas membros podem acessar o config token",
            )
            encrypted_token = await conn.fetchval(
                "SELECT config_token FROM projects WHERE id = $1",
                project["id"],
            )
            if not encrypted_token:
                raise HTTPException(404, "Config token não disponível")
            token = await decrypt_project_secret(
                conn,
                project_id=project["id"],
                column="config_token",
                ciphertext=encrypted_token,
            )
            await audit_studio_action(
                conn,
                project_id=project["id"],
                actor_user_id=auth_user["db_user_id"],
                action="project_config_token_read",
                target_type="project_secret",
                target_id=project_ref,
            )

    return JSONResponse(
        content={"project": project_ref, "config_token": token},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/projects/{project_ref}/queue-status", response_model=ProjectQueueStatusResponse)
async def get_project_queue_status(
    project_ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Retorna o estado atual da fila de ações do projeto.

    Inclui o job em execução (se houver), o tamanho da fila, e os jobs
    pendentes/rodando do banco para fins de UI (polling).
    """
    project_ref = validate_project_ref(project_ref)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_public_project_row(conn, project_ref)
        project_id = project_row["id"]
        await ensure_project_member_access(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )

        in_flight_rows = await conn.fetch(
            """
            SELECT
                job_id,
                status,
                message,
                action,
                progress,
                current_step,
                total_steps,
                updated_at
            FROM jobs
            WHERE project_uuid = $1
              AND status IN ('queued', 'running')
            ORDER BY updated_at ASC
            """,
            project_id,
        )

    queue_state = action_queue.status(project_row["name"])
    in_flight = [
        {
            "job_id": str(r["job_id"]),
            "status": r["status"],
            "message": r["message"],
            "action": r["action"],
            "progress": r["progress"],
            "current_step": r["current_step"],
            "total_steps": r["total_steps"],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in in_flight_rows
    ]

    return {
        "project": project_ref,
        "is_busy": queue_state["is_busy"],
        "current_job_id": queue_state["current_job_id"],
        "queued": queue_state["queued"],
        "in_flight": in_flight,
        "message": (
            "Projeto ocioso."
            if not queue_state["is_busy"] and not in_flight
            else (
                f"Job atual: {queue_state['current_job_id']}."
                if queue_state["is_busy"]
                else f"{len(in_flight)} job(s) em fila no banco."
            )
        ),
    }


@router.get(
    "/api/projects/{project_ref}/rename-history", response_model=ProjectRenameHistoryResponse
)
async def get_project_rename_history(
    project_ref: str,
    request: Request,
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=500),
):
    """Retorna auditoria e historico duravel da referencia publica."""
    project_ref = validate_project_ref(project_ref)

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project_row = await get_public_project_row(conn, project_ref)
        project_id = project_row["id"]
        await ensure_project_member_access(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )

        rows = await conn.fetch(
            """
            SELECT
                a.id,
                a.action,
                a.target_id,
                a.old_value::text AS old_value,
                a.new_value::text AS new_value,
                a.created_at,
                a.actor_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM studio_audit_log a
            LEFT JOIN users u ON u.id = a.actor_user_id
            WHERE a.project_id = $1
              AND a.action = ANY($2::text[])
            ORDER BY a.created_at DESC
            LIMIT $3
            """,
            project_id,
            list(_RENAME_HISTORY_ACTIONS),
            limit,
        )
        history_rows = await conn.fetch(
            """
            SELECT
                h.id,
                h.job_id,
                h.old_ref,
                h.new_ref,
                h.status,
                h.error,
                h.created_at,
                h.updated_at,
                h.completed_at,
                h.actor_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM project_reference_history h
            LEFT JOIN users u ON u.id = h.actor_user_id
            WHERE h.project_id = $1
            ORDER BY h.created_at DESC
            LIMIT $2
            """,
            project_id,
            limit,
        )

    return {
        "project": project_row["public_ref"],
        "requested_ref": project_ref,
        "events": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "actor_user_id": (str(r["actor_user_id"]) if r["actor_user_id"] else None),
                "actor_name": r["actor_name"],
                "target_id": r["target_id"],
                "old_value": _audit_object(r["old_value"]),
                "new_value": _audit_object(r["new_value"]),
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
        "renames": [
            {
                "id": str(r["id"]),
                "job_id": str(r["job_id"]),
                "actor_user_id": (str(r["actor_user_id"]) if r["actor_user_id"] else None),
                "actor_name": r["actor_name"],
                "old_ref": r["old_ref"],
                "new_ref": r["new_ref"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "completed_at": (r["completed_at"].isoformat() if r["completed_at"] else None),
            }
            for r in history_rows
        ],
    }
