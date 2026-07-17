"""Rotas internas consumidas por Nginx, Studio e serviços do control plane."""

import hmac

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from app.control_plane_service import sync_user_record
from app.database import get_pool
from app.project_secret_service import decrypt_project_secret
from app.runtime_config import (
    ANALYTICS_INTERNAL_URL,
    LOGFLARE_PRIVATE_ACCESS_TOKEN,
    service_key_transport_fernet,
)
from app.schemas import UserSyncPayload
from app.validation import validate_project_id


router = APIRouter(tags=["internal"])


@router.api_route(
    "/api/internal/analytics/{analytics_path:path}",
    methods=["GET", "POST"],
)
async def proxy_global_analytics(
    analytics_path: str,
    request: Request,
):
    if not analytics_path.startswith("api/") or ".." in analytics_path:
        raise HTTPException(404, "Analytics path not allowed")

    provided_token = request.headers.get("x-api-key", "")
    authorization = request.headers.get("authorization", "")
    if not provided_token and authorization.lower().startswith("bearer "):
        provided_token = authorization[7:].strip()
    if not provided_token or not hmac.compare_digest(
        provided_token,
        LOGFLARE_PRIVATE_ACCESS_TOKEN,
    ):
        raise HTTPException(403, "Invalid Analytics token")

    upstream_headers = {"x-api-key": LOGFLARE_PRIVATE_ACCESS_TOKEN}
    content_type = request.headers.get("content-type")
    if content_type:
        upstream_headers["content-type"] = content_type

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0)
        ) as client:
            upstream = await client.request(
                request.method,
                f"{ANALYTICS_INTERNAL_URL}/{analytics_path}",
                params=list(request.query_params.multi_items()),
                headers=upstream_headers,
                content=await request.body(),
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
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")

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


@router.get("/api/projects/internal/enc-key/{ref}")
async def enc_key(
    ref: str,
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")

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
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")
    version = await pool.fetchval(
        "SELECT project_key_version FROM projects WHERE name = $1",
        ref,
    )
    if version is None:
        raise HTTPException(404, "Project not found")
    return {"project_key_version": version}
