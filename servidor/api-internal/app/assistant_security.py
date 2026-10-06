from __future__ import annotations

import json
import asyncio
from typing import Annotated

from fastapi import HTTPException
from pglast import parse_sql
from pydantic import BaseModel, ConfigDict, Field

from app.assistant_sql import _normalize


class SecurityBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tables: list[Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$", max_length=63)]] = Field(min_length=1, max_length=20)


AUTH_IDENTITY_SQL = {
    "uid": """select coalesce(nullif(current_setting('request.jwt.claim.sub', true), ''),
        (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub'))::uuid""",
    "jwt": """select coalesce(nullif(current_setting('request.jwt.claim', true), ''),
        nullif(current_setting('request.jwt.claims', true), ''))::jsonb""",
}


def _canonical_tree(value):
    if isinstance(value, dict):
        return {key: _canonical_tree(child) for key, child in value.items() if key != "location"}
    if isinstance(value, list):
        return [_canonical_tree(child) for child in value]
    return value


def identity_body_is_safe(name: str, source: str) -> bool:
    try:
        statements = parse_sql(source)
        if len(statements) != 1:
            return False
        actual = _canonical_tree(_normalize(statements[0].stmt()))
        expected = _canonical_tree(_normalize(parse_sql(AUTH_IDENTITY_SQL[name])[0].stmt()))
        return actual == expected
    except Exception:
        return False


async def verify_identity_functions(connection, names):
    for name in names:
        row = await connection.fetchrow("""
            SELECT p.prosrc, p.prosecdef, p.provolatile::text, l.lanname, p.proconfig,
                   p.prorettype = CASE WHEN $1='uid' THEN 'uuid'::regtype ELSE 'jsonb'::regtype END AS valid_type
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            JOIN pg_language l ON l.oid=p.prolang
            WHERE n.nspname='auth' AND p.proname=$1 AND p.pronargs=0 AND p.prokind='f'
        """, name)
        if not row or row["prosecdef"] or row["provolatile"] != "s" or row["lanname"] != "sql" or not row["valid_type"]:
            raise HTTPException(403, "Policy identity function does not match the supported read-only implementation")
        if row["proconfig"] or not identity_body_is_safe(name, row["prosrc"]):
            raise HTTPException(403, "Policy identity function body cannot be safely validated")


async def inspect_table_security(connection, tables):
    result = []
    async with asyncio.timeout(15), connection.transaction(readonly=True, isolation="repeatable_read"):
        await connection.execute("SET LOCAL statement_timeout='10s'; SET LOCAL search_path=pg_catalog")
        for table in tables:
            row = await connection.fetchrow("""
                SELECT c.oid, c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=$1 AND c.relkind='r'
            """, table)
            if not row:
                raise HTTPException(404, "Security inspection requires an existing ordinary public table")
            policies = await connection.fetch("""
                SELECT policyname AS name, permissive, roles, cmd AS command,
                       qual AS using_expression, with_check AS check_expression
                FROM pg_policies WHERE schemaname='public' AND tablename=$1 ORDER BY policyname LIMIT 101
            """, table)
            privileges = {}
            for role in ("anon", "authenticated"):
                if not await connection.fetchval("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=$1)", role):
                    raise HTTPException(503, "Application role is missing; security inspection is unavailable")
                privileges[role] = dict(await connection.fetchrow("""
                    SELECT has_schema_privilege($1,'public','USAGE') AS schema_usage,
                           has_table_privilege($1,$2::oid,'SELECT') AS select,
                           has_any_column_privilege($1,$2::oid,'SELECT') AS column_select,
                           has_table_privilege($1,$2::oid,'INSERT') AS insert,
                           has_any_column_privilege($1,$2::oid,'INSERT') AS column_insert,
                           has_table_privilege($1,$2::oid,'UPDATE') AS update,
                           has_any_column_privilege($1,$2::oid,'UPDATE') AS column_update,
                           has_table_privilege($1,$2::oid,'DELETE') AS delete,
                           has_table_privilege($1,$2::oid,'TRUNCATE') AS truncate,
                           (r.rolbypassrls OR r.rolsuper) AS bypass_rls,
                           EXISTS(SELECT 1 FROM pg_class c WHERE c.oid=$2::oid AND c.relowner=r.oid) AS owns_table
                    FROM pg_roles r WHERE r.rolname=$1
                """, role, row["oid"]))
            if len(policies) > 100:
                raise HTTPException(400, "Security inspection policy limit exceeded")
            result.append({"table": table, "rls_enabled": row["rls_enabled"], "rls_forced": row["rls_forced"],
                           "policies": [dict(policy) for policy in policies], "effective_privileges": privileges})
        if len(json.dumps(result).encode()) > 500_000:
            raise HTTPException(400, "Security inspection response limit exceeded")
    return result
