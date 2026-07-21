import os
import uuid
import pathlib
import asyncpg
import hmac
import base64
import hashlib
import time
import datetime as dt
import asyncio, json, re
import urllib.parse
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from app.schemas import NewProject, DuplicateProject, UserSyncPayload, AddMember, TransferBody, UpdateSettings, RecreateServices, ProjectNoteCreate, ProjectTagAssign, ProjectHintCreate, ProjectHintStatusUpdate, ProjectThreadMessageCreate, ProjectRenameRequest, ProjectDisplayNameUpdate, ProjectNotificationRead, RestorePointCreate
from typing import Any, List, Dict
from dotenv import dotenv_values
from app.pg_meta_crypto import encrypt_postgres_meta_uri
from app.project_secret_service import (
    decrypt_project_secret,
    ensure_project_secrets_schema,
    store_project_secrets,
)
from app.jobs import (
    IDEMPOTENT_ACTIONS,
    action_queue,
    configure_jobs,
    create_project_job as _create_project_job,
    create_retry_job,
    ensure_jobs_schema,
    serialize_job,
    set_job_status as _set_job_status,
)
from app.runtime_config import (
    ANALYTICS_INTERNAL_URL, BASE_DIR, DB_DSN,
    KEY_EXPIRY_WARNING_DAYS, NGINX_HMAC_SECRET, NGINX_SHARED_TOKEN, PG_META_CRYPTO_KEY,
    LOGFLARE_PRIVATE_ACCESS_TOKEN, PG_META_INTERNAL_URL, REALTIME_INTERNAL_URL,
    SUPAVISOR_INTERNAL_URL, USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    service_key_transport_fernet,
)
from app.host_agent import (
    HostAgentError,
    HostAgentOffline,
    command_result,
    ensure_host_agent_schema,
    fetch_project_containers,
    run_command as run_host_agent_command,
    run_command_for_job as run_host_agent_command_for_job,
    worker_alive as host_agent_alive,
)
from app.validation import (
    normalize_groups, parse_uuid_value, validate_project_id,
    validate_service_name,
)
from app.database_schema import (
    ensure_collaboration_schema,
    ensure_identity_schema,
    ensure_restore_points_schema,
)
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
)
from app.service_key_cache import invalidate_service_key_cache
from app.snippets_migration import rename_project_snippets
from app.jwt_metadata import get_unverified_jwt_expiry
from app.project_telemetry import (
    TelemetryValidationError,
    fetch_project_user_telemetry,
    resolve_telemetry_period,
)
from app.project_identity import (
    ProjectIdentityError,
    get_job_project_identity as _get_job_project_identity,
    parse_tenant_uuid,
    reconcile_project_tenant_uuids,
)
from app.database import close_pool, get_pool, initialize_pool
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
configure_jobs(get_pool)

PROJECTS_ROOT = pathlib.Path("/docker/projects").resolve()


async def _enqueue_project_action(
    project_name: str,
    job_id: str,
    runner,
) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1",
            project_name,
        )
    if project_id is None:
        raise HTTPException(404, f"Projeto '{project_name}' nao encontrado")
    try:
        return await action_queue.submit(project_name, project_id, job_id, runner)
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="Nao foi possivel enfileirar a operacao.",
            current_step="enqueue_failed",
            error_code="queue_submit_failed",
        )
        raise RuntimeError("falha ao enfileirar operacao do projeto") from exc

async def rollback_project_from_db(
    pool,
    project_name: str,
    project_uuid: uuid.UUID | None = None,
) -> bool:
    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM projects
                WHERE name = $1 AND ($2::uuid IS NULL OR id = $2)
                """,
                project_name,
                project_uuid,
            )
        removed = result.endswith("1")
        if removed:
            print(f"Rollback: Projeto '{project_name}' removido do banco")
        else:
            print(
                f"Rollback: registro de '{project_name}' já não existia "
                "ou pertence a outra tentativa"
            )
        return removed
    except Exception as e:
        print(f"Erro no rollback do banco: {e}")
        return False


async def _get_job_project_uuid(pool, job_id: str) -> uuid.UUID | None:
    return await pool.fetchval(
        "SELECT project_uuid FROM jobs WHERE job_id = $1", uuid.UUID(str(job_id))
    )


async def _failed_create_recovery_context(
    pool,
    *,
    job_id: str,
    project_name: str,
    created_by: uuid.UUID,
) -> tuple[bool, list[str]]:
    """Localiza resíduos atribuíveis a criações falhas recentes do usuário.

    O opt-in de limpeza nunca é inferido apenas pela existência de um banco
    físico. Ele exige histórico durável de um job ``create`` falho para o
    mesmo nome e autor, reduzindo o risco de apagar um banco legítimo que
    tenha perdido apenas o registro do control plane.
    """
    rows = await pool.fetch(
        """
        SELECT hc.args->>'tenant_uuid' AS tenant_uuid
        FROM jobs j
        JOIN host_agent_commands hc ON hc.job_id = j.job_id
        WHERE j.job_id <> $1
          AND j.project = $2
          AND j.created_by = $3
          AND j.action = 'create'
          AND j.status = 'failed'
          AND j.finished_at >= now() - interval '7 days'
          AND hc.command = 'create_project'
          AND hc.status IN ('done', 'failed', 'cancelled')
        ORDER BY hc.created_at DESC
        LIMIT 20
        """,
        uuid.UUID(str(job_id)),
        project_name,
        created_by,
    )
    tenant_uuids: list[str] = []
    for row in rows:
        candidate = str(row["tenant_uuid"] or "").lower()
        if parse_uuid_value(candidate) is not None and candidate not in tenant_uuids:
            tenant_uuids.append(candidate)
    return bool(rows), tenant_uuids


def _job_progress_mirror(job_id: str):
    """Espelha progresso do comando do host-agent no job correspondente."""

    async def on_progress(command_row) -> None:
        try:
            progress = command_row["progress"]
            await _set_job_status(
                job_id,
                "running",
                message=command_row["message"],
                progress=max(1, min(95, progress)) if progress else None,
                current_step=command_row["current_step"],
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[host_agent] falha ao espelhar progresso do job {job_id}: {exc}")

    return on_progress


async def _fail_job_from_command(
    job_id: str,
    command_row,
    *,
    default_error: str,
    message_prefix: str,
) -> None:
    """Propaga a falha de um comando do host-agent para o job."""
    detail = command_row["message"] or command_row["error_code"] or "erro desconhecido"
    await _set_job_status(
        job_id,
        "failed",
        message=f"{message_prefix}: {detail}",
        stdout_tail=command_row["stdout_tail"],
        stderr_tail=command_row["stderr_tail"],
        error_code=command_row["error_code"] or default_error,
    )


def _read_project_secret_keys(project_name: str) -> dict[str, str]:
    """Le as chaves do projeto direto do .env gerado pelos scripts.

    Substitui o antigo extract_token.sh: as chaves nunca mais passam por
    stdout de subprocesso (que agora e sanitizado pelo host-agent).
    """
    env_values = _read_env_file(_get_project_env_path(project_name))
    return {
        "tenant_uuid": (env_values.get("PROJECT_UUID") or "").strip(),
        "anon_key": (env_values.get("ANON_KEY_PROJETO") or "").strip(),
        "service_role": (env_values.get("SERVICE_ROLE_KEY_PROJETO") or "").strip(),
        "config_token": (env_values.get("CONFIG_TOKEN_PROJETO") or "").strip(),
    }


app = FastAPI()
app.include_router(health_router)
app.include_router(collaboration_router)
app.include_router(internal_router)
app.include_router(lifecycle_router)

# ``create`` nao e repetivel, mas e retomavel: o runner se religa ao mesmo
# host_agent_command duravel com ``reuse_terminal=True`` e nunca dispara um
# segundo script para o mesmo job.
RECOVERABLE_RUNNING_ACTIONS = IDEMPOTENT_ACTIONS | {"create"}


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
        return lambda: _rotate_project_key_background(
            job_id,
            project_name,
            owner_id,
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


@app.on_event("startup")
async def startup():
    pool = await initialize_pool(DB_DSN)
    await ensure_identity_schema(pool)
    await ensure_project_secrets_schema(pool)
    await ensure_jobs_schema(pool)
    await ensure_host_agent_schema(pool)
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
    await ensure_collaboration_schema(pool)
    await ensure_restore_points_schema(pool)
    print("✅ Database pool initialized")
    await _recover_pending_jobs()

@app.on_event("shutdown")
async def shutdown():
    await action_queue.shutdown()
    await close_pool()
    print("✅ Database pool closed")

@app.middleware("http")
async def validate_shared_token(request: Request, call_next):
    if request.url.path == "/healthz":
        return await call_next(request)

    token = request.headers.get("X-Shared-Token")
    
    if not token:
        return JSONResponse(
            status_code=401,
            content={"detail": "Unauthorized: Missing X-Shared-Token"}
        )
    
    if not hmac.compare_digest(token, NGINX_SHARED_TOKEN):
        return JSONResponse(
            status_code=403,
            content={"detail": "Forbidden: Invalid X-Shared-Token"}
        )
    
    response = await call_next(request)
    return response


# Rota extraída para app.routers.internal.




# Rota extraída para app.routers.internal.


# Dependências de autenticação e autorização: app.dependencies.

# Rota extraída para app.routers.internal.


@app.get("/api/projects")
async def list_projects(
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("""
                SELECT p.id, p.tenant_uuid, p.name, p.display_name,
                       p.anon_key, p.service_role
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
                anon_token = await decrypt_project_secret(
                    conn,
                    project_id=r["id"],
                    column="anon_key",
                    ciphertext=r["anon_key"],
                )
                service_role_token = (
                    await decrypt_project_secret(
                        conn,
                        project_id=r["id"],
                        column="service_role",
                        ciphertext=r["service_role"],
                    )
                    if r["service_role"]
                    else ""
                )
                expiries = [
                    expiry
                    for expiry in (
                        get_unverified_jwt_expiry(anon_token),
                        get_unverified_jwt_expiry(service_role_token),
                    )
                    if expiry is not None
                ]
                key_expires_at = min(expiries) if expiries else None
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
                    "anon_token": anon_token,
                    "file_size_limit": _get_project_file_size_limit(r["name"]),
                    "storage_limit_token": _get_project_storage_limit_token(r["name"]),
                    "key_expires_at": key_expires_at,
                    "key_expired": (
                        seconds_remaining is not None and seconds_remaining <= 0
                    ),
                    "key_expiring_soon": (
                        seconds_remaining is not None
                        and seconds_remaining <= KEY_EXPIRY_WARNING_DAYS * 86400
                    ),
                    "key_expiry_warning_days": KEY_EXPIRY_WARNING_DAYS,
                })
    return result


# Endpoints de colaboração: app.routers.collaboration.




_RENAME_HISTORY_ACTIONS = (
    "project_rename_started",
    "project_rename_succeeded",
    "project_rename_failed",
    "project_rename_rolled_back",
    "project_display_name_changed",
)


def _validate_rename_target(raw: str) -> str:
    return validate_project_id(raw)


async def _update_rename_history(
    conn: asyncpg.Connection,
    history_id: int,
    status: str,
    *,
    error: str | None = None,
) -> None:
    await conn.execute(
        """
        UPDATE project_name_history
        SET status = $1,
            error = $2,
            updated_at = now(),
            completed_at = CASE
                WHEN $1 IN ('succeeded', 'failed', 'rolled_back') THEN now()
                ELSE NULL
            END
        WHERE id = $3
        """,
        status,
        error,
        history_id,
    )


async def _rename_project_background(
    job_id: str,
    project_id: uuid.UUID,
    history_id: int,
    old_name: str,
    new_name: str,
    actor_user_id: uuid.UUID,
) -> None:
    """Delegar o rename ao host-agent e finalizar o control plane.

    Em caso de shutdown da API o comando segue executando no host-agent;
    o recovery do startup religa neste job e finaliza o rename (ou o
    rollback) com o resultado persistido pelo agent.
    """
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            await _update_rename_history(conn, history_id, "running")
        await _set_job_status(
            job_id,
            "running",
            message=f"Renomeando {old_name} -> {new_name}...",
            progress=5,
            current_step="migrate_infrastructure",
            total_steps=9,
        )

        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="rename_project",
            project=old_name,
            project_uuid=project_id,
            requested_by=actor_user_id,
            args={"new_name": new_name},
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )

        if record["status"] != "done":
            output = (record["stdout_tail"] or record["message"] or "").strip()
            rolled_back = (
                bool(command_result(record).get("rolled_back"))
                or "ROLLBACK_COMPLETE" in output
            )
            history_status = "rolled_back" if rolled_back else "failed"
            audit_action = (
                "project_rename_rolled_back"
                if rolled_back
                else "project_rename_failed"
            )
            async with pool.acquire() as conn:
                await _update_rename_history(
                    conn,
                    history_id,
                    history_status,
                    error=output[-4000:],
                )
                await audit_studio_action(
                    conn,
                    project_id=project_id,
                    actor_user_id=actor_user_id,
                    action=audit_action,
                    target_type="project",
                    target_id=old_name,
                    old_value={"name": old_name, "path": f"/{old_name}"},
                    new_value={
                        "name": new_name,
                        "path": f"/{new_name}",
                        "new_name": new_name,
                        "returncode": record["exit_code"],
                        "error_code": record["error_code"],
                        "error_excerpt": output[-2000:],
                    },
                )
            await _set_job_status(
                job_id,
                "failed",
                message=(
                    "Falha no rename. Projeto pode estar em estado parcial."
                    f"\n\n{output[-2000:]}"
                ),
                current_step=(
                    "rollback_completed" if rolled_back else "rollback_unconfirmed"
                ),
                error_code=(
                    "rename_rolled_back" if rolled_back else "rename_failed"
                ),
                stdout_tail=record["stdout_tail"],
                stderr_tail=record["stderr_tail"],
            )
            return

        # Migra as pastas de snippets SQL do usuario no Studio para o novo slug.
        # Best-effort: o rename ja commitou; se falhar, os snippets ficam orfaos
        # ate um retry manual, mas o projeto renomeado continua valido.
        snippet_note = ""
        try:
            await rename_project_snippets(old_name, new_name)
        except Exception as exc:  # noqa: BLE001
            snippet_note = (
                "\n\n⚠️ Snippets do Studio não migraram automaticamente "
                "por uma falha interna."
            )
            print(f"[rename_project] snippets {old_name} -> {new_name}: {exc}")

        await _set_job_status(
            job_id,
            "running",
            message="Finalizando histórico e notificações do rename...",
            progress=92,
            current_step="finalize_control_plane",
        )
        async with pool.acquire() as conn:
            await _update_rename_history(conn, history_id, "succeeded")
            await conn.execute(
                "UPDATE jobs SET project = $1 WHERE job_id = $2",
                new_name,
                job_id,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=actor_user_id,
                action="project_rename_succeeded",
                target_type="project",
                target_id=old_name,
                old_value={"name": old_name, "path": f"/{old_name}"},
                new_value={"name": new_name, "path": f"/{new_name}"},
            )
            notification_targets = await conn.fetch(
                """
                SELECT user_id FROM project_members
                WHERE project_id = $1 AND user_id <> $2
                """,
                project_id,
                actor_user_id,
            )
            for target in notification_targets:
                await create_studio_notification(
                    conn,
                    project_id=project_id,
                    target_user_id=target["user_id"],
                    actor_user_id=actor_user_id,
                    kind="project_renamed",
                    target_type="project",
                    target_id=str(project_id),
                    payload={
                        "old_name": old_name,
                        "new_name": new_name,
                        "old_path": f"/{old_name}",
                        "new_path": f"/{new_name}",
                    },
                )

        await _set_job_status(
            job_id,
            "done",
            message=f"Projeto renomeado: {old_name} -> {new_name}{snippet_note}",
            current_step="completed",
        )
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada ao renomear o projeto.",
            error_code="unexpected_rename_error",
        )
        try:
            async with pool.acquire() as conn:
                await _update_rename_history(
                    conn,
                    history_id,
                    "failed",
                    error="Falha interna inesperada ao renomear o projeto.",
                )
                await audit_studio_action(
                    conn,
                    project_id=project_id,
                    actor_user_id=actor_user_id,
                    action="project_rename_failed",
                    target_type="project",
                    target_id=old_name,
                    old_value={"name": old_name, "path": f"/{old_name}"},
                    new_value={
                        "name": new_name,
                        "path": f"/{new_name}",
                        "error_code": "unexpected_rename_error",
                    },
                )
        except Exception:
            pass
        print(f"[rename_project] {old_name} -> {new_name}: {exc}")


@app.post("/api/projects/{project_name}/rename", status_code=202)
async def rename_project(
    project_name: str,
    body: ProjectRenameRequest,
    request: Request,
    pool=Depends(get_pool),
):
    """Renomeia o slug/path do projeto (migração completa em background).

    O escopo inclui: nome interno na meta DB, banco Postgres, roles
    por projeto, replication slots do Realtime, tenant Supavisor,
    diretório físico e templates (nginx, docker-compose, .env).
    """
    project_name = validate_project_id(project_name)
    new_name = _validate_rename_target(body.new_name)
    if new_name == project_name:
        raise HTTPException(400, "O novo nome deve ser diferente do atual")
    display_name_raw = (
        body.display_name.strip() if body.display_name is not None else None
    )

    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admin do projeto ou admin global pode renomear",
            )

            collision = await conn.fetchval(
                "SELECT 1 FROM projects WHERE name = $1",
                new_name,
            )
            if collision:
                raise HTTPException(409, f"Já existe um projeto com nome '{new_name}'")

            active_rename = await conn.fetchval(
                """
                SELECT 1
                FROM project_name_history
                WHERE project_id = $1
                  AND status IN ('queued', 'running')
                LIMIT 1
                """,
                project_id,
            )
            if active_rename:
                raise HTTPException(409, "Ja existe uma renomeacao ativa para este projeto")

            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message=f"Rename iniciado: {project_name} -> {new_name}",
                action="rename",
                payload={
                    "old_name": project_name,
                    "new_name": new_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                },
                total_steps=9,
                project_uuid=project_id,
                connection=conn,
            )
            history_id = await conn.fetchval(
                """
                INSERT INTO project_name_history(
                    project_id, job_id, actor_user_id,
                    old_name, new_name, old_path, new_path
                )
                VALUES($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                project_id,
                job_id,
                auth_user["db_user_id"],
                project_name,
                new_name,
                f"/{project_name}",
                f"/{new_name}",
            )

            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_rename_started",
                target_type="project",
                target_id=project_name,
                old_value={"name": project_name, "path": f"/{project_name}"},
                new_value={"name": new_name, "path": f"/{new_name}"},
            )

            if display_name_raw:
                current_display = project_row["display_name"]
                if current_display != display_name_raw:
                    await conn.execute(
                        "UPDATE projects SET display_name = $1 WHERE id = $2",
                        display_name_raw,
                        project_id,
                    )
                    await audit_studio_action(
                        conn,
                        project_id=project_id,
                        actor_user_id=auth_user["db_user_id"],
                        action="project_display_name_changed",
                        target_type="project",
                        target_id=project_name,
                        old_value={"display_name": current_display},
                        new_value={"display_name": display_name_raw},
                    )

    try:
        position = await _enqueue_project_action(
            project_name,
            job_id,
            lambda: _rename_project_background(
                job_id,
                project_id,
                history_id,
                project_name,
                new_name,
                auth_user["db_user_id"],
            ),
        )
    except Exception as exc:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed',
                        message = $1,
                        current_step = 'enqueue_failed',
                        error_code = 'queue_submit_failed',
                        finished_at = now(),
                        updated_at = now()
                    WHERE job_id = $2
                    """,
                    "Falha interna ao enfileirar a renomeação.",
                    job_id,
                )
                await _update_rename_history(
                    conn,
                    history_id,
                    "failed",
                    error="queue_submit_failed",
                )
        raise HTTPException(503, "Nao foi possivel enfileirar a renomeacao") from exc

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "old_name": project_name,
            "new_name": new_name,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Renomeação enfileirada. O projeto ficará indisponível "
                "durante a migração."
                if position == 0
                else f"Renomeação enfileirada. Existem {position} ações "
                f"na fila para {project_name}; este job é o próximo."
            ),
        },
    )


@app.patch("/api/projects/{project_name}/display-name")
async def update_project_display_name(
    project_name: str,
    body: ProjectDisplayNameUpdate,
    request: Request,
    pool=Depends(get_pool),
):
    """Atualiza apenas o display_name do projeto (sem migrar infraestrutura)."""
    project_name = validate_project_id(project_name)
    new_display = body.display_name.strip()
    if not new_display:
        raise HTTPException(400, "display_name não pode ser vazio")

    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admin do projeto ou admin global pode alterar o display_name",
            )
            current_display = await conn.fetchval(
                "SELECT display_name FROM projects WHERE id = $1",
                project_id,
            )
            if current_display == new_display:
                return {
                    "project": project_name,
                    "display_name": new_display,
                    "status": "noop",
                }
            await conn.execute(
                "UPDATE projects SET display_name = $1 WHERE id = $2",
                new_display,
                project_id,
            )
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_display_name_changed",
                target_type="project",
                target_id=project_name,
                old_value={"display_name": current_display},
                new_value={"display_name": new_display},
            )

    return {
        "project": project_name,
        "display_name": new_display,
        "status": "updated",
    }


@app.get("/api/projects/{project_name}/config-token")
async def get_project_config_token(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Entrega o token compartilhado aos membros do projeto e registra a leitura."""
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project = await get_project_row(conn, project_name)
            await ensure_project_member_access(
                conn,
                project_id=project["id"],
                auth_user=auth_user,
                message="Apenas membros podem acessar o config token",
            )
            encrypted_token = await conn.fetchval(
                "SELECT config_token FROM projects WHERE id = $1",
                project["id"],
            )
            if not encrypted_token:
                raise HTTPException(404, "Config token não disponível")
            token = await decrypt_project_secret(
                conn,
                project_id=project["id"],
                column="config_token",
                ciphertext=encrypted_token,
            )
            await audit_studio_action(
                conn,
                project_id=project["id"],
                actor_user_id=auth_user["db_user_id"],
                action="project_config_token_read",
                target_type="project_secret",
                target_id=project_name,
            )

    return JSONResponse(
        content={"project": project_name, "config_token": token},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/projects/{project_name}/queue-status")
async def get_project_queue_status(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Retorna o estado atual da fila de ações do projeto.

    Inclui o job em execução (se houver), o tamanho da fila, e os jobs
    pendentes/rodando do banco para fins de UI (polling).
    """
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        project_id = project_row["id"]
        await ensure_project_member_access(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )

        in_flight_rows = await conn.fetch(
            """
            SELECT
                job_id,
                status,
                message,
                action,
                progress,
                current_step,
                total_steps,
                updated_at
            FROM jobs
            WHERE project = $1
              AND status IN ('queued', 'running')
            ORDER BY updated_at ASC
            """,
            project_name,
        )

    queue_state = action_queue.status(project_name)
    in_flight = [
        {
            "job_id": str(r["job_id"]),
            "status": r["status"],
            "message": r["message"],
            "action": r["action"],
            "progress": r["progress"],
            "current_step": r["current_step"],
            "total_steps": r["total_steps"],
            "updated_at": r["updated_at"].isoformat(),
        }
        for r in in_flight_rows
    ]

    return {
        "project": project_name,
        "is_busy": queue_state["is_busy"],
        "current_job_id": queue_state["current_job_id"],
        "queued": queue_state["queued"],
        "in_flight": in_flight,
        "message": (
            "Projeto ocioso."
            if not queue_state["is_busy"] and not in_flight
            else (
                f"Job atual: {queue_state['current_job_id']}."
                if queue_state["is_busy"]
                else f"{len(in_flight)} job(s) em fila no banco."
            )
        ),
    }


@app.get("/api/projects/{project_name}/rename-history")
async def get_project_rename_history(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
    limit: int = Query(50, ge=1, le=500),
):
    """Retorna auditoria e historico duravel de nome/path do projeto."""
    project_name = validate_project_id(project_name)

    auth_user = await resolve_authenticated_user(request, pool)
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE name = $1",
            project_name,
        )
        if not project_row:
            project_row = await conn.fetchrow(
                """
                SELECT p.id, p.name
                FROM project_name_history h
                JOIN projects p ON p.id = h.project_id
                WHERE h.old_name = $1 OR h.new_name = $1
                ORDER BY h.created_at DESC
                LIMIT 1
                """,
                project_name,
            )
        if not project_row:
            raise HTTPException(404, "Project not found")
        project_id = project_row["id"]
        await ensure_project_member_access(
            conn,
            project_id=project_id,
            auth_user=auth_user,
        )

        rows = await conn.fetch(
            """
            SELECT
                a.id,
                a.action,
                a.target_id,
                a.old_value,
                a.new_value,
                a.created_at,
                a.actor_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM studio_audit_log a
            LEFT JOIN users u ON u.id = a.actor_user_id
            WHERE a.project_id = $1
              AND a.action = ANY($2::text[])
            ORDER BY a.created_at DESC
            LIMIT $3
            """,
            project_id,
            list(_RENAME_HISTORY_ACTIONS),
            limit,
        )
        history_rows = await conn.fetch(
            """
            SELECT
                h.id,
                h.job_id,
                h.old_name,
                h.new_name,
                h.old_path,
                h.new_path,
                h.status,
                h.error,
                h.created_at,
                h.updated_at,
                h.completed_at,
                h.actor_user_id,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS actor_name
            FROM project_name_history h
            LEFT JOIN users u ON u.id = h.actor_user_id
            WHERE h.project_id = $1
            ORDER BY h.created_at DESC
            LIMIT $2
            """,
            project_id,
            limit,
        )

    return {
        "project": project_row["name"],
        "requested_name": project_name,
        "events": [
            {
                "id": str(r["id"]),
                "action": r["action"],
                "actor_user_id": (
                    str(r["actor_user_id"]) if r["actor_user_id"] else None
                ),
                "actor_name": r["actor_name"],
                "target_id": r["target_id"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ],
        "renames": [
            {
                "id": str(r["id"]),
                "job_id": str(r["job_id"]),
                "actor_user_id": (
                    str(r["actor_user_id"]) if r["actor_user_id"] else None
                ),
                "actor_name": r["actor_name"],
                "old_name": r["old_name"],
                "new_name": r["new_name"],
                "old_path": r["old_path"],
                "new_path": r["new_path"],
                "status": r["status"],
                "error": r["error"],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "completed_at": (
                    r["completed_at"].isoformat() if r["completed_at"] else None
                ),
            }
            for r in history_rows
        ],
    }


RESTORE_POINT_LIMIT = 15


def _serialize_restore_point(row: asyncpg.Record) -> dict[str, Any]:
    def iso(column: str) -> str | None:
        value = row[column]
        return value.isoformat() if value else None

    return {
        "id": str(row["id"]),
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "is_automatic": row["is_automatic"],
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "created_by_name": row["created_by_name"],
        "project_ref_at_creation": row["project_ref_at_creation"],
        "size_bytes": row["size_bytes"],
        "last_restored_at": iso("last_restored_at"),
        "restore_count": row["restore_count"],
        "error": row["error"],
        "created_at": iso("created_at"),
        "completed_at": iso("completed_at"),
    }


async def _fetch_restore_point_locked(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
    point_id: uuid.UUID,
) -> asyncpg.Record:
    row = await conn.fetchrow(
        """
        SELECT * FROM project_restore_points
        WHERE id = $1 AND project_id = $2
        FOR UPDATE
        """,
        point_id,
        project_id,
    )
    if not row:
        raise HTTPException(404, "Ponto de restauração não encontrado")
    return row


async def _count_active_restore_points(
    conn: asyncpg.Connection,
    project_id: uuid.UUID,
) -> int:
    return await conn.fetchval(
        """
        SELECT count(*) FROM project_restore_points
        WHERE project_id = $1 AND status <> 'failed'
        """,
        project_id,
    )


@app.get("/api/projects/{project_name}/restore-points")
async def list_project_restore_points(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        await ensure_project_member_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        is_owner = project_row["owner_id"] == auth_user["db_user_id"]
        is_global_admin = auth_user["is_global_admin"]
        rows = await conn.fetch(
            """
            SELECT
                p.*,
                COALESCE(u.display_name, u.authelia_username, 'Sistema') AS created_by_name
            FROM project_restore_points p
            LEFT JOIN users u ON u.id = p.created_by
            WHERE p.project_id = $1
            ORDER BY p.created_at DESC
            """,
            project_row["id"],
        )

    return {
        "project": project_name,
        "limit": RESTORE_POINT_LIMIT,
        "permissions": {
            "can_create": is_global_admin or is_owner or role == "admin",
            "can_restore": is_global_admin or is_owner,
            "can_delete": is_global_admin or is_owner,
        },
        "points": [_serialize_restore_point(row) for row in rows],
    }


@app.post("/api/projects/{project_name}/restore-points", status_code=202)
async def create_project_restore_point(
    project_name: str,
    body: RestorePointCreate,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)
    title = (body.title or "").strip() or dt.datetime.now().strftime("%d/%m/%Y %H:%M")
    description = (body.description or "").strip() or None
    point_id = uuid.uuid4()

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_admin_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas admins podem criar pontos de restauração",
            )
            active = await _count_active_restore_points(conn, project_id)
            if active >= RESTORE_POINT_LIMIT:
                raise HTTPException(
                    409,
                    f"Limite de {RESTORE_POINT_LIMIT} pontos de restauração "
                    "atingido; exclua um ponto antes de criar outro.",
                )
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Criação de ponto de restauração enfileirada.",
                action="backup",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(point_id),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=2,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                INSERT INTO project_restore_points(
                    id, project_id, title, description, status, is_automatic,
                    job_id, created_by, project_ref_at_creation
                )
                VALUES($1, $2, $3, $4, 'creating', false, $5, $6, $7)
                """,
                point_id,
                project_id,
                title,
                description,
                uuid.UUID(job_id),
                auth_user["db_user_id"],
                project_name,
            )

    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _create_restore_point_background(
            job_id, project_name, auth_user["db_user_id"], point_id
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "restore_point_id": str(point_id),
            "status": "queued",
            "queue_position": position,
            "message": (
                "Criação do ponto de restauração enfileirada."
                if position == 0
                else f"Criação enfileirada. Existem {position} ações antes "
                f"desta na fila para {project_name}."
            ),
        },
    )


@app.post(
    "/api/projects/{project_name}/restore-points/{point_id}/restore",
    status_code=202,
)
async def restore_project_restore_point(
    project_name: str,
    point_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_point = parse_uuid_value(point_id)
    if parsed_point is None:
        raise HTTPException(400, "Id do ponto de restauração inválido")
    auth_user = await resolve_authenticated_user(request, pool)
    safety_point_id = uuid.uuid4()

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_owner_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas o dono do projeto ou admin global pode restaurar o projeto",
            )
            point = await _fetch_restore_point_locked(conn, project_id, parsed_point)
            if point["status"] != "ready":
                raise HTTPException(
                    409,
                    f"Ponto de restauração em estado '{point['status']}'; "
                    "apenas pontos prontos podem ser restaurados.",
                )
            active = await _count_active_restore_points(conn, project_id)
            if active >= RESTORE_POINT_LIMIT:
                raise HTTPException(
                    409,
                    "A restauração cria um ponto automático de segurança e o "
                    f"limite de {RESTORE_POINT_LIMIT} pontos foi atingido; "
                    "exclua um ponto antes de restaurar.",
                )
            safety_title = f"Automático — antes de restaurar '{point['title']}'"[:80]
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Restauração enfileirada.",
                action="restore",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(parsed_point),
                    "safety_point_id": str(safety_point_id),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=3,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                INSERT INTO project_restore_points(
                    id, project_id, title, description, status, is_automatic,
                    job_id, created_by, project_ref_at_creation
                )
                VALUES($1, $2, $3, NULL, 'creating', true, $4, $5, $6)
                """,
                safety_point_id,
                project_id,
                safety_title,
                uuid.UUID(job_id),
                auth_user["db_user_id"],
                project_name,
            )
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = 'restoring', job_id = $2, error = NULL, updated_at = now()
                WHERE id = $1
                """,
                parsed_point,
                uuid.UUID(job_id),
            )

    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _restore_project_background(
            job_id,
            project_name,
            auth_user["db_user_id"],
            parsed_point,
            safety_point_id,
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "restore_point_id": str(parsed_point),
            "safety_point_id": str(safety_point_id),
            "status": "queued",
            "queue_position": position,
            "message": (
                "Restauração enfileirada. O projeto ficará indisponível "
                "durante o processo."
                if position == 0
                else f"Restauração enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )


@app.delete(
    "/api/projects/{project_name}/restore-points/{point_id}",
    status_code=202,
)
async def delete_project_restore_point(
    project_name: str,
    point_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    parsed_point = parse_uuid_value(point_id)
    if parsed_point is None:
        raise HTTPException(400, "Id do ponto de restauração inválido")
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, project_name)
            project_id = project_row["id"]
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(project_id),
            )
            await ensure_project_owner_access(
                conn,
                project_id=project_id,
                auth_user=auth_user,
                message="Apenas o dono do projeto ou admin global pode excluir pontos de restauração",
            )
            point = await _fetch_restore_point_locked(conn, project_id, parsed_point)
            if point["status"] not in ("ready", "failed"):
                raise HTTPException(
                    409,
                    f"Ponto de restauração em estado '{point['status']}'; "
                    "aguarde a operação atual terminar.",
                )
            job_id = await _create_project_job(
                pool,
                project_name,
                auth_user["db_user_id"],
                message="Exclusão de ponto de restauração enfileirada.",
                action="delete_restore_point",
                payload={
                    "project_name": project_name,
                    "actor_user_id": str(auth_user["db_user_id"]),
                    "restore_point_id": str(parsed_point),
                    "tenant_uuid": (
                        str(project_row["tenant_uuid"])
                        if project_row["tenant_uuid"]
                        else None
                    ),
                },
                total_steps=1,
                project_uuid=project_id,
                connection=conn,
            )
            await conn.execute(
                """
                UPDATE project_restore_points
                SET status = 'deleting', job_id = $2, updated_at = now()
                WHERE id = $1
                """,
                parsed_point,
                uuid.UUID(job_id),
            )

    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _delete_restore_point_background(
            job_id, project_name, auth_user["db_user_id"], parsed_point
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "restore_point_id": str(parsed_point),
            "status": "queued",
            "queue_position": position,
            "message": "Exclusão do ponto de restauração enfileirada.",
        },
    )


async def _create_restore_point_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID,
    point_id: uuid.UUID,
) -> None:
    pool = await get_pool()
    try:
        project_uuid, tenant_uuid = await _get_job_project_identity(pool, job_id)
        await _set_job_status(
            job_id,
            "running",
            message="Criando ponto de restauração...",
            progress=5,
            current_step="capture_backup",
            total_steps=2,
        )
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="backup_project",
            project=project_name,
            project_uuid=project_uuid,
            requested_by=actor_user_id,
            args={
                "backup_id": str(point_id),
                "tenant_uuid": str(tenant_uuid),
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            detail = record["message"] or record["error_code"] or "erro desconhecido"
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1
                """,
                point_id,
                str(detail)[:2000],
            )
            await _fail_job_from_command(
                job_id,
                record,
                default_error="backup_failed",
                message_prefix="Falha ao criar ponto de restauração",
            )
            return

        size_bytes = command_result(record).get("size_bytes")
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE project_restore_points
                SET status = 'ready', size_bytes = $2, error = NULL,
                    completed_at = now(), updated_at = now()
                WHERE id = $1
                RETURNING project_id, title
                """,
                point_id,
                size_bytes,
            )
            if row:
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=actor_user_id,
                    action="restore_point_created",
                    target_type="restore_point",
                    target_id=str(point_id),
                    new_value={"title": row["title"], "size_bytes": size_bytes},
                )
        await _set_job_status(
            job_id,
            "done",
            message="Ponto de restauração criado.",
            current_step="completed",
        )
    except Exception as exc:
        try:
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1 AND status = 'creating'
                """,
                point_id,
                "Falha interna inesperada ao criar o ponto de restauração.",
            )
        except Exception:
            pass
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada ao criar o ponto de restauração.",
            error_code="unexpected_backup_error",
        )
        print(f"[restore_point] backup {project_name}: {exc}")


async def _restore_project_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID,
    point_id: uuid.UUID,
    safety_point_id: uuid.UUID,
) -> None:
    pool = await get_pool()
    try:
        project_uuid, tenant_uuid = await _get_job_project_identity(pool, job_id)
        await _set_job_status(
            job_id,
            "running",
            message="Restaurando projeto para o ponto selecionado...",
            progress=5,
            current_step="restore_project",
            total_steps=3,
        )
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="restore_project",
            project=project_name,
            project_uuid=project_uuid,
            requested_by=actor_user_id,
            args={
                "backup_id": str(point_id),
                "safety_backup_id": str(safety_point_id),
                "tenant_uuid": str(tenant_uuid),
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        result = command_result(record)
        safety_completed = bool(result.get("safety_backup_completed"))
        async with pool.acquire() as conn:
            if safety_completed:
                await conn.execute(
                    """
                    UPDATE project_restore_points
                    SET status = 'ready', size_bytes = $2, error = NULL,
                        completed_at = now(), updated_at = now()
                    WHERE id = $1
                    """,
                    safety_point_id,
                    result.get("safety_backup_size_bytes"),
                )
            else:
                await conn.execute(
                    "DELETE FROM project_restore_points WHERE id = $1",
                    safety_point_id,
                )

        if record["status"] != "done":
            output = (record["stdout_tail"] or record["message"] or "").strip()
            rolled_back = (
                bool(result.get("rolled_back")) or "ROLLBACK_COMPLETE" in output
            )
            detail = record["message"] or record["error_code"] or "erro desconhecido"
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    UPDATE project_restore_points
                    SET status = 'ready', error = $2, updated_at = now()
                    WHERE id = $1
                    RETURNING project_id, title
                    """,
                    point_id,
                    str(detail)[:2000],
                )
                if row:
                    await audit_studio_action(
                        conn,
                        project_id=row["project_id"],
                        actor_user_id=actor_user_id,
                        action="restore_point_restore_failed",
                        target_type="restore_point",
                        target_id=str(point_id),
                        new_value={
                            "title": row["title"],
                            "rolled_back": rolled_back,
                            "error_code": record["error_code"],
                        },
                    )
            await _set_job_status(
                job_id,
                "failed",
                message=(
                    "Falha na restauração."
                    + (
                        " O estado anterior foi restaurado (rollback)."
                        if rolled_back
                        else " O projeto pode estar em estado parcial."
                    )
                    + f"\n\n{output[-2000:]}"
                ),
                current_step=(
                    "rollback_completed" if rolled_back else "rollback_unconfirmed"
                ),
                error_code=(
                    "restore_rolled_back" if rolled_back else "restore_failed"
                ),
                stdout_tail=record["stdout_tail"],
                stderr_tail=record["stderr_tail"],
            )
            return

        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE project_restore_points
                SET status = 'ready', last_restored_at = now(),
                    restore_count = restore_count + 1, error = NULL,
                    updated_at = now()
                WHERE id = $1
                RETURNING project_id, title
                """,
                point_id,
            )
            if row:
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=actor_user_id,
                    action="restore_point_restored",
                    target_type="restore_point",
                    target_id=str(point_id),
                    new_value={
                        "title": row["title"],
                        "safety_point_id": str(safety_point_id)
                        if safety_completed
                        else None,
                    },
                )
        safety_note = (
            " Um ponto automático com o estado anterior foi criado."
            if safety_completed
            else ""
        )
        await _set_job_status(
            job_id,
            "done",
            message=f"Projeto restaurado para o ponto selecionado.{safety_note}",
            current_step="completed",
        )
    except Exception as exc:
        try:
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'ready', error = $2, updated_at = now()
                WHERE id = $1 AND status = 'restoring'
                """,
                point_id,
                "Falha interna inesperada durante a restauração.",
            )
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1 AND status = 'creating'
                """,
                safety_point_id,
                "Falha interna inesperada durante a restauração.",
            )
        except Exception:
            pass
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada durante a restauração.",
            error_code="unexpected_restore_error",
        )
        print(f"[restore_point] restore {project_name}: {exc}")


async def _delete_restore_point_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID,
    point_id: uuid.UUID,
) -> None:
    pool = await get_pool()
    try:
        project_uuid, tenant_uuid = await _get_job_project_identity(pool, job_id)
        await _set_job_status(
            job_id,
            "running",
            message="Excluindo ponto de restauração...",
            progress=10,
            current_step="delete_restore_point",
            total_steps=1,
        )
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="delete_restore_point",
            project=project_name,
            project_uuid=project_uuid,
            requested_by=actor_user_id,
            args={
                "backup_id": str(point_id),
                "tenant_uuid": str(tenant_uuid),
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            detail = record["message"] or record["error_code"] or "erro desconhecido"
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1
                """,
                point_id,
                str(detail)[:2000],
            )
            await _fail_job_from_command(
                job_id,
                record,
                default_error="delete_backup_failed",
                message_prefix="Falha ao excluir ponto de restauração",
            )
            return
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                DELETE FROM project_restore_points
                WHERE id = $1
                RETURNING project_id, title, is_automatic
                """,
                point_id,
            )
            if row:
                await audit_studio_action(
                    conn,
                    project_id=row["project_id"],
                    actor_user_id=actor_user_id,
                    action="restore_point_deleted",
                    target_type="restore_point",
                    target_id=str(point_id),
                    old_value={
                        "title": row["title"],
                        "is_automatic": row["is_automatic"],
                    },
                )
        await _set_job_status(
            job_id,
            "done",
            message="Ponto de restauração excluído.",
            current_step="completed",
        )
    except Exception as exc:
        try:
            await pool.execute(
                """
                UPDATE project_restore_points
                SET status = 'failed', error = $2, updated_at = now()
                WHERE id = $1 AND status = 'deleting'
                """,
                point_id,
                "Falha interna inesperada ao excluir o ponto de restauração.",
            )
        except Exception:
            pass
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada ao excluir o ponto de restauração.",
            error_code="unexpected_delete_backup_error",
        )
        print(f"[restore_point] delete {project_name}: {exc}")


# Endpoints de tags: app.routers.collaboration.

@app.post("/api/projects", status_code=202)
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
                INSERT INTO projects(id, tenant_uuid, name, owner_id)
                VALUES($1, $1, $2, $3)
                """,
                project_id,
                name,
                auth_user["db_user_id"],
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
    return {
        "job_id": job_id,
        "project_uuid": str(project_id),
        "tenant_uuid": str(project_id),
        "status": "queued",
        "queue_position": position,
        "message": (
            "Criação enfileirada."
            if position == 0
            else f"Criação enfileirada. Existem {position} ações antes desta na fila para {name}."
        ),
    }


@app.post("/api/projects/duplicate", status_code=202)
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
                INSERT INTO projects(id, tenant_uuid, name, owner_id)
                VALUES($1, $1, $2, $3)
                """,
                project_id,
                new_name,
                auth_user["db_user_id"],
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

    return {
        "job_id": job_id,
        "project_uuid": str(project_id),
        "tenant_uuid": str(project_id),
        "status": "queued",
        "queue_position": position,
        "message": (
            "Duplicação enfileirada."
            if position == 0
            else f"Duplicação enfileirada. Existem {position} ações antes desta na fila para {new_name}."
        ),
    }


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
        if not keys["anon_key"] or not keys["service_role"] or not keys["config_token"]:
            await _set_job_status(
                job_id,
                "failed",
                message="Chaves obrigatórias ausentes no projeto duplicado",
                error_code="missing_keys",
            )
            print("Missing tokens")
            await rollback_project_from_db(pool, new_name, project_uuid)
            return

        await _set_job_status(
            job_id,
            "running",
            message="Persistindo chaves criptografadas...",
            progress=90,
            current_step="store_keys",
        )
        async with pool.acquire() as conn:
            project_id = await conn.fetchval(
                """
                SELECT id FROM projects
                WHERE name = $1 AND owner_id = $2 AND id = $3
                """,
                new_name,
                owner_id,
                project_uuid,
            )
            if project_id is None:
                raise RuntimeError("Projeto duplicado não encontrado ao persistir chaves")
            await store_project_secrets(
                conn,
                project_id=project_id,
                anon_key=keys["anon_key"],
                service_role=keys["service_role"],
                config_token=keys["config_token"],
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


def _base64url_no_padding(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _create_hs256_jwt(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _base64url_no_padding(
        json.dumps(header, separators=(",", ":")).encode("utf-8")
    )
    payload_b64 = _base64url_no_padding(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(
        secret.encode("utf-8"),
        f"{header_b64}.{payload_b64}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{header_b64}.{payload_b64}.{_base64url_no_padding(signature)}"


def _get_global_jwt_secret() -> str:
    env_secret = os.getenv("JWT_SECRET", "").strip()
    if env_secret:
        return env_secret

    try:
        return _read_env_file(_get_root_env_path()).get("JWT_SECRET", "").strip()
    except Exception as exc:
        print(f"[delete_project] falha ao ler JWT_SECRET do .env raiz: {exc}")
        return ""


def _build_short_lived_jwt(secret: str, issuer: str) -> str:
    now = int(time.time())
    return _create_hs256_jwt(
        {
            "role": "anon",
            "iss": issuer,
            "iat": now,
            "exp": now + 3600,
        },
        secret,
    )


def _load_project_env(project_name: str) -> dict[str, str]:
    env_path = PROJECTS_ROOT / project_name / ".env"
    try:
        return _read_env_file(env_path) if env_path.exists() else {}
    except Exception as exc:
        print(f"[delete_project] falha ao ler .env de {project_name}: {exc}")
        return {}


def _build_realtime_delete_token(
    project_env: dict[str, str],
    tenant_external_id: str,
) -> str:
    anon_token = project_env.get("ANON_KEY_PROJETO", "").strip()
    if anon_token:
        return anon_token

    jwt_secret = project_env.get("JWT_SECRET_PROJETO", "").strip()
    if jwt_secret:
        return _build_short_lived_jwt(jwt_secret, tenant_external_id)

    return ""


def _build_global_delete_token(issuer: str) -> str:
    secret = _get_global_jwt_secret()
    return _build_short_lived_jwt(secret, issuer) if secret else ""


async def _tenant_api_fallback(
    *,
    pool,
    job_id: str | None,
    project_name: str,
    requested_by: uuid.UUID | None,
    command: str,
) -> str | None:
    """Fallback do host-agent quando a chamada HTTP direta falha.

    O agent constroi o token localmente a partir dos .env do host e chama
    a API do tenant com curl dentro do proprio container do servico, no
    lugar do acesso que a Projects API tinha antes da migracao.
    """
    try:
        if job_id:
            record = await run_host_agent_command_for_job(
                pool,
                job_id=job_id,
                command=command,
                project=project_name,
                project_uuid=None,
                requested_by=requested_by,
                reuse_terminal=True,
            )
        else:
            record = await run_host_agent_command(
                pool,
                command=command,
                project=project_name,
                project_uuid=None,
                requested_by=requested_by,
            )
    except HostAgentError as exc:
        print(f"[delete_project] fallback {command}: {exc}")
        return f"{command}: falha no host-agent"
    if record["status"] == "done":
        return None
    return record["message"] or record["error_code"] or f"{command} falhou"


async def _delete_tenant_api(
    *,
    service_label: str,
    base_url: str,
    fallback_command: str,
    tenant_id: str,
    token: str,
    pool,
    job_id: str | None,
    project_name: str,
    requested_by: uuid.UUID | None,
) -> str | None:
    if not token:
        print(
            f"[delete_project] {service_label}: token ausente; "
            "seguindo com fallback SQL."
        )
        return None

    encoded_tenant = urllib.parse.quote(tenant_id, safe="")
    path = f"/api/tenants/{encoded_tenant}"
    headers = {"Authorization": f"Bearer {token}"}
    accepted_statuses = {200, 202, 204, 404}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(f"{base_url}{path}", headers=headers)
        if response.status_code in accepted_statuses:
            return None
        direct_error = f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        print(f"[delete_project] {service_label}: {exc}")
        direct_error = "erro de transporte"

    fallback_error = await _tenant_api_fallback(
        pool=pool,
        job_id=job_id,
        project_name=project_name,
        requested_by=requested_by,
        command=fallback_command,
    )
    if fallback_error is None:
        return None

    return (
        f"{service_label}: falha ao remover tenant {tenant_id}; "
        f"direto={direct_error}; host_agent={fallback_error}"
    )


async def _terminate_supavisor_pools(
    *,
    tenant_id: str,
    token: str,
    pool,
    job_id: str | None,
    project_name: str,
    requested_by: uuid.UUID | None,
) -> str | None:
    """Solicita ao Supavisor que encerre pools antes do banco ser removido."""
    if not token:
        return "Supavisor: token ausente para encerrar os pools do tenant"

    encoded_tenant = urllib.parse.quote(tenant_id, safe="")
    path = f"/api/tenants/{encoded_tenant}/terminate"
    headers = {"Authorization": f"Bearer {token}"}
    accepted_statuses = {200, 204, 404}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{SUPAVISOR_INTERNAL_URL}{path}",
                headers=headers,
            )
        if response.status_code in accepted_statuses:
            return None
        direct_error = f"HTTP {response.status_code}"
    except httpx.HTTPError as exc:
        print(f"[delete_project] Supavisor terminate: {exc}")
        direct_error = "erro de transporte"

    fallback_error = await _tenant_api_fallback(
        pool=pool,
        job_id=job_id,
        project_name=project_name,
        requested_by=requested_by,
        command="terminate_supavisor_tenant",
    )
    if fallback_error is None:
        return None

    return (
        f"Supavisor: falha ao encerrar pools do tenant {tenant_id}; "
        f"direto={direct_error}; host_agent={fallback_error}"
    )


async def _drain_database_connections(
    conn: asyncpg.Connection,
    db_name: str,
    *,
    timeout_seconds: float = 10.0,
) -> bool:
    """Encerra conexões e detecta pools que continuam tentando reconectar."""
    deadline = time.monotonic() + timeout_seconds
    quiet_since: float | None = None
    while True:
        active_connections = await conn.fetchval(
            """
            SELECT count(*)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        now = time.monotonic()
        if active_connections:
            quiet_since = None
            await conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
                """,
                db_name,
            )
        elif quiet_since is None:
            quiet_since = now
        elif now - quiet_since >= 2.0:
            return True

        if now >= deadline:
            return False
        await asyncio.sleep(0.5)


async def _drop_database_force_or_fallback(
    conn: asyncpg.Connection,
    db_name: str,
) -> None:
    quoted_db = '"' + db_name.replace('"', '""') + '"'
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {quoted_db} WITH (FORCE)")
        return
    except Exception as force_error:
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1 AND pid <> pg_backend_pid()
            """,
            db_name,
        )
        await asyncio.sleep(1)
        try:
            await conn.execute(f"DROP DATABASE IF EXISTS {quoted_db}")
        except Exception as drop_error:
            raise RuntimeError(
                f"{drop_error}; tentativa com FORCE: {force_error}"
            ) from drop_error


async def _delete_project_impl(
    project_name: str,
    pool,
    *,
    current_job_id: str | None = None,
) -> dict:
    errors: list[str] = []
    db_name = f"_supabase_{project_name}"
    database_removed = False

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
                total_steps=8,
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
    project_env = _load_project_env(project_name)
    identity_row = await pool.fetchrow(
        "SELECT id, tenant_uuid FROM projects WHERE name = $1",
        project_name,
    )
    persisted_tenant_uuid = (
        parse_tenant_uuid(identity_row["tenant_uuid"]) if identity_row else None
    )
    env_tenant_uuid = parse_tenant_uuid(project_env.get("PROJECT_UUID"))
    tenant_candidates = {
        candidate
        for candidate in (
            persisted_tenant_uuid,
            env_tenant_uuid,
            job_tenant_uuid,
        )
        if candidate is not None
    }
    if len(tenant_candidates) > 1:
        raise ProjectIdentityError(
            f"Projeto {project_name} possui tenant UUID divergente no delete"
        )
    tenant_uuid = tenant_candidates.pop() if tenant_candidates else None
    if identity_row and persisted_tenant_uuid is None and tenant_uuid is not None:
        await pool.execute(
            "UPDATE projects SET tenant_uuid = $2 WHERE id = $1",
            identity_row["id"],
            tenant_uuid,
        )
    tenant_external_id = str(tenant_uuid) if tenant_uuid else project_name

    if tenant_uuid:
        print(f"Deletando projeto com tenant UUID: {tenant_uuid}")
    else:
        print(
            "Deletando projeto antigo (sem UUID), "
            f"usando project_name: {project_name}"
        )

    await report(15, "remove_containers", "Removendo containers do projeto...")
    containers_record = await agent_step("delete_project_containers", job_project_uuid)
    if containers_record["status"] != "done":
        container_errors = command_result(containers_record).get("errors") or [
            containers_record["message"]
            or containers_record["error_code"]
            or "falha ao remover containers"
        ]
        errors.extend(str(item) for item in container_errors)

    await report(30, "remove_tenants", "Removendo tenants globais...")
    supavisor_token = _build_global_delete_token(tenant_external_id)
    supavisor_terminate_error = await _terminate_supavisor_pools(
        tenant_id=project_name,
        token=supavisor_token,
        pool=pool,
        job_id=current_job_id,
        project_name=project_name,
        requested_by=job_requested_by,
    )
    realtime_error = await _delete_tenant_api(
        service_label="Realtime",
        base_url=REALTIME_INTERNAL_URL,
        fallback_command="delete_realtime_tenant",
        tenant_id=tenant_external_id,
        token=_build_realtime_delete_token(project_env, tenant_external_id),
        pool=pool,
        job_id=current_job_id,
        project_name=project_name,
        requested_by=job_requested_by,
    )

    supavisor_error = await _delete_tenant_api(
        service_label="Supavisor",
        base_url=SUPAVISOR_INTERNAL_URL,
        fallback_command="delete_supavisor_tenant",
        tenant_id=project_name,
        token=supavisor_token,
        pool=pool,
        job_id=current_job_id,
        project_name=project_name,
        requested_by=job_requested_by,
    )

    await asyncio.sleep(1)

    await report(50, "clean_global_metadata", "Limpando metadata global...")
    async with pool.acquire() as conn:
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

        if realtime_error:
            print(f"[delete_project] {realtime_error}")

        if supavisor_terminate_error:
            print(f"[delete_project] {supavisor_terminate_error}")
        if supavisor_error:
            print(f"[delete_project] {supavisor_error}")

        await report(65, "drop_database", "Removendo slots e database...")
        connections_drained = await _drain_database_connections(conn, db_name)

        slot_errors = await drop_supabase_replication_slots(conn, project_name)
        if slot_errors:
            errors.extend(slot_errors)

        if not connections_drained:
            errors.append(
                "Supavisor continuou abrindo conexões após a remoção do "
                f"tenant; o banco {db_name} foi preservado para evitar "
                "estado inconsistente"
            )
        else:
            try:
                await _drop_database_force_or_fallback(conn, db_name)
                database_removed = True
            except Exception as drop_error:
                errors.append(f"Erro ao dropar banco {db_name}: {drop_error}")

        await report(
            78,
            "remove_control_plane",
            "Removendo registros do control plane...",
        )
        if database_removed:
            project_id = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1",
                project_name,
            )
            if project_id:
                await conn.execute(
                    "DELETE FROM project_members WHERE project_id = $1",
                    project_id,
                )
                await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
            else:
                errors.append(
                    f"Projeto {project_name} não encontrado para limpeza final."
                )

    await report(90, "remove_files", "Removendo arquivos do projeto...")
    if database_removed:
        files_args = (
            {"tenant_uuid": str(tenant_uuid)}
            if tenant_uuid is not None
            else None
        )
        files_record = await agent_step("delete_project_files", None, files_args)
        if files_record["status"] != "done":
            detail = (
                (files_record["stderr_tail"] or "").strip()
                or (files_record["message"] or "").strip()
                or files_record["error_code"]
                or "erro desconhecido"
            )
            errors.append(f"Erro ao excluir diretórios: {detail}")

    await report(96, "verify_cleanup", "Verificando limpeza final...")
    async with pool.acquire() as conn:
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

    return {
        "project": project_name,
        "status": "success" if not errors else "partial_success",
        "message": (
            "Projeto excluído com sucesso."
            if not errors
            else "Projeto excluído com avisos."
        ),
        "errors": errors,
        "success": len(errors) == 0,
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

async def drop_supabase_replication_slots(
    conn: asyncpg.Connection, project_name: str
) -> List[str]:
    """
    Remove os replication slots do Supabase Realtime de um projeto, na ordem EXATA:
        1. Termina o backend do slot *messages*
        2. Dropa o slot *messages*
        3. Termina o backend do slot *replication*
        4. Dropa o slot *replication*

    Parameters
    ----------
    conn : asyncpg.Connection
        Conexão já aberta (superuser) com o Postgres.
    project_name : str
        Slug do projeto, p.ex. "sistema_novo".

    Returns
    -------
    List[str]
        Lista de erros/avisos (vazia se tudo correu bem).
    """
    errors: List[str] = []

    msg_slot  = f"supabase_realtime_messages_replication_slot_{project_name}"[:63]
    repl_slot = f"supabase_realtime_replication_slot_{project_name}"[:63]

    async def terminate_if_active(slot: str) -> None:
        try:
            pid = await conn.fetchval(
                "SELECT active_pid FROM pg_replication_slots WHERE slot_name = $1",
                slot,
            )
            if pid:
                await conn.execute("SELECT pg_terminate_backend($1)", pid)
                await asyncio.sleep(1)
        except Exception as exc:
            if "does not exist" not in str(exc):
                print(f"[delete_project] terminate slot {slot}: {exc}")
                errors.append(f"Não foi possível encerrar o slot {slot}.")

    async def drop_slot(slot: str) -> None:
        try:
            await conn.execute("SELECT pg_drop_replication_slot($1)", slot)
        except Exception as exc:
            if "does not exist" not in str(exc):
                print(f"[delete_project] drop slot {slot}: {exc}")
                errors.append(f"Não foi possível remover o slot {slot}.")

    await terminate_if_active(msg_slot)
    await drop_slot(msg_slot)

    await terminate_if_active(repl_slot)
    await drop_slot(repl_slot)

    return errors

@app.delete("/api/projects/{project_name}")
async def delete_project(
    project_name: str,
    request: Request,
    x_delete_password: str = Header(..., alias="X-Delete-Password"),
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "Admin required")

    DELETE_PASSWORD = os.getenv("PROJECT_DELETE_PASSWORD")
    if not DELETE_PASSWORD:
        raise HTTPException(500, "Delete password not configured")

    if not hmac.compare_digest(x_delete_password, DELETE_PASSWORD):
        raise HTTPException(403, "Invalid delete password")

    async with pool.acquire() as conn:
        project_row = await conn.fetchrow(
            "SELECT id, tenant_uuid FROM projects WHERE name = $1",
            project_name,
        )
        if not project_row:
            raise HTTPException(404, "Project not found")

    project_id = project_row["id"]
    tenant_uuid = parse_tenant_uuid(project_row["tenant_uuid"])

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Exclusão enfileirada.",
        action="delete",
        payload={
            "project_name": project_name,
            "tenant_uuid": str(tenant_uuid) if tenant_uuid else None,
        },
        total_steps=8,
        project_uuid=project_id,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _delete_project_background(job_id, project_name),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Exclusão enfileirada. Será executada quando não houver "
                "outras ações em andamento para este projeto."
                if position == 0
                else f"Exclusão enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )





@app.post("/api/projects/{project_name}/rotate-key", status_code=202)
async def rotate_project_key(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Rotaciona anon/service_role via script. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
            message="Only project admin or system admin can rotate keys",
        )

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Rotação de chaves enfileirada.",
        action="rotate_key",
        payload={
            "project_name": project_name,
            "actor_user_id": str(auth_user["db_user_id"]),
        },
        total_steps=4,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _rotate_project_key_background(
            job_id, project_name, auth_user["db_user_id"]
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "project": project_name,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Rotação enfileirada."
                if position == 0
                else f"Rotação enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )


async def _rotate_project_key_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID,
) -> None:
    await _set_job_status(
        job_id,
        "running",
        message="Rotacionando chaves...",
        progress=10,
        current_step="rotate_keys",
        total_steps=4,
    )
    try:
        pool = await get_pool()
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="rotate_keys",
            project=project_name,
            project_uuid=await _get_job_project_uuid(pool, job_id),
            requested_by=actor_user_id,
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            await _fail_job_from_command(
                job_id,
                record,
                default_error="rotate_script_failed",
                message_prefix="Rotate failed",
            )
            return

        # O script persiste as chaves novas no .env do projeto; nada de
        # segredo transita por stdout (que agora e sanitizado pelo agent).
        keys = _read_project_secret_keys(project_name)
        anon = keys["anon_key"]
        service = keys["service_role"]
        if not anon or not service:
            await _set_job_status(
                job_id,
                "failed",
                message="Keys not found in project .env after rotate",
                error_code="missing_keys",
            )
            return

        await _set_job_status(
            job_id,
            "running",
            message="Persistindo novas chaves...",
            progress=85,
            current_step="store_keys",
        )
        async with pool.acquire() as conn:
            async with conn.transaction():
                project_row = await conn.fetchrow(
                    "SELECT id FROM projects WHERE name = $1 FOR UPDATE",
                    project_name,
                )
                if project_row is None:
                    raise RuntimeError("Projeto não encontrado ao rotacionar chaves")
                await store_project_secrets(
                    conn,
                    project_id=project_row["id"],
                    anon_key=anon,
                    service_role=service,
                )
                key_version = await conn.fetchval(
                    """
                    UPDATE projects
                    SET project_key_version = project_key_version + 1
                    WHERE id = $1
                    RETURNING project_key_version
                    """,
                    project_row["id"],
                )

        await _set_job_status(
            job_id,
            "running",
            message="Invalidando cache da service key...",
            progress=95,
            current_step="invalidate_service_key_cache",
        )
        try:
            await invalidate_service_key_cache(project_name, key_version)
        except Exception as cache_exc:
            await _set_job_status(
                job_id,
                "failed",
                message=(
                    "Chaves rotacionadas, mas a invalidação imediata do cache falhou. "
                    "A verificação de versão corrigirá o cache dentro da janela configurada."
                ),
                current_step="invalidate_service_key_cache",
                error_code="service_key_cache_invalidation_failed",
                stderr_tail=str(cache_exc),
            )
            return

        await _set_job_status(
            job_id,
            "done",
            message="Chaves rotacionadas com sucesso.",
            current_step="completed",
        )
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="O host-agent não conseguiu rotacionar as chaves.",
            error_code=exc.error_code,
        )
        print(f"[rotate-key] {project_name}: host-agent: {exc}")
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="Falha interna inesperada durante a rotação de chaves.",
            error_code="rotate_failed",
        )
        print(f"[rotate-key] {project_name}: {exc}")


@app.post("/api/projects/{project_name}/members")
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


@app.get("/api/projects/{name}/members")
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


@app.delete(
    "/api/projects/{name}/members/{member_id}",
    status_code=200,
    response_model=dict
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


@app.get("/api/jobs")
async def list_job_history(
    request: Request,
    project_uuid: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, max_length=80),
    status: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    pool=Depends(get_pool),
):
    """Lista o historico duravel de jobs visivel para o usuario autenticado."""
    auth_user = await resolve_authenticated_user(request, pool)
    filters: list[str] = []
    values: list[Any] = []

    def add_filter(expression: str, value: Any) -> None:
        values.append(value)
        filters.append(expression.format(index=len(values)))

    if not auth_user["is_global_admin"]:
        add_filter("created_by = ${index}", auth_user["db_user_id"])
    if project_uuid is not None:
        add_filter("project_uuid = ${index}", project_uuid)
    if action:
        add_filter("action = ${index}", action.strip())
    if status:
        add_filter("status = ${index}", status.strip())

    where_sql = " WHERE " + " AND ".join(filters) if filters else ""
    values.extend((limit, offset))
    rows = await pool.fetch(
        f"""
        SELECT *
        FROM jobs
        {where_sql}
        ORDER BY created_at DESC, job_id DESC
        LIMIT ${len(values) - 1} OFFSET ${len(values)}
        """,
        *values,
    )
    return {
        "items": [serialize_job(row) for row in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
    }


@app.post("/api/jobs/{job_id}/retry", status_code=202)
async def retry_project_job(
    job_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Cria uma nova tentativa apenas para acoes explicitamente idempotentes."""
    parsed_job_id = parse_uuid_value(job_id)
    if parsed_job_id is None:
        raise HTTPException(400, "job_id invalido")
    auth_user = await resolve_authenticated_user(request, pool)
    source = await pool.fetchrow("SELECT * FROM jobs WHERE job_id = $1", parsed_job_id)
    if source is None:
        raise HTTPException(404, "Job not found")
    if (
        source["created_by"] != auth_user["db_user_id"]
        and not auth_user["is_global_admin"]
    ):
        raise HTTPException(403, "Acesso negado a este job")

    try:
        retry_row = await create_retry_job(
            pool, parsed_job_id, auth_user["db_user_id"]
        )
    except LookupError as exc:
        raise HTTPException(404, "Job not found") from exc
    except ValueError as exc:
        if str(exc) == "job_not_failed":
            raise HTTPException(409, "Somente jobs com falha podem ser reexecutados") from exc
        raise
    except PermissionError as exc:
        raise HTTPException(
            409,
            "Este job nao e idempotente e foi marcado como nao-reexecutavel",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(409, f"Ja existe um retry ativo: {exc}") from exc

    runner = await _build_recovery_runner(retry_row)
    if runner is None:
        await _set_job_status(
            str(retry_row["job_id"]),
            "failed",
            message="Nao foi possivel reconstruir o runner para o retry.",
            current_step="retry_dispatch_failed",
            error_code="retry_runner_unavailable",
        )
        raise HTTPException(409, "Runner indisponivel para retry")

    position = await _enqueue_project_action(
        retry_row["project"], str(retry_row["job_id"]), runner
    )
    result = serialize_job(retry_row)
    result["queue_position"] = position
    return result


@app.get("/api/projects/status/{job_id}")
async def project_status(
    job_id: str,
    request: Request,
    pool=Depends(get_pool),
):
    parsed_job_id = parse_uuid_value(job_id)
    if parsed_job_id is None:
        raise HTTPException(400, "job_id inválido")
    auth_user = await resolve_authenticated_user(request, pool)
    row = await pool.fetchrow("SELECT * FROM jobs WHERE job_id=$1", parsed_job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    if row["created_by"] != auth_user["db_user_id"] and not auth_user["is_global_admin"]:
        raise HTTPException(403, "Acesso negado a este job")
    return serialize_job(row, include_output=True)

# Rota extraída para app.routers.internal.


# Rota extraída para app.routers.internal.

async def _provision_and_store_keys(job_id: str, project_name: str, user: uuid.UUID):
    pool = await get_pool()
    project_uuid = await _get_job_project_uuid(pool, job_id)
    await _set_job_status(
        job_id,
        "running",
        message="Provisionando infraestrutura do projeto...",
        progress=5,
        current_step="provision_infrastructure",
        total_steps=3,
    )

    try:
        resolved_project_uuid, tenant_uuid = await _get_job_project_identity(
            pool, job_id
        )
        if project_uuid != resolved_project_uuid:
            raise ProjectIdentityError("projects.id do job mudou durante criacao")
        recover_stale, stale_tenant_uuids = await _failed_create_recovery_context(
            pool,
            job_id=job_id,
            project_name=project_name,
            created_by=user,
        )

        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="create_project",
            project=project_name,
            project_uuid=project_uuid,
            requested_by=user,
            args={
                "tenant_uuid": str(tenant_uuid),
                "recover_stale": recover_stale,
                "stale_tenant_uuids": stale_tenant_uuids,
            },
            reuse_terminal=True,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            result = command_result(record)
            rollback_completed = result.get("rollback_completed") is True
            stale_state = result.get("stale_state_detected") is True
            await _fail_job_from_command(
                job_id,
                record,
                default_error="provision_failed",
                message_prefix="Falha ao provisionar infraestrutura",
            )
            await rollback_project_from_db(pool, project_name, project_uuid)
            if not rollback_completed or stale_state:
                detail = (
                    record["message"]
                    or record["error_code"]
                    or "falha física não confirmada"
                )
                await _set_job_status(
                    job_id,
                    "failed",
                    message=(
                        f"Falha ao provisionar infraestrutura: {detail}. "
                        "A limpeza física não pôde ser confirmada; os resíduos "
                        "foram registrados e serão recuperados numa nova tentativa."
                    ),
                    current_step="rollback_unconfirmed",
                    error_code=record["error_code"] or "rollback_unconfirmed",
                )
            return

        await _set_job_status(
            job_id,
            "running",
            message="Lendo chaves do projeto...",
            progress=70,
            current_step="extract_keys",
        )
        keys = _read_project_secret_keys(project_name)
        env_tenant_uuid = parse_tenant_uuid(keys["tenant_uuid"])
        if env_tenant_uuid != tenant_uuid:
            await _set_job_status(
                job_id,
                "failed",
                message="PROJECT_UUID gerado diverge da identidade persistida",
                error_code="tenant_uuid_mismatch",
            )
            await rollback_project_from_db(pool, project_name, project_uuid)
            return
        if not keys["anon_key"] or not keys["service_role"] or not keys["config_token"]:
            await _set_job_status(
                job_id,
                "failed",
                message="Chaves obrigatórias ausentes",
                error_code="missing_keys",
            )
            print("Missing tokens")
            await rollback_project_from_db(pool, project_name, project_uuid)
            return

        await _set_job_status(
            job_id,
            "running",
            message="Persistindo chaves criptografadas...",
            progress=90,
            current_step="store_keys",
        )
        async with pool.acquire() as conn:
            project_id = await conn.fetchval(
                """
                SELECT id FROM projects
                WHERE name = $1 AND owner_id = $2 AND id = $3
                """,
                project_name,
                user,
                project_uuid,
            )
            if project_id is None:
                raise RuntimeError("Projeto não encontrado ao persistir chaves")
            await store_project_secrets(
                conn,
                project_id=project_id,
                anon_key=keys["anon_key"],
                service_role=keys["service_role"],
                config_token=keys["config_token"],
            )

        await _set_job_status(
            job_id,
            "done",
            message="Projeto criado com sucesso.",
            current_step="completed",
        )

    except ProjectIdentityError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="A identidade persistida do tenant esta inconsistente.",
            error_code="tenant_identity_error",
        )
        print(f"[project_identity] create job {job_id}: {exc}")
        await rollback_project_from_db(pool, project_name, project_uuid)
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message=(
                "O host-agent não conseguiu criar o projeto. A limpeza física "
                "não foi confirmada; uma nova tentativa fará a recuperação."
            ),
            current_step="rollback_unconfirmed",
            error_code=exc.error_code,
        )
        await rollback_project_from_db(pool, project_name, project_uuid)
    except Exception as e:
        await _set_job_status(
            job_id,
            "failed",
            message=(
                "Falha interna inesperada ao criar o projeto. Possíveis resíduos "
                "foram registrados para recuperação na próxima tentativa."
            ),
            current_step="rollback_unconfirmed",
            error_code="unexpected_create_error",
        )
        print(f"Worker error: {e}")
        await rollback_project_from_db(pool, project_name, project_uuid)


async def get_project_containers(project: str) -> list[dict]:
    """Snapshot dos containers mantido pelo host-agent no control plane."""
    pool = await get_pool()
    return await fetch_project_containers(pool, project)


def _get_root_env_path() -> pathlib.Path:
    return BASE_DIR / ".env"


def _get_project_env_path(project_name: str) -> pathlib.Path:
    return PROJECTS_ROOT / project_name / ".env"


def _get_project_dir(project_name: str) -> pathlib.Path:
    return PROJECTS_ROOT / project_name


def _get_project_pending_settings_path(project_name: str) -> pathlib.Path:
    return _get_project_dir(project_name) / ".settings_pending.json"


def _read_project_pending_settings(project_name: str) -> dict[str, Any]:
    pending_path = _get_project_pending_settings_path(project_name)
    if not pending_path.exists():
        return {}
    try:
        data = json.loads(pending_path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_project_pending_settings(
    project_name: str,
    affected_services: list[str],
) -> None:
    pending_path = _get_project_pending_settings_path(project_name)
    payload = {
        "affected_services": affected_services,
        "storage_limit_token": _get_project_storage_limit_token(project_name),
        "updated_at": int(time.time()),
    }
    pending_path.write_text(json.dumps(payload))


def _clear_project_pending_settings(project_name: str) -> None:
    pending_path = _get_project_pending_settings_path(project_name)
    try:
        pending_path.unlink()
    except FileNotFoundError:
        pass


def _get_project_file_size_limit(project_name: str) -> str:
    return get_project_file_size_limit(
        project_name,
        projects_root=PROJECTS_ROOT,
    )


def _get_project_storage_limit_token(project_name: str) -> str:
    limit = _get_project_file_size_limit(project_name)
    ts = str(int(time.time()))
    payload = f"{project_name}.{limit}.{ts}"
    sig = hmac.new(
        NGINX_HMAC_SECRET.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}"


def _extract_project_admin_apikey(request: Request) -> str:
    apikey = (request.headers.get("apikey") or "").strip()
    if apikey:
        return apikey

    authorization = (request.headers.get("authorization") or "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return ""


def _read_env_file(env_path: pathlib.Path) -> dict[str, str]:
    return {k: (v or "") for k, v in dotenv_values(env_path).items()}


async def _container_lifecycle_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID | None,
    *,
    command: str,
    initial_message: str,
    success_prefix: str,
    error_code: str,
) -> None:
    """Delegar start/stop/restart ao host-agent espelhando o progresso."""
    await _set_job_status(
        job_id,
        "running",
        message=initial_message,
        progress=1,
        current_step="dispatch_host_agent",
    )
    try:
        pool = await get_pool()
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command=command,
            project=project_name,
            project_uuid=await _get_job_project_uuid(pool, job_id),
            requested_by=actor_user_id,
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            await _fail_job_from_command(
                job_id,
                record,
                default_error=error_code,
                message_prefix=initial_message.rstrip("."),
            )
            print(f"[{command}] {project_name}: {record['error_code']}")
            return

        touched = command_result(record).get("containers", [])
        await _set_job_status(
            job_id,
            "done",
            message=f"{success_prefix}: {', '.join(touched)}" if touched else success_prefix,
            current_step="completed",
        )
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="O host-agent não conseguiu concluir a operação do projeto.",
            error_code=exc.error_code,
        )
        print(f"[{command}] {project_name}: host-agent: {exc}")
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message=f"{initial_message.rstrip('.')}: falha interna inesperada.",
            error_code=error_code,
        )
        print(f"[{command}] {project_name}: background task failed: {exc}")


async def _stop_project_containers_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID | None = None,
) -> None:
    await _container_lifecycle_background(
        job_id,
        project_name,
        actor_user_id,
        command="stop_project",
        initial_message="Parando servicos do projeto...",
        success_prefix="Projeto parado com sucesso.",
        error_code="stop_failed",
    )


async def _recreate_project_services_background(
    job_id: str,
    project_name: str,
    services: list[str],
) -> None:
    await _set_job_status(
        job_id,
        "running",
        message=f"Recriando servicos: {', '.join(services)}",
        progress=10,
        current_step="recreate_services",
        total_steps=2,
    )
    try:
        pool = await get_pool()
        job_row = await pool.fetchrow(
            "SELECT created_by, project_uuid FROM jobs WHERE job_id = $1",
            uuid.UUID(str(job_id)),
        )
        record = await run_host_agent_command_for_job(
            pool,
            job_id=job_id,
            command="recreate_services",
            project=project_name,
            project_uuid=job_row["project_uuid"] if job_row else None,
            requested_by=job_row["created_by"] if job_row else None,
            args={"services": services},
            on_progress=_job_progress_mirror(job_id),
        )
        if record["status"] != "done":
            await _fail_job_from_command(
                job_id,
                record,
                default_error="recreate_failed",
                message_prefix="Falha ao recriar servicos",
            )
            print(
                f"[recreate_project_services] {project_name}: "
                f"{record['error_code']}"
            )
            return

        _clear_project_pending_settings(project_name)
        await _set_job_status(
            job_id,
            "running",
            message="Limpando configurações pendentes...",
            progress=90,
            current_step="clear_pending_settings",
        )
        await _set_job_status(
            job_id,
            "done",
            message=f"Servicos recriados: {', '.join(services)}",
            current_step="completed",
        )
    except HostAgentError as exc:
        await _set_job_status(
            job_id,
            "failed",
            message="O host-agent não conseguiu recriar os serviços.",
            error_code=exc.error_code,
        )
        print(f"[recreate_project_services] {project_name}: host-agent: {exc}")
    except Exception as exc:
        message = "Falha interna inesperada ao recriar os serviços."
        await _set_job_status(
            job_id,
            "failed",
            message=message,
            error_code="recreate_failed",
        )
        print(
            f"[recreate_project_services] {project_name}: "
            f"background task failed: {exc}"
        )

# Estado de containers: app.routers.lifecycle.

@app.post("/api/projects/{project_name}/stop")
async def stop_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Parada enfileirada.",
        action="stop",
        payload={"project_name": project_name},
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _stop_project_containers_background(
            job_id,
            project_name,
            auth_user["db_user_id"],
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Parada enfileirada."
                if position == 0
                else f"Parada enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )

@app.post("/api/projects/{project_name}/start", status_code=202)
async def start_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    """Inicia os containers do projeto. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Inicialização enfileirada.",
        action="start",
        payload={
            "project_name": project_name,
            "actor_user_id": str(auth_user["db_user_id"]),
        },
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _start_project_containers_background(
            job_id, project_name, auth_user["db_user_id"]
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Inicialização enfileirada."
                if position == 0
                else f"Inicialização enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )


async def _start_project_containers_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    await _container_lifecycle_background(
        job_id,
        project_name,
        actor_user_id,
        command="start_project",
        initial_message="Iniciando containers...",
        success_prefix="Iniciado",
        error_code="start_failed",
    )


@app.post("/api/projects/{project_name}/restart", status_code=202)
async def restart_project(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    """Reinicia os containers do projeto. Enfileirado por projeto."""
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    containers = await get_project_containers(project_name)
    if not containers:
        if not await host_agent_alive(pool):
            raise HTTPException(503, "Host-agent offline; estado dos containers indisponivel")
        raise HTTPException(404, "No containers found for this project")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Reinicialização enfileirada.",
        action="restart",
        payload={
            "project_name": project_name,
            "actor_user_id": str(auth_user["db_user_id"]),
        },
        total_steps=max(len(containers), 1),
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _restart_project_containers_background(
            job_id, project_name, auth_user["db_user_id"]
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Reinicialização enfileirada."
                if position == 0
                else f"Reinicialização enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )


async def _restart_project_containers_background(
    job_id: str,
    project_name: str,
    actor_user_id: uuid.UUID | None,
) -> None:
    await _container_lifecycle_background(
        job_id,
        project_name,
        actor_user_id,
        command="restart_project",
        initial_message="Reiniciando containers...",
        success_prefix="Reiniciado",
        error_code="restart_failed",
    )


# Logs de containers: app.routers.lifecycle.

@app.post("/api/projects/admin/projects-info")
async def get_projects_for_user(
    body: Dict[str, str],
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

    uid = body.get("user_id")
    if not uid:
        raise HTTPException(400, "user_id é obrigatório")
    target_uuid = parse_uuid_value(uid)
    if target_uuid is None:
        raise HTTPException(400, "user_id inválido")

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT p.name, p.display_name
            FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = $1
              AND m.role = 'admin'
        """, target_uuid)

        projects = []
        for r in rows:
            project_status = await get_project_status(r["name"])
            projects.append({
                "name": r["name"],
                "display_name": r["display_name"],
                "status": project_status["status"],
                "running_containers": project_status["running"],
                "total_containers": project_status["total"],
                "file_size_limit": _get_project_file_size_limit(r["name"]),
                "storage_limit_token": _get_project_storage_limit_token(r["name"]),
            })

    return {"projects": projects}


@app.get("/api/admin/projects/{name}/all-users")
async def list_all_users_for_admin(
    name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Lista todos os usuários disponíveis para admins.
    Como a API não tem acesso ao cache, retorna uma estrutura
    que o Nginx pode completar ou usa proxy para Nginx.
    """
    name = validate_project_id(name)
    auth_user = await resolve_authenticated_user(request, pool)
    if not auth_user["is_global_admin"]:
        raise HTTPException(403, "admin access required")

    async with pool.acquire() as conn:
        project = await conn.fetchrow(
            "SELECT id FROM projects WHERE name = $1",
            name,
        )
        if not project:
            raise HTTPException(404, "project not found")

        current_members = await conn.fetch(
            "SELECT user_id, role FROM project_members WHERE project_id=$1",
            project["id"],
        )

    return {
        "project_name": name,
        "project_id": project["id"],
        "current_members": [
            {
                "user_id": str(m["user_id"]),
                "role": m["role"],
                "status": "member"
            } for m in current_members
        ],
        "cache_users_needed": True,
        "nginx_route": f"/api/projects/{name}/all-users"
    }



@app.post("/api/projects/{project_name}/transfer", status_code=200)
async def transfer_project(
    project_name: str,
    body: TransferBody,
    request: Request,
    pool                   = Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    new_owner = body.new_owner_id.strip()
    if not new_owner:
        raise HTTPException(400, "new_owner_id é obrigatório")

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        if not auth_user["is_global_admin"]:
            raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

        async with conn.transaction():
            proj_row = await get_project_row(conn, project_name)
            new_owner_user = await require_synced_user_record(
                conn,
                identifier=new_owner,
                field_name="new_owner_id",
                missing_message="Novo proprietário ainda não foi sincronizado com o banco",
            )

            project_id = proj_row["id"]
            current_owner = proj_row["owner_id"]

            if current_owner == new_owner_user["id"]:
                return {"status": "noop", "detail": "Já é o proprietário"}

            await conn.execute(
                "UPDATE projects SET owner_id = $1 WHERE id = $2",
                new_owner_user["id"], project_id,
            )

            previous_target_role = await upsert_project_member(
                conn,
                project_id=project_id,
                user_id=new_owner_user["id"],
                role="admin",
            )
            await audit_project_member_change(
                conn,
                project_id=project_id,
                target_user_id=new_owner_user["id"],
                old_role=previous_target_role,
                new_role="admin",
                action="owner_transfer",
                actor_user_id=auth_user["db_user_id"],
            )

            await conn.execute(
                """
                UPDATE project_members
                SET role = 'member'
                WHERE project_id = $1
                  AND user_id = $2
                  AND role       = 'admin'
                """,
                project_id, current_owner,
            )
            if current_owner:
                await audit_project_member_change(
                    conn,
                    project_id=project_id,
                    target_user_id=current_owner,
                    old_role="admin",
                    new_role="member",
                    action="owner_transfer",
                    actor_user_id=auth_user["db_user_id"],
                )

    return {
        "project": project_name,
        "new_owner_id": str(new_owner_user["id"]),
        "status": "transferred"
    }

async def get_project_conn(project_ref: str):
    dsn = urllib.parse.urlparse(DB_DSN)
    db_name = f"_supabase_{project_ref}"
    return await asyncpg.connect(
        host=dsn.hostname,
        port=dsn.port,
        user=dsn.username,
        password=dsn.password,
        database=db_name
    )


def get_project_meta_connection_string(project_ref: str) -> str:
    dsn = urllib.parse.urlparse(DB_DSN)
    if dsn.scheme not in {"postgres", "postgresql"} or not dsn.hostname or not dsn.username:
        raise RuntimeError("DB_DSN inválido para construir a conexão administrativa do projeto")

    db_name = f"_supabase_{project_ref}"
    return urllib.parse.urlunparse(
        dsn._replace(
            path=f"/{urllib.parse.quote(db_name, safe='')}",
            params="",
            query="",
            fragment="",
        )
    )


@app.get("/api/projects/{project_name}/telemetry/users")
async def get_project_user_telemetry(
    project_name: str,
    request: Request,
    response: Response,
    period: str = Query("24h"),
    start: dt.datetime | None = Query(None),
    end: dt.datetime | None = Query(None),
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)
    auth_user = await resolve_authenticated_user(request, pool)

    try:
        telemetry_period = resolve_telemetry_period(
            period,
            start=start,
            end=end,
        )
    except TelemetryValidationError as exc:
        raise HTTPException(422, str(exc)) from exc

    async with pool.acquire() as conn:
        project_row = await get_project_row(conn, project_name)
        project_role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        is_owner = project_row["owner_id"] == auth_user["db_user_id"]
        if (
            project_role != "admin"
            and not is_owner
            and not auth_user["is_global_admin"]
        ):
            raise HTTPException(
                403,
                "Acesso negado: telemetria exige owner ou admin do projeto",
            )
        await audit_studio_action(
            conn,
            project_id=project_row["id"],
            actor_user_id=auth_user["db_user_id"],
            action="project_auth_telemetry_read",
            target_type="project_auth_telemetry",
            target_id=project_name,
            new_value={
                "period": telemetry_period.key,
                "start": telemetry_period.start.isoformat(),
                "end": telemetry_period.end.isoformat(),
            },
        )

    project_conn: asyncpg.Connection | None = None
    try:
        project_conn = await get_project_conn(project_name)
        result = await fetch_project_user_telemetry(
            project_conn,
            telemetry_period,
        )
    except asyncpg.InvalidCatalogNameError as exc:
        raise HTTPException(409, "Database do projeto nao esta disponivel") from exc
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
        raise HTTPException(
            409,
            "Schema Auth/GoTrue do projeto nao suporta esta telemetria",
        ) from exc
    except asyncpg.PostgresError as exc:
        raise HTTPException(
            502,
            "Falha ao consultar a telemetria Auth/GoTrue do projeto",
        ) from exc
    finally:
        if project_conn is not None:
            await project_conn.close()

    response.headers["Cache-Control"] = "no-store"
    return {"project": project_name, **result}


@app.api_route(
    "/api/projects/{ref}/meta",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
@app.api_route(
    "/api/projects/{ref}/meta/{meta_path:path}",
    methods=["GET", "POST", "PATCH", "DELETE"],
)
async def proxy_project_meta(
    ref: str,
    request: Request,
    meta_path: str = "",
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            project_row = await get_project_row(conn, ref)
            await ensure_project_admin_access(
                conn,
                project_id=project_row["id"],
                auth_user=auth_user,
                message="Apenas admins podem acessar roles e metadados do banco",
            )
            encrypted_service_role = await conn.fetchval(
                "SELECT service_role FROM projects WHERE id = $1",
                project_row["id"],
            )
            if not encrypted_service_role:
                raise HTTPException(409, "service_role administrativa não disponível")
            expected_apikey = await decrypt_project_secret(
                conn,
                project_id=project_row["id"],
                column="service_role",
                ciphertext=encrypted_service_role,
            )

    try:
        project_connection_string = get_project_meta_connection_string(ref)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    provided_apikey = _extract_project_admin_apikey(request)
    if not provided_apikey:
        raise HTTPException(status_code=401, detail="apikey administrativa ausente")
    if not hmac.compare_digest(provided_apikey, expected_apikey):
        raise HTTPException(status_code=403, detail="apikey administrativa inválida para o projeto")

    target_path = meta_path.lstrip("/")
    target_url = f"{PG_META_INTERNAL_URL}/{target_path}" if target_path else PG_META_INTERNAL_URL
    upstream_headers = {
        "x-connection-encrypted": encrypt_postgres_meta_uri(
            project_connection_string,
            PG_META_CRYPTO_KEY,
        )
    }

    content_type = request.headers.get("content-type")
    if content_type:
        upstream_headers["content-type"] = content_type

    x_pg_application_name = request.headers.get("x-pg-application-name")
    if x_pg_application_name:
        upstream_headers["x-pg-application-name"] = x_pg_application_name

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
            upstream_response = await client.request(
                request.method,
                target_url,
                params=list(request.query_params.multi_items()),
                headers=upstream_headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        print(f"[postgres_meta_proxy] {project_name}: {exc}")
        raise HTTPException(
            status_code=502,
            detail="Falha ao acessar postgres-meta global.",
        ) from exc

    response_headers: dict[str, str] = {}
    response_content_type = upstream_response.headers.get("content-type")
    if response_content_type:
        response_headers["content-type"] = response_content_type

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )

@app.get("/api/projects/{ref}/functions")
async def get_project_ai_functions(
    ref: str,
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, ref)
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    proj_conn = None
    try:
        proj_conn = await get_project_conn(ref)
        rows = await proj_conn.fetch("""
            SELECT
                p.proname AS name,
                pg_get_function_identity_arguments(p.oid) AS argument_types,
                pg_get_function_result(p.oid) AS return_type,
                obj_description(p.oid, 'pg_proc') AS comment
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
              AND p.proargmodes IS NULL
              AND obj_description(p.oid, 'pg_proc') ILIKE '%[AI]%'
            ORDER BY p.proname, p.oid
        """)
    except Exception as exc:
        raise HTTPException(503, "Cannot connect to project database") from exc
    finally:
        if proj_conn:
            await proj_conn.close()

    functions = []
    for r in rows:
        comment = r["comment"] or ""
        clean_desc = re.sub(r"\[AI\]", "", comment, flags=re.IGNORECASE).strip()
        functions.append({
            "name": r["name"],
            "argument_types": r["argument_types"] or "",
            "return_type": r["return_type"] or "void",
            "comment": clean_desc,
            "schema": "public",
        })
    return functions


AI_TOOL_MAX_ROWS = 1000
AI_TOOL_TIMEOUT_MS = 30000


@app.post("/api/projects/{ref}/execute-function")
async def execute_project_function(
    ref: str,
    body: Dict[str, Any],
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    
    function_name = body.get("function_name")
    arguments = body.get("arguments", {})
    
    if not function_name:
        raise HTTPException(400, "function_name is required")
    
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', function_name):
        raise HTTPException(400, "Invalid function name")
    
    if not isinstance(arguments, dict):
        raise HTTPException(400, "arguments must be an object with named parameters")

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, ref)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
            message="Apenas admins podem executar AI tools",
        )
        project_id = project_row["id"]

    proj_conn = None
    try:
        proj_conn = await get_project_conn(ref)

        candidates = await proj_conn.fetch("""
            SELECT
                p.oid,
                p.proname AS name,
                p.proargnames AS argument_names,
                p.pronargs AS argument_count,
                p.pronargdefaults AS default_count
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public'
              AND p.prokind = 'f'
              AND p.proargmodes IS NULL
            AND p.proname = $1
              AND obj_description(p.oid, 'pg_proc') ILIKE '%[AI]%'
            ORDER BY p.oid
        """, function_name)

        if not candidates:
            raise HTTPException(404, f"Function '{function_name}' not found in public schema")
        if len(candidates) > 1:
            raise HTTPException(
                409,
                "AI tool com overload ambíguo; mantenha uma única assinatura por nome",
            )

        function = candidates[0]
        argument_count = int(function["argument_count"] or 0)
        default_count = int(function["default_count"] or 0)
        argument_names = list(function["argument_names"] or [])[:argument_count]
        if len(argument_names) != argument_count or any(
            not name or not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", name)
            for name in argument_names
        ):
            raise HTTPException(409, "AI tools exigem nomes em todos os argumentos")

        unknown_arguments = set(arguments) - set(argument_names)
        if unknown_arguments:
            raise HTTPException(
                400,
                f"Unexpected parameters: {', '.join(sorted(unknown_arguments))}",
            )
        required_count = argument_count - default_count
        missing = [name for name in argument_names[:required_count] if name not in arguments]
        if missing:
            raise HTTPException(400, f"Missing required parameter: {missing[0]}")

        values: list[Any] = []
        named_placeholders: list[str] = []
        for name in argument_names:
            if name not in arguments:
                continue
            values.append(arguments[name])
            named_placeholders.append(f'"{name}" => ${len(values)}')

        query = (
            f'SELECT public."{function_name}"('
            + ", ".join(named_placeholders)
            + f") AS result LIMIT {AI_TOOL_MAX_ROWS}"
        )
        async with proj_conn.transaction():
            await proj_conn.fetchval(
                "SELECT set_config('statement_timeout', $1, true)",
                str(AI_TOOL_TIMEOUT_MS),
            )
            rows = await proj_conn.fetch(query, *values)

        async with pool.acquire() as conn:
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_ai_tool_executed",
                target_type="database_function",
                target_id=f"public.{function_name}",
                new_value={
                    "argument_names": sorted(arguments.keys()),
                    "returned_rows": len(rows),
                    "row_limit": AI_TOOL_MAX_ROWS,
                },
            )

        return [dict(row) for row in rows]

    except HTTPException:
        raise
    except asyncpg.QueryCanceledError as exc:
        raise HTTPException(504, "AI tool execution timed out") from exc
    except Exception as exc:
        raise HTTPException(400, "Function execution failed") from exc
    finally:
        if proj_conn:
            await proj_conn.close()

@app.get("/api/projects/{project_name}/settings")
async def get_project_settings(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    env_path = _get_project_env_path(project_name)
    if not env_path.exists():
        raise HTTPException(404, f"Arquivo .env não encontrado para o projeto '{project_name}'")

    settings = _read_env_whitelisted(env_path)
    pending = _read_project_pending_settings(project_name)

    return {
        "settings": settings,
        "pending_affected_services": pending.get("affected_services", []),
        "storage_limit_token": pending.get("storage_limit_token"),
    }


@app.put("/api/projects/{project_name}/settings")
async def update_project_settings(
    project_name: str,
    body: UpdateSettings,
    request: Request,
    pool=Depends(get_pool),
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    updates = _normalize_settings_updates(body.settings)

    env_path = _get_project_env_path(project_name)
    if not env_path.exists():
        raise HTTPException(404, f"Arquivo .env não encontrado para o projeto '{project_name}'")

    _write_env_whitelisted(env_path, updates)

    affected = _get_affected_services(list(updates.keys()))
    if affected:
        _write_project_pending_settings(project_name, affected)
    else:
        _clear_project_pending_settings(project_name)

    return {
        "status": "updated",
        "updated_keys": list(updates.keys()),
        "affected_services": affected,
        "file_size_limit": _get_project_file_size_limit(project_name),
        "storage_limit_token": _get_project_storage_limit_token(project_name),
        "message": f"Configurações salvas. Serviços afetados: {', '.join(affected)}. Recrie-os para aplicar.",
    }


ALLOWED_RECREATE_SERVICES = {"auth", "rest", "storage", "imgproxy", "nginx", "meta"}

@app.post("/api/projects/{project_name}/recreate-services")
async def recreate_project_services(
    project_name: str,
    body: RecreateServices,
    request: Request,
    pool=Depends(get_pool),
):
    """
    Recreate specific services of a project using docker compose down + up.
    This is needed (instead of just restart) because env vars are read at
    container creation time, not on restart.
    """
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(conn, project_id=project_row["id"], auth_user=auth_user)

    invalid_services = set(body.services) - ALLOWED_RECREATE_SERVICES
    if invalid_services:
        raise HTTPException(400, f"Serviços inválidos: {', '.join(sorted(invalid_services))}")

    if not body.services:
        raise HTTPException(400, "Nenhum serviço especificado")

    services = body.services
    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Recriação enfileirada.",
        action="recreate_services",
        payload={"project_name": project_name, "services": services},
        total_steps=2,
    )
    position = await _enqueue_project_action(
        project_name,
        job_id,
        lambda: _recreate_project_services_background(
            job_id,
            project_name,
            services,
        ),
    )
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "queue_position": position,
            "message": (
                "Recriação enfileirada."
                if position == 0
                else f"Recriação enfileirada. Existem {position} ações "
                f"antes desta na fila para {project_name}."
            ),
        },
    )
