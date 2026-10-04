from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access, ensure_project_member_access,
    get_project_role, get_public_project_row, resolve_authenticated_user,
)
from app.meta_connections import get_project_assistant_reader_connection_string
from app.routers.project_insights import execute_project_function, get_project_ai_functions
from app.validation import validate_project_ref

router = APIRouter(tags=["assistant"])


class ReadRowsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$", max_length=63)
    limit: int = Field(ge=1, le=50, strict=True)


async def _context(ref: str, request: Request, pool, *, database: bool = False):
    ref = validate_project_ref(ref)
    if getattr(request.state, "internal_service", None) != "studio-nginx":
        raise HTTPException(403, "Assistant tools require the Studio gateway")
    user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, ref)
        if database:
            await ensure_project_admin_access(conn, project_id=project["id"], auth_user=user)
        else:
            await ensure_project_member_access(conn, project_id=project["id"], auth_user=user)
        role = await get_project_role(conn, project_id=project["id"], auth_user=user)
    if user["is_global_admin"]:
        role = "admin"
    return project, user, role


async def _connect(project):
    try:
        return await asyncpg.connect(
            get_project_assistant_reader_connection_string(project["name"], project["tenant_uuid"]),
            timeout=5, command_timeout=15,
        )
    except Exception as exc:
        raise HTTPException(503, "Assistant project database unavailable") from exc


async def _audit(pool, project, user, action, target, count):
    async with pool.acquire() as conn:
        await audit_studio_action(
            conn, project_id=project["id"], actor_user_id=user["db_user_id"], action=action,
            target_type="database_table", target_id=target,
            new_value={"returned_rows": count},
        )


@router.get("/api/projects/{ref}/assistant/context")
async def assistant_context(ref: str, request: Request, pool=Depends(get_pool)):
    project, user, role = await _context(ref, request, pool)
    return {"project_id": str(project["id"]), "user_id": str(user["db_user_id"]), "role": role}


@router.get("/api/projects/{ref}/assistant/schema")
async def assistant_schema(ref: str, request: Request, pool=Depends(get_pool)):
    project, user, _ = await _context(ref, request, pool, database=True)
    connection = await _connect(project)
    try:
        async with connection.transaction(readonly=True):
            await connection.execute("SET LOCAL statement_timeout = '10s'")
            rows = await connection.fetch("""
                SELECT c.relname AS table_name, a.attname AS column_name,
                       format_type(a.atttypid, a.atttypmod) AS data_type
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
                WHERE n.nspname='public' AND c.relkind='r'
                  AND a.attnum > 0 AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum LIMIT 1000
            """)
        await _audit(pool, project, user, "assistant_schema_read", "public", len(rows))
        return [dict(row) for row in rows]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Assistant schema query failed") from exc
    finally:
        await connection.close()


@router.post("/api/projects/{ref}/assistant/rows")
async def assistant_rows(ref: str, body: ReadRowsBody, request: Request, pool=Depends(get_pool)):
    project, user, _ = await _context(ref, request, pool, database=True)
    connection = await _connect(project)
    try:
        async with connection.transaction(readonly=True):
            await connection.execute("SET LOCAL statement_timeout = '10s'")
            ordinary = await connection.fetchval("""
                SELECT c.oid FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=$1 AND c.relkind='r'
            """, body.table)
            if not ordinary:
                raise HTTPException(404, "Assistant reads only ordinary public tables")
            rows = await connection.fetch(f'SELECT * FROM public."{body.table}" LIMIT $1', body.limit)
        await _audit(pool, project, user, "assistant_rows_read", f"public.{body.table}", len(rows))
        return [dict(row) for row in rows]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Assistant row query failed") from exc
    finally:
        await connection.close()


@router.get("/api/projects/{ref}/assistant/functions")
async def assistant_functions(ref: str, request: Request, pool=Depends(get_pool)):
    await _context(ref, request, pool, database=True)
    return await get_project_ai_functions(ref, request, pool)


@router.post("/api/projects/{ref}/assistant/execute")
async def assistant_execute(ref: str, body: dict, request: Request, pool=Depends(get_pool)):
    await _context(ref, request, pool, database=True)
    return await execute_project_function(ref, body, request, pool)
