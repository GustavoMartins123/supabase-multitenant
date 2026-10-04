from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ConfigDict, Field

from app.assistant_sql import SqlPolicyError, default_has_side_effects, inspect_sql


class SqlApproval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: UUID
    call_id: str = Field(min_length=1, max_length=200)
    approval_id: str = Field(min_length=1, max_length=200)
    sql_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool: Literal["execute_sql", "execute_destructive_sql"]


class ExecuteSqlBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=20000)
    label: str = Field(min_length=1, max_length=100)
    permission: Literal["full"]
    approval: SqlApproval


async def execute_approved_sql(connection, body: ExecuteSqlBody):
    if not hmac.compare_digest(hashlib.sha256(body.sql.encode()).hexdigest(), body.approval.sql_hash):
        raise HTTPException(403, "SQL does not match its approval")
    try:
        plan = inspect_sql(body.sql)
    except SqlPolicyError as exc:
        raise HTTPException(400, str(exc)) from exc
    explicit_deletion = body.approval.tool == "execute_destructive_sql"
    if plan.destructive and not explicit_deletion:
        raise HTTPException(409, "Explicit destructive approval is required")
    async with connection.transaction():
        await connection.execute("SET LOCAL search_path = pg_catalog; SET LOCAL statement_timeout = '10s'; SET LOCAL lock_timeout = '2s'")
        indirect = False
        for table in plan.relations:
            relation = await connection.fetchrow("""
                SELECT c.oid, c.relkind::text AS relkind, c.relowner = current_user::regrole AS owned,
                       EXISTS(SELECT 1 FROM pg_depend d WHERE d.objid=c.oid
                              AND d.classid='pg_class'::regclass AND d.deptype='e') AS extension
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=$1
            """, table)
            if not relation:
                if table in plan.creates:
                    continue
                raise HTTPException(404, "SQL references an unavailable public table")
            if relation["relkind"] != "r" or not relation["owned"] or relation["extension"]:
                raise HTTPException(403, "SQL is limited to tenant-owned ordinary public tables")
            quoted = table.replace('"', '""')
            await connection.execute(f'LOCK TABLE public."{quoted}" IN SHARE ROW EXCLUSIVE MODE')
            locked_oid = await connection.fetchval("SELECT to_regclass($1)::oid", f'public."{quoted}"')
            if locked_oid != relation["oid"]:
                raise HTTPException(403, "Table identity changed; review a new SQL operation")
            if await connection.fetchval("""
                SELECT EXISTS(SELECT 1 FROM pg_attribute a JOIN pg_type t ON t.oid=a.atttypid
                    JOIN pg_namespace n ON n.oid=t.typnamespace
                    WHERE a.attrelid=$1 AND a.attnum>0 AND NOT a.attisdropped
                    AND (n.nspname <> 'pg_catalog' OR t.typtype NOT IN ('b','p')))
            """, relation["oid"]):
                raise HTTPException(403, "Tables with custom column types are not supported")
            side_effects = await connection.fetchval("""
                SELECT EXISTS(SELECT 1 FROM pg_trigger WHERE tgrelid=$1)
                    OR EXISTS(SELECT 1 FROM pg_rewrite WHERE ev_class=$1)
                    OR EXISTS(SELECT 1 FROM pg_attrdef a JOIN pg_depend d ON d.objid=a.oid
                        AND d.classid='pg_attrdef'::regclass AND d.refclassid='pg_proc'::regclass
                        JOIN pg_proc p ON p.oid=d.refobjid JOIN pg_namespace n ON n.oid=p.pronamespace
                        WHERE a.adrelid=$1 AND n.nspname <> 'pg_catalog')
            """, relation["oid"])
            indirect = indirect or bool(side_effects)
            if plan.writes:
                defaults = await connection.fetch("SELECT pg_get_expr(adbin, adrelid) AS expression FROM pg_attrdef WHERE adrelid=$1", relation["oid"])
                indirect = indirect or any(default_has_side_effects(row["expression"]) for row in defaults)
                checks = await connection.fetch("SELECT pg_get_expr(conbin, conrelid) AS expression FROM pg_constraint WHERE conrelid=$1 AND contype='c'", relation["oid"])
                indirect = indirect or any(default_has_side_effects(row["expression"]) for row in checks)
        if indirect and plan.writes and not explicit_deletion:
            raise HTTPException(409, "Table side effects require explicit destructive approval")
        prepared = await connection.prepare(body.sql)
        if prepared.get_attributes():
            cursor = await prepared.cursor()
            rows = [dict(row) for row in await cursor.fetch(51)]
            if len(rows) > 50:
                raise HTTPException(400, "SQL may return at most 50 rows; use LIMIT or omit RETURNING")
        else:
            await prepared.fetch()
            rows = []
        result = jsonable_encoder({"result": rows, "status": prepared.get_statusmsg()},
                                 custom_encoder={bytes: lambda value: base64.b64encode(value).decode()})
        if len(json.dumps(result).encode()) > 500_000:
            raise HTTPException(400, "SQL result exceeds the assistant response limit")
    return plan, result


