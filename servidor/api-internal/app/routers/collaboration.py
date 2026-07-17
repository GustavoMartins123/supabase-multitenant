"""Notas, hints, threads, tags e notificações de colaboração."""

import re

from fastapi import APIRouter, Depends, HTTPException, Request

from app.control_plane_service import audit_studio_action, create_studio_notification
from app.database import get_pool
from app.dependencies import (
    ensure_project_member_access,
    get_project_member_row,
    get_project_role,
    get_project_row,
    resolve_authenticated_user,
)
from app.schemas import (
    ProjectHintCreate,
    ProjectHintStatusUpdate,
    ProjectNoteCreate,
    ProjectNotificationRead,
    ProjectTagAssign,
    ProjectThreadMessageCreate,
)
from app.validation import parse_uuid_value, validate_project_id


router = APIRouter(tags=["collaboration"])


@router.get("/api/projects/{project_name}/collaboration")
async def get_project_collaboration(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project = await get_project_row(conn, project_name)
        project_id = project["id"]
        await ensure_project_member_access(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )
        project_role = await get_project_role(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )

        tag_rows = await conn.fetch(
            """
            SELECT
                t.id,
                t.name,
                t.color,
                t.category,
                t.is_system,
                a.created_at AS assigned_at
            FROM studio_project_tags t
            LEFT JOIN studio_project_tag_assignments a
              ON a.tag_id = t.id
             AND a.project_id = $1
            ORDER BY t.is_system DESC, t.category, t.name
            """,
            project_id,
        )
        notes = await conn.fetch(
            """
            SELECT
                n.id,
                n.visibility,
                n.body,
                n.is_encrypted,
                n.created_at,
                n.updated_at,
                n.author_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Operador') AS author_name
            FROM studio_project_notes n
            LEFT JOIN users u ON u.id = n.author_user_id
            WHERE n.project_id = $1
              AND (
                  n.visibility = 'public'
                  OR n.author_user_id = $2
              )
            ORDER BY n.created_at DESC
            LIMIT 20
            """,
            project_id,
            auth_user["db_user_id"],
        )
        member_rows = await conn.fetch(
            """
            SELECT
                u.id,
                COALESCE(u.display_name, u.authelia_username, 'Operador') AS display_name,
                u.authelia_username,
                pm.role
            FROM project_members pm
            JOIN users u ON u.id = pm.user_id
            WHERE pm.project_id = $1
              AND u.is_active = true
            ORDER BY pm.role = 'admin' DESC, display_name
            """,
            project_id,
        )
        hints = await conn.fetch(
            """
            SELECT
                h.id,
                h.body,
                h.status,
                h.created_at,
                h.updated_at,
                h.resolved_at,
                h.author_user_id,
                h.target_user_id,
                COALESCE(author.display_name, author.authelia_username, 'Operador') AS author_name,
                COALESCE(target.display_name, target.authelia_username, 'Operador') AS target_name,
                COALESCE(resolver.display_name, resolver.authelia_username) AS resolved_by_name
            FROM studio_project_hints h
            LEFT JOIN users author ON author.id = h.author_user_id
            LEFT JOIN users target ON target.id = h.target_user_id
            LEFT JOIN users resolver ON resolver.id = h.resolved_by
            WHERE h.project_id = $1
            ORDER BY h.status = 'open' DESC, h.created_at DESC
            LIMIT 40
            """,
            project_id,
        )
        thread_messages = await conn.fetch(
            """
            SELECT *
            FROM (
                SELECT
                    m.id,
                    m.body,
                    m.created_at,
                    m.updated_at,
                    m.author_user_id,
                    COALESCE(u.display_name, u.authelia_username, 'Operador') AS author_name
                FROM studio_project_thread_messages m
                LEFT JOIN users u ON u.id = m.author_user_id
                WHERE m.project_id = $1
                ORDER BY m.created_at DESC
                LIMIT 50
            ) recent
            ORDER BY created_at ASC
            """,
            project_id,
        )
        notification_rows = await conn.fetch(
            """
            SELECT
                n.id,
                n.kind,
                n.target_type,
                n.target_id,
                n.payload,
                n.read_at,
                n.created_at,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM studio_project_notifications n
            LEFT JOIN users u ON u.id = n.actor_user_id
            WHERE n.project_id = $1
              AND n.target_user_id = $2
            ORDER BY n.created_at DESC
            LIMIT 50
            """,
            project_id,
            auth_user["db_user_id"],
        )

    available_tags = [
        {
            "id": str(row["id"]),
            "name": row["name"],
            "color": row["color"],
            "category": row["category"],
            "is_system": row["is_system"],
            "assigned": row["assigned_at"] is not None,
        }
        for row in tag_rows
    ]

    return {
        "project": project_name,
        "available_tags": available_tags,
        "assigned_tags": [tag for tag in available_tags if tag["assigned"]],
        "members": [
            {
                "id": str(row["id"]),
                "display_name": row["display_name"],
                "username": row["authelia_username"],
                "role": row["role"],
            }
            for row in member_rows
        ],
        "notes": [
            {
                "id": str(row["id"]),
                "visibility": row["visibility"],
                "body": row["body"],
                "is_encrypted": row["is_encrypted"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                "author_user_id": str(row["author_user_id"]) if row["author_user_id"] else None,
                "author_name": row["author_name"],
                "can_delete": (
                    auth_user["is_global_admin"]
                    or row["author_user_id"] == auth_user["db_user_id"]
                    or project_role == "admin"
                ),
            }
            for row in notes
        ],
        "hints": [
            {
                "id": str(row["id"]),
                "body": row["body"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                "author_user_id": str(row["author_user_id"]) if row["author_user_id"] else None,
                "author_name": row["author_name"],
                "target_user_id": str(row["target_user_id"]) if row["target_user_id"] else None,
                "target_name": row["target_name"],
                "resolved_by_name": row["resolved_by_name"],
                "can_update": (
                    auth_user["is_global_admin"]
                    or project_role == "admin"
                    or row["author_user_id"] == auth_user["db_user_id"]
                    or row["target_user_id"] == auth_user["db_user_id"]
                ),
            }
            for row in hints
        ],
        "thread_messages": [
            {
                "id": str(row["id"]),
                "body": row["body"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
                "author_user_id": str(row["author_user_id"]) if row["author_user_id"] else None,
                "author_name": row["author_name"],
            }
            for row in thread_messages
        ],
        "notifications": [
            {
                "id": str(row["id"]),
                "kind": row["kind"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "payload": row["payload"],
                "actor_name": row["actor_name"],
                "read_at": row["read_at"].isoformat() if row["read_at"] else None,
                "created_at": row["created_at"].isoformat(),
            }
            for row in notification_rows
        ],
    }


@router.post("/api/projects/{project_name}/notes", status_code=201)
async def create_project_note(
    project_name: str,
    body: ProjectNoteCreate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    visibility = body.visibility.strip().lower()
    note_body = body.body.strip()

    if visibility not in {"public", "private"}:
        raise HTTPException(400, "visibility deve ser public ou private")
    if not note_body:
        raise HTTPException(400, "body é obrigatório")
    if len(note_body) > 4000:
        raise HTTPException(400, "body deve ter no máximo 4000 caracteres")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            note = await conn.fetchrow(
                """
                INSERT INTO studio_project_notes(
                    project_id, author_user_id, visibility, body
                )
                VALUES($1, $2, $3, $4)
                RETURNING id, visibility, body, is_encrypted, created_at, updated_at
                """,
                project_id,
                auth_user["db_user_id"],
                visibility,
                note_body,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_note_created",
                target_type="studio_project_note",
                target_id=str(note["id"]),
                new_value={"visibility": visibility, "is_encrypted": False},
            )

    return {
        "id": str(note["id"]),
        "visibility": note["visibility"],
        "body": note["body"],
        "is_encrypted": note["is_encrypted"],
        "created_at": note["created_at"].isoformat(),
        "updated_at": note["updated_at"].isoformat(),
        "author_user_id": str(auth_user["db_user_id"]),
        "author_name": auth_user["display_name"] or auth_user["username"],
    }


@router.delete("/api/projects/{project_name}/notes/{note_id}")
async def delete_project_note(
    project_name: str,
    note_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_note_id = parse_uuid_value(note_id)
    if parsed_note_id is None:
        raise HTTPException(400, "note_id inválido")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )

            note = await conn.fetchrow(
                """
                SELECT id, author_user_id, visibility, body
                FROM studio_project_notes
                WHERE id = $1
                  AND project_id = $2
                """,
                parsed_note_id,
                project_id,
            )
            if not note:
                raise HTTPException(404, "Anotação não encontrada")

            role = await get_project_role(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            can_delete = (
                auth_user["is_global_admin"]
                or note["author_user_id"] == auth_user["db_user_id"]
                or role == "admin"
            )
            if not can_delete:
                raise HTTPException(403, "Sem permissão para excluir esta anotação")

            await conn.execute(
                "DELETE FROM studio_project_notes WHERE id = $1",
                parsed_note_id,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_note_deleted",
                target_type="studio_project_note",
                target_id=str(parsed_note_id),
                old_value={
                    "visibility": note["visibility"],
                    "author_user_id": str(note["author_user_id"]) if note["author_user_id"] else None,
                },
            )

    return {"status": "ok"}


@router.post("/api/projects/{project_name}/hints", status_code=201)
async def create_project_hint(
    project_name: str,
    body: ProjectHintCreate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    hint_body = body.body.strip()
    if not hint_body:
        raise HTTPException(400, "body é obrigatório")
    if len(hint_body) > 2000:
        raise HTTPException(400, "body deve ter no máximo 2000 caracteres")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            target_member = await get_project_member_row(
                conn,
                project_id=project_id,
                user_id=body.target_user_id,
            )
            if not target_member:
                raise HTTPException(400, "Usuário alvo não é membro deste projeto")

            hint = await conn.fetchrow(
                """
                INSERT INTO studio_project_hints(
                    project_id, author_user_id, target_user_id, body
                )
                VALUES($1, $2, $3, $4)
                RETURNING id, status, created_at, updated_at
                """,
                project_id,
                auth_user["db_user_id"],
                body.target_user_id,
                hint_body,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_hint_created",
                target_type="studio_project_hint",
                target_id=str(hint["id"]),
                new_value={
                    "target_user_id": str(body.target_user_id),
                    "status": hint["status"],
                    "body_length": len(hint_body),
                },
            )
            await create_studio_notification(
                conn,
                project_id=project_id,
                target_user_id=body.target_user_id,
                actor_user_id=auth_user["db_user_id"],
                kind="project_hint_created",
                target_type="studio_project_hint",
                target_id=str(hint["id"]),
                payload={"status": hint["status"]},
            )

    return {
        "id": str(hint["id"]),
        "status": hint["status"],
        "created_at": hint["created_at"].isoformat(),
        "updated_at": hint["updated_at"].isoformat(),
    }


@router.put("/api/projects/{project_name}/hints/{hint_id}")
async def update_project_hint_status(
    project_name: str,
    hint_id: str,
    body: ProjectHintStatusUpdate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_hint_id = parse_uuid_value(hint_id)
    if parsed_hint_id is None:
        raise HTTPException(400, "hint_id inválido")

    status = body.status.strip().lower()
    if status not in {"open", "resolved"}:
        raise HTTPException(400, "status deve ser open ou resolved")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            hint = await conn.fetchrow(
                """
                SELECT id, author_user_id, target_user_id, status
                FROM studio_project_hints
                WHERE id = $1
                  AND project_id = $2
                """,
                parsed_hint_id,
                project_id,
            )
            if not hint:
                raise HTTPException(404, "Hint não encontrado")

            project_role = await get_project_role(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            can_update = (
                auth_user["is_global_admin"]
                or project_role == "admin"
                or hint["author_user_id"] == auth_user["db_user_id"]
                or hint["target_user_id"] == auth_user["db_user_id"]
            )
            if not can_update:
                raise HTTPException(403, "Sem permissão para alterar este hint")

            if status == "resolved":
                await conn.execute(
                    """
                    UPDATE studio_project_hints
                    SET status = 'resolved',
                        resolved_by = $1,
                        resolved_at = now(),
                        updated_at = now()
                    WHERE id = $2
                    """,
                    auth_user["db_user_id"],
                    parsed_hint_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE studio_project_hints
                    SET status = 'open',
                        resolved_by = NULL,
                        resolved_at = NULL,
                        updated_at = now()
                    WHERE id = $1
                    """,
                    parsed_hint_id,
                )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_hint_status_updated",
                target_type="studio_project_hint",
                target_id=str(parsed_hint_id),
                old_value={"status": hint["status"]},
                new_value={
                    "status": status,
                    "resolved_by": (
                        str(auth_user["db_user_id"])
                        if status == "resolved"
                        else None
                    ),
                },
            )

    return {"status": status}


@router.post("/api/projects/{project_name}/thread/messages", status_code=201)
async def create_project_thread_message(
    project_name: str,
    body: ProjectThreadMessageCreate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    message_body = body.body.strip()
    if not message_body:
        raise HTTPException(400, "body é obrigatório")
    if len(message_body) > 4000:
        raise HTTPException(400, "body deve ter no máximo 4000 caracteres")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            message = await conn.fetchrow(
                """
                INSERT INTO studio_project_thread_messages(
                    project_id, author_user_id, body
                )
                VALUES($1, $2, $3)
                RETURNING id, created_at, updated_at
                """,
                project_id,
                auth_user["db_user_id"],
                message_body,
            )
            notification_targets = await conn.fetch(
                """
                SELECT user_id
                FROM project_members
                WHERE project_id = $1
                  AND user_id <> $2
                """,
                project_id,
                auth_user["db_user_id"],
            )
            for target in notification_targets:
                await create_studio_notification(
                    conn,
                    project_id=project_id,
                    target_user_id=target["user_id"],
                    actor_user_id=auth_user["db_user_id"],
                    kind="project_thread_message_created",
                    target_type="studio_project_thread_message",
                    target_id=str(message["id"]),
                )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_thread_message_created",
                target_type="studio_project_thread_message",
                target_id=str(message["id"]),
                new_value={
                    "body_length": len(message_body),
                    "notification_count": len(notification_targets),
                },
            )

    return {
        "id": str(message["id"]),
        "created_at": message["created_at"].isoformat(),
        "updated_at": message["updated_at"].isoformat(),
    }


@router.patch("/api/projects/{project_name}/notifications/{notification_id}")
async def update_project_notification_read_state(
    project_name: str,
    notification_id: str,
    body: ProjectNotificationRead,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_notification_id = parse_uuid_value(notification_id)
    if parsed_notification_id is None:
        raise HTTPException(400, "notification_id invalido")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            notification = await conn.fetchrow(
                """
                SELECT id, read_at
                FROM studio_project_notifications
                WHERE id = $1
                  AND project_id = $2
                  AND target_user_id = $3
                FOR UPDATE
                """,
                parsed_notification_id,
                project_id,
                auth_user["db_user_id"],
            )
            if not notification:
                raise HTTPException(404, "Notificacao nao encontrada")

            old_read = notification["read_at"] is not None
            if old_read != body.read:
                updated_at = await conn.fetchval(
                    """
                    UPDATE studio_project_notifications
                    SET read_at = CASE WHEN $1 THEN now() ELSE NULL END
                    WHERE id = $2
                    RETURNING read_at
                    """,
                    body.read,
                    parsed_notification_id,
                )
                await audit_studio_action(
                    conn,
                    project_id=project_id,
                    actor_user_id=auth_user["db_user_id"],
                    action="project_notification_read_state_changed",
                    target_type="studio_project_notification",
                    target_id=str(parsed_notification_id),
                    old_value={"read": old_read},
                    new_value={"read": body.read},
                )
            else:
                updated_at = notification["read_at"]

    return {
        "id": str(parsed_notification_id),
        "read": body.read,
        "read_at": updated_at.isoformat() if updated_at else None,
    }


@router.post("/api/projects/{project_name}/tags", status_code=201)
async def assign_project_tag(
    project_name: str,
    body: ProjectTagAssign,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    color = (body.color or "#3ECF8E").strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise HTTPException(400, "color deve estar no formato #RRGGBB")

    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )

            tag_id = body.tag_id
            if tag_id is None:
                tag_name = (body.name or "").strip()
                if not tag_name:
                    raise HTTPException(400, "tag_id ou name é obrigatório")
                if len(tag_name) > 40:
                    raise HTTPException(400, "name deve ter no máximo 40 caracteres")
                if not auth_user["is_global_admin"]:
                    raise HTTPException(403, "Apenas admin do sistema pode criar novas tags")

                tag_id = await conn.fetchval(
                    """
                    INSERT INTO studio_project_tags(name, color, category, created_by)
                    VALUES($1, $2, 'custom', $3)
                    ON CONFLICT (name)
                    DO UPDATE SET name = EXCLUDED.name
                    RETURNING id
                    """,
                    tag_name,
                    color,
                    auth_user["db_user_id"],
                )
            else:
                tag_exists = await conn.fetchval(
                    "SELECT 1 FROM studio_project_tags WHERE id = $1",
                    tag_id,
                )
                if not tag_exists:
                    raise HTTPException(404, "Tag não encontrada")

            await conn.execute(
                """
                INSERT INTO studio_project_tag_assignments(project_id, tag_id, assigned_by)
                VALUES($1, $2, $3)
                ON CONFLICT (project_id, tag_id) DO NOTHING
                """,
                project_id,
                tag_id,
                auth_user["db_user_id"],
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_tag_assigned",
                target_type="studio_project_tag",
                target_id=str(tag_id),
            )

            tag = await conn.fetchrow(
                """
                SELECT id, name, color, category, is_system
                FROM studio_project_tags
                WHERE id = $1
                """,
                tag_id,
            )

    return {
        "id": str(tag["id"]),
        "name": tag["name"],
        "color": tag["color"],
        "category": tag["category"],
        "is_system": tag["is_system"],
        "assigned": True,
    }


@router.delete("/api/projects/{project_name}/tags/{tag_id}")
async def unassign_project_tag(
    project_name: str,
    tag_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_tag_id = parse_uuid_value(tag_id)
    if parsed_tag_id is None:
        raise HTTPException(400, "tag_id inválido")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            project_id = project["id"]
            await ensure_project_member_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
            )
            deleted = await conn.fetchval(
                """
                DELETE FROM studio_project_tag_assignments
                WHERE project_id = $1 AND tag_id = $2
                RETURNING tag_id
                """,
                project_id,
                parsed_tag_id,
            )
            if deleted:
                await audit_studio_action(
                    conn,
                    project_id=project_id,
                    actor_user_id=auth_user["db_user_id"],
                    action="project_tag_removed",
                    target_type="studio_project_tag",
                    target_id=str(parsed_tag_id),
                )

    return {"status": "ok"}
