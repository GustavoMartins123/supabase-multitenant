from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError

from app.database import get_pool
from app.dependencies import ensure_project_member_access, get_public_project_row, resolve_authenticated_user
from app.studio_content import (
    ContentQuery, FolderBody, SnippetBody, delete_content, folder_response,
    get_snippet, list_snippets, require_folder, save_snippet,
)
from app.validation import validate_project_ref

router = APIRouter(prefix="/api/projects/{ref}/content", tags=["studio-content"])


@asynccontextmanager
async def content_context(ref, request, response, pool):
    ref = validate_project_ref(ref)
    if getattr(request.state, "internal_service", None) != "studio-nginx":
        raise HTTPException(403, "Studio content requires the authenticated gateway")
    user = await resolve_authenticated_user(request, pool)
    response.headers["Cache-Control"] = "no-store"
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_public_project_row(conn, ref)
            await ensure_project_member_access(conn, project_id=project["id"], auth_user=user)
            yield conn, project["id"], user["db_user_id"]


def content_query(request):
    if len(request.query_params.multi_items()) != len(request.query_params):
        raise HTTPException(400, "Repeated content query parameters")
    try:
        return ContentQuery.model_validate(dict(request.query_params))
    except ValidationError as exc:
        raise HTTPException(400, "Invalid content query") from exc


def content_ids(request):
    if set(request.query_params) != {"ids"} or len(request.query_params.multi_items()) != 1:
        raise HTTPException(400, "Content IDs are required")
    try:
        ids = [UUID(value) for value in request.query_params["ids"].split(",")]
    except ValueError as exc:
        raise HTTPException(400, "Invalid content IDs") from exc
    if not ids or len(ids) > 1000 or len(ids) != len(set(ids)):
        raise HTTPException(400, "Invalid content IDs")
    return ids


@router.get("")
async def content_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    query = content_query(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        contents, cursor = await list_snippets(conn, project_id, user_id, query)
    return {"data": contents, "cursor": cursor}


@router.put("")
async def content_save(ref: str, body: SnippetBody, request: Request, response: Response, pool=Depends(get_pool)):
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        return await save_snippet(conn, project_id, user_id, body)


@router.delete("")
async def content_delete(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    ids = content_ids(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        return await delete_content(conn, project_id, user_id, ids)


@router.get("/item/{id}")
async def content_item(ref: str, id: UUID, request: Request, response: Response, pool=Depends(get_pool)):
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        return await get_snippet(conn, project_id, user_id, id)


@router.get("/count")
async def content_count(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    query = content_query(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        row = await conn.fetchrow("""SELECT count(*) AS private,count(*) FILTER(WHERE favorite) AS favorites
            FROM studio_sql_snippets WHERE project_id=$1 AND owner_id=$2 AND strpos(lower(name),lower($3))>0""",
            project_id, user_id, query.name)
    return {"count": row["private"]} if query.name else {"shared": 0, **dict(row)}


@router.get("/folders")
async def folders_list(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    query = content_query(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        folders = await conn.fetch("SELECT * FROM studio_sql_folders WHERE project_id=$1 AND owner_id=$2 ORDER BY lower(name),id",
                                   project_id, user_id)
        contents, cursor = await list_snippets(conn, project_id, user_id, query)
    return {"data": {"folders": [folder_response(row) for row in folders], "contents": contents}, "cursor": cursor}


@router.post("/folders", status_code=201)
async def folder_create(ref: str, body: FolderBody, request: Request, response: Response, pool=Depends(get_pool)):
    try:
        async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
            row = await conn.fetchrow("INSERT INTO studio_sql_folders(id,project_id,owner_id,name) VALUES($1,$2,$3,$4) RETURNING *",
                                      uuid4(), project_id, user_id, body.name)
        return folder_response(row)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "Folder name already exists") from exc


@router.delete("/folders")
async def folders_delete(ref: str, request: Request, response: Response, pool=Depends(get_pool)):
    ids = content_ids(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        await delete_content(conn, project_id, user_id, ids, folders=True)
    return {}


@router.get("/folders/{id}")
async def folder_item(ref: str, id: UUID, request: Request, response: Response, pool=Depends(get_pool)):
    query = content_query(request)
    async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
        await require_folder(conn, project_id, user_id, id)
        contents, cursor = await list_snippets(conn, project_id, user_id, query, folder_id=id)
    return {"data": {"folders": [], "contents": contents}, "cursor": cursor}


@router.patch("/folders/{id}")
async def folder_update(ref: str, id: UUID, body: FolderBody, request: Request, response: Response, pool=Depends(get_pool)):
    try:
        async with content_context(ref, request, response, pool) as (conn, project_id, user_id):
            await require_folder(conn, project_id, user_id, id)
            row = await conn.fetchrow("UPDATE studio_sql_folders SET name=$4 WHERE project_id=$1 AND owner_id=$2 AND id=$3 RETURNING *",
                                      project_id, user_id, id, body.name)
        return folder_response(row)
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "Folder name already exists") from exc
