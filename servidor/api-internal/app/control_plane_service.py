"""Servicos de identidade, auditoria e notificacao do control plane."""

import json
import uuid
from typing import Any

import asyncpg
from fastapi import HTTPException

from app.validation import normalize_groups

PROFILE_FIELDS = {
    "display_name",
    "given_name",
    "family_name",
    "middle_name",
    "nickname",
    "picture",
    "website",
    "profile",
    "gender",
    "birthdate",
    "zoneinfo",
    "locale",
    "phone_number",
    "phone_extension",
    "street_address",
    "locality",
    "region",
    "postal_code",
    "country",
}

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


def normalize_user_sync_source(
    source: str | dict[str, Any] | None,
) -> tuple[str, str | None, dict[str, str] | None]:
    if not isinstance(source, dict):
        return (str(source or "studio_sync"), None, None)

    source_name = str(source.get("name") or "studio_sync").strip() or "studio_sync"
    email_value = source.get("email")
    email = str(email_value).strip().lower() if email_value else None
    raw_profile = source.get("profile")
    if not isinstance(raw_profile, dict):
        return source_name, email, None

    profile: dict[str, str] = {}
    for field in PROFILE_FIELDS:
        value = raw_profile.get(field)
        profile[field] = "" if value is None else str(value).strip()
    return source_name, email, profile


async def sync_user_record(
    conn: asyncpg.Connection,
    *,
    user_id: uuid.UUID,
    username: str,
    display_name: str | None,
    groups: list[str] | tuple[str, ...] | str | None,
    is_active: bool,
    source: str | dict[str, Any],
) -> dict[str, Any]:
    normalized_username = (username or "").strip()
    normalized_groups = normalize_groups(groups)
    source_name, email, profile_data = normalize_user_sync_source(source)
    profile_supplied = profile_data is not None
    picture_url = (profile_data or {}).get("picture") or None

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
        SELECT id, display_name, email, picture_url, profile_data, profile_version
        FROM users
        WHERE id = $1
        """,
        user_id,
    )
    old_profile = dict(row["profile_data"] or {}) if row else {}
    old_email = row["email"] if row else None
    old_picture = row["picture_url"] if row else None
    old_display_name = row["display_name"] if row else None
    changed_fields: list[str] = []
    if profile_supplied:
        keys = set(old_profile) | set(profile_data or {})
        changed_fields.extend(
            sorted(
                field
                for field in keys
                if old_profile.get(field, "") != (profile_data or {}).get(field, "")
            )
        )
        if old_email != email:
            changed_fields.append("email")
        if old_picture != picture_url and "picture" not in changed_fields:
            changed_fields.append("picture")
        if old_display_name != display_name and "display_name" not in changed_fields:
            changed_fields.append("display_name")
    changed_fields = sorted(set(changed_fields))
    profile_changed = bool(changed_fields)
    serialized_profile = json.dumps(profile_data or {})
    previous_version = int(row["profile_version"] or 1) if row else 0
    next_version = previous_version + 1 if row else 1

    if row:
        await conn.execute(
            """
            UPDATE users
            SET authelia_username = $1,
                display_name = $2,
                is_active = $3,
                source = $4,
                email = CASE WHEN $5 THEN $6 ELSE email END,
                picture_url = CASE WHEN $5 THEN $7 ELSE picture_url END,
                profile_data = CASE WHEN $5 THEN $8::jsonb ELSE profile_data END,
                profile_version = CASE WHEN $9 THEN profile_version + 1 ELSE profile_version END,
                profile_updated_at = CASE WHEN $9 THEN now() ELSE profile_updated_at END,
                last_sync_at = now(),
                updated_at = now()
            WHERE id = $10
            """,
            normalized_username,
            display_name,
            is_active,
            source_name,
            profile_supplied,
            email,
            picture_url,
            serialized_profile,
            profile_changed,
            user_id,
        )
    else:
        user_id = await conn.fetchval(
            """
            INSERT INTO users(
                id, authelia_username, display_name,
                is_active, source, email, picture_url,
                profile_data, profile_version, profile_updated_at
            )
            VALUES($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 1,
                   CASE WHEN $9 THEN now() ELSE NULL END)
            RETURNING id
            """,
            user_id,
            normalized_username,
            display_name,
            is_active,
            source_name,
            email,
            picture_url,
            serialized_profile,
            profile_supplied,
        )
        profile_changed = profile_supplied
        if profile_supplied and not changed_fields:
            changed_fields = sorted(profile_data or {})

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
            actor_type=source_name,
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
            source_name,
        )
        if group_name not in current_groups:
            await audit_user_group_change(
                conn,
                user_id=user_id,
                group_name=group_name,
                action="added",
                old_value={"present": False},
                new_value={"present": True},
                actor_type=source_name,
            )

    if profile_changed:
        await audit_studio_action(
            conn,
            project_id=None,
            actor_user_id=user_id,
            action="user_profile_updated",
            target_type="user",
            target_id=str(user_id),
            old_value={"profile_version": previous_version or None},
            new_value={
                "profile_version": next_version,
                "changed_fields": changed_fields,
            },
        )

    projection = await conn.fetchrow(
        """
        SELECT email, picture_url, profile_data, profile_version, profile_updated_at
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    return {
        "id": str(user_id),
        "username": normalized_username,
        "groups": normalized_groups,
        "is_active": is_active,
        "email": projection["email"] if projection else None,
        "picture_url": projection["picture_url"] if projection else None,
        "profile": dict(projection["profile_data"] or {}) if projection else {},
        "profile_version": projection["profile_version"] if projection else 1,
        "profile_updated_at": (
            projection["profile_updated_at"].isoformat()
            if projection and projection["profile_updated_at"]
            else None
        ),
    }
