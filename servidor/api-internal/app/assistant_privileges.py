from __future__ import annotations

import hashlib
import hmac
import asyncio
from typing import Annotated, Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PrivilegeExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: UUID
    call_id: str = Field(min_length=1, max_length=200)
    approval_id: str = Field(min_length=1, max_length=200)
    sql_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool: Literal["manage_table_privileges"]


class PrivilegeChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["grant", "revoke"]
    tables: list[Annotated[str, Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$", max_length=63)]] = Field(min_length=1, max_length=20)
    role: Literal["anon", "authenticated"]
    privileges: list[Literal["SELECT", "INSERT", "UPDATE", "DELETE"]] = Field(min_length=1, max_length=4)
    label: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_targets(self):
        if len(set(self.tables)) != len(self.tables) or len(set(self.privileges)) != len(self.privileges):
            raise ValueError("Specify each table and privilege exactly once")
        return self


class PrivilegeChangeBody(PrivilegeChange):
    permission: Literal["full"]
    execution: PrivilegeExecution


def privilege_sql(change: PrivilegeChange) -> str:
    tables = ", ".join(f'public."{table}"' for table in change.tables)
    privileges = ", ".join(change.privileges)
    if change.operation == "grant":
        return f'GRANT {privileges} ON TABLE {tables} TO "{change.role}";'
    return f'REVOKE {privileges} ON TABLE {tables} FROM "{change.role}" RESTRICT;'


async def execute_privilege_change(connection, body: PrivilegeChangeBody):
    sql = privilege_sql(body)
    if not hmac.compare_digest(hashlib.sha256(sql.encode()).hexdigest(), body.execution.sql_hash):
        raise HTTPException(403, "Privilege change does not match its execution authority")
    async with asyncio.timeout(15), connection.transaction():
        await connection.execute("SET LOCAL search_path=pg_catalog; SET LOCAL statement_timeout='10s'; SET LOCAL lock_timeout='2s'")
        role = await connection.fetchrow("""
            SELECT rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication AS privileged
            FROM pg_roles WHERE rolname=$1
        """, body.role)
        if not role:
            raise HTTPException(503, "Application role is missing")
        if role["privileged"]:
            raise HTTPException(403, "Privilege changes require an unprivileged application role")
        relations = {}
        for table in sorted(body.tables):
            row = await connection.fetchrow("""
                SELECT c.oid, c.relkind::text AS kind, c.relowner=current_user::regrole AS owned,
                       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced,
                       EXISTS(SELECT 1 FROM pg_depend d WHERE d.objid=c.oid
                           AND d.classid='pg_class'::regclass AND d.deptype='e') AS extension
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relname=$1
            """, table)
            if not row:
                raise HTTPException(404, "Privilege changes require existing public tables")
            if row["kind"] != "r" or not row["owned"] or row["extension"]:
                raise HTTPException(403, "Privilege changes require tenant-owned ordinary public tables")
            await connection.execute(f'LOCK TABLE public."{table}" IN SHARE ROW EXCLUSIVE MODE')
            if await connection.fetchval("SELECT to_regclass($1)::oid", f'public."{table}"') != row["oid"]:
                raise HTTPException(403, "Table identity changed; review a new privilege operation")
            relations[table] = row
        status = await connection.execute(sql)
        effective = []
        for table in body.tables:
            privileges = dict(await connection.fetchrow("""
                SELECT has_schema_privilege($1,'public','USAGE') AS schema_usage,
                       has_table_privilege($1,$2::oid,'SELECT') AS select,
                       has_any_column_privilege($1,$2::oid,'SELECT') AS column_select,
                       has_table_privilege($1,$2::oid,'INSERT') AS insert,
                       has_any_column_privilege($1,$2::oid,'INSERT') AS column_insert,
                       has_table_privilege($1,$2::oid,'UPDATE') AS update,
                       has_any_column_privilege($1,$2::oid,'UPDATE') AS column_update,
                       has_table_privilege($1,$2::oid,'DELETE') AS delete,
                       c.relrowsecurity AS rls_enabled, c.relforcerowsecurity AS rls_forced
                FROM pg_class c WHERE c.oid=$2::oid
            """, body.role, relations[table]["oid"]))
            effective.append({"table": table, "rls_enabled": privileges.pop("rls_enabled"),
                              "rls_forced": privileges.pop("rls_forced"), "privileges": privileges})
        return {"status": status, "operation": body.operation, "role": body.role,
                "requested_privileges": body.privileges, "effective_privileges": effective}
