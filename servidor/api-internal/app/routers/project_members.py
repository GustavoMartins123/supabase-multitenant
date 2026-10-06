from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Literal
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.database import get_pool
from app.dependencies import (
    audit_project_member_change,
    ensure_project_admin_access,
    ensure_member_role_change_allowed,
    ensure_project_member_access,
    get_project_member_row,
    get_public_project_row,
    get_user_record_by_identifier,
    require_synced_user_record,
    resolve_authenticated_user,
    upsert_project_member,
)
from app.schemas import AddMember
from app.validation import parse_uuid_value, validate_project_ref

router = APIRouter(tags=["project-members"])


class AvailableProjectUser(BaseModel):
    user_id: str
    display_name: str
    username: str
    is_active: bool
    status: Literal["active", "member", "available"]
    picture_url: str | None


@router.get("/api/projects/{project_ref}/available-users", response_model=list[AvailableProjectUser])
async def list_available_project_users(
    project_ref: str,
    request: Request,
    include_members: bool = Query(False),
    mode: Literal["owner", "admin"] = Query("owner"),
    pool=Depends(get_pool),
):
    project_ref = validate_project_ref(project_ref)
    auth_user = await resolve_authenticated_user(request, pool)
    if mode == "admin" and not auth_user["is_global_admin"]:
        raise HTTPException(403, "Global admin access required for admin mode")
    async with pool.acquire() as conn:
        project = await get_public_project_row(conn, project_ref)
        await ensure_project_admin_access(conn, project_id=project["id"], auth_user=auth_user)
        rows = await conn.fetch(
            """
            SELECT u.id, u.display_name, u.authelia_username, u.picture_url, m.role
            FROM users u
            LEFT JOIN project_members m ON m.user_id=u.id AND m.project_id=$1
            WHERE u.is_active
              AND (m.role IS NULL OR ($2 AND m.role='member'))
            ORDER BY u.authelia_username, u.id
            """,
            project["id"], include_members,
        )
    if any(not isinstance(row["display_name"], str) or not row["display_name"].strip() for row in rows):
        raise HTTPException(503, "Canonical directory contains a user without a display name")
    return [
        {
            "user_id": str(row["id"]),
            "display_name": row["display_name"],
            "username": row["authelia_username"],
            "picture_url": row["picture_url"],
            "is_active": True,
            "status": "member" if row["role"] == "member" else "available" if include_members else "active",
        }
        for row in rows
    ]


class AddMemberResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool


class MemberItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_id: str
    role: str


class RemoveMemberResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    ok: bool


@router.post("/api/projects/{project_ref}/members", response_model=AddMemberResponse)
async def add_member(
    project_ref: str,
    member: AddMember,
    request: Request,
    pool=Depends(get_pool),
):
    project_ref = validate_project_ref(project_ref)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        async with conn.transaction():
            project_row = await get_public_project_row(conn, project_ref, for_update=True)
            await ensure_project_admin_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
                message="Only admin can add members",
            )

            target_user = await require_synced_user_record(
                conn,
                identifier=member.user_id,
                field_name="user_id",
                missing_message="Usuário alvo ainda não foi sincronizado com o banco",
            )
            old_member = await get_project_member_row(
                conn, project_id=project_row["id"], user_id=target_user["id"]
            )
            await ensure_member_role_change_allowed(
                conn, project_row=project_row, auth_user=auth_user,
                target_user_id=target_user["id"],
                old_role=old_member["role"] if old_member else None,
                new_role=member.role,
            )
            existing_role = await upsert_project_member(
                conn,
                project_id=project_row["id"],
                user_id=target_user["id"],
                role=member.role,
            )
            await audit_project_member_change(
                conn,
                project_id=project_row["id"],
                target_user_id=target_user["id"],
                old_role=existing_role,
                new_role=member.role,
                action="added" if existing_role is None else "updated",
                actor_user_id=auth_user["db_user_id"],
            )
    return {"ok": True}


@router.get("/api/projects/{project_ref}/members", response_model=list[MemberItem])
async def list_members_by_ref(
    project_ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_ref = validate_project_ref(project_ref)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        row = await get_public_project_row(conn, project_ref)
        pid = row["id"]
        await ensure_project_member_access(conn, project_id=pid, auth_user=auth_user)

        rows = await conn.fetch(
            "SELECT user_id, role FROM project_members "
            "WHERE project_id=$1",
            pid,
        )
    return [
        {
            "user_id": str(r["user_id"]),
            "role": r["role"],
        }
        for r in rows
    ]


@router.delete(
    "/api/projects/{project_ref}/members/{member_id}",
    status_code=200,
    response_model=RemoveMemberResponse
)
async def remove_member_by_ref(
    project_ref: str,
    member_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_ref = validate_project_ref(project_ref)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        async with conn.transaction():
            project_row = await get_public_project_row(conn, project_ref, for_update=True)
            project_id = project_row["id"]
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Only admin can remove members",
            )

            target_member = await get_user_record_by_identifier(
                conn,
                identifier=member_id,
                field_name="member_id",
            )
            target_uuid = target_member["id"] if target_member else parse_uuid_value(member_id)
            if target_uuid is None:
                raise HTTPException(404, "Membro não encontrado")
            old_member_row = await get_project_member_row(
                conn,
                project_id=project_id,
                user_id=target_uuid,
            )
            old_role = old_member_row["role"] if old_member_row else None
            if old_role is None:
                raise HTTPException(404, "Membro não encontrado")

            await ensure_member_role_change_allowed(
                conn, project_row=project_row, auth_user=auth_user,
                target_user_id=target_uuid, old_role=old_role, new_role=None,
            )

            await conn.execute(
                """
                DELETE FROM project_members
                WHERE project_id = $1
                  AND user_id = $2
                """,
                project_id,
                target_uuid,
            )
            await audit_project_member_change(
                conn,
                project_id=project_id,
                target_user_id=target_uuid,
                old_role=old_role,
                new_role=None,
                action="removed",
                actor_user_id=auth_user["db_user_id"],
            )

    return {"ok": True}
