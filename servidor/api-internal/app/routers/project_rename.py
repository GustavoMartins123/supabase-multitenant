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
    set_job_status as _set_job_status,
)
from app.host_agent import (
    command_result,
    run_command_for_job as run_host_agent_command_for_job,
)
from app.validation import validate_project_id
from app.control_plane_service import (
    audit_studio_action,
    create_studio_notification,
)
from app.snippets_migration import rename_project_snippets
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.main import _RENAME_HISTORY_ACTIONS
from app.project_backgrounds import (
    _job_progress_mirror,
    _rename_project_background,
    _serialize_queued_job,
    _update_rename_history,
)

router = APIRouter(tags=["project-rename"])


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
    old_name: str
    new_name: str


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
    old_name: str
    new_name: str
    old_path: str
    new_path: str
    status: str
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


class ProjectRenameHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    requested_name: str
    events: list[RenameHistoryEvent]
    renames: list[RenameHistoryEntry]


def _validate_rename_target(raw: str) -> str:
    return validate_project_id(raw)


@router.post("/api/projects/{project_name}/rename", status_code=202, response_model=RenameProjectResponse)
async def rename_project(
    project_name: str,
    body: ProjectRenameRequest,
    request: Request,
    pool=Depends(get_pool),
):
    """Renomeia o slug/path do projeto (migração completa em background).

    O escopo inclui: nome interno na meta DB, banco Postgres, roles
    por projeto, replication slots do Realtime, tenant Supavisor,
    diretório físico e templates (nginx, docker-compose, .env).
    """
    project_name = validate_project_id(project_name)
    new_name = _validate_rename_target(body.new_name)
    if new_name == project_name:
        raise HTTPException(400, "O novo nome deve ser diferente do atual")
    display_name_raw = (
        body.display_name.strip() if body.display_name is not None else None
    )

    auth_user = await resolve_authenticated_user(request, pool)

    display_name_changed = False
    previous_display: str | None = None

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                f"project-name:{new_name}",
            )
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admin do projeto ou admin global pode renomear",
            )

            collision = await conn.fetchval(
                "SELECT 1 FROM projects WHERE name = $1",
                new_name,
            )
            if collision:
                raise HTTPException(409, f"Já existe um projeto com nome '{new_name}'")

            reserved_destination = await conn.fetchval(
                """
                SELECT 1
                FROM project_name_history
                WHERE new_name = $1
                  AND status IN ('queued', 'running')
                LIMIT 1
                """,
                new_name,
            )
            if reserved_destination:
                raise HTTPException(
                    409, f"Ja existe uma renomeacao ativa para o nome '{new_name}'"
                )

            active_rename = await conn.fetchval(
                """
                SELECT 1
                FROM project_name_history
                WHERE project_id = $1
                  AND status IN ('queued', 'running')
                LIMIT 1
                """,
                project_id,
            )
            if active_rename:
                raise HTTPException(409, "Ja existe uma renomeacao ativa para este projeto")

            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message=f"Rename iniciado: {project_name} -> {new_name}",
                action="rename",
                payload={
                    "old_name": project_name,
                    "new_name": new_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                },
                total_steps=9,
                project_uuid=project_id,
                connection=conn,
            )
            history_id = await conn.fetchval(
                """
                INSERT INTO project_name_history(
                    project_id, job_id, actor_user_id,
                    old_name, new_name, old_path, new_path
                )
                VALUES($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                project_id,
                job_id,
                auth_user["db_user_id"],
                project_name,
                new_name,
                f"/{project_name}",
                f"/{new_name}",
            )

            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_rename_started",
                target_type="project",
                target_id=project_name,
                old_value={"name": project_name, "path": f"/{project_name}"},
                new_value={"name": new_name, "path": f"/{new_name}"},
            )

            if display_name_raw:
                current_display = project_row["display_name"]
                if current_display != display_name_raw:
                    previous_display = current_display
                    await conn.execute(
                        "UPDATE projects SET display_name = $1 WHERE id = $2",
                        display_name_raw,
                        project_id,
                    )
                    await audit_studio_action(
                        conn,
                        project_id=project_id,
                        actor_user_id=auth_user["db_user_id"],
                        action="project_display_name_changed",
                        target_type="project",
                        target_id=project_name,
                        old_value={"display_name": current_display},
                        new_value={"display_name": display_name_raw},
                    )
                    display_name_changed = True

    try:
        position = await _enqueue_project_action(
            project_name,
            job_id,
            lambda: _rename_project_background(
                job_id,
                project_id,
                history_id,
                project_name,
                new_name,
                auth_user["db_user_id"],
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        message = $1,
                        current_step = 'enqueue_failed',
                        error_code = 'queue_submit_failed',
                        finished_at = now(),
                        updated_at = now()
                    WHERE job_id = $2
                    """,
                    "Falha interna ao enfileirar a renomeação.",
                    job_id,
                )
                await _update_rename_history(
                    conn,
                    history_id,
                    "failed",
                    error="queue_submit_failed",
                )
                if display_name_changed:
                    await conn.execute(
                        """
                        UPDATE projects SET display_name = $1
                        WHERE id = $2 AND display_name = $3
                        """,
                        previous_display,
                        project_id,
                        display_name_raw,
                    )
                    await audit_studio_action(
                        conn,
                        project_id=project_id,
                        actor_user_id=auth_user["db_user_id"],
                        action="project_display_name_changed",
                        target_type="project",
                        target_id=project_name,
                        old_value={"display_name": display_name_raw},
                        new_value={"display_name": previous_display},
                    )
        raise HTTPException(503, "Nao foi possivel enfileirar a renomeacao") from exc

    message = (
        "Renomeação enfileirada. O projeto ficará indisponível durante a migração."
        if position == 0
        else f"Renomeação enfileirada. Existem {position} ações na fila para "
        f"{project_name}; este job é o próximo."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(
            pool,
            job_id,
            position,
            message,
            extra={"old_name": project_name, "new_name": new_name},
        ),
    )


@router.patch("/api/projects/{project_name}/display-name", response_model=UpdateDisplayNameResponse)
async def update_project_display_name(
    project_name: str,
    body: ProjectDisplayNameUpdate,
    request: Request,
    pool=Depends(get_pool),
):
    """Atualiza apenas o display_name do projeto (sem migrar infraestrutura)."""
    project_name = validate_project_id(project_name)
    new_display = body.display_name.strip()
    if not new_display:
        raise HTTPException(400, "display_name não pode ser vazio")

    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
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
                    "project": project_name,
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
                target_id=project_name,
                old_value={"display_name": current_display},
                new_value={"display_name": new_display},
            )

    return {
        "project": project_name,
        "display_name": new_display,
        "status": "updated",
    }


@router.get("/api/projects/{project_name}/config-token", response_model=ProjectConfigTokenResponse)
async def get_project_config_token(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Entrega o token compartilhado aos membros do projeto e registra a leitura."""
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
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
                target_id=project_name,
            )

    return JSONResponse(
        content={"project": project_name, "config_token": token},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/projects/{project_name}/queue-status", response_model=ProjectQueueStatusResponse)
async def get_project_queue_status(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Retorna o estado atual da fila de ações do projeto.

    Inclui o job em execução (se houver), o tamanho da fila, e os jobs
    pendentes/rodando do banco para fins de UI (polling).
    """
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
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
            WHERE project = $1
              AND status IN ('queued', 'running')
            ORDER BY updated_at ASC
            """,
            project_name,
        )

    queue_state = action_queue.status(project_name)
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
        "project": project_name,
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


@router.get("/api/projects/{project_name}/rename-history", response_model=ProjectRenameHistoryResponse)
async def get_project_rename_history(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=500),
):
    """Retorna auditoria e historico duravel de nome/path do projeto."""
    project_name = validate_project_id(project_name)

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE name = $1",
            project_name,
        )
        if not project_row:
            project_row = await conn.fetchrow(
                """
                SELECT p.id, p.name
                FROM project_name_history h
                JOIN projects p ON p.id = h.project_id
                WHERE h.old_name = $1 OR h.new_name = $1
                ORDER BY h.created_at DESC
                LIMIT 1
                """,
                project_name,
            )
        if not project_row:
            raise HTTPException(404, "Project not found")
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
                a.old_value,
                a.new_value,
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
                h.old_name,
                h.new_name,
                h.old_path,
                h.new_path,
                h.status,
                h.error,
                h.created_at,
                h.updated_at,
                h.completed_at,
                h.actor_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM project_name_history h
            LEFT JOIN users u ON u.id = h.actor_user_id
            WHERE h.project_id = $1
            ORDER BY h.created_at DESC
            LIMIT $2
            """,
            project_id,
            limit,
        )

    return {
        "project": project_row["name"],
        "requested_name": project_name,
        "events": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "actor_user_id": (
                    str(r["actor_user_id"]) if r["actor_user_id"] else None
                ),
                "actor_name": r["actor_name"],
                "target_id": r["target_id"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
        "renames": [
            {
                "id": str(r["id"]),
                "job_id": str(r["job_id"]),
                "actor_user_id": (
                    str(r["actor_user_id"]) if r["actor_user_id"] else None
                ),
                "actor_name": r["actor_name"],
                "old_name": r["old_name"],
                "new_name": r["new_name"],
                "old_path": r["old_path"],
                "new_path": r["new_path"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "completed_at": (
                    r["completed_at"].isoformat() if r["completed_at"] else None
                ),
            }
            for r in history_rows
        ],
    }
