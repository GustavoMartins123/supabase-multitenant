import datetime as dt
import hmac
import re
import asyncpg
import httpx
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import audit_project_member_change, ensure_project_admin_access, ensure_project_member_access, get_project_role, get_project_row, require_synced_user_record, resolve_authenticated_user, upsert_project_member
from app.main import AI_TOOL_MAX_ROWS, AI_TOOL_TIMEOUT_MS, _extract_project_admin_apikey, get_project_conn
from app.project_backgrounds import _get_project_file_size_limit, _get_project_storage_limit_token
from app.meta_connections import get_project_meta_connection_string, get_project_reader_connection_string
from app.pg_meta_crypto import encrypt_postgres_meta_uri
from app.project_secret_service import decrypt_project_secret
from app.project_telemetry import TelemetryValidationError, fetch_project_user_telemetry, resolve_telemetry_period
from app.routers.lifecycle import get_project_status
from app.runtime_config import PG_META_CRYPTO_KEY, PG_META_INTERNAL_URL
from app.schemas import TransferBody
from app.validation import parse_uuid_value, validate_project_id

router = APIRouter(tags=["project-insights"])


@router.post("/api/admin/projects-info")
async def get_projects_for_user(
    body: Dict[str, str],
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

    uid = body.get("user_id")
    if not uid:
        raise HTTPException(400, "user_id é obrigatório")
    target_uuid = parse_uuid_value(uid)
    if target_uuid is None:
        raise HTTPException(400, "user_id inválido")

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT p.name, p.display_name
            FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = $1
              AND m.role = 'admin'
        """, target_uuid)

        projects = []
        for r in rows:
            project_status = await get_project_status(r["name"])
            projects.append({
                "name": r["name"],
                "display_name": r["display_name"],
                "status": project_status["status"],
                "running_containers": project_status["running"],
                "total_containers": project_status["total"],
                "file_size_limit": _get_project_file_size_limit(r["name"]),
                "storage_limit_token": _get_project_storage_limit_token(r["name"]),
            })

    return {"projects": projects}


@router.get("/api/admin/projects/{name}/all-users")
async def list_all_users_for_admin(
    name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Lista todos os usuários disponíveis para admins.
    Como a API não tem acesso ao cache, retorna uma estrutura
    que o Nginx pode completar ou usa proxy para Nginx.
    """
    name = validate_project_id(name)
    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "admin access required")

    async with pool.acquire() as conn:
        project = await conn.fetchrow(
            "SELECT id FROM projects WHERE name = $1",
            name,
        )
        if not project:
            raise HTTPException(404, "project not found")

        current_members = await conn.fetch(
            "SELECT user_id, role FROM project_members WHERE project_id=$1",
            project["id"],
        )

    return {
        "project_name": name,
        "project_id": project["id"],
        "current_members": [
            {
                "user_id": str(m["user_id"]),
                "role": m["role"],
                "status": "member"
            } for m in current_members
        ],
        "cache_users_needed": True,
        "nginx_route": f"/api/projects/{name}/all-users"
    }


@router.post("/api/projects/{project_name}/transfer", status_code=200)
async def transfer_project(
    project_name: str,
    body: TransferBody,
    request: Request,
    pool                   = Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    new_owner = body.new_owner_id.strip()
    if not new_owner:
        raise HTTPException(400, "new_owner_id é obrigatório")

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        if not auth_user["is_global_admin"]:
            raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

        async with conn.transaction():
            proj_row = await get_project_row(conn, project_name)
            new_owner_user = await require_synced_user_record(
                conn,
                identifier=new_owner,
                field_name="new_owner_id",
                missing_message="Novo proprietário ainda não foi sincronizado com o banco",
            )

            project_id = proj_row["id"]
            current_owner = proj_row["owner_id"]

            if current_owner == new_owner_user["id"]:
                return {"status": "noop", "detail": "Já é o proprietário"}

            await conn.execute(
                "UPDATE projects SET owner_id = $1 WHERE id = $2",
                new_owner_user["id"], project_id,
            )

            previous_target_role = await upsert_project_member(
                conn,
                project_id=project_id,
                user_id=new_owner_user["id"],
                role="admin",
            )
            await audit_project_member_change(
                conn,
                project_id=project_id,
                target_user_id=new_owner_user["id"],
                old_role=previous_target_role,
                new_role="admin",
                action="owner_transfer",
                actor_user_id=auth_user["db_user_id"],
            )

            await conn.execute(
                """
                UPDATE project_members
                SET role = 'member'
                WHERE project_id = $1
                  AND user_id = $2
                  AND role       = 'admin'
                """,
                project_id, current_owner,
            )
            if current_owner:
                await audit_project_member_change(
                    conn,
                    project_id=project_id,
                    target_user_id=current_owner,
                    old_role="admin",
                    new_role="member",
                    action="owner_transfer",
                    actor_user_id=auth_user["db_user_id"],
                )

    return {
        "project": project_name,
        "new_owner_id": str(new_owner_user["id"]),
        "status": "transferred"
    }


@router.get("/api/projects/{project_name}/telemetry/users")
async def get_project_user_telemetry(
    project_name: str,
    request: Request,
    response: Response,
    period: str = Query("24h"),
    start: dt.datetime | None = Query(None),
    end: dt.datetime | None = Query(None),
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    try:
        telemetry_period = resolve_telemetry_period(
            period,
            start=start,
            end=end,
        )
    except TelemetryValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        project_role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        is_owner = project_row["owner_id"] == auth_user["db_user_id"]
        if (
            project_role != "admin"
            and not is_owner
            and not auth_user["is_global_admin"]
        ):
            raise HTTPException(
                403,
                "Acesso negado: telemetria exige owner ou admin do projeto",
            )
        await audit_studio_action(
            conn,
            project_id=project_row["id"],
            actor_user_id=auth_user["db_user_id"],
            action="project_auth_telemetry_read",
            target_type="project_auth_telemetry",
            target_id=project_name,
            new_value={
                "period": telemetry_period.key,
                "start": telemetry_period.start.isoformat(),
                "end": telemetry_period.end.isoformat(),
            },
        )

    project_conn: asyncpg.Connection | None = None
    try:
        project_conn = await get_project_conn(project_name)
        result = await fetch_project_user_telemetry(
            project_conn,
            telemetry_period,
        )
    except asyncpg.InvalidCatalogNameError as exc:
        raise HTTPException(409, "Database do projeto nao esta disponivel") from exc
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
        raise HTTPException(
            409,
            "Schema Auth/GoTrue do projeto nao suporta esta telemetria",
        ) from exc
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            502,
            "Falha ao consultar a telemetria Auth/GoTrue do projeto",
        ) from exc
    finally:
        if project_conn is not None:
            await project_conn.close()

    response.headers["Cache-Control"] = "no-store"
    return {"project": project_name, **result}


@router.api_route(
    "/api/projects/{ref}/meta",
    methods=["GET"],
    operation_id="proxy_project_meta_get",
)
@router.api_route(
    "/api/projects/{ref}/meta",
    methods=["POST"],
    operation_id="proxy_project_meta_post",
)
@router.api_route(
    "/api/projects/{ref}/meta",
    methods=["PATCH"],
    operation_id="proxy_project_meta_patch",
)
@router.api_route(
    "/api/projects/{ref}/meta",
    methods=["DELETE"],
    operation_id="proxy_project_meta_delete",
)
@router.api_route(
    "/api/projects/{ref}/meta/{meta_path:path}",
    methods=["GET"],
    operation_id="proxy_project_meta_path_get",
)
@router.api_route(
    "/api/projects/{ref}/meta/{meta_path:path}",
    methods=["POST"],
    operation_id="proxy_project_meta_path_post",
)
@router.api_route(
    "/api/projects/{ref}/meta/{meta_path:path}",
    methods=["PATCH"],
    operation_id="proxy_project_meta_path_patch",
)
@router.api_route(
    "/api/projects/{ref}/meta/{meta_path:path}",
    methods=["DELETE"],
    operation_id="proxy_project_meta_path_delete",
)
async def proxy_project_meta(
    ref: str,
    request: Request,
    meta_path: str = "",
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, ref)
            await ensure_project_admin_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
                message="Apenas admins podem acessar roles e metadados do banco",
            )
            encrypted_service_role = await conn.fetchval(
                "SELECT service_role FROM projects WHERE id = $1",
                project_row["id"],
            )
            if not encrypted_service_role:
                raise HTTPException(409, "service_role administrativa não disponível")
            expected_apikey = await decrypt_project_secret(
                conn,
                project_id=project_row["id"],
                column="service_role",
                ciphertext=encrypted_service_role,
            )

    try:
        meta_key = (request.query_params.get("key") or "").strip().lower()
        if meta_key.startswith("users"):
            project_connection_string = get_project_reader_connection_string(ref)
        else:
            project_connection_string = get_project_meta_connection_string(ref)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    provided_apikey = _extract_project_admin_apikey(request)
    if not provided_apikey:
        raise HTTPException(status_code=401, detail="apikey administrativa ausente")
    if not hmac.compare_digest(provided_apikey, expected_apikey):
        raise HTTPException(status_code=403, detail="apikey administrativa inválida para o projeto")

    target_path = meta_path.lstrip("/")
    target_url = f"{PG_META_INTERNAL_URL}/{target_path}" if target_path else PG_META_INTERNAL_URL
    upstream_headers = {
        "x-connection-encrypted": encrypt_postgres_meta_uri(
            project_connection_string,
            PG_META_CRYPTO_KEY,
        )
    }

    content_type = request.headers.get("content-type")
    if content_type:
        upstream_headers["content-type"] = content_type

    x_pg_application_name = request.headers.get("x-pg-application-name")
    if x_pg_application_name:
        upstream_headers["x-pg-application-name"] = x_pg_application_name

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            upstream_response = await client.request(
                request.method,
                target_url,
                params=list(request.query_params.multi_items()),
                headers=upstream_headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        print(f"[postgres_meta_proxy] {ref}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Falha ao acessar postgres-meta global.",
        ) from exc

    response_headers: dict[str, str] = {}
    response_content_type = upstream_response.headers.get("content-type")
    if response_content_type:
        response_headers["content-type"] = response_content_type

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )


@router.get("/api/projects/{ref}/functions")
async def get_project_ai_functions(
    ref: str,
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, ref)
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    proj_conn = None
    try:
        proj_conn = await get_project_conn(ref)
        rows = await proj_conn.fetch("""
            SELECT
                p.proname AS name,
                pg_get_function_identity_arguments(p.oid) AS argument_types,
                pg_get_function_result(p.oid) AS return_type,
                obj_description(p.oid, 'pg_proc') AS comment
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
              AND p.proargmodes IS NULL
              AND obj_description(p.oid, 'pg_proc') ILIKE '%[AI]%'
            ORDER BY p.proname, p.oid
        """)
    except Exception as exc:
        raise HTTPException(503, "Cannot connect to project database") from exc
    finally:
        if proj_conn:
            await proj_conn.close()

    functions = []
    for r in rows:
        comment = r["comment"] or ""
        clean_desc = re.sub(r"\[AI\]", "", comment, flags=re.IGNORECASE).strip()
        functions.append({
            "name": r["name"],
            "argument_types": r["argument_types"] or "",
            "return_type": r["return_type"] or "void",
            "comment": clean_desc,
            "schema": "public",
        })
    return functions


@router.post("/api/projects/{ref}/execute-function")
async def execute_project_function(
    ref: str,
    body: Dict[str, Any],
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    
    function_name = body.get("function_name")
    arguments = body.get("arguments", {})
    
    if not function_name:
        raise HTTPException(400, "function_name is required")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', function_name):
        raise HTTPException(400, "Invalid function name")
    
    if not isinstance(arguments, dict):
        raise HTTPException(400, "arguments must be an object with named parameters")

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, ref)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
            message="Apenas admins podem executar AI tools",
        )
        project_id = project_row["id"]

    proj_conn = None
    try:
        proj_conn = await get_project_conn(ref)

        candidates = await proj_conn.fetch("""
            SELECT
                p.oid,
                p.proname AS name,
                p.proargnames AS argument_names,
                p.pronargs AS argument_count,
                p.pronargdefaults AS default_count
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
              AND p.proargmodes IS NULL
            AND p.proname = $1
              AND obj_description(p.oid, 'pg_proc') ILIKE '%[AI]%'
            ORDER BY p.oid
        """, function_name)

        if not candidates:
            raise HTTPException(404, f"Function '{function_name}' not found in public schema")
        if len(candidates) > 1:
            raise HTTPException(
                409,
                "AI tool com overload ambíguo; mantenha uma única assinatura por nome",
            )

        function = candidates[0]
        argument_count = int(function["argument_count"] or 0)
        default_count = int(function["default_count"] or 0)
        argument_names = list(function["argument_names"] or [])[:argument_count]
        if len(argument_names) != argument_count or any(
            not name or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name)
            for name in argument_names
        ):
            raise HTTPException(409, "AI tools exigem nomes em todos os argumentos")

        unknown_arguments = set(arguments) - set(argument_names)
        if unknown_arguments:
            raise HTTPException(
                400,
                f"Unexpected parameters: {', '.join(sorted(unknown_arguments))}",
            )
        required_count = argument_count - default_count
        missing = [name for name in argument_names[:required_count] if name not in arguments]
        if missing:
            raise HTTPException(400, f"Missing required parameter: {missing[0]}")

        values: list[Any] = []
        named_placeholders: list[str] = []
        for name in argument_names:
            if name not in arguments:
                continue
            values.append(arguments[name])
            named_placeholders.append(f'"{name}" => ${len(values)}')

        query = (
            f'SELECT public."{function_name}"('
            + ", ".join(named_placeholders)
            + f") AS result LIMIT {AI_TOOL_MAX_ROWS}"
        )
        async with proj_conn.transaction():
            await proj_conn.fetchval(
                "SELECT set_config('statement_timeout', $1, true)",
                str(AI_TOOL_TIMEOUT_MS),
            )
            rows = await proj_conn.fetch(query, *values)

        async with pool.acquire() as conn:
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_ai_tool_executed",
                target_type="database_function",
                target_id=f"public.{function_name}",
                new_value={
                    "argument_names": sorted(arguments.keys()),
                    "returned_rows": len(rows),
                    "row_limit": AI_TOOL_MAX_ROWS,
                },
            )

        return [dict(row) for row in rows]

    except HTTPException:
        raise
    except asyncpg.QueryCanceledError as exc:
        raise HTTPException(504, "AI tool execution timed out") from exc
    except Exception as exc:
        raise HTTPException(400, "Function execution failed") from exc
    finally:
        if proj_conn:
            await proj_conn.close()
