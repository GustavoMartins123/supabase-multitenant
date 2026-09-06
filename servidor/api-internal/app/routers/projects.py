from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.database import get_pool
from app.dependencies import (
    ensure_project_member_access,
    get_project_row,
    resolve_authenticated_user,
)
from app.host_agent import (
    HostAgentError,
    command_result,
    run_host_agent_command,
    run_host_agent_command_for_job,
)
from app.jobs import (
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
    set_job_status as _set_job_status,
)
from app.key_rotation import project_key_schedule
from app.main import (
    _fail_job_from_command,
    _get_job_project_uuid,
    _get_project_file_size_limit,
    _get_project_storage_limit_token,
    _job_progress_mirror,
    _provision_and_store_keys,
    _serialize_queued_job,
    rollback_project_from_db,
)
from app.opaque_key_service import bootstrap_project_opaque_keys
from app.project_deletion import (
    ProjectDeletionError,
    build_global_delete_token,
    build_realtime_delete_token,
    delete_realtime_tenant,
    delete_supavisor_tenant,
    drain_database_connections,
    drop_database_force,
    drop_supabase_replication_slots,
    global_admin_connection,
    load_project_environment,
    terminate_supavisor_pools,
)
from app.project_env_secrets import (
    PROJECTS_ROOT,
    read_project_secret_keys as _read_project_secret_keys,
)
from app.project_identity import (
    ProjectIdentityError,
    get_job_project_identity as _get_job_project_identity,
    parse_tenant_uuid,
)
from app.project_secret_service import store_project_secrets
from app.runtime_config import (
    AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
    KEY_EXPIRY_WARNING_DAYS,
    NGINX_HMAC_SECRET,
    USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
)
from app.schemas import DuplicateProject, NewProject
from app.step_up_auth import consume_step_up_grant
from app.validation import validate_project_id

router = APIRouter(tags=["projects"])


@router.get("/api/projects")
async def list_projects(
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("""
                SELECT p.id, p.tenant_uuid, p.name, p.display_name,
                       p.automatic_key_rotation_enabled,
                       p.automatic_key_rotation_blocked_at,
                       p.automatic_key_rotation_last_error,
                       p.last_key_rotation_at, p.key_expires_at,
                       p.opaque_keys_prepared_at,
                       p.opaque_keys_activated_at,
                       p.opaque_gateway_cutover_started_at,
                       p.opaque_gateway_ready_at,
                       (
                           SELECT count(*)
                           FROM project_api_key_slots s
                           WHERE s.project_id = p.id AND s.status = 'active'
                       ) AS opaque_key_slot_count
                FROM projects p
                WHERE p.anon_key IS NOT NULL
                  AND EXISTS (
                      SELECT 1
                      FROM project_members m
                      WHERE m.project_id = p.id
                        AND m.user_id = $1
                  )
                ORDER BY p.name
            """, auth_user["db_user_id"])
            result = []
            for r in rows:
                key_expires_at = (
                    int(r["key_expires_at"].timestamp())
                    if r["key_expires_at"] is not None
                    else None
                )
                seconds_remaining = (
                    key_expires_at - int(time.time())
                    if key_expires_at is not None
                    else None
                )
                result.append({
                    "project_uuid": str(r["id"]),
                    "tenant_uuid": (
                        str(r["tenant_uuid"]) if r["tenant_uuid"] else None
                    ),
                    "name": r["name"],
                    "display_name": r["display_name"],
                    "file_size_limit": _get_project_file_size_limit(r["name"]),
                    "storage_limit_token": _get_project_storage_limit_token(r["name"]),
                    "internal_token_expires_at": key_expires_at,
                    "internal_token_expired": (
                        seconds_remaining is not None and seconds_remaining <= 0
                    ),
                    "internal_token_expiring_soon": (
                        seconds_remaining is not None
                        and seconds_remaining <= KEY_EXPIRY_WARNING_DAYS * 86400
                    ),
                    "internal_token_expiry_warning_days": KEY_EXPIRY_WARNING_DAYS,
                    "automatic_key_rotation_enabled": r[
                        "automatic_key_rotation_enabled"
                    ],
                    "automatic_key_rotation_lead_days": (
                        AUTOMATIC_KEY_ROTATION_LEAD_DAYS
                    ),
                    "automatic_key_rotation_due_at": (
                        key_expires_at - AUTOMATIC_KEY_ROTATION_LEAD_DAYS * 86400
                        if key_expires_at is not None
                        else None
                    ),
                    "automatic_key_rotation_blocked": (
                        r["automatic_key_rotation_blocked_at"] is not None
                    ),
                    "automatic_key_rotation_last_error": r[
                        "automatic_key_rotation_last_error"
                    ],
                    "last_key_rotation_at": (
                        r["last_key_rotation_at"].isoformat()
                        if r["last_key_rotation_at"]
                        else None
                    ),
                    "opaque_api_keys_status": (
                        "active"
                        if r["opaque_gateway_ready_at"] is not None
                        else "gateway_recovery_required"
                        if (
                            r["opaque_gateway_cutover_started_at"] is not None
                            or r["opaque_keys_activated_at"] is not None
                        )
                        else "prepared"
                        if r["opaque_keys_prepared_at"] is not None
                        else "legacy"
                    ),
                    "opaque_api_key_slot_count": int(
                        r["opaque_key_slot_count"]
                    ),
                })
    return result


@router.post("/api/projects", status_code=202)
async def create_project(
    body: NewProject,
    request: Request,
    pool=Depends(get_pool),
):
    name = validate_project_id(body.name)

    if not name:
        raise HTTPException(400, "name required")

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            existing = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1",
                name
            )
            if existing:
                raise HTTPException(status_code=409, detail="Project already exists")
            project_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO projects(id, tenant_uuid, name, owner_id, resource_profile)
                VALUES($1, $1, $2, $3, $4)
                """,
                project_id,
                name,
                auth_user["db_user_id"],
                body.resource_profile,
            )
            await conn.execute(
                    """
                    INSERT INTO project_members(project_id, user_id, role)
                    VALUES($1, $2, 'admin')
                    """,
                    project_id, auth_user["db_user_id"]
                )
            job_id = await _create_project_job(
                pool,
                name,
                auth_user["db_user_id"],
                action="create",
                payload={
                    "project_name": name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "tenant_uuid": str(project_id),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )

    position = await _enqueue_project_action(
        name,
        job_id,
        lambda: _provision_and_store_keys(
            job_id, name, auth_user["db_user_id"]
        ),
    )
    message = (
        "Criação enfileirada."
        if position == 0
        else f"Criação enfileirada. Existem {position} ações antes desta na fila para {name}."
    )
    return await _serialize_queued_job(pool, job_id, position, message)


@router.post("/api/projects/duplicate", status_code=202)
async def duplicate_project(
    body: DuplicateProject,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Duplica um projeto existente.
    - Valida acesso do usuário ao projeto original
    - Cria registro no banco
    - Dispara job em background para executar script de duplicação
    """
    original = validate_project_id(body.original_name)
    new_name = validate_project_id(body.new_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, original)
            await ensure_project_member_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
            )

            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM projects WHERE name = $1)",
                new_name
            )
            if exists:
                raise HTTPException(409, "Nome de projeto já existe")

            project_id = uuid.uuid4()
            await conn.execute(
                """
                INSERT INTO projects(id, tenant_uuid, name, owner_id,
                                     resource_profile)
                SELECT $1, $1, $2, $3, resource_profile
                FROM projects WHERE id = $4
                """,
                project_id,
                new_name,
                auth_user["db_user_id"],
                project_row["id"],
            )

            await conn.execute("""
                INSERT INTO project_members(project_id, user_id, role)
                VALUES($1, $2, 'admin')
            """, project_id, auth_user["db_user_id"])

            job_id = await _create_project_job(
                pool,
                new_name,
                auth_user["db_user_id"],
                action="duplicate",
                payload={
                    "original_name": original,
                    "new_name": new_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "copy_data": body.copy_data,
                    "tenant_uuid": str(project_id),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )

    position = await _enqueue_project_action(
        new_name,
        job_id,
        lambda: _duplicate_and_store_keys(
            job_id,
            original,
            new_name,
            auth_user["db_user_id"],
            body.copy_data,
        ),
    )

    message = (
        "Duplicação enfileirada."
        if position == 0
        else f"Duplicação enfileirada. Existem {position} ações antes desta na fila para {new_name}."
    )
    return await _serialize_queued_job(pool, job_id, position, message)


async def _duplicate_and_store_keys(
    job_id: str,
    original_name: str,
    new_name: str,
    owner_id: uuid.UUID,
    copy_data: bool,
):
    pool = await get_pool()
    project_uuid = await _get_job_project_uuid(pool, job_id)
    await _set_job_status(
        job_id,
        "running",
        message="Duplicando infraestrutura e banco...",
        progress=5,
        current_step="duplicate_infrastructure",
        total_steps=3,
    )

    try:
        copy_mode = "with-data" if copy_data else "schema-only"
        resolved_project_uuid, tenant_uuid = await _get_job_project_identity(
            pool, job_id
        )
        if project_uuid != resolved_project_uuid:
            raise ProjectIdentityError("projects.id do job mudou durante duplicacao")

        resource_profile = await pool.fetchval(
            "SELECT resource_profile FROM projects WHERE id = $1",
            project_uuid,
        )

        gateway_token = secrets.token_hex(32)
        async with pool.acquire() as conn:
            async with conn.transaction():
                await bootstrap_project_opaque_keys(
                    conn,
                    project_id=project_uuid,
                    created_by=owner_id,
                    gateway_token=gateway_token,
                )

        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="duplicate_project",
            project=new_name,
            project_uuid=project_uuid,
            requested_by=owner_id,
            args={
                "original_name": original_name,
                "copy_mode": copy_mode,
                "tenant_uuid": str(tenant_uuid),
                "gateway_token": gateway_token,
                "resource_profile": resource_profile,
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            await _fail_job_from_command(
                job_id,
                record,
                default_error="duplicate_failed",
                message_prefix="Falha ao duplicar infraestrutura",
            )
            await rollback_project_from_db(pool, new_name, project_uuid)
            return

        await _set_job_status(
            job_id,
            "running",
            message="Lendo chaves do projeto duplicado...",
            progress=70,
            current_step="extract_keys",
        )
        keys = _read_project_secret_keys(new_name)
        env_tenant_uuid = parse_tenant_uuid(keys["tenant_uuid"])
        if env_tenant_uuid != tenant_uuid:
            await _set_job_status(
                job_id,
                "failed",
                message="PROJECT_UUID gerado diverge da identidade persistida",
                error_code="tenant_uuid_mismatch",
            )
            await rollback_project_from_db(pool, new_name, project_uuid)
            return
        if not all(
            keys[name]
            for name in (
                "anon_key", "service_role", "config_token", "gateway_token"
            )
        ):
            await _set_job_status(
                job_id,
                "failed",
                message="Chaves obrigatórias ausentes no projeto duplicado",
                error_code="missing_keys",
            )
            print("Missing tokens")
            await rollback_project_from_db(pool, new_name, project_uuid)
            return
        schedule = project_key_schedule(
            keys["anon_key"],
            keys["service_role"],
            lead_days=AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
        )

        await _set_job_status(
            job_id,
            "running",
            message="Persistindo chaves criptografadas...",
            progress=90,
            current_step="store_keys",
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                project_id = await conn.fetchval(
                    """
                    SELECT id FROM projects
                    WHERE name = $1 AND owner_id = $2 AND id = $3
                    FOR UPDATE
                    """,
                    new_name,
                    owner_id,
                    project_uuid,
                )
                if project_id is None:
                    raise RuntimeError(
                        "Projeto duplicado não encontrado ao persistir chaves"
                    )
                await store_project_secrets(
                    conn,
                    project_id=project_id,
                    anon_key=keys["anon_key"],
                    service_role=keys["service_role"],
                    config_token=keys["config_token"],
                )
                await conn.execute(
                    "UPDATE projects SET key_expires_at = $2 WHERE id = $1",
                    project_id,
                    schedule.expires_at,
                )

        await _set_job_status(
            job_id,
            "done",
            message="Projeto duplicado com sucesso.",
            current_step="completed",
        )

    except ProjectIdentityError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="A identidade persistida do tenant esta inconsistente.",
            error_code="tenant_identity_error",
        )
        print(f"[project_identity] duplicate job {job_id}: {exc}")
        await rollback_project_from_db(pool, new_name, project_uuid)
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="O host-agent não conseguiu duplicar o projeto.",
            error_code=exc.error_code,
        )
        await rollback_project_from_db(pool, new_name, project_uuid)
    except Exception as e:
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada ao duplicar o projeto.",
            error_code="unexpected_duplicate_error",
        )
        print(f"Worker error: {e}")
        await rollback_project_from_db(pool, new_name, project_uuid)


async def _delete_project_impl(
    project_name: str,
    pool,
    *,
    current_job_id: str | None = None,
) -> dict:
    errors: list[str] = []
    db_name = f"_supabase_{project_name}"

    job_requested_by: uuid.UUID | None = None
    job_project_uuid: uuid.UUID | None = None
    job_tenant_uuid: uuid.UUID | None = None
    if current_job_id:
        job_row = await pool.fetchrow(
            "SELECT created_by, project_uuid, payload FROM jobs WHERE job_id = $1",
            uuid.UUID(str(current_job_id)),
        )
        if job_row:
            job_requested_by = job_row["created_by"]
            job_project_uuid = job_row["project_uuid"]
            payload = job_row["payload"] or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            job_tenant_uuid = parse_tenant_uuid(payload.get("tenant_uuid"))

    async def report(progress: int, step: str, message: str) -> None:
        if current_job_id:
            await _set_job_status(
                current_job_id,
                "running",
                message=message,
                progress=progress,
                current_step=step,
                total_steps=9,
            )

    async def agent_step(
        command: str,
        project_uuid: uuid.UUID | None,
        args: dict[str, Any] | None = None,
    ):
        if current_job_id:
            return await run_host_agent_command_for_job(
                pool,
                job_id=current_job_id,
                command=command,
                project=project_name,
                project_uuid=project_uuid,
                requested_by=job_requested_by,
                args=args,
                reuse_terminal=True,
            )
        return await run_host_agent_command(
            pool,
            command=command,
            project=project_name,
            project_uuid=project_uuid,
            requested_by=job_requested_by,
            args=args,
        )

    await report(5, "load_project_state", "Carregando estado do projeto...")
    project_env = load_project_environment(PROJECTS_ROOT, project_name)
    identity_row = await pool.fetchrow(
        "SELECT id, tenant_uuid FROM projects WHERE name = $1",
        project_name,
    )
    persisted_tenant_uuid = (
        parse_tenant_uuid(identity_row["tenant_uuid"]) if identity_row else None
    )
    env_tenant_uuid = parse_tenant_uuid(project_env.get("PROJECT_UUID"))
    if persisted_tenant_uuid is None:
        raise ProjectIdentityError(
            f"Projeto {project_name} precisa de tenant UUID persistido antes do delete"
        )
    if env_tenant_uuid is None:
        raise ProjectIdentityError(
            f"Projeto {project_name} não possui PROJECT_UUID válido no ambiente"
        )
    if job_tenant_uuid is None:
        raise ProjectIdentityError(
            f"Job de exclusão de {project_name} não possui tenant UUID válido"
        )
    if len({persisted_tenant_uuid, env_tenant_uuid, job_tenant_uuid}) != 1:
        raise ProjectIdentityError(
            f"Projeto {project_name} possui tenant UUID divergente no delete"
        )
    tenant_uuid = persisted_tenant_uuid
    tenant_external_id = str(tenant_uuid)
    print(f"Deletando projeto com tenant UUID: {tenant_uuid}")

    await report(15, "remove_containers", "Removendo containers do projeto...")
    containers_record = await agent_step("delete_project_containers", job_project_uuid)
    if containers_record["status"] != "done":
        container_errors = command_result(containers_record).get("errors") or [
            containers_record["message"]
            or containers_record["error_code"]
            or "falha ao remover containers"
        ]
        errors.append("containers: " + "; ".join(str(item) for item in container_errors))

    await report(25, "remove_storage_tenant", "Removendo tenant e objetos do Storage...")
    storage_record = await agent_step(
        "delete_project_storage",
        job_project_uuid,
        {"tenant_uuid": str(tenant_uuid)},
    )
    if storage_record["status"] != "done":
        detail = (
            (storage_record["stderr_tail"] or "").strip()
            or (storage_record["message"] or "").strip()
            or storage_record["error_code"]
            or "falha ao remover tenant Storage"
        )
        errors.append(f"storage: {detail}")

    await report(35, "remove_tenants", "Removendo tenants globais...")
    try:
        supavisor_token = build_global_delete_token(tenant_external_id)
        await terminate_supavisor_pools(project_name, supavisor_token)
        await delete_realtime_tenant(
            tenant_external_id,
            build_realtime_delete_token(project_env),
        )
        await delete_supavisor_tenant(project_name, supavisor_token)
        await asyncio.sleep(1)
    except Exception as exc:
        errors.append(f"tenants globais: {exc}")

    await report(55, "clean_global_metadata", "Limpando metadata global...")
    try:
        async with global_admin_connection() as conn:
            deleted_ext = await conn.execute(
                'DELETE FROM _realtime.extensions WHERE tenant_external_id = $1',
                tenant_external_id,
            )
            deleted_tenant = await conn.execute(
                'DELETE FROM _realtime.tenants WHERE external_id = $1',
                tenant_external_id,
            )
            deleted_supavisor_users = await conn.execute(
                'DELETE FROM _supavisor.users WHERE tenant_external_id = $1',
                project_name,
            )
            deleted_supavisor_tenant = await conn.execute(
                'DELETE FROM _supavisor.tenants WHERE external_id = $1',
                project_name,
            )

            print(
                "Delete cleanup: "
                f"realtime_extensions={deleted_ext}, "
                f"realtime_tenants={deleted_tenant}, "
                f"supavisor_users={deleted_supavisor_users}, "
                f"supavisor_tenants={deleted_supavisor_tenant}"
            )
    except Exception as exc:
        errors.append(f"metadata global: {exc}")

    await report(70, "drop_database", "Removendo slots e database...")
    try:
        async with global_admin_connection() as conn:
            await drain_database_connections(conn, db_name)

            slot_errors = await drop_supabase_replication_slots(conn, project_name)
            errors.extend(f"slots: {item}" for item in slot_errors)
            if not slot_errors:
                await drop_database_force(conn, db_name)
    except Exception as exc:
        errors.append(f"database: {exc}")

    await report(82, "remove_files", "Removendo arquivos do projeto...")
    files_record = await agent_step(
        "delete_project_files",
        None,
        {"tenant_uuid": str(tenant_uuid)},
    )
    if files_record["status"] != "done":
        detail = (
            (files_record["stderr_tail"] or "").strip()
            or (files_record["message"] or "").strip()
            or files_record["error_code"]
            or "erro desconhecido"
        )
        errors.append(f"arquivos: {detail}")

    if errors:
        raise ProjectDeletionError(
            "Exclusao parcial de "
            f"{project_name}; etapas com falha: {'; '.join(errors)}. "
            "O registro permaneceu no control plane para nova tentativa."
        )

    await report(
        90,
        "remove_control_plane",
        "Removendo registros do control plane...",
    )
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1",
            project_name,
        )
        if project_id is None:
            raise ProjectDeletionError(
                f"Projeto {project_name} não encontrado para limpeza final"
            )
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM project_members WHERE project_id = $1",
                project_id,
            )
            await conn.execute("DELETE FROM projects WHERE id = $1", project_id)

    await report(96, "verify_cleanup", "Verificando limpeza final...")
    async with global_admin_connection() as conn:
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name,
        )
        if db_exists:
            errors.append(f"Banco {db_name} ainda existe")
        supavisor_tenant_exists = await conn.fetchval(
            "SELECT 1 FROM _supavisor.tenants WHERE external_id = $1",
            project_name,
        )
        supavisor_user_exists = await conn.fetchval(
            "SELECT 1 FROM _supavisor.users WHERE tenant_external_id = $1",
            project_name,
        )
        if supavisor_tenant_exists or supavisor_user_exists:
            errors.append(
                f"Metadata do tenant {project_name} ainda existe no Supavisor"
            )

    if errors:
        raise ProjectDeletionError("; ".join(errors))

    return {
        "project": project_name,
        "status": "success",
        "message": "Projeto excluído com sucesso.",
        "errors": [],
        "success": True,
    }


async def _delete_project_background(job_id: str, project_name: str) -> None:
    await _set_job_status(
        job_id,
        "running",
        message="Excluindo projeto...",
        progress=1,
        current_step="starting",
        total_steps=8,
    )

    try:
        pool = await get_pool()
        result = await _delete_project_impl(
            project_name,
            pool,
            current_job_id=job_id,
        )

        message = result["message"]
        if result["errors"]:
            message = message + "\n" + "\n".join(result["errors"])

        await _set_job_status(
            job_id,
            "done",
            message=message,
            current_step="completed",
        )
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="O host-agent não conseguiu excluir o projeto.",
            error_code=exc.error_code,
        )
        print(f"[delete_project] {project_name}: host-agent: {exc}")
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada ao excluir o projeto.",
            error_code="delete_failed",
        )
        print(f"[delete_project] {project_name}: background task failed: {exc}")

@router.delete("/api/projects/{project_name}")
async def delete_project(
    project_name: str,
    request: Request,
    x_step_up_token: str | None = Header(None, alias="X-Step-Up-Token"),
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "Admin required")

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await conn.fetchrow(
                """
                SELECT id, tenant_uuid
                FROM projects
                WHERE name = $1
                FOR UPDATE
                """,
                project_name,
            )
            if not project_row:
                raise HTTPException(404, "Project not found")
            await consume_step_up_grant(
                conn,
                token=x_step_up_token,
                secret=NGINX_HMAC_SECRET,
                max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
                auth_user=auth_user,
                action="delete_project",
                project_id=project_row["id"],
                project_ref=project_name,
                resource_id=project_name,
            )

    project_id = project_row["id"]
    tenant_uuid = parse_tenant_uuid(project_row["tenant_uuid"])
    if tenant_uuid is None:
        raise HTTPException(
            409,
            "Project tenant UUID is missing; run the canonical migration first",
        )

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Exclusão enfileirada.",
        action="delete",
        payload={
            "project_name": project_name,
            "tenant_uuid": str(tenant_uuid),
        },
        total_steps=8,
        project_uuid=project_id,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _delete_project_background(job_id, project_name),
    )
    message = (
        "Exclusão enfileirada. Será executada quando não houver outras ações "
        "em andamento para este projeto."
        if position == 0
        else f"Exclusão enfileirada. Existem {position} ações antes desta na "
        f"fila para {project_name}."
    )
    return JSONResponse(
        status_code=202,
        content=await _serialize_queued_job(pool, job_id, position, message),
    )
