"""Rotas internas consumidas por Nginx, Studio e serviços do control plane."""

import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.control_plane_service import sync_user_record
from app.database import get_pool
from app.dependencies import (
    ensure_project_member_access,
    get_project_role,
    resolve_authenticated_user,
)
from app.project_settings import get_project_file_size_limit
from app.project_secret_service import decrypt_project_secret
from app.runtime_config import (
    ANALYTICS_INTERNAL_URL,
    LOGFLARE_PRIVATE_ACCESS_TOKEN,
    service_key_transport_fernet,
)
from app.schemas import UserSyncPayload
from app.validation import validate_project_id


router = APIRouter(tags=["internal"])


def _require_studio_nginx(request: Request) -> None:
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")


def _analytics_allowed_methods(analytics_path: str) -> set[str] | None:
    safe_segment = r"[A-Za-z0-9_.-]{1,128}"
    if re.fullmatch(rf"api/endpoints/query/{safe_segment}", analytics_path):
        return {"GET"}
    if analytics_path == "api/backends":
        return {"GET", "POST"}
    if re.fullmatch(rf"api/backends/{safe_segment}", analytics_path):
        return {"GET", "PUT", "DELETE"}
    if analytics_path == "api/sources":
        return {"GET"}
    if analytics_path == "api/rules":
        return {"POST"}
    return None


@router.api_route(
    "/api/internal/analytics/{analytics_path:path}",
    methods=["GET", "POST", "PUT", "DELETE"],
)
async def proxy_global_analytics(
    analytics_path: str,
    request: Request,
):
    if getattr(request.state, "internal_service", None) != "studio-nginx":
        raise HTTPException(403, "Internal service access required")

    allowed_methods = _analytics_allowed_methods(analytics_path)
    if allowed_methods is None:
        raise HTTPException(404, "Analytics path not allowed")
    if request.method not in allowed_methods:
        raise HTTPException(405, "Analytics method not allowed")

    raw_query = request.scope.get("query_string", b"")
    if len(raw_query) > 16 * 1024:
        raise HTTPException(414, "Analytics query is too large")
    query_items = list(request.query_params.multi_items())
    if len(query_items) > 64:
        raise HTTPException(400, "Too many Analytics query parameters")

    raw_content_length = request.headers.get("content-length")
    if raw_content_length:
        try:
            content_length = int(raw_content_length)
        except ValueError as exc:
            raise HTTPException(400, "Invalid Content-Length") from exc
        if content_length < 0 or content_length > 256 * 1024:
            raise HTTPException(413, "Analytics request body is too large")

    body = await request.body()
    if len(body) > 256 * 1024:
        raise HTTPException(413, "Analytics request body is too large")

    if request.method in {"POST", "PUT"}:
        content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise HTTPException(415, "Analytics mutations require application/json")
    elif body:
        raise HTTPException(400, "Request body is not allowed for this Analytics method")

    upstream_headers = {
        "x-api-key": LOGFLARE_PRIVATE_ACCESS_TOKEN,
        "accept": "application/json",
    }
    if body:
        upstream_headers["content-type"] = "application/json"

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0)
        ) as client:
            upstream = await client.request(
                request.method,
                f"{ANALYTICS_INTERNAL_URL}/{analytics_path}",
                params=query_items,
                headers=upstream_headers,
                content=body,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Analytics service unavailable") from exc

    response_headers = {"Cache-Control": "no-store"}
    if upstream.headers.get("content-type"):
        response_headers["Content-Type"] = upstream.headers["content-type"]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )


@router.post("/api/projects/internal/users/sync")
async def sync_user_identity(
    body: UserSyncPayload,
    pool=Depends(get_pool),
):
    async with pool.acquire() as conn:
        async with conn.transaction():
            synced = await sync_user_record(
                conn,
                user_id=body.id,
                username=body.username,
                display_name=body.display_name,
                groups=body.groups,
                is_active=body.is_active,
                source=body.source,
            )
    return synced


@router.get("/api/projects/internal/content-identity/{project_name}")
async def get_content_project_identity(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Resolve o slug mutável para o UUID estável usado apenas por content."""
    project_name = validate_project_id(project_name)
    _require_studio_nginx(request)

    async with pool.acquire() as conn:
        project = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE name = $1",
            project_name,
        )
        if not project:
            raise HTTPException(404, "Project not found")

        history = await conn.fetch(
            """
            SELECT old_name, new_name
            FROM project_name_history
            WHERE project_id = $1
              AND status = 'succeeded'
            ORDER BY created_at ASC
            """,
            project["id"],
        )

    aliases: list[str] = []
    seen: set[str] = set()
    candidates = (
        [project["name"]]
        + [row["old_name"] for row in history]
        + [row["new_name"] for row in history]
    )
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            aliases.append(candidate)

    return JSONResponse(
        content={
            "project_id": str(project["id"]),
            "current_ref": project["name"],
            "aliases": aliases,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/projects/internal/studio-context/{ref}")
async def get_studio_project_context(
    ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Resolve and authorize the project carried by the Studio URL."""
    ref = validate_project_id(ref)
    _require_studio_nginx(request)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await conn.fetchrow(
                """
                SELECT id, tenant_uuid, name, display_name,
                       anon_key, project_key_version
                FROM projects
                WHERE name = $1
                """,
                ref,
            )
            if not project:
                raise HTTPException(404, "Project not found")

            await ensure_project_member_access(
                conn,
                project_id=project["id"],
                auth_user=auth_user,
            )
            role = await get_project_role(
                conn,
                project_id=project["id"],
                auth_user=auth_user,
            )
            if role is None and auth_user["is_global_admin"]:
                role = "admin"

            if not project["anon_key"]:
                raise HTTPException(409, "Project API key is not ready")
            anon_key = await decrypt_project_secret(
                conn,
                project_id=project["id"],
                column="anon_key",
                ciphertext=project["anon_key"],
            )

    return JSONResponse(
        content={
            "project_uuid": str(project["id"]),
            "tenant_uuid": (
                str(project["tenant_uuid"]) if project["tenant_uuid"] else None
            ),
            "ref": project["name"],
            "display_name": project["display_name"] or project["name"],
            "role": role,
            "anon_key": anon_key,
            "file_size_limit": int(get_project_file_size_limit(project["name"])),
            "project_key_version": project["project_key_version"],
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/projects/internal/enc-key/{ref}")
async def enc_key(
    ref: str,
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    _require_studio_nginx(request)

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, service_role, project_key_version
                FROM projects WHERE name=$1
                """,
                ref,
            )
            if not row or not row["service_role"]:
                raise HTTPException(status_code=404, detail="Project not found")
            service_key = await decrypt_project_secret(
                conn,
                project_id=row["id"],
                column="service_role",
                ciphertext=row["service_role"],
            )

    return {
        "enc_service_key": service_key_transport_fernet.encrypt(
            service_key.encode()
        ).decode(),
        "project_key_version": row["project_key_version"],
    }


@router.get("/api/projects/internal/key-version/{ref}")
async def project_key_version(
    ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    ref = validate_project_id(ref)
    _require_studio_nginx(request)
    version = await pool.fetchval(
        "SELECT project_key_version FROM projects WHERE name = $1",
        ref,
    )
    if version is None:
        raise HTTPException(404, "Project not found")
    return {"project_key_version": version}
