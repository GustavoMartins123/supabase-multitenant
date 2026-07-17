"""Leitura de estado e logs do ciclo de vida dos projetos."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    get_project_role,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import (
    HostAgentOffline,
    command_result,
    fetch_project_containers,
    run_command as run_host_agent_command,
    worker_alive as host_agent_alive,
)
from app.validation import validate_project_id, validate_service_name


router = APIRouter(tags=["lifecycle"])


async def get_project_status(project_name: str) -> dict:
    pool = await get_pool()
    containers = await fetch_project_containers(pool, project_name)

    if not containers:
        if not await host_agent_alive(pool):
            # Sem host-agent nao ha snapshot confiavel de containers.
            return {
                "status": "unknown",
                "containers": [],
                "running": 0,
                "total": 0,
                "agent_offline": True,
            }
        return {"status": "not_found", "containers": [], "running": 0, "total": 0}

    container_info = []
    running_count = 0

    for container in containers:
        c_status = container.get("State", "unknown")
        if c_status == "running":
            running_count += 1

        container_info.append({
            "name": container.get("Names", ""),
            "status": c_status,
            "image": container.get("Image", "unknown"),
            "created": container.get("CreatedAt", ""),
            "ports": container.get("Ports", "")
        })

    total_containers = len(containers)
    if running_count == 0:
        overall_status = "stopped"
    elif running_count == total_containers:
        overall_status = "running"
    else:
        overall_status = "partial"

    return {
        "status": overall_status,
        "containers": container_info,
        "running": running_count,
        "total": total_containers
    }


@router.get("/api/projects/{project_name}/status")
async def get_project_docker_status(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
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
        project_role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )

    status_info = await get_project_status(project_name)
    if project_role != "admin" and not auth_user["is_global_admin"]:
        status_info.pop("containers", None)
    return status_info


MAX_LOG_LINES = 1000

@router.get("/api/projects/{project_name}/logs/{service}")
async def get_container_logs(
    project_name: str,
    service: str,
    request: Request,
    pool=Depends(get_pool),
    lines: int = Query(100, ge=1, le=MAX_LOG_LINES)
):
    project_name = validate_project_id(project_name)
    service = validate_service_name(service)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
            message="Apenas admins podem consultar logs do projeto",
        )
        project_id = project_row["id"]

    container_name = f"supabase-{service}-{project_name}"

    try:
        record = await run_host_agent_command(
            pool,
            command="container_logs",
            project=project_name,
            project_uuid=project_id,
            requested_by=auth_user["db_user_id"],
            args={"service": service, "lines": lines},
            poll_interval=0.3,
        )
        if record["status"] != "done":
            if record["error_code"] == "container_not_found":
                raise HTTPException(404, f"Container {container_name} not found")
            raise HTTPException(500, "Error getting container logs")

        result = command_result(record)

        async with pool.acquire() as conn:
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_logs_read",
                target_type="container_logs",
                target_id=container_name,
                new_value={"service": service, "lines": lines},
            )

        return {
            "container": result.get("container", container_name),
            "logs": result.get("logs", ""),
            "status": result.get("status", "unknown"),
        }

    except HTTPException:
        raise
    except HostAgentOffline as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        print(f"[project_logs] {project_name}/{service}: {exc}")
        raise HTTPException(500, "Error accessing container logs") from exc
