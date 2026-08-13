"""Admin API for independent project opaque-key consumer slots."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.control_plane_service import audit_studio_action
from app.database import get_pool
from app.dependencies import (
    ensure_project_admin_access,
    ensure_project_member_access,
    get_project_role,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import run_command as run_host_agent_command
from app.opaque_key_service import (
    DEFAULT_ROTATION_INTERVAL_DAYS,
    OpaqueKeyLifecycleError,
    OpaqueKeyRevealGone,
    abort_prepared_project_opaque_keys,
    activate_prepared_project_opaque_keys,
    activate_pending_key,
    cancel_pending_key,
    claim_key_reveal,
    confirm_pending_key_installation,
    create_slot_with_active_key,
    disable_slot,
    list_reveals,
    list_slots,
    prepare_project_opaque_key_migration,
    prepare_slot_rotation,
    rotate_slot_immediately,
    update_slot_policy,
    validate_prepared_project_opaque_keys,
)
from app.opaque_keys import ALLOWED_SERVICES, OpaqueKeyError
from app.project_env_secrets import read_project_secret_keys
from app.runtime_config import (
    NGINX_HMAC_SECRET,
    USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
)
from app.step_up_auth import consume_step_up_grant
from app.validation import validate_project_id


router = APIRouter(prefix="/api/projects", tags=["opaque-api-keys"])
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
    "X-Content-Type-Options": "nosniff",
}


class OpaqueKeyRequest(BaseModel):
    class Config:
        extra = "forbid"


def _raise_host_command_failure(
    command: asyncpg.Record, *, operation: str
) -> None:
    status = command["status"]
    error_code = command["error_code"]
    message = command["message"]
    if status not in {"failed", "cancelled"}:
        raise HTTPException(
            502,
            f"{operation}: invalid host-agent terminal status {status!r}",
        )
    if not isinstance(error_code, str) or not error_code.strip():
        raise HTTPException(
            502,
            f"{operation}: host-agent omitted error_code",
        )
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(
            502,
            f"{operation}: host-agent omitted message ({error_code})",
        )
    raise HTTPException(
        503,
        f"{operation} failed ({error_code}): {message}",
    )


@router.get("/{project_name}/opaque-api-keys/migration")
async def get_opaque_api_key_migration(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    _, project, can_manage = await _authorize_project_access(
        request, pool, project_name
    )
    async with pool.acquire() as conn:
        state = await conn.fetchrow(
            """
            SELECT opaque_keys_prepared_at, opaque_keys_activated_at,
                   opaque_gateway_cutover_started_at,
                   opaque_gateway_ready_at, api_keyset_version
            FROM projects WHERE id = $1
            """,
            project["id"],
        )
        pending = await conn.fetchval(
            """
            SELECT count(*)
            FROM project_api_keys k
            JOIN project_api_key_slots s ON s.id = k.slot_id
            WHERE s.project_id = $1
              AND k.status = 'pending'
              AND ($2::boolean OR s.kind = 'publishable')
            """,
            project["id"],
            can_manage,
        )
        confirmed = await conn.fetchval(
            """
            SELECT count(*)
            FROM project_api_keys k
            JOIN project_api_key_slots s ON s.id = k.slot_id
            WHERE s.project_id = $1
              AND k.status = 'pending'
              AND k.confirmed_at IS NOT NULL
              AND ($2::boolean OR s.kind = 'publishable')
            """,
            project["id"],
            can_manage,
        )
    if state["opaque_gateway_ready_at"] is not None:
        status = "active"
    elif (
        state["opaque_gateway_cutover_started_at"] is not None
        or state["opaque_keys_activated_at"] is not None
    ):
        status = "gateway_recovery_required"
    elif state["opaque_keys_prepared_at"] is not None:
        status = "prepared"
    else:
        status = "legacy"
    return {
        "project": project_name,
        "status": status,
        "prepared_at": (
            state["opaque_keys_prepared_at"].isoformat()
            if state["opaque_keys_prepared_at"]
            else None
        ),
        "activated_at": (
            state["opaque_keys_activated_at"].isoformat()
            if state["opaque_keys_activated_at"]
            else None
        ),
        "cutover_started_at": (
            state["opaque_gateway_cutover_started_at"].isoformat()
            if state["opaque_gateway_cutover_started_at"]
            else None
        ),
        "gateway_ready_at": (
            state["opaque_gateway_ready_at"].isoformat()
            if state["opaque_gateway_ready_at"]
            else None
        ),
        "pending_key_count": int(pending),
        "confirmed_pending_key_count": int(confirmed),
        "api_keyset_version": int(state["api_keyset_version"]),
    }


@router.delete("/{project_name}/opaque-api-keys/migration")
async def abort_opaque_api_key_migration(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(
        request, pool, project_name
    )
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during migration abort",
                )
                version = await abort_prepared_project_opaque_keys(
                    conn, project_id=project["id"]
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_migration_aborted",
                    target_type="project",
                    target_id=project_name,
                    new_value={"api_keyset_version": version},
                )
    except OpaqueKeyLifecycleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "project": project_name,
        "status": "legacy",
        "api_keyset_version": version,
    }


class CreateApiKeySlot(OpaqueKeyRequest):
    name: str = Field(min_length=3, max_length=40)
    kind: Literal["publishable", "secret"]
    allowed_services: list[str] = Field(
        default_factory=lambda: sorted(ALLOWED_SERVICES), min_length=1
    )
    automatic_rotation_enabled: bool | None = None
    rotation_interval_days: int | None = Field(
        default=DEFAULT_ROTATION_INTERVAL_DAYS, ge=1, le=3650
    )


class RotateApiKeySlot(OpaqueKeyRequest):
    activate_at: dt.datetime | None = None


class UpdateApiKeySlotPolicy(OpaqueKeyRequest):
    automatic_rotation_enabled: bool | None = None
    rotation_interval_days: int | None = Field(default=None, ge=1, le=3650)
    allowed_services: list[str] | None = None


class ConfirmApiKeyInstallation(OpaqueKeyRequest):
    key_id: uuid.UUID


async def _authorize_project_admin(
    request: Request,
    pool: asyncpg.Pool,
    project_name: str,
) -> tuple[dict, asyncpg.Record]:
    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message="Apenas admin do projeto pode gerenciar API keys",
        )
    return auth_user, project


async def _authorize_project_access(
    request: Request,
    pool: asyncpg.Pool,
    project_name: str,
) -> tuple[dict, asyncpg.Record, bool]:
    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project = await get_project_row(conn, project_name)
        await ensure_project_member_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message="Apenas membros do projeto podem consultar API keys",
        )
        role = await get_project_role(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
        )
    can_manage = auth_user["is_global_admin"] or role == "admin"
    return auth_user, project, can_manage


def _migration_lock_name(project_id: uuid.UUID) -> str:
    return f"opaque-api-key-migration:{project_id}"


@router.post(
    "/{project_name}/opaque-api-keys/migration/prepare",
    status_code=201,
)
async def prepare_opaque_api_key_migration(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Prepare rejected opaque keys without changing the running gateway."""

    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)
    conn = await pool.acquire()
    owns_lock = False
    project = None
    try:
        project = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message="Apenas admin do projeto pode preparar a migracao de API keys",
        )
        lock_name = _migration_lock_name(project["id"])
        owns_lock = await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
            lock_name,
        )
        if not owns_lock:
            raise HTTPException(409, "Opaque API key migration is already running")
        state = await conn.fetchrow(
            """
            SELECT opaque_keys_prepared_at, opaque_keys_activated_at
            FROM projects WHERE id = $1
            """,
            project["id"],
        )
        if state["opaque_keys_activated_at"] is not None:
            raise HTTPException(409, "Opaque API keys are already active")
        if state["opaque_keys_prepared_at"] is not None:
            raise HTTPException(409, "Opaque API key migration is already prepared")

        command = await run_host_agent_command(
            pool,
            command="ensure_opaque_gateway_token",
            project=project_name,
            project_uuid=project["id"],
            requested_by=auth_user["db_user_id"],
            args={},
        )
        if command["status"] != "done":
            _raise_host_command_failure(
                command,
                operation="Prepare project gateway token",
            )
        gateway_token = read_project_secret_keys(project_name)["gateway_token"]

        try:
            async with conn.transaction():
                current_project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=current_project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during migration",
                )
                publishable, secret = await prepare_project_opaque_key_migration(
                    conn,
                    project_id=current_project["id"],
                    created_by=auth_user["db_user_id"],
                    gateway_token=gateway_token,
                )
                reveal_deadline = await conn.fetchval(
                    """
                    SELECT min(r.expires_at)
                    FROM project_api_key_reveals r
                    WHERE r.key_id = ANY($1::uuid[])
                    """,
                    [publishable.key_id, secret.key_id],
                )
                await audit_studio_action(
                    conn,
                    project_id=current_project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_migration_prepared",
                    target_type="project",
                    target_id=project_name,
                    new_value={
                        "key_ids": [
                            str(publishable.key_id),
                            str(secret.key_id),
                        ],
                        "token_hints": [
                            publishable.token_hint,
                            secret.token_hint,
                        ],
                        "reveal_deadline": reveal_deadline.isoformat(),
                    },
                )
        except OpaqueKeyLifecycleError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {
            "project": project_name,
            "status": "prepared",
            "key_ids": [str(publishable.key_id), str(secret.key_id)],
            "reveal_deadline": reveal_deadline.isoformat(),
            "next": (
                "claim both keys, install them, and confirm both installations"
            ),
        }
    finally:
        try:
            if owns_lock and project is not None:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))",
                    _migration_lock_name(project["id"]),
                )
        finally:
            await pool.release(conn)


@router.post("/{project_name}/opaque-api-keys/migration/cutover")
async def cutover_opaque_api_key_migration(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    """Stop legacy ingress, activate confirmed keys, and start opaque-only."""

    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)
    conn = await pool.acquire()
    owns_lock = False
    project = None
    try:
        project = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project["id"],
            auth_user=auth_user,
            message="Apenas admin do projeto pode concluir a migracao de API keys",
        )
        lock_name = _migration_lock_name(project["id"])
        owns_lock = await conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtextextended($1, 0))",
            lock_name,
        )
        if not owns_lock:
            raise HTTPException(409, "Opaque API key migration is already running")
        state = await conn.fetchrow(
            """
            SELECT opaque_keys_prepared_at, opaque_keys_activated_at,
                   opaque_gateway_cutover_started_at,
                   opaque_gateway_ready_at, api_keyset_version
            FROM projects WHERE id = $1
            """,
            project["id"],
        )
        if state["opaque_keys_prepared_at"] is None:
            raise HTTPException(409, "Opaque API key migration is not prepared")
        if state["opaque_gateway_ready_at"] is not None:
            raise HTTPException(409, "Opaque API key migration is already complete")

        needs_activation = state["opaque_keys_activated_at"] is None
        try:
            async with conn.transaction():
                current_project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=current_project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during cutover",
                )
                if needs_activation:
                    await validate_prepared_project_opaque_keys(
                        conn, project_id=current_project["id"]
                    )
                cutover_state = await conn.execute(
                    """
                    UPDATE projects
                    SET opaque_gateway_cutover_started_at = COALESCE(
                        opaque_gateway_cutover_started_at, now()
                    )
                    WHERE id = $1
                      AND opaque_keys_prepared_at IS NOT NULL
                      AND opaque_gateway_ready_at IS NULL
                    """,
                    current_project["id"],
                )
                if cutover_state != "UPDATE 1":
                    raise OpaqueKeyLifecycleError(
                        "opaque gateway cutover state conflicted"
                    )
        except OpaqueKeyLifecycleError as exc:
            raise HTTPException(409, str(exc)) from exc

        staged = await run_host_agent_command(
            pool,
            command="stage_opaque_gateway",
            project=project_name,
            project_uuid=project["id"],
            requested_by=auth_user["db_user_id"],
            args={},
        )
        if staged["status"] != "done":
            _raise_host_command_failure(
                staged,
                operation="Stop and stage project gateway",
            )

        version = int(state["api_keyset_version"])
        if needs_activation:
            async with conn.transaction():
                current_project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=current_project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during cutover",
                )
                version = await activate_prepared_project_opaque_keys(
                    conn, project_id=current_project["id"]
                )
                await audit_studio_action(
                    conn,
                    project_id=current_project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_migration_activated",
                    target_type="project",
                    target_id=project_name,
                    new_value={"api_keyset_version": version},
                )

        started = await run_host_agent_command(
            pool,
            command="recreate_services",
            project=project_name,
            project_uuid=project["id"],
            requested_by=auth_user["db_user_id"],
            args={"services": ["nginx"]},
        )
        if started["status"] != "done":
            _raise_host_command_failure(
                started,
                operation=(
                    "Opaque keys were activated but the gateway remains stopped"
                ),
            )

        async with conn.transaction():
            result = await conn.execute(
                """
                UPDATE projects
                SET opaque_gateway_ready_at = now()
                WHERE id = $1
                  AND opaque_keys_activated_at IS NOT NULL
                  AND opaque_gateway_cutover_started_at IS NOT NULL
                  AND opaque_gateway_ready_at IS NULL
                """,
                project["id"],
            )
            if result != "UPDATE 1":
                raise RuntimeError("Opaque gateway readiness state conflicted")
            await audit_studio_action(
                conn,
                project_id=project["id"],
                actor_user_id=auth_user["db_user_id"],
                action="opaque_api_key_migration_completed",
                target_type="project",
                target_id=project_name,
                new_value={"api_keyset_version": version},
            )
        return {
            "project": project_name,
            "status": "active",
            "gateway_mode": "opaque-only",
            "api_keyset_version": version,
        }
    finally:
        try:
            if owns_lock and project is not None:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock(hashtextextended($1, 0))",
                    _migration_lock_name(project["id"]),
                )
        finally:
            await pool.release(conn)


def _issued_response(issued, keyset_version: int, *, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=NO_STORE_HEADERS,
        content={
            "slot_id": str(issued.slot_id),
            "key_id": str(issued.key_id),
            "api_key": issued.token,
            "token_hint": issued.token_hint,
            "kind": issued.kind,
            "status": issued.status,
            "activate_at": (
                issued.activate_at.isoformat() if issued.activate_at else None
            ),
            "expires_at": (
                issued.expires_at.isoformat() if issued.expires_at else None
            ),
            "api_keyset_version": keyset_version,
            "reveal_once": True,
        },
    )


@router.get("/{project_name}/api-key-slots")
async def get_api_key_slots(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    _, project, can_manage = await _authorize_project_access(
        request, pool, project_name
    )
    async with pool.acquire() as conn:
        slots = await list_slots(conn, project_id=project["id"])
        keyset_version = await conn.fetchval(
            "SELECT api_keyset_version FROM projects WHERE id = $1", project["id"]
        )
    visible_slots = (
        slots
        if can_manage
        else [slot for slot in slots if slot["kind"] == "publishable"]
    )
    return {
        "project": project_name,
        "api_keyset_version": int(keyset_version),
        "slots": visible_slots,
    }


@router.post("/{project_name}/api-key-slots", status_code=201)
async def create_api_key_slot(
    project_name: str,
    body: CreateApiKeySlot,
    request: Request,
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key creation",
                )
                if body.kind == "secret":
                    await consume_step_up_grant(
                        conn,
                        token=x_step_up_token,
                        secret=NGINX_HMAC_SECRET,
                        max_clock_skew_seconds=(
                            USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
                        ),
                        auth_user=auth_user,
                        action="create_secret_key",
                        project_id=project["id"],
                        project_ref=project_name,
                        resource_id=body.name,
                    )
                issued, version = await create_slot_with_active_key(
                    conn,
                    project_id=project["id"],
                    name=body.name,
                    kind=body.kind,
                    allowed_services=body.allowed_services,
                    created_by=auth_user["db_user_id"],
                    automatic_rotation_enabled=body.automatic_rotation_enabled,
                    rotation_interval_days=body.rotation_interval_days,
                )
                created_policy = await conn.fetchrow(
                    """
                    SELECT automatic_rotation_enabled,
                           rotation_interval_days,
                           allowed_services
                    FROM project_api_key_slots
                    WHERE id = $1
                    """,
                    issued.slot_id,
                )
                if created_policy is None:
                    raise OpaqueKeyLifecycleError(
                        "created API key slot policy is unavailable"
                    )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_slot_created",
                    target_type="project_api_key_slot",
                    target_id=str(issued.slot_id),
                    new_value={
                        "key_id": str(issued.key_id),
                        "kind": issued.kind,
                        "token_hint": issued.token_hint,
                        "automatic_rotation_enabled": created_policy[
                            "automatic_rotation_enabled"
                        ],
                        "rotation_interval_days": created_policy[
                            "rotation_interval_days"
                        ],
                        "allowed_services": list(
                            created_policy["allowed_services"]
                        ),
                        "api_keyset_version": version,
                    },
                )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(409, "API key slot name already exists") from exc
    except (OpaqueKeyError, OpaqueKeyLifecycleError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _issued_response(issued, version, status_code=201)


@router.post("/{project_name}/api-key-slots/{slot_id}/rotation")
async def rotate_api_key_slot(
    project_name: str,
    slot_id: uuid.UUID,
    body: RotateApiKeySlot,
    request: Request,
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key rotation",
                )
                slot_kind = await conn.fetchval(
                    """
                    SELECT kind
                    FROM project_api_key_slots
                    WHERE id = $1 AND project_id = $2
                    FOR UPDATE
                    """,
                    slot_id,
                    project["id"],
                )
                if slot_kind is None:
                    raise OpaqueKeyLifecycleError(
                        "active API key slot not found"
                    )
                if slot_kind == "secret":
                    await consume_step_up_grant(
                        conn,
                        token=x_step_up_token,
                        secret=NGINX_HMAC_SECRET,
                        max_clock_skew_seconds=(
                            USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
                        ),
                        auth_user=auth_user,
                        action="rotate_secret_key",
                        project_id=project["id"],
                        project_ref=project_name,
                        resource_id=str(slot_id),
                    )
                if body.activate_at is None:
                    issued, version = await rotate_slot_immediately(
                        conn, project_id=project["id"], slot_id=slot_id
                    )
                    action = "opaque_api_key_rotated"
                else:
                    issued, version = await prepare_slot_rotation(
                        conn,
                        project_id=project["id"],
                        slot_id=slot_id,
                        activate_at=body.activate_at,
                        retain_reveal=False,
                    )
                    action = "opaque_api_key_rotation_prepared"
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action=action,
                    target_type="project_api_key",
                    target_id=str(issued.key_id),
                    new_value={
                        "slot_id": str(slot_id),
                        "status": issued.status,
                        "token_hint": issued.token_hint,
                        "activate_at": (
                            issued.activate_at.isoformat()
                            if issued.activate_at
                            else None
                        ),
                        "api_keyset_version": version,
                    },
                )
    except (OpaqueKeyError, OpaqueKeyLifecycleError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return _issued_response(issued, version, status_code=200)


@router.patch("/{project_name}/api-key-slots/{slot_id}")
async def update_api_key_slot_policy(
    project_name: str,
    slot_id: uuid.UUID,
    body: UpdateApiKeySlotPolicy,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    changed_fields = body.model_fields_set
    rotation_interval_days_provided = (
        "rotation_interval_days" in changed_fields
    )
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key policy update",
                )
                version = await update_slot_policy(
                    conn,
                    project_id=project["id"],
                    slot_id=slot_id,
                    automatic_rotation_enabled=body.automatic_rotation_enabled,
                    rotation_interval_days=body.rotation_interval_days,
                    rotation_interval_days_provided=(
                        rotation_interval_days_provided
                    ),
                    allowed_services=body.allowed_services,
                )
                updated_policy = await conn.fetchrow(
                    """
                    SELECT automatic_rotation_enabled,
                           rotation_interval_days,
                           allowed_services
                    FROM project_api_key_slots
                    WHERE id = $1
                    """,
                    slot_id,
                )
                if updated_policy is None:
                    raise OpaqueKeyLifecycleError(
                        "updated API key slot policy is unavailable"
                    )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_slot_policy_updated",
                    target_type="project_api_key_slot",
                    target_id=str(slot_id),
                    new_value={
                        "automatic_rotation_enabled": updated_policy[
                            "automatic_rotation_enabled"
                        ],
                        "rotation_interval_days": updated_policy[
                            "rotation_interval_days"
                        ],
                        "allowed_services": list(
                            updated_policy["allowed_services"]
                        ),
                        "api_keyset_version": version,
                    },
                )
    except (OpaqueKeyError, OpaqueKeyLifecycleError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "slot_id": str(slot_id),
        "api_keyset_version": version,
        "updated": True,
    }


@router.post("/{project_name}/api-key-slots/{slot_id}/activation")
async def activate_api_key_slot(
    project_name: str,
    slot_id: uuid.UUID,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key activation",
                )
                key_id, version = await activate_pending_key(
                    conn, project_id=project["id"], slot_id=slot_id
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_activated",
                    target_type="project_api_key",
                    target_id=str(key_id),
                    new_value={
                        "slot_id": str(slot_id),
                        "api_keyset_version": version,
                    },
                )
    except OpaqueKeyLifecycleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "slot_id": str(slot_id),
        "key_id": str(key_id),
        "status": "active",
        "api_keyset_version": version,
    }


@router.post("/{project_name}/api-key-slots/{slot_id}/rotation-confirmation")
async def confirm_api_key_slot_installation(
    project_name: str,
    slot_id: uuid.UUID,
    body: ConfirmApiKeyInstallation,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key confirmation",
                )
                version = await confirm_pending_key_installation(
                    conn,
                    project_id=project["id"],
                    slot_id=slot_id,
                    key_id=body.key_id,
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_installation_confirmed",
                    target_type="project_api_key",
                    target_id=str(body.key_id),
                    new_value={
                        "slot_id": str(slot_id),
                        "api_keyset_version": version,
                    },
                )
    except OpaqueKeyLifecycleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "slot_id": str(slot_id),
        "key_id": str(body.key_id),
        "installation_confirmed": True,
        "api_keyset_version": version,
    }


@router.delete("/{project_name}/api-key-slots/{slot_id}/rotation")
async def cancel_api_key_slot_rotation(
    project_name: str,
    slot_id: uuid.UUID,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during rotation cancellation",
                )
                key_id, version = await cancel_pending_key(
                    conn,
                    project_id=project["id"],
                    slot_id=slot_id,
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_rotation_cancelled",
                    target_type="project_api_key",
                    target_id=str(key_id),
                    new_value={
                        "slot_id": str(slot_id),
                        "api_keyset_version": version,
                    },
                )
    except OpaqueKeyLifecycleError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {
        "slot_id": str(slot_id),
        "key_id": str(key_id),
        "status": "revoked",
        "api_keyset_version": version,
    }


@router.delete("/{project_name}/api-key-slots/{slot_id}")
async def revoke_api_key_slot(
    project_name: str,
    slot_id: uuid.UUID,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project = await _authorize_project_admin(request, pool, project_name)
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_admin_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project admin permission changed during API key revocation",
                )
                version = await disable_slot(
                    conn, project_id=project["id"], slot_id=slot_id
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_slot_revoked",
                    target_type="project_api_key_slot",
                    target_id=str(slot_id),
                    new_value={"api_keyset_version": version},
                )
    except OpaqueKeyLifecycleError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {
        "slot_id": str(slot_id),
        "status": "disabled",
        "api_keyset_version": version,
    }


@router.get("/{project_name}/api-key-reveals")
async def get_api_key_reveals(
    project_name: str,
    request: Request,
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    _, project, can_manage = await _authorize_project_access(
        request, pool, project_name
    )
    async with pool.acquire() as conn:
        reveals = await list_reveals(conn, project_id=project["id"])
    visible_reveals = (
        reveals
        if can_manage
        else [
            reveal
            for reveal in reveals
            if reveal["kind"] == "publishable"
        ]
    )
    return {"project": project_name, "reveals": visible_reveals}


@router.post("/{project_name}/api-key-reveals/{key_id}/claim")
async def claim_api_key(
    project_name: str,
    key_id: uuid.UUID,
    request: Request,
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    pool: asyncpg.Pool = Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user, project, _ = await _authorize_project_access(
        request, pool, project_name
    )
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                project = await get_project_row(conn, project_name)
                await ensure_project_member_access(
                    conn,
                    project_id=project["id"],
                    auth_user=auth_user,
                    message="Project membership changed during API key reveal",
                )
                key_kind = await conn.fetchval(
                    """
                    SELECT s.kind
                    FROM project_api_keys k
                    JOIN project_api_key_slots s ON s.id = k.slot_id
                    JOIN project_api_key_reveals r ON r.key_id = k.id
                    WHERE k.id = $1
                      AND s.project_id = $2
                      AND r.expires_at > now()
                    FOR UPDATE OF k, s, r
                    """,
                    key_id,
                    project["id"],
                )
                if key_kind is None:
                    raise OpaqueKeyRevealGone(
                        "API key reveal is expired, claimed, or absent"
                    )
                if key_kind == "secret":
                    await ensure_project_admin_access(
                        conn,
                        project_id=project["id"],
                        auth_user=auth_user,
                        message=(
                            "Apenas admin do projeto pode revelar secret keys"
                        ),
                    )
                    await consume_step_up_grant(
                        conn,
                        token=x_step_up_token,
                        secret=NGINX_HMAC_SECRET,
                        max_clock_skew_seconds=(
                            USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
                        ),
                        auth_user=auth_user,
                        action="reveal_secret_key",
                        project_id=project["id"],
                        project_ref=project_name,
                        resource_id=str(key_id),
                    )
                token = await claim_key_reveal(
                    conn, project_id=project["id"], key_id=key_id
                )
                await audit_studio_action(
                    conn,
                    project_id=project["id"],
                    actor_user_id=auth_user["db_user_id"],
                    action="opaque_api_key_reveal_claimed",
                    target_type="project_api_key",
                    target_id=str(key_id),
                )
    except OpaqueKeyRevealGone as exc:
        raise HTTPException(410, str(exc)) from exc
    return JSONResponse(
        headers=NO_STORE_HEADERS,
        content={
            "key_id": str(key_id),
            "api_key": token,
            "reveal_once": True,
        },
    )
