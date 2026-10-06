"""Authenticated administration of geographic and traffic policies."""

import uuid

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.access_policy import (
    CATALOG,
    AccessUsageResponse,
    CountryCatalog,
    PolicyResponse,
    PolicyUpdate,
    parse_policy,
)
from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    get_public_project_row,
    resolve_authenticated_user,
)
from app.runtime_config import NGINX_HMAC_SECRET, USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
from app.step_up_auth import consume_step_up_grant
from app.validation import validate_project_ref

router = APIRouter(prefix="/api/projects", tags=["access-policies"])
NO_STORE = {"Cache-Control": "no-store, max-age=0"}


@router.get("/countries", response_model=CountryCatalog)
async def countries(request: Request, pool=Depends(get_pool)):
    await resolve_authenticated_user(request, pool)
    return JSONResponse(CATALOG, headers=NO_STORE)


async def policy_request(project_ref, slot_id, request, pool, body=None, step_up=None):
    project_ref = validate_project_ref(project_ref)
    actor = await resolve_authenticated_user(request, pool)
    scope = "slot" if slot_id is not None else "project"
    table, column = (
        ("slot_access_policies", "slot_id")
        if slot_id is not None
        else ("project_access_policies", "project_id")
    )
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_public_project_row(conn, project_ref)
            await ensure_project_admin_access(conn, project_id=project["id"], auth_user=actor)
            kind = None
            if slot_id is not None:
                kind = await conn.fetchval(
                    "SELECT kind FROM project_api_key_slots WHERE id=$1 AND project_id=$2",
                    slot_id,
                    project["id"],
                )
                if kind is None:
                    raise HTTPException(404, "Consumer slot not found")
            scope_id = slot_id if slot_id is not None else project["id"]
            row = await conn.fetchrow(
                f"SELECT * FROM {table} WHERE {column}=$1 FOR UPDATE", scope_id
            )
            project_row = await conn.fetchrow(
                "SELECT policy FROM project_access_policies WHERE project_id=$1", project["id"]
            )
            if row is None or project_row is None:
                raise HTTPException(503, "Canonical access policy is unavailable")
            try:
                old = parse_policy(row["policy"], scope)
                parent = parse_policy(project_row["policy"], "project")
            except (ValueError, ValidationError):
                raise HTTPException(503, "Canonical access policy is invalid") from None
            if body is not None:
                try:
                    policy = body.policy.for_scope(scope)
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
                if body.revision != row["revision"]:
                    raise HTTPException(409, "Access policy changed; reload before saving")
                if scope == "project" or kind == "secret":
                    await consume_step_up_grant(
                        conn,
                        token=step_up,
                        secret=NGINX_HMAC_SECRET,
                        max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
                        auth_user=actor,
                        action="update_access_policy",
                        project_id=project["id"],
                        project_ref=project_ref,
                        resource_id=f"{scope_id}:{body.revision}",
                    )
                row = await conn.fetchrow(
                    f"UPDATE {table} SET policy=$2::jsonb, revision=revision+1, updated_by=$3, updated_at=now() WHERE {column}=$1 RETURNING *",
                    scope_id,
                    policy.model_dump_json(),
                    actor["db_user_id"],
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=actor["db_user_id"],
                    action="access_policy_updated",
                    target_type=table,
                    target_id=str(scope_id),
                    old_value=old.model_dump(),
                    new_value={"revision": row["revision"], "policy": policy.model_dump()},
                )
                if scope == "project":
                    parent = policy
            result = PolicyResponse(
                scope=scope,
                scope_id=str(scope_id),
                revision=row["revision"],
                policy=parse_policy(row["policy"], scope),
                project_policy=parent,
                updated_at=row["updated_at"].isoformat(),
            )
    return JSONResponse(result.model_dump(mode="json"), headers=NO_STORE)


@router.get("/{project_ref}/access-policy", response_model=PolicyResponse)
async def project_policy(
    project_ref: str, request: Request, pool: asyncpg.Pool = Depends(get_pool)
):
    return await policy_request(project_ref, None, request, pool)


@router.put("/{project_ref}/access-policy", response_model=PolicyResponse)
async def update_project_policy(
    project_ref: str,
    body: PolicyUpdate,
    request: Request,
    x_step_up_token: str | None = Header(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    return await policy_request(project_ref, None, request, pool, body, x_step_up_token)


@router.get("/{project_ref}/api-key-slots/{slot_id}/access-policy", response_model=PolicyResponse)
async def slot_policy(
    project_ref: str, slot_id: uuid.UUID, request: Request, pool: asyncpg.Pool = Depends(get_pool)
):
    return await policy_request(project_ref, slot_id, request, pool)


@router.put("/{project_ref}/api-key-slots/{slot_id}/access-policy", response_model=PolicyResponse)
async def update_slot_policy(
    project_ref: str,
    slot_id: uuid.UUID,
    body: PolicyUpdate,
    request: Request,
    x_step_up_token: str | None = Header(None),
    pool: asyncpg.Pool = Depends(get_pool),
):
    return await policy_request(project_ref, slot_id, request, pool, body, x_step_up_token)


@router.get("/{project_ref}/access-usage", response_model=AccessUsageResponse)
async def usage(project_ref: str, request: Request, pool: asyncpg.Pool = Depends(get_pool)):
    actor = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, validate_project_ref(project_ref))
        await ensure_project_admin_access(conn, project_id=project["id"], auth_user=actor)
        rows = await conn.fetch(
            "SELECT scope_id,scope_type,period,period_start,admitted,((period_start AT TIME ZONE 'UTC') + CASE WHEN period='day' THEN interval '1 day' ELSE interval '1 month' END) AT TIME ZONE 'UTC' AS period_end FROM access_quota_usage WHERE project_id=$1 AND period_start=date_trunc(period, now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' ORDER BY scope_type,scope_id,period",
            project["id"],
        )
    values = [dict(row) for row in rows]
    return JSONResponse(AccessUsageResponse(usage=values).model_dump(mode="json"), headers=NO_STORE)
