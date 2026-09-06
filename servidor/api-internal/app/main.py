import os
import secrets
import uuid
import pathlib
import asyncpg
import hmac
import hashlib
import time
import datetime as dt
import asyncio, json, re
import urllib.parse
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from app.schemas import NewProject, DuplicateProject, UserSyncPayload, AddMember, TransferBody, UpdateSettings, RecreateServices, ProjectNoteCreate, ProjectTagAssign, ProjectHintCreate, ProjectHintStatusUpdate, ProjectThreadMessageCreate, ProjectRenameRequest, ProjectDisplayNameUpdate, ProjectNotificationRead, RestorePointCreate, AutomaticKeyRotationUpdate
from typing import Any, List, Dict
from app.pg_meta_crypto import encrypt_postgres_meta_uri
from app.project_secret_service import (
    decrypt_project_secret,
    store_project_secrets,
)
from app.jobs import (
    IDEMPOTENT_ACTIONS,
    action_queue,
    configure_jobs,
    create_project_job as _create_project_job,
    enqueue_project_action as _enqueue_project_action,
    serialize_job,
    set_job_status as _set_job_status,
)
from app.runtime_config import (
    ANALYTICS_INTERNAL_URL, BASE_DIR, DB_DSN,
    AUTOMATIC_KEY_ROTATION_LEAD_DAYS,
    KEY_EXPIRY_WARNING_DAYS, NGINX_HMAC_SECRET, PG_META_CRYPTO_KEY,
    LOGFLARE_PRIVATE_ACCESS_TOKEN, PG_META_INTERNAL_URL,
    USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    service_key_transport_fernet,
)
from app.host_agent import (
    HostAgentError,
    HostAgentOffline,
    command_result,
    fetch_project_containers,
    run_command as run_host_agent_command,
    run_command_for_job as run_host_agent_command_for_job,
    worker_alive as host_agent_alive,
)
from app.validation import (
    normalize_groups, parse_uuid_value, validate_project_id,
    validate_service_name,
)
from app.opaque_key_service import (
    bootstrap_project_opaque_keys,
    cancel_project_automatic_pending_keys,
)
from app.step_up_auth import consume_step_up_grant
from app.control_plane_service import (
    audit_studio_action,
    create_studio_notification,
    sync_user_record,
)
from app.project_settings import (
    SETTINGS_WHITELIST,
    _get_affected_services,
    _normalize_settings_updates,
    _read_env_whitelisted,
    _write_env_whitelisted,
    get_project_file_size_limit,
    resolve_resource_limits,
    split_resource_directives,
)
from app.project_env_secrets import (
    PROJECTS_ROOT,
    read_project_secret_keys as _read_project_secret_keys,
)
from app.service_key_cache import invalidate_service_key_cache
from app.snippets_migration import rename_project_snippets
from app.key_rotation import KeyRotationMetadataError, project_key_schedule
from app.automatic_key_rotation import (
    block_automatic_key_rotation,
    scan_automatic_key_rotations,
    start_automatic_key_rotation,
    stop_automatic_key_rotation,
)
from app.automatic_opaque_key_rotation import (
    scan_automatic_opaque_key_rotations,
    start_automatic_opaque_key_rotation,
    stop_automatic_opaque_key_rotation,
)
from app.project_telemetry import (
    TelemetryValidationError,
    fetch_project_user_telemetry,
    resolve_telemetry_period,
)
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
from app.routers.lifecycle import get_project_status
from app.project_identity import (
    ProjectIdentityError,
    get_job_project_identity as _get_job_project_identity,
    parse_tenant_uuid,
    reconcile_project_tenant_uuids,
)
from app.database import close_pool, get_pool, initialize_pool
from app.schema_migrations import verify_control_plane_schema
from app.dependencies import (
    audit_project_member_change,
    ensure_project_admin_access,
    ensure_project_member_access,
    ensure_project_owner_access,
    get_project_member_row,
    get_project_role,
    get_project_row,
    get_user_record_by_identifier,
    require_synced_user_record,
    resolve_authenticated_user,
    resolve_user_claims_from_hmac_token,
    resolve_user_id_from_hmac_token,
    upsert_project_member,
)
from app.routers.collaboration import router as collaboration_router
from app.routers.internal import router as internal_router
from app.routers.lifecycle import router as lifecycle_router
from app.routers.health import router as health_router
from app.meta_connections import (
    get_project_meta_connection_string,
    get_project_reader_connection_string,
)
from app.routers.opaque_keys import router as opaque_keys_router
from app.routers.platform_auth import router as platform_auth_router
from app.version import API_VERSION
from app.project_backgrounds import (
    _create_restore_point_background,
    _delete_project_background,
    _delete_restore_point_background,
    _duplicate_and_store_keys,
    _provision_and_store_keys,
    _recreate_project_services_background,
    _rename_project_background,
    _restart_project_containers_background,
    _restore_project_background,
    _rotate_project_key_background,
    _start_project_containers_background,
    _stop_project_containers_background,
)
configure_jobs(get_pool)


app = FastAPI(
    title="Supabase Multitenant Projects API",
    version=API_VERSION,
    description="Control plane for isolated Supabase projects on shared infrastructure.",
    license_info={"name": "Apache-2.0", "identifier": "Apache-2.0"},
    generate_unique_id_function=lambda route: (
        f"{re.sub(r'\W', '_', f'{route.name}{route.path_format}')}"
        f"_{'_'.join(sorted(method.lower() for method in route.methods or ()))}"
    ),
)
app.include_router(health_router)
app.include_router(collaboration_router)
app.include_router(internal_router)
app.include_router(lifecycle_router)
app.include_router(opaque_keys_router)
app.include_router(platform_auth_router)

# ``create`` nao e repetivel, mas e retomavel: o runner se religa ao mesmo
# host_agent_command duravel com ``reuse_terminal=True`` e nunca dispara um
# segundo script para o mesmo job.
RECOVERABLE_RUNNING_ACTIONS = IDEMPOTENT_ACTIONS | {"create", "rotate_key"}


async def _build_recovery_runner(row: asyncpg.Record):
    action = row["action"]
    job_id = str(row["job_id"])
    project_name = row["project"]
    payload = row["payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    owner_id = row["owner_id"]

    if action == "create":
        return lambda: _provision_and_store_keys(job_id, project_name, owner_id)
    if action == "duplicate":
        original_name = validate_project_id(str(payload.get("original_name") or ""))
        copy_data = bool(payload.get("copy_data"))
        return lambda: _duplicate_and_store_keys(
            job_id,
            original_name,
            project_name,
            owner_id,
            copy_data,
        )
    if action == "delete":
        return lambda: _delete_project_background(job_id, project_name)
    if action == "rotate_key":
        raw_trigger = payload.get("trigger")
        if raw_trigger not in {"manual", "automatic"}:
            return None
        trigger = str(raw_trigger)
        actor_user_id = owner_id if trigger == "manual" else None
        return lambda: _rotate_project_key_background(
            job_id,
            project_name,
            actor_user_id,
            trigger=trigger,
        )
    if action == "rename":
        pool = await get_pool()
        async with pool.acquire() as conn:
            history = await conn.fetchrow(
                """
                SELECT id, project_id, actor_user_id, old_name, new_name
                FROM project_name_history
                WHERE job_id = $1
                """,
                row["job_id"],
            )
        if not history:
            return None
        actor_user_id = history["actor_user_id"] or owner_id
        return lambda: _rename_project_background(
            job_id,
            history["project_id"],
            history["id"],
            history["old_name"],
            history["new_name"],
            actor_user_id,
        )
    if action == "backup":
        point_id = parse_uuid_value(str(payload.get("restore_point_id") or ""))
        if point_id is None:
            return None
        actor = parse_uuid_value(str(payload.get("actor_user_id") or "")) or owner_id
        return lambda: _create_restore_point_background(
            job_id,
            project_name,
            actor,
            point_id,
        )
    if action == "restore":
        point_id = parse_uuid_value(str(payload.get("restore_point_id") or ""))
        safety_id = parse_uuid_value(str(payload.get("safety_point_id") or ""))
        if point_id is None or safety_id is None:
            return None
        actor = parse_uuid_value(str(payload.get("actor_user_id") or "")) or owner_id
        return lambda: _restore_project_background(
            job_id,
            project_name,
            actor,
            point_id,
            safety_id,
        )
    if action == "delete_restore_point":
        point_id = parse_uuid_value(str(payload.get("restore_point_id") or ""))
        if point_id is None:
            return None
        actor = parse_uuid_value(str(payload.get("actor_user_id") or "")) or owner_id
        return lambda: _delete_restore_point_background(
            job_id,
            project_name,
            actor,
            point_id,
        )
    if action in {"start", "stop", "restart"}:
        async def run_container_action() -> None:
            if action == "start":
                await _start_project_containers_background(
                    job_id,
                    project_name,
                    owner_id,
                )
            elif action == "stop":
                await _stop_project_containers_background(
                    job_id,
                    project_name,
                    owner_id,
                )
            else:
                await _restart_project_containers_background(
                    job_id,
                    project_name,
                    owner_id,
                )

        return run_container_action
    if action == "recreate_services":
        services = payload.get("services") or []
        if not isinstance(services, list) or not services:
            return None
        normalized_services = [validate_service_name(str(item)) for item in services]
        return lambda: _recreate_project_services_background(
            job_id,
            project_name,
            normalized_services,
        )
    return None


async def _recover_pending_jobs() -> None:
    """Retoma jobs seguros e preserva o ponto de parada dos demais."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                job_id, project, owner_id, status, message, action, payload,
                progress, current_step, total_steps, project_uuid, created_by,
                is_idempotent, retryable, retry_of, attempt
            FROM jobs
            WHERE status IN ('queued', 'running')
            ORDER BY updated_at ASC
            """
        )

    if not rows:
        return

    print(
        f"[recovery] {len(rows)} job(s) pendentes do startup anterior"
    )
    for r in rows:
        job_id = str(r["job_id"])
        project = r["project"]
        old_status = r["status"]
        action = r["action"]
        # Rename, backup, restore e delete de ponto sao retomaveis: o
        # runner religa no comando que o host-agent continua executando
        # (ou reusa o resultado terminal), em vez de reexecutar o script.
        can_resume = (
            old_status == "queued"
            or action in RECOVERABLE_RUNNING_ACTIONS
            or action in {"rename", "backup", "restore", "delete_restore_point"}
        )
        try:
            runner = await _build_recovery_runner(r) if can_resume and action else None
            if runner is not None:
                message = (
                    f"Job retomado após reinício da API em "
                    f"{r['current_step'] or 'queued'} ({r['progress'] or 0}%)."
                )
                await _set_job_status(
                    job_id,
                    "queued",
                    message=message,
                    current_step=r["current_step"] or "queued",
                )
                await _enqueue_project_action(project, job_id, runner)
                async with pool.acquire() as conn:
                    project_id = await conn.fetchval(
                        "SELECT id FROM projects WHERE name = $1",
                        project,
                    )
                    if project_id:
                        await audit_studio_action(
                            conn,
                            project_id=project_id,
                            actor_user_id=None,
                            action="project_recovery_resumed",
                            target_type="job",
                            target_id=job_id,
                            old_value={
                                "status": old_status,
                                "current_step": r["current_step"],
                                "progress": r["progress"],
                            },
                            new_value={"status": "queued", "action": action},
                        )
                print(
                    f"[recovery] job {job_id} ({project}, {action}) retomado"
                )
                continue

            message = (
                "API reiniciada durante operação não idempotente. "
                f"Ação={action or 'desconhecida'}, etapa="
                f"{r['current_step'] or 'desconhecida'}, progresso="
                f"{r['progress'] or 0}%. Revisão manual obrigatória."
            )
            await _set_job_status(
                job_id,
                "failed",
                message=message,
                error_code="recovery_manual_review_required",
            )
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE project_name_history
                    SET status = 'failed',
                        error = $1,
                        updated_at = now(),
                        completed_at = now()
                    WHERE job_id = $2
                      AND status IN ('queued', 'running')
                    """,
                    message,
                    r["job_id"],
                )
                await conn.execute(
                    """
                    UPDATE project_restore_points
                    SET status = 'failed', error = $1, updated_at = now()
                    WHERE job_id = $2 AND status IN ('creating', 'deleting')
                    """,
                    message,
                    r["job_id"],
                )
                await conn.execute(
                    """
                    UPDATE project_restore_points
                    SET status = 'ready', error = $1, updated_at = now()
                    WHERE job_id = $2 AND status = 'restoring'
                    """,
                    message,
                    r["job_id"],
                )
                project_row = await conn.fetchrow(
                    "SELECT id FROM projects WHERE name = $1",
                    project,
                )
                if project_row:
                    await audit_studio_action(
                        conn,
                        project_id=project_row["id"],
                        actor_user_id=None,
                        action="project_recovery_failed",
                        target_type="job",
                        target_id=job_id,
                        old_value={"status": old_status},
                        new_value={
                            "status": "failed",
                            "reason": "api_restart",
                            "action": action,
                            "current_step": r["current_step"],
                            "progress": r["progress"],
                        },
                    )
            print(
                f"[recovery] job {job_id} ({project}, {old_status}) "
                "marcado como failed"
            )
        except Exception as exc:  # noqa: BLE001
            try:
                await _set_job_status(
                    job_id,
                    "failed",
                    message="Falha interna ao reconstruir job após reinício.",
                    error_code="recovery_dispatch_failed",
                )
            except Exception:
                pass
            print(
                f"[recovery] falha ao reconstruir job {job_id}: {exc}"
            )


async def _scan_automatic_key_rotations() -> int:
    return await scan_automatic_key_rotations(
        enqueue_action=_enqueue_project_action,
        rotation_runner=_rotate_project_key_background,
    )


@app.on_event("startup")
async def startup():
    if not (os.getenv("META_ADMIN_DSN") or "").strip():
        raise RuntimeError(
            "META_ADMIN_DSN ausente; a Projects API nao expoe credenciais "
            "administrativas globais para o Postgres-Meta"
        )
    reader_password = (os.getenv("PLATFORM_READER_DB_PASSWORD") or "").strip()
    if not reader_password or reader_password == "pass":
        raise RuntimeError(
            "PLATFORM_READER_DB_PASSWORD ausente ou placeholder no ambiente da "
            "Projects API; gere a senha e provisione a role platform_reader "
            "(scripts de lifecycle) antes de iniciar"
        )
    pool = await initialize_pool(DB_DSN)
    schema = await verify_control_plane_schema(pool)
    print(
        "[migrations] control plane na versao "
        f"{schema.current_version} "
        f"({len(schema.applied_versions)} aplicadas)"
    )
    if schema.unknown_versions:
        print(
            "[migrations] banco a frente desta imagem: "
            + ", ".join(schema.unknown_versions)
        )
    identity_result = await reconcile_project_tenant_uuids(pool, PROJECTS_ROOT)
    print(
        "[identity] tenant UUIDs: "
        f"migrados={identity_result.migrated}, "
        f"persistidos={identity_result.already_persisted}, "
        f"pendentes={len(identity_result.unresolved)}"
    )
    if identity_result.unresolved:
        print(
            "[identity] projetos sem tenant UUID verificavel: "
            + ", ".join(identity_result.unresolved)
        )
    print("✅ Database pool initialized")
    await _recover_pending_jobs()
    await start_automatic_key_rotation(
        enqueue_action=_enqueue_project_action,
        rotation_runner=_rotate_project_key_background,
    )
    await start_automatic_opaque_key_rotation()

@app.on_event("shutdown")
async def shutdown():
    await stop_automatic_opaque_key_rotation()
    await stop_automatic_key_rotation()
    await action_queue.shutdown()
    await close_pool()
    print("✅ Database pool closed")


# Rota extraída para app.routers.internal.


# Rota extraída para app.routers.internal.


# Dependências de autenticação e autorização: app.dependencies.

# Rota extraída para app.routers.internal.


# Endpoints de colaboração: app.routers.collaboration.


_RENAME_HISTORY_ACTIONS = (
    "project_rename_started",
    "project_rename_succeeded",
    "project_rename_failed",
    "project_rename_rolled_back",
    "project_display_name_changed",
)


RESTORE_POINT_LIMIT = 15


# Endpoints de tags: app.routers.collaboration.


# Rota extraída para app.routers.internal.


# Rota extraída para app.routers.internal.


async def get_project_containers(project: str) -> list[dict]:
    """Snapshot dos containers mantido pelo host-agent no control plane."""
    pool = await get_pool()
    return await fetch_project_containers(pool, project)


def _extract_project_admin_apikey(request: Request) -> str:
    apikey = (request.headers.get("apikey") or "").strip()
    if apikey:
        return apikey

    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""

# Estado de containers: app.routers.lifecycle.


# Logs de containers: app.routers.lifecycle.

async def get_project_conn(project_ref: str):
    dsn = urllib.parse.urlparse(DB_DSN)
    db_name = f"_supabase_{project_ref}"
    # Identidade de leitura dedicada por tenant (GRANT SELECT em auth.*),
    # provisionada pelos scripts de lifecycle. Falha fechado: sem a senha
    # configurada, a telemetria nao existe — nunca cai em credencial global.
    reader_password = (os.getenv("PLATFORM_READER_DB_PASSWORD") or "").strip()
    if not reader_password or reader_password == "pass":
        raise HTTPException(
            503,
            "PLATFORM_READER_DB_PASSWORD ausente ou placeholder; "
            "provisione a role platform_reader antes de usar a telemetria",
        )
    return await asyncpg.connect(
        host=dsn.hostname,
        port=dsn.port,
        user="platform_reader",
        password=reader_password,
        database=db_name
    )


AI_TOOL_MAX_ROWS = 1000
AI_TOOL_TIMEOUT_MS = 30000


ALLOWED_RECREATE_SERVICES = {"auth", "rest", "storage", "nginx", "meta"}
