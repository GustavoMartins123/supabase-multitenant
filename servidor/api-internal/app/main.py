import os
import uuid
import pathlib
import asyncpg
import hmac
import base64
import hashlib
import signal
import time
import datetime as dt
import asyncio, json, re
import urllib.parse
import httpx
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from app.schemas import NewProject, DuplicateProject, UserSyncPayload, AddMember, TransferBody, UpdateSettings, RecreateServices, ProjectNoteCreate, ProjectTagAssign, ProjectHintCreate, ProjectHintStatusUpdate, ProjectThreadMessageCreate, ProjectRenameRequest, ProjectDisplayNameUpdate, ProjectNotificationRead
from typing import Any, Optional, List, Dict
from dotenv import dotenv_values
from app.security_tokens import resolve_user_id_from_hmac_token as resolve_signed_user_id
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
    ANALYTICS_INTERNAL_URL, BASE_DIR, DB_DSN, DELETE_SCRIPT, DUPLICATE_SCRIPT, EXTRACTOR,
    KEY_EXPIRY_WARNING_DAYS, NGINX_HMAC_SECRET, NGINX_SHARED_TOKEN, PG_META_CRYPTO_KEY,
    LOGFLARE_PRIVATE_ACCESS_TOKEN, PG_META_INTERNAL_URL, REALTIME_INTERNAL_URL, RENAME_SCRIPT, ROTATE_SCRIPT,
    SCRIPT, SUPAVISOR_INTERNAL_URL, USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    service_key_transport_fernet,
)
from app.validation import (
    normalize_groups, parse_uuid_value, validate_project_id,
    validate_service_name,
)
from app.database_schema import ensure_collaboration_schema, ensure_identity_schema
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
)
from app.service_key_cache import invalidate_service_key_cache
from app.snippets_migration import rename_project_snippets
from app.jwt_metadata import get_unverified_jwt_expiry
from app.project_telemetry import (
    TelemetryValidationError,
    fetch_project_user_telemetry,
    resolve_telemetry_period,
)

db_pool: Optional[asyncpg.Pool] = None


def resolve_user_id_from_hmac_token(request: Request) -> uuid.UUID:
    return resolve_signed_user_id(
        request,
        secret=NGINX_HMAC_SECRET,
        max_clock_skew_seconds=USER_TOKEN_MAX_CLOCK_SKEW_SECONDS,
    )


async def get_pool():
    global db_pool
    if db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return db_pool


configure_jobs(get_pool)



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

async def rollback_project_from_db(pool, project_name: str):
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM projects WHERE name = $1", project_name)
        print(f"Rollback: Projeto '{project_name}' removido do banco")
    except Exception as e:
        print(f"Erro no rollback do banco: {e}")


app = FastAPI()


RECOVERABLE_RUNNING_ACTIONS = IDEMPOTENT_ACTIONS


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
    if action in {"start", "stop", "restart"}:
        async def run_container_action() -> None:
            containers = await get_project_containers(project_name)
            if not containers:
                await _set_job_status(
                    job_id,
                    "failed",
                    message="Retomada falhou: nenhum container do projeto foi encontrado.",
                    error_code="recovery_containers_missing",
                )
                return
            if action == "start":
                await _start_project_containers_background(
                    job_id,
                    project_name,
                    containers,
                    owner_id,
                )
            elif action == "stop":
                await _stop_project_containers_background(
                    job_id,
                    project_name,
                    containers,
                )
            else:
                await _restart_project_containers_background(
                    job_id,
                    project_name,
                    containers,
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
        can_resume = old_status == "queued" or action in RECOVERABLE_RUNNING_ACTIONS
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
                    message=f"Falha ao reconstruir job após reinício: {exc}",
                    error_code="recovery_dispatch_failed",
                )
            except Exception:
                pass
            print(
                f"[recovery] falha ao reconstruir job {job_id}: {exc}"
            )


@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=10)
    await ensure_identity_schema(db_pool)
    await ensure_project_secrets_schema(db_pool)
    await ensure_jobs_schema(db_pool)
    await ensure_collaboration_schema(db_pool)
    print("✅ Database pool initialized")
    await _recover_pending_jobs()


@app.on_event("shutdown")
async def shutdown():
    global db_pool
    await action_queue.shutdown()
    if db_pool:
        await db_pool.close()
        print("✅ Database pool closed")

@app.middleware("http")
async def validate_shared_token(request: Request, call_next):
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


@app.api_route(
    "/api/internal/analytics/{analytics_path:path}",
    methods=["GET", "POST"],
)
async def proxy_global_analytics(
    analytics_path: str,
    request: Request,
):
    if not analytics_path.startswith("api/") or ".." in analytics_path:
        raise HTTPException(404, "Analytics path not allowed")

    provided_token = request.headers.get("x-api-key", "")
    authorization = request.headers.get("authorization", "")
    if not provided_token and authorization.lower().startswith("bearer "):
        provided_token = authorization[7:].strip()
    if not provided_token or not hmac.compare_digest(
        provided_token,
        LOGFLARE_PRIVATE_ACCESS_TOKEN,
    ):
        raise HTTPException(403, "Invalid Analytics token")

    upstream_headers = {"x-api-key": LOGFLARE_PRIVATE_ACCESS_TOKEN}
    content_type = request.headers.get("content-type")
    if content_type:
        upstream_headers["content-type"] = content_type

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=5.0)
        ) as client:
            upstream = await client.request(
                request.method,
                f"{ANALYTICS_INTERNAL_URL}/{analytics_path}",
                params=list(request.query_params.multi_items()),
                headers=upstream_headers,
                content=await request.body(),
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Analytics service unavailable") from exc

    response_headers = {"Cache-Control": "no-store"}
    if upstream.headers.get("content-type"):
        response_headers["Content-Type"] = upstream.headers["content-type"]
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
    )




@app.post("/api/projects/internal/users/sync")
async def sync_user_identity(
    body: UserSyncPayload,
    pool=Depends(get_pool),
):
    async with pool.acquire() as conn:
        async with conn.transaction():
            synced = await sync_user_record(
                conn,
                user_id=body.id,
                username=body.username,
                display_name=body.display_name,
                groups=body.groups,
                is_active=body.is_active,
                source=body.source,
            )
    return synced


async def resolve_authenticated_user(
    request: Request,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    signed_user_id = resolve_user_id_from_hmac_token(request)

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
            await conn.execute(
                """
                UPDATE users
                SET last_login_at = now(), updated_at = now()
                WHERE id = $1
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
        "SELECT id, name, display_name, owner_id FROM projects WHERE name = $1",
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

@app.get("/api/projects/internal/content-identity/{project_name}")
async def get_content_project_identity(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
    """Resolve o slug mutável para o UUID estável usado apenas por content."""
    project_name = validate_project_id(project_name)
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")

    async with pool.acquire() as conn:
        project = await conn.fetchrow(
            "SELECT id, name FROM projects WHERE name = $1",
            project_name,
        )
        if not project:
            raise HTTPException(404, "Project not found")

        history = await conn.fetch(
            """
            SELECT old_name, new_name
            FROM project_name_history
            WHERE project_id = $1
              AND status = 'succeeded'
            ORDER BY created_at ASC
            """,
            project["id"],
        )

    aliases: list[str] = []
    seen: set[str] = set()
    candidates = (
        [project["name"]]
        + [row["old_name"] for row in history]
        + [row["new_name"] for row in history]
    )
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            aliases.append(candidate)

    return JSONResponse(
        content={
            "project_id": str(project["id"]),
            "current_ref": project["name"],
            "aliases": aliases,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/projects")
async def list_projects(
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch("""
                SELECT p.id, p.name, p.display_name, p.anon_key, p.service_role
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


@app.get("/api/projects/{project_name}/collaboration")
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


@app.post("/api/projects/{project_name}/notes", status_code=201)
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


@app.delete("/api/projects/{project_name}/notes/{note_id}")
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


@app.post("/api/projects/{project_name}/hints", status_code=201)
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


@app.put("/api/projects/{project_name}/hints/{hint_id}")
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


@app.post("/api/projects/{project_name}/thread/messages", status_code=201)
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


@app.patch("/api/projects/{project_name}/notifications/{notification_id}")
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
    """Executa o script de rename em background e atualiza o job/audit."""
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

        if not RENAME_SCRIPT.exists():
            raise RuntimeError(f"Script de rename não encontrado: {RENAME_SCRIPT}")

        proc = await asyncio.create_subprocess_exec(
            "bash",
            str(RENAME_SCRIPT),
            old_name,
            new_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            stdout, _ = await proc.communicate()
        except asyncio.CancelledError:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                # O shell trata SIGTERM executando rollback compensatório. O
                # timeout precisa cobrir o Compose e as verificações do banco.
                await asyncio.wait_for(proc.wait(), timeout=210)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
            cancel_output = ""
            if proc.stdout is not None:
                cancel_output = (
                    await proc.stdout.read()
                ).decode(errors="replace").strip()
            rolled_back = "ROLLBACK_COMPLETE" in cancel_output
            history_status = "rolled_back" if rolled_back else "failed"
            audit_action = (
                "project_rename_rolled_back"
                if rolled_back
                else "project_rename_failed"
            )
            try:
                async with pool.acquire() as conn:
                    await _update_rename_history(
                        conn,
                        history_id,
                        history_status,
                        error=(
                            "API shutdown durante o rename.\n"
                            f"{cancel_output[-4000:]}"
                        ),
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
                            "reason": "api_shutdown",
                            "error_excerpt": cancel_output[-2000:],
                        },
                    )
                await _set_job_status(
                    job_id,
                    "failed",
                    message=(
                        "Rename interrompido pelo shutdown da API; "
                        + (
                            "rollback concluído."
                            if rolled_back
                            else "rollback não confirmado."
                        )
                    ),
                    current_step=(
                        "rollback_completed" if rolled_back else "rollback_unconfirmed"
                    ),
                    error_code=(
                        "rename_cancelled_rolled_back"
                        if rolled_back
                        else "rename_cancelled"
                    ),
                    stdout_tail=cancel_output,
                )
            except Exception as exc:
                print(
                    f"[rename_project] falha ao registrar cancelamento "
                    f"{old_name} -> {new_name}: {exc}"
                )
            raise
        output = stdout.decode(errors="replace").strip()

        if proc.returncode != 0:
            rolled_back = "ROLLBACK_COMPLETE" in output
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
                        "returncode": proc.returncode,
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
                stdout_tail=output,
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
                f"({exc})."
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
            message=f"Falha inesperada no rename: {exc}",
            error_code="unexpected_rename_error",
        )
        try:
            async with pool.acquire() as conn:
                await _update_rename_history(
                    conn,
                    history_id,
                    "failed",
                    error=str(exc),
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
                        "exception": str(exc),
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
                    f"Falha ao enfileirar rename: {exc}",
                    job_id,
                )
                await _update_rename_history(
                    conn,
                    history_id,
                    "failed",
                    error=f"queue_submit_failed: {exc}",
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


@app.post("/api/projects/{project_name}/tags", status_code=201)
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


@app.delete("/api/projects/{project_name}/tags/{tag_id}")
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
            project_id = await conn.fetchval(
                    """
                    INSERT INTO projects(name, owner_id)
                    VALUES($1, $2)
                    RETURNING id
                    """,
                    name, auth_user["db_user_id"]
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

            project_id = await conn.fetchval("""
                INSERT INTO projects(name, owner_id)
                VALUES($1, $2) RETURNING id
            """, new_name, auth_user["db_user_id"])

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
        
        project_uuid = str(uuid.uuid4())

        proc = await asyncio.create_subprocess_exec(
            "bash", str(DUPLICATE_SCRIPT), original_name, new_name, copy_mode, project_uuid,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            output = stdout.decode(errors="replace")
            await _set_job_status(
                job_id,
                "failed",
                message="Falha ao duplicar infraestrutura",
                stdout_tail=output,
                error_code="duplicate_failed",
            )
            print(output)
            await rollback_project_from_db(pool, new_name)
            return

        await _set_job_status(
            job_id,
            "running",
            message="Extraindo chaves do projeto duplicado...",
            progress=70,
            current_step="extract_keys",
        )
        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), new_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            error_output = err2.decode(errors="replace")
            await _set_job_status(
                job_id,
                "failed",
                message="Falha ao extrair chaves do projeto duplicado",
                stderr_tail=error_output,
                error_code="key_extraction_failed",
            )
            print(error_output)
            await rollback_project_from_db(pool, new_name)
            return

        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        config_token = kv.get("CONFIG_TOKEN_PROJETO")
        if not anon or not service or not config_token:
            await _set_job_status(
                job_id,
                "failed",
                message="Chaves obrigatórias ausentes no projeto duplicado",
                error_code="missing_keys",
            )
            print("Missing tokens")
            await rollback_project_from_db(pool, new_name)
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
                "SELECT id FROM projects WHERE name = $1 AND owner_id = $2",
                new_name,
                owner_id,
            )
            if project_id is None:
                raise RuntimeError("Projeto duplicado não encontrado ao persistir chaves")
            await store_project_secrets(
                conn,
                project_id=project_id,
                anon_key=anon,
                service_role=service,
                config_token=config_token,
            )

        await _set_job_status(
            job_id,
            "done",
            message="Projeto duplicado com sucesso.",
            current_step="completed",
        )

    except Exception as e:
        await _set_job_status(
            job_id,
            "failed",
            message=f"Falha inesperada ao duplicar projeto: {e}",
            error_code="unexpected_duplicate_error",
        )
        print(f"Worker error: {e}")
        await rollback_project_from_db(pool, new_name)


async def execute_delete_script(project_name: str):
    if not DELETE_SCRIPT.exists():
        raise RuntimeError(f"Script não encontrado em: {DELETE_SCRIPT}")

    proc = await asyncio.create_subprocess_exec(
        "bash", str(DELETE_SCRIPT), project_name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    success = proc.returncode == 0
    return success, stdout.decode(), stderr.decode()


async def _run_command(*command: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


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
    env_path = pathlib.Path("/docker/projects") / project_name / ".env"
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


def _parse_curl_status(stdout: str) -> tuple[int | None, str]:
    body, separator, status_text = stdout.rpartition("\n")
    if not separator:
        return None, stdout
    try:
        return int(status_text.strip()), body.strip()
    except ValueError:
        return None, stdout


async def _delete_tenant_api(
    *,
    service_label: str,
    base_url: str,
    fallback_container: str,
    tenant_id: str,
    token: str,
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
        direct_error = (
            f"HTTP {response.status_code}: {response.text.strip()[:300]}"
        )
    except httpx.HTTPError as exc:
        direct_error = str(exc)

    code, stdout, stderr = await _run_command(
        "docker",
        "exec",
        fallback_container,
        "curl",
        "-sS",
        "-w",
        "\n%{http_code}",
        "-X",
        "DELETE",
        f"http://localhost:4000{path}",
        "-H",
        f"Authorization: Bearer {token}",
    )
    if code == 0:
        status, body = _parse_curl_status(stdout)
        if status in accepted_statuses:
            return None
        fallback_error = f"HTTP {status}: {body[:300]}" if status else stdout[:300]
    else:
        fallback_error = stderr or stdout or f"codigo {code}"

    return (
        f"{service_label}: falha ao remover tenant {tenant_id}; "
        f"direto={direct_error}; docker_exec={fallback_error}"
    )


async def _terminate_supavisor_pools(
    *,
    tenant_id: str,
    token: str,
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
        direct_error = (
            f"HTTP {response.status_code}: {response.text.strip()[:300]}"
        )
    except httpx.HTTPError as exc:
        direct_error = str(exc)

    code, stdout, stderr = await _run_command(
        "docker",
        "exec",
        "supabase-pooler",
        "curl",
        "-sS",
        "-w",
        "\n%{http_code}",
        f"http://localhost:4000{path}",
        "-H",
        f"Authorization: Bearer {token}",
    )
    if code == 0:
        status, body = _parse_curl_status(stdout)
        if status in accepted_statuses:
            return None
        fallback_error = (
            f"HTTP {status}: {body[:300]}" if status else stdout[:300]
        )
    else:
        fallback_error = stderr or stdout or f"codigo {code}"

    return (
        f"Supavisor: falha ao encerrar pools do tenant {tenant_id}; "
        f"direto={direct_error}; docker_exec={fallback_error}"
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

    await report(5, "load_project_state", "Carregando estado do projeto...")
    project_env = _load_project_env(project_name)
    project_uuid = (
        project_env.get("PROJECT_UUID", "").strip()
        or get_project_uuid_from_env(project_name)
    )
    tenant_external_id = project_uuid if project_uuid else project_name

    if project_uuid:
        print(f"Deletando projeto com UUID: {project_uuid}")
    else:
        print(
            "Deletando projeto antigo (sem UUID), "
            f"usando project_name: {project_name}"
        )

    await report(15, "remove_containers", "Removendo containers do projeto...")
    containers = await get_project_containers(project_name)
    for container in containers:
        container_name = container.get("Names", "")
        if not container_name:
            continue

        code, _, stderr = await _run_command(
            "docker", "rm", "-f", container_name
        )
        if code != 0:
            errors.append(
                f"Erro ao remover {container_name}: {stderr or f'codigo {code}'}"
            )

    await report(30, "remove_tenants", "Removendo tenants globais...")
    supavisor_token = _build_global_delete_token(tenant_external_id)
    supavisor_terminate_error = await _terminate_supavisor_pools(
        tenant_id=project_name,
        token=supavisor_token,
    )
    realtime_error = await _delete_tenant_api(
        service_label="Realtime",
        base_url=REALTIME_INTERNAL_URL,
        fallback_container="realtime-dev.supabase-realtime",
        tenant_id=tenant_external_id,
        token=_build_realtime_delete_token(project_env, tenant_external_id),
    )

    supavisor_error = await _delete_tenant_api(
        service_label="Supavisor",
        base_url=SUPAVISOR_INTERNAL_URL,
        fallback_container="supabase-pooler",
        tenant_id=project_name,
        token=supavisor_token,
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
        success, stdout, stderr = await execute_delete_script(project_name)
        if not success:
            detail = stderr.strip() or stdout.strip() or "erro desconhecido"
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
    except Exception as exc:
        message = f"Falha ao excluir projeto: {exc}"
        await _set_job_status(
            job_id,
            "failed",
            message=message,
            error_code="delete_failed",
        )
        print(f"[delete_project] {project_name}: background task failed: {exc}")

def get_project_uuid_from_env(project_name: str) -> Optional[str]:
    try:
        env_path = pathlib.Path("/docker/projects") / project_name / ".env"
        
        if not env_path.exists():
            print(f"Arquivo .env não encontrado em: {env_path}")
            return None
        
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('PROJECT_UUID='):
                    uuid_value = line.split('=', 1)[1].strip()
                    if uuid_value:
                        print(f"PROJECT_UUID encontrado: {uuid_value}")
                        return uuid_value
        
        print(f"PROJECT_UUID não encontrado no .env de {project_name}")
        return None
    except Exception as e:
        print(f"Erro ao ler PROJECT_UUID do .env: {e}")
        return None

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
                errors.append(f"terminate {slot}: {exc}")

    async def drop_slot(slot: str) -> None:
        try:
            await conn.execute("SELECT pg_drop_replication_slot($1)", slot)
        except Exception as exc:
            if "does not exist" not in str(exc):
                errors.append(f"drop {slot}: {exc}")

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
        project_exists = await conn.fetchval(
            "SELECT 1 FROM projects WHERE name = $1",
            project_name,
        )
        if not project_exists:
            raise HTTPException(404, "Project not found")

    job_id = await _create_project_job(
        pool,
        project_name,
        auth_user["db_user_id"],
        message="Exclusão enfileirada.",
        action="delete",
        payload={"project_name": project_name},
        total_steps=8,
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
        if not ROTATE_SCRIPT.exists():
            raise RuntimeError(f"Rotate script não encontrado: {ROTATE_SCRIPT}")

        proc = await asyncio.create_subprocess_exec(
            "bash", str(ROTATE_SCRIPT), project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            stdout_text = stdout.decode().strip()
            stderr_text = stderr.decode().strip()
            print(f"[rotate-key] stdout for {project_name}: {stdout_text}")
            print(f"[rotate-key] stderr for {project_name}: {stderr_text}")
            detail = (
                stderr_text or stdout_text or "rotate script exited with no output"
            )
            await _set_job_status(
                job_id,
                "failed",
                message=f"Rotate failed: {detail}",
                stdout_tail=stdout_text,
                stderr_tail=stderr_text,
                error_code="rotate_script_failed",
            )
            return

        lines = stdout.decode().splitlines()
        kv = {
            k: v
            for k, v in (line.split("=", 1) for line in lines if "=" in line)
        }
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        if not anon or not service:
            await _set_job_status(
                job_id,
                "failed",
                message="Keys not returned from script",
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
        pool = await get_pool()
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
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message=f"Falha na rotação: {exc}",
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

@app.get("/api/projects/internal/enc-key/{ref}")
async def enc_key(
    ref: str,
    request: Request,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id, service_role, project_key_version
                FROM projects WHERE name=$1
                """,
                ref,
            )
            if not row or not row["service_role"]:
                raise HTTPException(status_code=404, detail="Project not found")
            service_key = await decrypt_project_secret(
                conn,
                project_id=row["id"],
                column="service_role",
                ciphertext=row["service_role"],
            )

    return {
        "enc_service_key": service_key_transport_fernet.encrypt(
            service_key.encode()
        ).decode(),
        "project_key_version": row["project_key_version"],
    }


@app.get("/api/projects/internal/key-version/{ref}")
async def project_key_version(
    ref: str,
    request: Request,
    pool=Depends(get_pool),
):
    ref = validate_project_id(ref)
    if request.headers.get("X-Internal-Service") != "studio-nginx":
        raise HTTPException(403, "Internal service access required")
    version = await pool.fetchval(
        "SELECT project_key_version FROM projects WHERE name = $1",
        ref,
    )
    if version is None:
        raise HTTPException(404, "Project not found")
    return {"project_key_version": version}

async def _provision_and_store_keys(job_id: str, project_name: str, user: uuid.UUID):
    pool = await get_pool()
    await _set_job_status(
        job_id,
        "running",
        message="Provisionando infraestrutura do projeto...",
        progress=5,
        current_step="provision_infrastructure",
        total_steps=3,
    )

    try:
        project_uuid = str(uuid.uuid4())
        
        proc = await asyncio.create_subprocess_exec(
            "bash", str(SCRIPT), project_name, project_uuid,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            output = stdout.decode(errors="replace")
            await _set_job_status(
                job_id,
                "failed",
                message="Falha ao provisionar infraestrutura",
                stdout_tail=output,
                error_code="provision_failed",
            )
            print(output)
            await rollback_project_from_db(pool, project_name)
            return

        await _set_job_status(
            job_id,
            "running",
            message="Extraindo chaves do projeto...",
            progress=70,
            current_step="extract_keys",
        )
        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            error_output = err2.decode(errors="replace")
            await _set_job_status(
                job_id,
                "failed",
                message="Falha ao extrair chaves",
                stderr_tail=error_output,
                error_code="key_extraction_failed",
            )
            print(error_output)
            await rollback_project_from_db(pool, project_name)
            return

        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        config_token = kv.get("CONFIG_TOKEN_PROJETO")
        if not anon or not service or not config_token:
            await _set_job_status(
                job_id,
                "failed",
                message="Chaves obrigatórias ausentes",
                error_code="missing_keys",
            )
            print("Missing tokens")
            await rollback_project_from_db(pool, project_name)
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
                "SELECT id FROM projects WHERE name = $1 AND owner_id = $2",
                project_name,
                user,
            )
            if project_id is None:
                raise RuntimeError("Projeto não encontrado ao persistir chaves")
            await store_project_secrets(
                conn,
                project_id=project_id,
                anon_key=anon,
                service_role=service,
                config_token=config_token,
            )

        await _set_job_status(
            job_id,
            "done",
            message="Projeto criado com sucesso.",
            current_step="completed",
        )

    except Exception as e:
        await _set_job_status(
            job_id,
            "failed",
            message=f"Falha inesperada ao criar projeto: {e}",
            error_code="unexpected_create_error",
        )
        print(f"Worker error: {e}")
        await rollback_project_from_db(pool, project_name)

def _name_matches(cont_json: dict, project: str) -> bool:
    patt = re.compile(rf"-{re.escape(project)}$")
    names = cont_json.get("Names", "")
    if isinstance(names, str):
        return any(patt.search(n) for n in names.split(","))
    return any(patt.search(n) for n in names)

async def get_project_containers(project: str) -> list[dict]:
    proc = await asyncio.create_subprocess_exec(
        "docker", "ps", "--format", "{{json .}}", "-a",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = stdout.decode().splitlines()
    containers = [json.loads(l) for l in lines if _name_matches(json.loads(l), project)]
    return containers


PROJECT_SERVICE_ORDER = ["meta", "auth", "rest", "imgproxy", "storage", "nginx"]


def _get_project_service_priority(name: str) -> int:
    lowered = name.lower()
    for idx, service in enumerate(PROJECT_SERVICE_ORDER):
        if service in lowered:
            return idx
    return 999


def _sort_project_containers(containers: list[dict]) -> list[dict]:
    return sorted(
        containers,
        key=lambda container: _get_project_service_priority(
            container.get("Names", "")
        ),
    )


def _services_touch_project_nginx(services: list[str]) -> bool:
    return any(service.strip().lower() == "nginx" for service in services)


def _containers_touch_project_nginx(containers: list[dict]) -> bool:
    return any("nginx" in container.get("Names", "").lower() for container in containers)


def _get_root_env_path() -> pathlib.Path:
    return BASE_DIR / ".env"


def _get_project_env_path(project_name: str) -> pathlib.Path:
    return pathlib.Path("/docker/projects") / project_name / ".env"


def _get_project_dir(project_name: str) -> pathlib.Path:
    return pathlib.Path("/docker/projects") / project_name


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
    env_path = _get_project_env_path(project_name)
    try:
        values = _read_env_file(env_path)
    except Exception:
        return "524288000"

    value = str(values.get("FILE_SIZE_LIMIT", "")).strip()
    if re.fullmatch(r"\d+", value) and int(value) > 0:
        return value
    return "524288000"


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


def _normalize_public_base_url(url: str, proto: str | None = None) -> str:
    normalized = url.rstrip("/")
    if not re.match(r"^https?://", normalized):
        normalized_proto = (proto or "").strip().lower()
        if normalized_proto in {"http", "https"}:
            normalized = f"{normalized_proto}://{normalized}"
        else:
            normalized = f"https://{normalized}"
    return normalized


def _read_env_file(env_path: pathlib.Path) -> dict[str, str]:
    return {k: (v or "") for k, v in dotenv_values(env_path).items()}


def _read_existing_env_file(env_path: pathlib.Path, missing_message: str) -> dict[str, str]:
    if not env_path.exists():
        raise RuntimeError(missing_message)
    return _read_env_file(env_path)


def _render_generated_template(
    template_path: pathlib.Path,
    output_path: pathlib.Path,
    replacements: dict[str, str],
) -> None:
    content = template_path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


def _get_project_template_replacements(project_name: str) -> dict[str, str]:
    root_env_path = _get_root_env_path()
    project_env_path = _get_project_env_path(project_name)

    root_env = _read_existing_env_file(
        root_env_path,
        "Arquivo .env raiz não encontrado",
    )
    project_env = _read_existing_env_file(
        project_env_path,
        f"Arquivo .env não encontrado para o projeto '{project_name}'",
    )

    server_url = root_env.get("SERVER_URL", "").strip()
    server_proto = root_env.get("SERVER_PROTO", "").strip()
    host_project_root = root_env.get("HOST_PROJECT_ROOT", "").strip()
    if not server_url:
        raise RuntimeError("SERVER_URL ausente no .env raiz")
    if not host_project_root:
        raise RuntimeError("HOST_PROJECT_ROOT ausente no .env raiz")

    required_project_keys = (
        "ANON_KEY_PROJETO",
        "SERVICE_ROLE_KEY_PROJETO",
        "CONFIG_TOKEN_PROJETO",
        "JWT_SECRET_PROJETO",
    )
    missing_project_keys = [
        key for key in required_project_keys if not project_env.get(key, "").strip()
    ]
    if missing_project_keys:
        joined = ", ".join(missing_project_keys)
        raise RuntimeError(
            f".env do projeto '{project_name}' sem chaves obrigatórias: {joined}"
        )

    public_base_url = _normalize_public_base_url(server_url, server_proto)
    project_public_url = f"{public_base_url}/{project_name}"
    project_auth_external_url = f"{project_public_url}/auth/v1"

    return {
        "anon_key": project_env["ANON_KEY_PROJETO"],
        "service_role_key": project_env["SERVICE_ROLE_KEY_PROJETO"],
        "project_id": project_name,
        "project_uuid": project_env.get("PROJECT_UUID") or project_name,
        "config_token": project_env["CONFIG_TOKEN_PROJETO"],
        "jwt_secret": project_env["JWT_SECRET_PROJETO"],
        "server_url": server_url,
        "public_base_url": public_base_url,
        "project_public_url": project_public_url,
        "project_auth_external_url": project_auth_external_url,
        "project_root": host_project_root,
    }


def _sync_project_nginx_generated_files(project_name: str) -> None:
    project_dir = _get_project_dir(project_name)
    if not project_dir.exists():
        raise RuntimeError(f"Diretório do projeto '{project_name}' não encontrado")

    script_dir = BASE_DIR / "scripts"
    replacements = _get_project_template_replacements(project_name)

    nginx_config_path = project_dir / "nginx" / f"nginx_{project_name}.conf"
    _render_generated_template(
        script_dir / "nginxtemplate",
        nginx_config_path,
        replacements,
    )
    nginx_config_path.chmod(0o600)
    _render_generated_template(
        script_dir / "Dockerfile",
        project_dir / "Dockerfile",
        replacements,
    )
    _render_generated_template(
        script_dir / "dockercomposetemplate",
        project_dir / "docker-compose.yml",
        replacements,
    )


async def _stop_project_containers(
    project_name: str,
    containers: list[dict],
    *,
    job_id: str | None = None,
) -> dict:
    stopped_containers: list[str] = []
    errors: list[str] = []

    sorted_containers = _sort_project_containers(containers)
    for index, container in enumerate(sorted_containers, start=1):
        container_name = container.get("Names", "")
        container_status = container.get("State", "")

        try:
            if container_status == "running":
                proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "stop",
                    container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode == 0:
                    stopped_containers.append(container_name)
                else:
                    errors.append(
                        f"Error stopping {container_name}: {stderr.decode().strip()}"
                    )
            else:
                stopped_containers.append(f"{container_name} (already stopped)")
        except Exception as exc:
            errors.append(f"Error stopping {container_name}: {exc}")

        if job_id:
            await _set_job_status(
                job_id,
                "running",
                message=f"Parando containers ({index}/{len(sorted_containers)})...",
                progress=min(95, int(index * 95 / max(len(sorted_containers), 1))),
                current_step=f"stop_container:{container_name}",
                total_steps=max(len(sorted_containers), 1),
            )

    return {
        "project": project_name,
        "stopped_containers": stopped_containers,
        "errors": errors,
        "success": len(errors) == 0,
    }


async def _stop_project_containers_background(
    job_id: str,
    project_name: str,
    containers: list[dict],
) -> None:
    await _set_job_status(
        job_id,
        "running",
        message="Parando servicos do projeto...",
        progress=1,
        current_step="load_containers",
    )
    try:
        result = await _stop_project_containers(
            project_name,
            containers,
            job_id=job_id,
        )
        if result["errors"]:
            message = "\n".join(result["errors"])
            await _set_job_status(
                job_id,
                "failed",
                message=message,
                error_code="stop_failed",
            )
            print(
                f"[stop_project] {project_name}: "
                + " | ".join(result["errors"])
            )
            return

        await _set_job_status(
            job_id,
            "done",
            message="Projeto parado com sucesso.",
            current_step="completed",
        )
    except Exception as exc:
        message = f"Falha ao parar projeto: {exc}"
        await _set_job_status(
            job_id,
            "failed",
            message=message,
            error_code="stop_failed",
        )
        print(f"[stop_project] {project_name}: background task failed: {exc}")


async def _recreate_project_services_impl(
    project_name: str,
    services: list[str],
) -> dict:
    project_dir = _get_project_dir(project_name)
    if not project_dir.exists():
        raise HTTPException(404, f"Diretório do projeto '{project_name}' não encontrado")

    errors: list[str] = []

    compose_base = [
        "docker", "compose",
        "-p", project_name,
        "--env-file", "../../.env",
        "--env-file", ".env",
    ]

    if _services_touch_project_nginx(services):
        _sync_project_nginx_generated_files(project_name)

    step_cmd = compose_base + ["up", "-d"]
    if _services_touch_project_nginx(services):
        step_cmd.append("--build")
    step_cmd.append("--force-recreate")
    step_cmd += services
    proc = await asyncio.create_subprocess_exec(
        *step_cmd,
        cwd=str(project_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        errors.append(f"Erro no recreate: {stderr.decode().strip()}")

    return {
        "project": project_name,
        "recreated_services": services if not errors else [],
        "errors": errors,
        "success": len(errors) == 0,
    }


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
        result = await _recreate_project_services_impl(project_name, services)
        if result["errors"]:
            message = "\n".join(result["errors"])
            await _set_job_status(
                job_id,
                "failed",
                message=message,
                error_code="recreate_failed",
            )
            print(
                f"[recreate_project_services] {project_name}: "
                + " | ".join(result["errors"])
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
    except Exception as exc:
        message = f"Falha ao recriar servicos: {exc}"
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

async def get_project_status(project_name: str) -> dict:
    containers = await get_project_containers(project_name)

    if not containers:
        return {"status": "not_found", "containers": []}

    container_info = []
    running_count = 0

    for container in containers:
        c_status = container.get("State", "unknown")
        if c_status == "running":
            running_count += 1

        container_info.append({
            "name": container.get("Names", ""),
            "status": c_status,
            "image": container.get("Image", "unknown"),
            "created": container.get("CreatedAt", ""),
            "ports": container.get("Ports", "")
        })

    total_containers = len(containers)
    if running_count == 0:
        overall_status = "stopped"
    elif running_count == total_containers:
        overall_status = "running"
    else:
        overall_status = "partial"

    return {
        "status": overall_status,
        "containers": container_info,
        "running": running_count,
        "total": total_containers
    }


@app.get("/api/projects/{project_name}/status")
async def get_project_docker_status(
    project_name: str,
    request: Request,
    pool=Depends(get_pool)
):
    project_name = validate_project_id(project_name)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_member_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )
        project_role = await get_project_role(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
        )

    status_info = await get_project_status(project_name)
    if project_role != "admin" and not auth_user["is_global_admin"]:
        status_info.pop("containers", None)
    return status_info

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
            containers,
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
            job_id, project_name, containers, auth_user["db_user_id"]
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
    containers: list[dict],
    actor_user_id: uuid.UUID,
) -> None:
    await _set_job_status(
        job_id,
        "running",
        message="Iniciando containers...",
        progress=1,
        current_step="load_containers",
        total_steps=max(len(containers), 1),
    )
    try:
        sorted_containers = _sort_project_containers(containers)
        started_containers: list[str] = []
        errors: list[str] = []
        for index, container in enumerate(sorted_containers, start=1):
            container_name = container.get("Names", "")
            container_status = container.get("State", "")
            try:
                if container_status != "running":
                    proc = await asyncio.create_subprocess_exec(
                        "docker", "start", container_name,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await proc.communicate()
                    if proc.returncode == 0:
                        started_containers.append(container_name)
                        await asyncio.sleep(2)
                    else:
                        errors.append(
                            f"Error starting {container_name}: "
                            f"{stderr.decode().strip()}"
                        )
                else:
                    started_containers.append(f"{container_name} (already running)")
            except Exception as exc:
                errors.append(f"Error starting {container_name}: {exc}")

            await _set_job_status(
                job_id,
                "running",
                message=f"Iniciando containers ({index}/{len(sorted_containers)})...",
                progress=min(95, int(index * 95 / max(len(sorted_containers), 1))),
                current_step=f"start_container:{container_name}",
            )

        if errors:
            await _set_job_status(
                job_id,
                "failed",
                message="\n".join(errors),
                error_code="start_failed",
            )
            return
        await _set_job_status(
            job_id,
            "done",
            message=f"Iniciado: {', '.join(started_containers)}",
            current_step="completed",
        )
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message=f"Falha ao iniciar: {exc}",
            error_code="start_failed",
        )
        print(f"[start_project] {project_name}: {exc}")


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
            job_id, project_name, containers, auth_user["db_user_id"]
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
    containers: list[dict],
    actor_user_id: uuid.UUID,
) -> None:
    await _set_job_status(
        job_id,
        "running",
        message="Reiniciando containers...",
        progress=1,
        current_step="load_containers",
        total_steps=max(len(containers), 1),
    )
    try:
        sorted_containers = _sort_project_containers(containers)
        restarted_containers: list[str] = []
        errors: list[str] = []
        for index, cont in enumerate(sorted_containers, start=1):
            name = cont.get("Names", "")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "docker",
                    "restart",
                    "-t",
                    "30",
                    name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0:
                    restarted_containers.append(name)
                    await asyncio.sleep(2)
                else:
                    errors.append(
                        f"Error restarting {name}: {stderr.decode().strip()}"
                    )
            except Exception as exc:
                errors.append(f"Error restarting {name}: {exc}")

            await _set_job_status(
                job_id,
                "running",
                message=f"Reiniciando containers ({index}/{len(sorted_containers)})...",
                progress=min(95, int(index * 95 / max(len(sorted_containers), 1))),
                current_step=f"restart_container:{name}",
            )

        if errors:
            await _set_job_status(
                job_id,
                "failed",
                message="\n".join(errors),
                error_code="restart_failed",
            )
            return
        await _set_job_status(
            job_id,
            "done",
            message=f"Reiniciado: {', '.join(restarted_containers)}",
            current_step="completed",
        )
    except Exception as exc:
        await _set_job_status(
            job_id,
            "failed",
            message=f"Falha ao reiniciar: {exc}",
            error_code="restart_failed",
        )
        print(f"[restart_project] {project_name}: {exc}")

MAX_LOG_LINES = 1000

@app.get("/api/projects/{project_name}/logs/{service}")
async def get_container_logs(
    project_name: str,
    service: str,
    request: Request,
    pool=Depends(get_pool),
    lines: int = Query(100, ge=1, le=MAX_LOG_LINES)
):
    project_name = validate_project_id(project_name)
    service = validate_service_name(service)

    async with pool.acquire() as conn:
        auth_user = await resolve_authenticated_user(request, pool)
        project_row = await get_project_row(conn, project_name)
        await ensure_project_admin_access(
            conn,
            project_id=project_row["id"],
            auth_user=auth_user,
            message="Apenas admins podem consultar logs do projeto",
        )
        project_id = project_row["id"]

    container_name = f"supabase-{service}-{project_name}"

    try:
        proc_check = await asyncio.create_subprocess_exec(
            "docker", "inspect", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_check, stderr_check = await proc_check.communicate()

        if proc_check.returncode != 0:
            raise HTTPException(404, f"Container {container_name} not found")

        proc_logs = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), "--timestamps", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout_logs, _ = await proc_logs.communicate()

        if proc_logs.returncode != 0:
            raise HTTPException(500, "Error getting container logs")

        container_info = json.loads(stdout_check.decode())[0]
        c_status = container_info.get("State", {}).get("Status", "unknown")

        async with pool.acquire() as conn:
            await audit_studio_action(
                conn,
                project_id=project_id,
                actor_user_id=auth_user["db_user_id"],
                action="project_logs_read",
                target_type="container_logs",
                target_id=container_name,
                new_value={"service": service, "lines": lines},
            )

        return {
            "container": container_name,
            "logs": stdout_logs.decode("utf-8", errors="replace"),
            "status": c_status
        }

    except HTTPException:
        raise
    except Exception as exc:
        print(f"[project_logs] {project_name}/{service}: {exc}")
        raise HTTPException(500, "Error accessing container logs") from exc

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
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao acessar postgres-meta global: {exc}",
        )

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
