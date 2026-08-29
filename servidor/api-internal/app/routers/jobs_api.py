"""Rotas de historico, retry e status de jobs de projeto.

Extraidas de app.main para manter o modulo de ciclo de vida abaixo do limite de
tamanho verificado em tests/smoke. Os helpers de execucao (_build_recovery_runner,
_enqueue_project_action, _set_job_status) continuam em app.main: este modulo e
importado por app.asgi depois que app.main ja foi carregado, entao a importacao
nao e circular.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    resolve_authenticated_user,
)
from app.jobs import (
    create_retry_job,
    enqueue_project_action as _enqueue_project_action,
    serialize_job,
    set_job_status as _set_job_status,
)
from app.main import _build_recovery_runner
from app.validation import parse_uuid_value

router = APIRouter(tags=["jobs"])


@router.get("/api/jobs")
async def list_job_history(
    request: Request,
    project_uuid: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_pool),
):
    """Lista o historico duravel de jobs visivel para o usuario autenticado."""
    auth_user = await resolve_authenticated_user(request, pool)
    filters: list[str] = []
    values: list[Any] = []

    def add_filter(expression: str, value: Any) -> None:
        values.append(value)
        filters.append(expression.format(index=len(values)))

    if not auth_user["is_global_admin"]:
        add_filter(
            """
            (
                j.created_by = ${index}
                OR (
                    j.created_by IS NULL
                    AND EXISTS (
                        SELECT 1
                        FROM projects p
                        WHERE p.id = j.project_uuid
                          AND (
                              p.owner_id = ${index}
                              OR EXISTS (
                                  SELECT 1 FROM project_members pm
                                  WHERE pm.project_id = p.id
                                    AND pm.user_id = ${index}
                              )
                          )
                    )
                )
            )
            """,
            auth_user["db_user_id"],
        )
    if project_uuid is not None:
        add_filter("j.project_uuid = ${index}", project_uuid)
    if action:
        add_filter("j.action = ${index}", action.strip())
    if status:
        add_filter("j.status = ${index}", status.strip())

    where_sql = " WHERE " + " AND ".join(filters) if filters else ""
    values.extend((limit, offset))
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM jobs j
        {where_sql}
        ORDER BY j.created_at DESC, j.job_id DESC
        LIMIT ${len(values) - 1} OFFSET ${len(values)}
        """,
        *values,
    )
    return {
        "items": [serialize_job(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
    }


@router.post("/api/jobs/{job_id}/retry", status_code=202)
async def retry_project_job(
    job_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Cria uma nova tentativa apenas para acoes explicitamente idempotentes."""
    parsed_job_id = parse_uuid_value(job_id)
    if parsed_job_id is None:
        raise HTTPException(400, "job_id invalido")
    auth_user = await resolve_authenticated_user(request, pool)
    source = await pool.fetchrow("SELECT * FROM jobs WHERE job_id = $1", parsed_job_id)
    if source is None:
        raise HTTPException(404, "Job not found")
    if (
        source["created_by"] != auth_user["db_user_id"]
        and not auth_user["is_global_admin"]
    ):
        raise HTTPException(403, "Acesso negado a este job")

    # created_by e um direito historico: um retry reexecuta start/stop/restart/
    # recreate_services, que exigem admin do projeto nas rotas diretas. Revalida
    # o papel atual para que quem saiu do projeto perca o controle operacional.
    if source["project_uuid"] is None:
        if not auth_user["is_global_admin"]:
            raise HTTPException(403, "Acesso negado a este job")
    else:
        async with pool.acquire() as conn:
            await ensure_project_admin_access(
                conn,
                project_id=source["project_uuid"],
                auth_user=auth_user,
            )

    try:
        retry_row = await create_retry_job(
            pool, parsed_job_id, auth_user["db_user_id"]
        )
    except LookupError as exc:
        raise HTTPException(404, "Job not found") from exc
    except ValueError as exc:
        if str(exc) == "job_not_failed":
            raise HTTPException(409, "Somente jobs com falha podem ser reexecutados") from exc
        raise
    except PermissionError as exc:
        raise HTTPException(
            409,
            "Este job nao e idempotente e foi marcado como nao-reexecutavel",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(409, f"Ja existe um retry ativo: {exc}") from exc

    runner = await _build_recovery_runner(retry_row)
    if runner is None:
        await _set_job_status(
            str(retry_row["job_id"]),
            "failed",
            message="Nao foi possivel reconstruir o runner para o retry.",
            current_step="retry_dispatch_failed",
            error_code="retry_runner_unavailable",
        )
        raise HTTPException(409, "Runner indisponivel para retry")

    position = await _enqueue_project_action(
        retry_row["project"], str(retry_row["job_id"]), runner
    )
    result = serialize_job(retry_row)
    result["queue_position"] = position
    return result


@router.get("/api/projects/status/{job_id}")
async def project_status(
    job_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    parsed_job_id = parse_uuid_value(job_id)
    if parsed_job_id is None:
        raise HTTPException(400, "job_id inválido")
    auth_user = await resolve_authenticated_user(request, pool)
    row = await pool.fetchrow("SELECT * FROM jobs WHERE job_id=$1", parsed_job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    if not auth_user["is_global_admin"]:
        is_creator = row["created_by"] == auth_user["db_user_id"]
        if not is_creator and row["created_by"] is not None:
            raise HTTPException(403, "Acesso negado a este job")
        # Mesmo o criador do job precisa continuar no projeto: o vinculo atual
        # manda, nao o historico. project_uuid nulo so ocorre em jobs de create
        # anteriores a existencia do projeto, onde resta o criador.
        if row["project_uuid"] is not None:
            can_view = await pool.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM projects p
                    WHERE p.id = $1
                      AND (
                          p.owner_id = $2
                          OR EXISTS (
                              SELECT 1 FROM project_members pm
                              WHERE pm.project_id = p.id AND pm.user_id = $2
                          )
                      )
                )
                """,
                row["project_uuid"],
                auth_user["db_user_id"],
            )
            if not can_view:
                raise HTTPException(403, "Acesso negado a este job")
        elif not is_creator:
            raise HTTPException(403, "Acesso negado a este job")
    return serialize_job(row, include_output=True)
