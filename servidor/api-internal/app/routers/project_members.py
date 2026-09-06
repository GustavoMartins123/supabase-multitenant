from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.database import get_pool
from app.dependencies import (
    audit_project_member_change,
    ensure_project_admin_access,
    ensure_project_member_access,
    get_project_member_row,
    get_project_row,
    get_user_record_by_identifier,
    require_synced_user_record,
    resolve_authenticated_user,
    upsert_project_member,
)
from app.schemas import AddMember
from app.validation import parse_uuid_value, validate_project_id

router = APIRouter(tags=["project-members"])


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


@router.post("/api/projects/{project_name}/members", response_model=AddMemberResponse)
async def add_member(
    project_name: str,
    member: AddMember,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
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


@router.get("/api/projects/{name}/members", response_model=list[MemberItem])
async def list_members_by_ref(
    name: str,
    request: Request,
    pool=Depends(get_pool),
):
    name = validate_project_id(name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        row = await get_project_row(conn, name)
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
    "/api/projects/{name}/members/{member_id}",
    status_code=200,
    response_model=RemoveMemberResponse
)
async def remove_member_by_ref(
    name: str,
    member_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    name = validate_project_id(name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, name)
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
        old_member_row = await get_project_member_row(
            conn,
            project_id=project_id,
            user_id=target_uuid,
        )
        old_role = old_member_row["role"] if old_member_row else None

        if target_uuid is not None and target_uuid == project_row["owner_id"]:
            raise HTTPException(
                409,
                "O dono do projeto nao pode ser removido; transfira a posse antes",
            )

        if old_role == "admin" and target_uuid != auth_user["db_user_id"]:
            is_owner = project_row["owner_id"] == auth_user["db_user_id"]
            if not is_owner and not auth_user["is_global_admin"]:
                raise HTTPException(
                    403,
                    "Apenas o dono do projeto ou um administrador global pode "
                    "remover outro admin",
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
        if old_role is not None:
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
