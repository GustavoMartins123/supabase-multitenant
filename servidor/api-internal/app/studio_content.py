from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SqlContent(BaseModel):
    model_config = ConfigDict(extra="allow")
    sql: str = Field(strict=True, max_length=5_000_000)
    content_id: UUID
    schema_version: str = Field(strict=True, max_length=50)


class SnippetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    type: Literal["sql"]
    name: str = Field(strict=True, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=100_000)
    visibility: Literal["user"]
    folder_id: UUID | None = None
    favorite: bool = Field(default=False, strict=True)
    content: SqlContent
    project_id: int | str | None = None
    owner_id: int | str | None = None
    owner: dict | None = None
    updated_by: dict | None = None
    inserted_at: str | None = None
    updated_at: str | None = None
    status: str | None = None
    project_uuid: UUID | None = None
    owner_uuid: UUID | None = None

    @model_validator(mode="after")
    def same_identity(self):
        if self.content.content_id != self.id:
            raise ValueError("Snippet ID and content ID must match")
        return self


class FolderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(strict=True, min_length=1, max_length=500)
    parentId: None = None


class ContentQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["sql"] = "sql"
    visibility: Literal["user", "project"] = "user"
    name: str = Field(default="", max_length=500)
    favorite: bool | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    cursor: UUID | None = None
    sort_by: Literal["name", "inserted_at"] = "inserted_at"
    sort_order: Literal["asc", "desc"] = "desc"


def snippet_response(row, *, with_content=False):
    result = {
        "id": str(row["id"]), "type": "sql", "name": row["name"],
        "description": row["description"], "visibility": "user",
        "favorite": row["favorite"],
        "folder_id": str(row["folder_id"]) if row["folder_id"] else None,
        "project_id": 1, "owner_id": 1,
        "project_uuid": str(row["project_id"]), "owner_uuid": str(row["owner_id"]),
        "inserted_at": row["inserted_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
    if with_content:
        result["content"] = json.loads(row["content"]) if isinstance(row["content"], str) else row["content"]
    return result


def folder_response(row):
    return {"id": str(row["id"]), "name": row["name"], "parent_id": None,
            "project_id": 1, "owner_id": 1,
            "project_uuid": str(row["project_id"]), "owner_uuid": str(row["owner_id"])}


async def require_folder(conn, project_id, user_id, folder_id):
    row = await conn.fetchrow("""SELECT * FROM studio_sql_folders
        WHERE project_id=$1 AND owner_id=$2 AND id=$3 FOR KEY SHARE""", project_id, user_id, folder_id)
    if row is None:
        raise HTTPException(404, "Folder not found")
    return row


async def save_snippet(conn, project_id, user_id, body: SnippetBody):
    if body.folder_id:
        await require_folder(conn, project_id, user_id, body.folder_id)
    row = await conn.fetchrow("""
        INSERT INTO studio_sql_snippets(id,project_id,owner_id,folder_id,name,description,favorite,content)
        VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb)
        ON CONFLICT(id) DO UPDATE SET folder_id=excluded.folder_id,name=excluded.name,
            description=excluded.description,favorite=excluded.favorite,content=excluded.content,updated_at=now()
        WHERE studio_sql_snippets.project_id=excluded.project_id
            AND studio_sql_snippets.owner_id=excluded.owner_id
        RETURNING *
    """, body.id, project_id, user_id, body.folder_id, body.name, body.description or "",
        body.favorite, body.content.model_dump_json())
    if row is None:
        raise HTTPException(409, "Snippet ID is unavailable")
    return snippet_response(row, with_content=True)


async def get_snippet(conn, project_id, user_id, snippet_id):
    row = await conn.fetchrow("""SELECT * FROM studio_sql_snippets
        WHERE project_id=$1 AND owner_id=$2 AND id=$3""", project_id, user_id, snippet_id)
    if row is None:
        raise HTTPException(404, "Content not found.")
    return snippet_response(row, with_content=True)


async def list_snippets(conn, project_id, user_id, query: ContentQuery, *, folder_id=None):
    if query.visibility == "project":
        if query.cursor:
            raise HTTPException(400, "Invalid content cursor")
        return [], None
    values = [project_id, user_id]
    filters = ["project_id=$1", "owner_id=$2"]
    if folder_id is not None:
        values.append(folder_id)
        filters.append(f"folder_id=${len(values)}::uuid")
    if query.name:
        values.append(query.name.lower())
        filters.append(f"strpos(lower(name),${len(values)})>0")
    elif query.favorite is None and folder_id is None:
        values.append(folder_id)
        filters.append(f"folder_id IS NOT DISTINCT FROM ${len(values)}::uuid")
    if query.favorite is not None:
        values.append(query.favorite)
        filters.append(f"favorite=${len(values)}")
    column = "lower(name)" if query.sort_by == "name" else "inserted_at"
    direction = query.sort_order.upper()
    where = " AND ".join(filters)
    if query.cursor:
        cursor = await conn.fetchrow(f"SELECT id,{column} AS value FROM studio_sql_snippets WHERE {where} AND id=${len(values)+1}",
                                    *values, query.cursor)
        if cursor is None:
            raise HTTPException(400, "Invalid content cursor")
        values.extend([cursor["value"], cursor["id"]])
        comparison = ">" if query.sort_order == "asc" else "<"
        where += f" AND ({column},id){comparison}(${len(values)-1},${len(values)})"
    values.append(query.limit + 1)
    rows = await conn.fetch(f"""SELECT id,project_id,owner_id,folder_id,name,description,favorite,inserted_at,updated_at
        FROM studio_sql_snippets WHERE {where} ORDER BY {column} {direction},id {direction} LIMIT ${len(values)}""", *values)
    page = rows[:query.limit]
    return [snippet_response(row) for row in page], str(page[-1]["id"]) if len(rows) > query.limit else None


async def delete_content(conn, project_id, user_id, ids, *, folders=False):
    table = "studio_sql_folders" if folders else "studio_sql_snippets"
    rows = await conn.fetch(f"SELECT id FROM {table} WHERE project_id=$1 AND owner_id=$2 AND id=ANY($3::uuid[]) FOR UPDATE",
                            project_id, user_id, ids)
    if {row["id"] for row in rows} != set(ids):
        raise HTTPException(404, "Content not found.")
    await conn.execute(f"DELETE FROM {table} WHERE project_id=$1 AND owner_id=$2 AND id=ANY($3::uuid[])", project_id, user_id, ids)
    return [{"id": str(identity)} for identity in ids]
