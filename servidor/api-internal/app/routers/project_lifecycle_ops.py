from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import worker_alive as host_agent_alive
from app.jobs import (
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
)
from app.main import (
    _clear_project_pending_settings,
    _get_project_env_path,
    _get_project_file_size_limit,
    _get_project_storage_limit_token,
    _read_project_pending_settings,
    _recreate_project_services_background,
    _restart_project_containers_background,
    _serialize_queued_job,
    _start_project_containers_background,
    _stop_project_containers_background,
    _write_project_pending_settings,
    get_project_containers,
)
from app.project_settings import (
    _get_affected_services,
    _normalize_settings_updates,
    _read_env_whitelisted,
    _write_env_whitelisted,
    resolve_resource_limits,
    split_resource_directives,
)
from app.schemas import RecreateServices, UpdateSettings
from app.validation import validate_project_id

router = APIRouter(tags=["lifecycle-ops"])


@router.post("/api/projects/{project_name}/stop")
async def stop_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Parada enfileirada.",
        action="stop",
        payload={"project_name": project_name},
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _stop_project_containers_background(
            job_id,
            project_name,
            auth_user["db_user_id"],
        ),
    )
    message = (
        "Parada enfileirada."
        if position == 0
        else f"Parada enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )


@router.post("/api/projects/{project_name}/start", status_code=202)
async def start_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    """Inicia os containers do projeto. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Inicialização enfileirada.",
        action="start",
        payload={
            "project_name": project_name,
            "actor_user_id": str(auth_user["db_user_id"]),
        },
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _start_project_containers_background(
            job_id, project_name, auth_user["db_user_id"]
        ),
    )
    message = (
        "Inicialização enfileirada."
        if position == 0
        else f"Inicialização enfileirada. Existem {position} ações antes desta "
        f"na fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )


@router.post("/api/projects/{project_name}/restart", status_code=202)
async def restart_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    """Reinicia os containers do projeto. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Reinicialização enfileirada.",
        action="restart",
        payload={
            "project_name": project_name,
            "actor_user_id": str(auth_user["db_user_id"]),
        },
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _restart_project_containers_background(
            job_id, project_name, auth_user["db_user_id"]
        ),
    )
    message = (
        "Reinicialização enfileirada."
        if position == 0
        else f"Reinicialização enfileirada. Existem {position} ações antes "
        f"desta na fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )


@router.get("/api/projects/{project_name}/settings")
async def get_project_settings(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    env_path = _get_project_env_path(project_name)
    if not env_path.exists():
        raise HTTPException(404, f"Arquivo .env não encontrado para o projeto '{project_name}'")

    settings = _read_env_whitelisted(env_path)
    pending = _read_project_pending_settings(project_name)

    return {
        "settings": settings,
        "pending_affected_services": pending.get("affected_services", []),
        "storage_limit_token": pending.get("storage_limit_token"),
    }


@router.put("/api/projects/{project_name}/settings")
async def update_project_settings(
    project_name: str,
    body: UpdateSettings,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    updates = _normalize_settings_updates(body.settings)

    env_path = _get_project_env_path(project_name)
    if not env_path.exists():
        raise HTTPException(404, f"Arquivo .env não encontrado para o projeto '{project_name}'")

    had_profile_directive = "PROJECT_RESOURCE_PROFILE" in updates
    updates, resolved_limits = split_resource_directives(
        updates, current_env=_read_env_whitelisted(env_path)
    )
    if had_profile_directive:
        resolved_limits = {
            **resolve_resource_limits(updates["PROJECT_RESOURCE_PROFILE"]),
            **resolved_limits,
        }

    _write_env_whitelisted(env_path, {**updates, **resolved_limits})

    final_profile = (
        resolved_limits.get("PROJECT_RESOURCE_PROFILE")
        or project_row.get("resource_profile")
    )
    if final_profile and final_profile != project_row.get("resource_profile"):
        await pool.execute(
            "UPDATE projects SET resource_profile = $1 WHERE name = $2",
            final_profile,
            project_name,
        )

    affected = _get_affected_services(list(updates.keys()))
    if affected:
        _write_project_pending_settings(project_name, affected)
    else:
        _clear_project_pending_settings(project_name)

    return {
        "status": "updated",
        "updated_keys": list(updates.keys()),
        "affected_services": affected,
        "file_size_limit": _get_project_file_size_limit(project_name),
        "storage_limit_token": _get_project_storage_limit_token(project_name),
        "message": f"Configurações salvas. Serviços afetados: {', '.join(affected)}. Recrie-os para aplicar.",
    }


ALLOWED_RECREATE_SERVICES = {"auth", "rest", "storage", "nginx", "meta"}


@router.post("/api/projects/{project_name}/recreate-services")
async def recreate_project_services(
    project_name: str,
    body: RecreateServices,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Recreate specific services of a project using docker compose down + up.
    This is needed (instead of just restart) because env vars are read at
    container creation time, not on restart.
    """
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    invalid_services = set(body.services) - ALLOWED_RECREATE_SERVICES
    if invalid_services:
        raise HTTPException(400, f"Serviços inválidos: {', '.join(sorted(invalid_services))}")

    if not body.services:
        raise HTTPException(400, "Nenhum serviço especificado")
    if (
        "nginx" in body.services
        and project_row["opaque_gateway_ready_at"] is None
    ):
        raise HTTPException(
            409,
            "Use o cutover coordenado para materializar o gateway opaco",
        )

    services = body.services
    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Recriação enfileirada.",
        action="recreate_services",
        payload={"project_name": project_name, "services": services},
        total_steps=2,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _recreate_project_services_background(
            job_id,
            project_name,
            services,
        ),
    )
    message = (
        "Recriação enfileirada."
        if position == 0
        else f"Recriação enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )
