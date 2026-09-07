import uuid
import asyncpg
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typing import Any

from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    ensure_project_owner_access,
    get_project_role,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import command_result, run_command_for_job as run_host_agent_command_for_job
from app.main import (
    RESTORE_POINT_LIMIT,
)
from app.jobs import (
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
    set_job_status as _set_job_status,
)
from app.project_backgrounds import (
    _create_restore_point_background,
    _delete_restore_point_background,
    _fail_job_from_command,
    _job_progress_mirror,
    _restore_project_background,
    _serialize_queued_job,
)
from app.project_identity import (
    get_job_project_identity as _get_job_project_identity,
)
from app.schemas import RestorePointCreate
from app.validation import parse_uuid_value, validate_project_id

router = APIRouter(tags=["restore-points"])


class RestorePointItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    description: str | None
    status: str
    is_automatic: bool
    job_id: str | None
    created_by: str | None
    created_by_name: str
    project_ref_at_creation: str
    size_bytes: int | None
    last_restored_at: str | None
    restore_count: int
    error: str | None
    created_at: str | None
    completed_at: str | None


class RestorePointsPermissions(BaseModel):
    model_config = ConfigDict(extra="allow")

    can_create: bool
    can_restore: bool
    can_delete: bool


class ListRestorePointsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    limit: int
    permissions: RestorePointsPermissions
    points: list[RestorePointItem]


class CreateRestorePointResponse(BaseModel):
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
    restore_point_id: str


class RestoreRestorePointResponse(BaseModel):
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
    restore_point_id: str
    safety_point_id: str


class DeleteRestorePointResponse(BaseModel):
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
    restore_point_id: str


def _serialize_restore_point(row: asyncpg.Record) -> dict[str, Any]:
    def iso(column: str) -> str | None:
        value = row[column]
        return value.isoformat() if value else None

    return {
        "id": str(row["id"]),
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "is_automatic": row["is_automatic"],
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_name": row["created_by_name"],
        "project_ref_at_creation": row["project_ref_at_creation"],
        "size_bytes": row["size_bytes"],
        "last_restored_at": iso("last_restored_at"),
        "restore_count": row["restore_count"],
        "error": row["error"],
        "created_at": iso("created_at"),
        "completed_at": iso("completed_at"),
    }


async def _fetch_restore_point_locked(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    point_id: uuid.UUID,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT * FROM project_restore_points
        WHERE id = $1 AND project_id = $2
        FOR UPDATE
        """,
        point_id,
        project_id,
    )
    if not row:
        raise HTTPException(404, "Ponto de restauração não encontrado")
    return row


async def _count_active_restore_points(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
) -> int:
    return await conn.fetchval(
        """
        SELECT count(*) FROM project_restore_points
        WHERE project_id = $1 AND status <> 'failed'
        """,
        project_id,
    )


@router.get("/api/projects/{project_name}/restore-points", response_model=ListRestorePointsResponse)
async def list_project_restore_points(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        await ensure_project_member_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        is_owner = project_row["owner_id"] == auth_user["db_user_id"]
        is_global_admin = auth_user["is_global_admin"]
        rows = await conn.fetch(
            """
            SELECT
                p.*,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS created_by_name
            FROM project_restore_points p
            LEFT JOIN users u ON u.id = p.created_by
            WHERE p.project_id = $1
            ORDER BY p.created_at DESC
            """,
            project_row["id"],
        )

    return {
        "project": project_name,
        "limit": RESTORE_POINT_LIMIT,
        "permissions": {
            "can_create": is_global_admin or is_owner or role == "admin",
            "can_restore": is_global_admin or is_owner,
            "can_delete": is_global_admin or is_owner,
        },
        "points": [_serialize_restore_point(row) for row in rows],
    }


@router.post("/api/projects/{project_name}/restore-points", status_code=202, response_model=CreateRestorePointResponse)
async def create_project_restore_point(
    project_name: str,
    body: RestorePointCreate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)
    title = (body.title or "").strip() or dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    description = (body.description or "").strip() or None
    point_id = uuid.uuid4()

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admins podem criar pontos de restauração",
            )
            active = await _count_active_restore_points(conn, project_id)
            if active >= RESTORE_POINT_LIMIT:
                raise HTTPException(
                    409,
                    f"Limite de {RESTORE_POINT_LIMIT} pontos de restauração "
                    "atingido; exclua um ponto antes de criar outro.",
                )
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Criação de ponto de restauração enfileirada.",
                action="backup",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(point_id),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=2,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                INSERT INTO project_restore_points(
                    id, project_id, title, description, status, is_automatic,
                    job_id, created_by, project_ref_at_creation
                )
                VALUES($1, $2, $3, $4, 'creating', false, $5, $6, $7)
                """,
                point_id,
                project_id,
                title,
                description,
                uuid.UUID(job_id),
                auth_user["db_user_id"],
                project_name,
            )

    try:
        position = await _enqueue_project_action(
            project_name,
            job_id,
            lambda: _create_restore_point_background(
                job_id, project_name, auth_user["db_user_id"], point_id
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1 AND status = 'creating'
                """,
                point_id,
                "Nao foi possivel enfileirar a criacao do ponto.",
            )
        raise HTTPException(
            503, "Nao foi possivel enfileirar a criacao do ponto"
        ) from exc
    message = (
        "Criação do ponto de restauração enfileirada."
        if position == 0
        else f"Criação enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(
            pool,
            job_id,
            position,
            message,
            extra={"restore_point_id": str(point_id)},
        ),
    )


@router.post(
    "/api/projects/{project_name}/restore-points/{point_id}/restore",
    status_code=202,
    response_model=RestoreRestorePointResponse,
)
async def restore_project_restore_point(
    project_name: str,
    point_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_point = parse_uuid_value(point_id)
    if parsed_point is None:
        raise HTTPException(400, "Id do ponto de restauração inválido")
    auth_user = await resolve_authenticated_user(request, pool)
    safety_point_id = uuid.uuid4()

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_owner_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas o dono do projeto ou admin global pode restaurar o projeto",
            )
            point = await _fetch_restore_point_locked(conn, project_id, parsed_point)
            if point["status"] != "ready":
                raise HTTPException(
                    409,
                    f"Ponto de restauração em estado '{point['status']}'; "
                    "apenas pontos prontos podem ser restaurados.",
                )
            active = await _count_active_restore_points(conn, project_id)
            if active >= RESTORE_POINT_LIMIT:
                raise HTTPException(
                    409,
                    "A restauração cria um ponto automático de segurança e o "
                    f"limite de {RESTORE_POINT_LIMIT} pontos foi atingido; "
                    "exclua um ponto antes de restaurar.",
                )
            safety_title = f"Automático — antes de restaurar '{point['title']}'"[:80]
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Restauração enfileirada.",
                action="restore",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(parsed_point),
                    "safety_point_id": str(safety_point_id),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                INSERT INTO project_restore_points(
                    id, project_id, title, description, status, is_automatic,
                    job_id, created_by, project_ref_at_creation
                )
                VALUES($1, $2, $3, NULL, 'creating', true, $4, $5, $6)
                """,
                safety_point_id,
                project_id,
                safety_title,
                uuid.UUID(job_id),
                auth_user["db_user_id"],
                project_name,
            )
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = 'restoring', job_id = $2, error = NULL, updated_at = now()
                WHERE id = $1
                """,
                parsed_point,
                uuid.UUID(job_id),
            )

    try:
        position = await _enqueue_project_action(
            project_name,
            job_id,
            lambda: _restore_project_background(
                job_id,
                project_name,
                auth_user["db_user_id"],
                parsed_point,
                safety_point_id,
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE project_restore_points
                    SET status = 'failed', error = $2, updated_at = now()
                    WHERE id = $1 AND status = 'creating'
                    """,
                    safety_point_id,
                    "Nao foi possivel enfileirar a restauracao.",
                )
                await conn.execute(
                    """
                    UPDATE project_restore_points
                    SET status = 'ready', error = NULL, updated_at = now()
                    WHERE id = $1 AND status = 'restoring'
                    """,
                    parsed_point,
                )
        raise HTTPException(
            503, "Nao foi possivel enfileirar a restauracao"
        ) from exc
    message = (
        "Restauração enfileirada. O projeto ficará indisponível durante o processo."
        if position == 0
        else f"Restauração enfileirada. Existem {position} ações antes desta "
        f"na fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(
            pool,
            job_id,
            position,
            message,
            extra={
                "restore_point_id": str(parsed_point),
                "safety_point_id": str(safety_point_id),
            },
        ),
    )


@router.delete(
    "/api/projects/{project_name}/restore-points/{point_id}",
    status_code=202,
    response_model=DeleteRestorePointResponse,
)
async def delete_project_restore_point(
    project_name: str,
    point_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_point = parse_uuid_value(point_id)
    if parsed_point is None:
        raise HTTPException(400, "Id do ponto de restauração inválido")
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_owner_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas o dono do projeto ou admin global pode excluir pontos de restauração",
            )
            point = await _fetch_restore_point_locked(conn, project_id, parsed_point)
            if point["status"] not in ("ready", "failed"):
                raise HTTPException(
                    409,
                    f"Ponto de restauração em estado '{point['status']}'; "
                    "aguarde a operação atual terminar.",
                )
            previous_status = point["status"]
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Exclusão de ponto de restauração enfileirada.",
                action="delete_restore_point",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(parsed_point),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=1,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = 'deleting', job_id = $2, updated_at = now()
                WHERE id = $1
                """,
                parsed_point,
                uuid.UUID(job_id),
            )

    try:
        position = await _enqueue_project_action(
            project_name,
            job_id,
            lambda: _delete_restore_point_background(
                job_id, project_name, auth_user["db_user_id"], parsed_point
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = $2, updated_at = now()
                WHERE id = $1 AND status = 'deleting'
                """,
                parsed_point,
                previous_status,
            )
        raise HTTPException(
            503, "Nao foi possivel enfileirar a exclusao do ponto"
        ) from exc
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(
            pool,
            job_id,
            position,
            "Exclusão do ponto de restauração enfileirada.",
            extra={"restore_point_id": str(parsed_point)},
        ),
    )
