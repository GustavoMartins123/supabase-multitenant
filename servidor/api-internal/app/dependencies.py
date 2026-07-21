"""Dependências compartilhadas de autenticação e autorização."""

from __future__ import annotations

import re
import uuid
from typing import Any

import asyncpg
from fastapi import HTTPException, Request

from app.runtime_config import NGINX_HMAC_SECRET, USER_TOKEN_MAX_CLOCK_SKEW_SECONDS
from app.security_tokens import (
    resolve_user_claims_from_hmac_token as resolve_signed_user_claims,
    resolve_user_id_from_hmac_token as resolve_signed_user_id,
)
from app.validation import normalize_groups, parse_uuid_value


def resolve_user_id_from_hmac_token(request: Request) -> uuid.UUID:
    return resolve_signed_user_id(
        request,
        secret=NGINX_HMAC_SECRET,
        max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    )


def resolve_user_claims_from_hmac_token(
    request: Request,
) -> tuple[uuid.UUID, dict[str, Any]]:
    return resolve_signed_user_claims(
        request,
        secret=NGINX_HMAC_SECRET,
        max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    )


async def resolve_authenticated_user(
    request: Request,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    signed_user_id, token_claims = resolve_user_claims_from_hmac_token(request)
    login_session = str(token_claims.get("login_session") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", login_session):
        login_session = ""

    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            """
            SELECT
                u.id,
                u.authelia_username,
                u.display_name,
                u.is_active,
                COALESCE(
                    array_agg(ug.group_name) FILTER (WHERE ug.group_name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS groups
            FROM users u
            LEFT JOIN user_groups ug ON ug.user_id = u.id
            WHERE u.id = $1
            GROUP BY u.id
            """,
            signed_user_id,
        )

        if user_row:
            if login_session:
                await conn.execute(
                    """
                    UPDATE users
                    SET last_login_at = now(),
                        last_login_session_hash = $2,
                        updated_at = now()
                    WHERE id = $1
                      AND last_login_session_hash IS DISTINCT FROM $2
                    """,
                    user_row["id"],
                    login_session,
                )
            await conn.execute(
                """
                UPDATE users
                SET last_seen_at = now(), updated_at = now()
                WHERE id = $1
                  AND (
                      last_seen_at IS NULL
                      OR last_seen_at < now() - interval '5 minutes'
                  )
                """,
                user_row["id"],
            )

    if not user_row:
        raise HTTPException(403, "Usuário não sincronizado com o banco")
    if not user_row["is_active"]:
        raise HTTPException(403, "Usuário desativado")

    groups = normalize_groups(user_row["groups"])
    return {
        "db_user_id": user_row["id"],
        "username": user_row["authelia_username"],
        "display_name": user_row["display_name"],
        "groups": groups,
        "is_global_admin": "admin" in groups,
    }


async def get_user_record_by_identifier(
    conn: asyncpg.Connection,
    *,
    identifier: str,
    field_name: str = "user_id",
) -> asyncpg.Record | None:
    raw_identifier = (identifier or "").strip()
    maybe_uuid = parse_uuid_value(raw_identifier)

    if maybe_uuid is None:
        raise HTTPException(400, f"{field_name} inválido")

    return await conn.fetchrow(
        """
        SELECT id, authelia_username, display_name, is_active
        FROM users
        WHERE id = $1
        """,
        maybe_uuid,
    )


async def require_synced_user_record(
    conn: asyncpg.Connection,
    *,
    identifier: str,
    field_name: str = "user_id",
    missing_message: str = "Usuário alvo ainda não foi sincronizado com o banco",
    allow_inactive: bool = False,
) -> asyncpg.Record:
    row = await get_user_record_by_identifier(conn, identifier=identifier, field_name=field_name)
    if not row:
        raise HTTPException(409, missing_message)
    if not allow_inactive and not row["is_active"]:
        raise HTTPException(409, "Usuário alvo está desativado")
    return row


async def get_project_row(conn: asyncpg.Connection, project_name: str) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT id, tenant_uuid, name, display_name, owner_id
        FROM projects WHERE name = $1
        """,
        project_name,
    )
    if not row:
        raise HTTPException(404, "Project not found")
    return row


async def get_project_role(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    auth_user: dict[str, Any],
) -> str | None:
    return await conn.fetchval(
        """
        SELECT role
        FROM project_members
        WHERE project_id = $1
          AND user_id = $2
        LIMIT 1
        """,
        project_id,
        auth_user["db_user_id"],
    )


async def get_project_member_row(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    user_id: uuid.UUID | None,
) -> asyncpg.Record | None:
    if user_id is None:
        return None

    return await conn.fetchrow(
        """
        SELECT user_id, role
        FROM project_members
        WHERE project_id = $1
          AND user_id = $2
        LIMIT 1
        """,
        project_id,
        user_id,
    )


async def upsert_project_member(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    user_id: uuid.UUID,
    role: str,
) -> str | None:
    if role not in {"admin", "member"}:
        raise ValueError("project member role must be 'admin' or 'member'")

    existing_role = await conn.fetchval(
        """
        SELECT role
        FROM project_members
        WHERE project_id = $1
          AND user_id = $2
        """,
        project_id,
        user_id,
    )

    await conn.execute(
        """
        INSERT INTO project_members(project_id, user_id, role)
        VALUES($1, $2, $3)
        ON CONFLICT (project_id, user_id)
        DO UPDATE SET role = EXCLUDED.role
        """,
        project_id,
        user_id,
        role,
    )

    return existing_role


async def ensure_project_member_access(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    auth_user: dict[str, Any],
    message: str = "Acesso negado: você não é membro deste projeto",
) -> None:
    in_project = await conn.fetchval(
        """
        SELECT 1
        FROM project_members
        WHERE project_id = $1
          AND user_id = $2
        LIMIT 1
        """,
        project_id,
        auth_user["db_user_id"],
    )
    if not in_project and not auth_user["is_global_admin"]:
        raise HTTPException(403, message)


async def ensure_project_admin_access(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    auth_user: dict[str, Any],
    message: str = "Acesso negado: apenas admin do projeto ou administrador do sistema",
) -> None:
    role = await get_project_role(conn, project_id=project_id, auth_user=auth_user)
    if role != "admin" and not auth_user["is_global_admin"]:
        raise HTTPException(403, message)


async def ensure_project_owner_access(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    auth_user: dict[str, Any],
    message: str = "Acesso negado: apenas o dono do projeto ou administrador do sistema",
) -> None:
    owner_id = await conn.fetchval(
        "SELECT owner_id FROM projects WHERE id = $1",
        project_id,
    )
    if owner_id != auth_user["db_user_id"] and not auth_user["is_global_admin"]:
        raise HTTPException(403, message)


async def audit_project_member_change(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    target_user_id: uuid.UUID | None,
    old_role: str | None,
    new_role: str | None,
    action: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO project_members_audit(
            project_id, target_user_id, old_role, new_role, action, actor_user_id
        )
        VALUES($1, $2, $3, $4, $5, $6)
        """,
        project_id,
        target_user_id,
        old_role,
        new_role,
        action,
        actor_user_id,
    )
