from __future__ import annotations

import json
import os
import urllib.parse

import asyncpg
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.project_deletion import load_project_environment
from app.project_env_secrets import PROJECTS_ROOT
from app.validation import validate_project_id

router = APIRouter()

GOTRUE_INTERNAL_PORT = 9999
ALLOWED_GOTRUE_ROOTS = (
    "auth/v1/admin/",
    "auth/v1/invite",
    "auth/v1/recover",
    "auth/v1/magiclink",
    "auth/v1/otp",
)
STRIPPED_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "x-internal-version",
        "x-internal-service",
        "x-internal-timestamp",
        "x-internal-nonce",
        "x-internal-signature",
    }
)


def _reader_connection_params(
    project_ref: str,
) -> tuple[str, int, str, str, str]:
    meta_dsn = (os.getenv("META_ADMIN_DSN") or "").strip()
    reader_password = (os.getenv("PLATFORM_READER_DB_PASSWORD") or "").strip()
    if not meta_dsn or not reader_password or reader_password == "pass":
        raise HTTPException(
            503, "platform_reader indisponivel para leitura de usuarios"
        )
    parsed = urllib.parse.urlparse(meta_dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise HTTPException(503, "META_ADMIN_DSN invalido")
    return (
        parsed.hostname,
        parsed.port or 5432,
        f"_supabase_{project_ref}",
        "platform_reader",
        reader_password,
    )


@router.get("/api/projects/internal/auth-users/{project_name}")
async def list_project_auth_users(
    project_name: str,
    request: Request,
    page: int = 1,
    per_page: int = 50,
    pool=Depends(get_pool),
) -> Response:
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )

    page = max(1, page)
    per_page = min(max(1, per_page), 200)
    host, port, database, user, password = _reader_connection_params(project_name)
    try:
        reader_conn = await asyncpg.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            timeout=10,
        )
    except (OSError, asyncpg.PostgresError) as exc:
        print(f"[auth_users_list] {project_name}: {exc}")
        raise HTTPException(502, "Falha ao ler usuarios do projeto.") from exc

    try:
        total = await reader_conn.fetchval("SELECT count(*) FROM auth.users")
        rows = await reader_conn.fetch(
            """
            SELECT id, email, phone, email_confirmed_at, created_at,
                   last_sign_in_at, raw_user_meta_data, is_sso_user
            FROM auth.users
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            per_page,
            (page - 1) * per_page,
        )
    except asyncpg.PostgresError as exc:
        print(f"[auth_users_list] {project_name}: {exc}")
        raise HTTPException(502, "Falha ao ler usuarios do projeto.") from exc
    finally:
        await reader_conn.close()

    users = [
        {
            "id": str(row["id"]),
            "email": row["email"],
            "phone": row["phone"],
            "email_confirmed_at": row["email_confirmed_at"].isoformat()
            if row["email_confirmed_at"]
            else None,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "last_sign_in_at": row["last_sign_in_at"].isoformat()
            if row["last_sign_in_at"]
            else None,
            "raw_user_meta_data": row["raw_user_meta_data"],
            "is_sso_user": row["is_sso_user"],
        }
        for row in rows
    ]
    return Response(
        content=json.dumps({"users": users, "total": total or 0}),
        media_type="application/json",
    )


def _gotrue_internal_url(project_name: str, gotrue_path: str) -> str:
    return (
        f"http://supabase-auth-{project_name}:"
        f"{GOTRUE_INTERNAL_PORT}/{gotrue_path.lstrip('/')}"
    )


def _project_service_key(project_name: str) -> str:
    project_env = load_project_environment(PROJECTS_ROOT, project_name)
    return (project_env.get("SERVICE_ROLE_KEY_PROJETO") or "").strip()


@router.api_route(
    "/api/projects/internal/auth-admin/{project_name}/{gotrue_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def proxy_project_auth_admin(
    project_name: str,
    gotrue_path: str,
    request: Request,
) -> Response:
    project_name = validate_project_id(project_name)
    if not gotrue_path.startswith(ALLOWED_GOTRUE_ROOTS):
        raise HTTPException(400, "operacao auth-admin nao suportada")

    service_key = _project_service_key(project_name)
    if not service_key:
        raise HTTPException(409, "service key do projeto indisponivel")

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in STRIPPED_REQUEST_HEADERS
    }
    headers["Authorization"] = f"Bearer {service_key}"
    headers["apikey"] = service_key

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=5.0)
        ) as client:
            upstream = await client.request(
                request.method,
                _gotrue_internal_url(project_name, gotrue_path),
                params=list(request.query_params.multi_items()),
                headers=headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        print(f"[auth_admin_proxy] {project_name}: {exc}")
        raise HTTPException(
            502, "Falha ao acessar o GoTrue do projeto."
        ) from exc

    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type"),
    )
