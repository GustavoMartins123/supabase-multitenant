"""Servicos de identidade, auditoria e notificacao do control plane."""

import json
import uuid
from typing import Any

import asyncpg

from app.validation import normalize_groups

async def audit_studio_action(
    conn: asyncpg.Connection,
    *,
    project_id: str | uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    action: str,
    target_type: str,
    target_id: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO studio_audit_log(
            project_id, actor_user_id, action, target_type, target_id, old_value, new_value
        )
        VALUES($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb)
        """,
        project_id,
        actor_user_id,
        action,
        target_type,
        target_id,
        json.dumps(old_value) if old_value is not None else None,
        json.dumps(new_value) if new_value is not None else None,
    )


async def create_studio_notification(
    conn: asyncpg.Connection,
    *,
    project_id: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    kind: str,
    target_type: str,
    target_id: str | None,
    payload: dict[str, Any] | None = None,
) -> uuid.UUID:
    notification_id = await conn.fetchval(
        """
        INSERT INTO studio_project_notifications(
            project_id, target_user_id, actor_user_id, kind,
            target_type, target_id, payload
        )
        VALUES($1, $2, $3, $4, $5, $6, $7::jsonb)
        RETURNING id
        """,
        project_id,
        target_user_id,
        actor_user_id,
        kind,
        target_type,
        target_id,
        json.dumps(payload or {}),
    )
    await audit_studio_action(
        conn,
        project_id=project_id,
        actor_user_id=actor_user_id,
        action="project_notification_created",
        target_type="studio_project_notification",
        target_id=str(notification_id),
        new_value={
            "kind": kind,
            "target_user_id": str(target_user_id),
            "source_target_type": target_type,
            "source_target_id": target_id,
        },
    )
    return notification_id


async def audit_user_group_change(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    group_name: str,
    action: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    actor_type: str,
) -> None:
    await conn.execute(
        """
        INSERT INTO user_group_audit(user_id, group_name, action, old_value, new_value, actor_type)
        VALUES($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        """,
        user_id,
        group_name,
        action,
        json.dumps(old_value) if old_value is not None else None,
        json.dumps(new_value) if new_value is not None else None,
        actor_type,
    )


async def sync_user_record(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    username: str,
    display_name: str | None,
    groups: list[str] | tuple[str, ...] | str | None,
    is_active: bool,
    source: str,
) -> dict[str, Any]:
    normalized_username = (username or "").strip()
    normalized_groups = normalize_groups(groups)

    if not normalized_username:
        raise HTTPException(400, "username é obrigatório")

    conflicting_user_id = await conn.fetchval(
        """
        SELECT id
        FROM users
        WHERE authelia_username = $1
          AND id <> $2
        LIMIT 1
        """,
        normalized_username,
        user_id,
    )
    if conflicting_user_id:
        raise HTTPException(409, "username já vinculado a outro identificador")

    row = await conn.fetchrow(
        """
        SELECT id
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    if row:
        await conn.execute(
            """
            UPDATE users
            SET authelia_username = $1,
                display_name = $2,
                is_active = $3,
                source = $4,
                last_sync_at = now(),
                updated_at = now()
            WHERE id = $5
            """,
            normalized_username,
            display_name,
            is_active,
            source,
            user_id,
        )
    else:
        user_id = await conn.fetchval(
            """
            INSERT INTO users(
                id, authelia_username, display_name,
                is_active, source
            )
            VALUES($1, $2, $3, $4, $5)
            RETURNING id
            """,
            user_id,
            normalized_username,
            display_name,
            is_active,
            source,
        )

    current_groups = {
        r["group_name"]
        for r in await conn.fetch("SELECT group_name FROM user_groups WHERE user_id = $1", user_id)
    }
    desired_groups = set(normalized_groups)

    for group_name in current_groups - desired_groups:
        await conn.execute(
            "DELETE FROM user_groups WHERE user_id = $1 AND group_name = $2",
            user_id,
            group_name,
        )
        await audit_user_group_change(
            conn,
            user_id=user_id,
            group_name=group_name,
            action="removed",
            old_value={"present": True},
            new_value={"present": False},
            actor_type=source,
        )

    for group_name in desired_groups:
        await conn.execute(
            """
            INSERT INTO user_groups(user_id, group_name, source, synced_at)
            VALUES($1, $2, $3, now())
            ON CONFLICT (user_id, group_name)
            DO UPDATE SET source = EXCLUDED.source, synced_at = now()
            """,
            user_id,
            group_name,
            source,
        )
        if group_name not in current_groups:
            await audit_user_group_change(
                conn,
                user_id=user_id,
                group_name=group_name,
                action="added",
                old_value={"present": False},
                new_value={"present": True},
                actor_type=source,
            )

    return {
        "id": str(user_id),
        "username": normalized_username,
        "groups": normalized_groups,
        "is_active": is_active,
    }

