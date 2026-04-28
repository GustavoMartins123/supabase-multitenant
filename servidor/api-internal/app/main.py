import os
import uuid
import pathlib
import asyncpg
import hmac
import asyncio, json, re
from fastapi import FastAPI, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
from typing import Any, Optional, List, Dict
from dotenv import dotenv_values

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "generate_project.sh"
DUPLICATE_SCRIPT = BASE_DIR / "scripts" / "duplicate_project.sh"
ROTATE_SCRIPT = BASE_DIR / "scripts" / "rotate_key.sh"
DELETE_SCRIPT = BASE_DIR / "scripts" / "delete_project.sh"
EXTRACTOR = BASE_DIR / "scripts" / "extract_token.sh"
DB_DSN = os.getenv("DB_DSN")
FERNET_SECRET = os.getenv("FERNET_SECRET")
DELETE_PASSWORD = os.getenv("PROJECT_DELETE_PASSWORD")
NGINX_SHARED_TOKEN = os.getenv("NGINX_SHARED_TOKEN")

if not FERNET_SECRET:
    raise RuntimeError("Missing FERNET_SECRET environment variable")
if not NGINX_SHARED_TOKEN:
    raise RuntimeError("Missing NGINX_SHARED_TOKEN environment variable")
    
try:
    fernet = Fernet(FERNET_SECRET.encode())
except ValueError:
    raise RuntimeError(
        "Invalid FERNET_SECRET: must be a 32-byte url-safe base64-encoded key, "
        "generated via Fernet.generate_key()."
    )

JOB_STATUS: dict[str, str] = {}
JOB_DETAILS: dict[str, dict[str, Any]] = {}

db_pool: Optional[asyncpg.Pool] = None


def normalize_groups(raw_groups: list[str] | tuple[str, ...] | str | None) -> list[str]:
    if isinstance(raw_groups, str):
        values = raw_groups.split(",")
    else:
        values = raw_groups or []

    normalized: list[str] = []
    seen: set[str] = set()
    for group in values:
        clean = (group or "").strip().lower()
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return normalized


def parse_uuid_value(raw: str | None) -> uuid.UUID | None:
    candidate = (raw or "").strip()
    if not candidate:
        return None

    try:
        return uuid.UUID(candidate)
    except ValueError:
        return None


async def ensure_identity_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                authelia_username TEXT UNIQUE NOT NULL,
                display_name TEXT,
                authelia_groups TEXT[] NOT NULL DEFAULT '{}'::text[],
                is_active BOOLEAN NOT NULL DEFAULT true,
                source TEXT NOT NULL DEFAULT 'authelia',
                last_login_at TIMESTAMPTZ,
                last_sync_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS user_groups (
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                group_name TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'authelia',
                synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (user_id, group_name)
            );

            CREATE TABLE IF NOT EXISTS user_group_audit (
                id BIGSERIAL PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                group_name TEXT NOT NULL,
                action TEXT NOT NULL,
                old_value JSONB,
                new_value JSONB,
                actor_type TEXT NOT NULL DEFAULT 'system',
                actor_user_id UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE TABLE IF NOT EXISTS project_members_audit (
                id BIGSERIAL PRIMARY KEY,
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                target_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                old_role TEXT,
                new_role TEXT,
                action TEXT NOT NULL,
                actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            ALTER TABLE projects
                ADD COLUMN IF NOT EXISTS owner_uuid UUID REFERENCES users(id) ON DELETE SET NULL;

            ALTER TABLE project_members
                ADD COLUMN IF NOT EXISTS user_uuid UUID REFERENCES users(id) ON DELETE SET NULL;

            CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);
            CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);
            CREATE INDEX IF NOT EXISTS idx_projects_owner_uuid ON projects(owner_uuid);
            CREATE INDEX IF NOT EXISTS idx_project_members_user_uuid ON project_members(user_uuid);
            CREATE INDEX IF NOT EXISTS idx_project_members_audit_project_id ON project_members_audit(project_id);
            """
        )


async def audit_user_group_change(
    conn: asyncpg.Connection,
    *,
    user_id: str,
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
        SELECT id, authelia_groups
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
                authelia_groups = $3,
                is_active = $4,
                source = $5,
                last_sync_at = now(),
                updated_at = now()
            WHERE id = $6
            """,
            normalized_username,
            display_name,
            normalized_groups,
            is_active,
            source,
            user_id,
        )
    else:
        user_id = await conn.fetchval(
            """
            INSERT INTO users(
                id, authelia_username, display_name,
                authelia_groups, is_active, source
            )
            VALUES($1, $2, $3, $4, $5, $6)
            RETURNING id
            """,
            user_id,
            normalized_username,
            display_name,
            normalized_groups,
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

async def get_pool():
    """Retorna o pool global de conexões"""
    global db_pool
    if db_pool is None:
        raise RuntimeError("Database pool not initialized")
    return db_pool


def _set_job_message(job_id: str, message: str | None) -> None:
    if message is None:
        return
    JOB_DETAILS.setdefault(job_id, {})["message"] = message


async def _set_job_status(
    job_id: str,
    new_status: str,
    *,
    message: str | None = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE jobs SET status=$1, updated_at=now() WHERE job_id=$2",
            new_status,
            job_id,
        )
    _set_job_message(job_id, message)


async def _create_project_job(
    pool,
    project_name: str,
    user: str,
    *,
    message: str | None = None,
) -> str:
    job_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO jobs(job_id, project, owner_id, status)
               VALUES($1, $2, $3, 'queued')""",
            job_id,
            project_name,
            user,
        )
    _set_job_message(job_id, message)
    return job_id

async def rollback_project_from_db(pool, project_name: str):
    """Remove projeto do banco em caso de falha na criação/duplicação"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM projects WHERE name = $1", project_name)
        print(f"Rollback: Projeto '{project_name}' removido do banco")
    except Exception as e:
        print(f"Erro no rollback do banco: {e}")


RESERVED_WORDS = {
    'select','from','where','insert','update','delete','table',
    'create','drop','join','group','order','limit','into','index',
    'view','trigger','procedure','function','database','schema',
    'primary','foreign','key','constraint','unique','null','not',
    'and','or','in','like','between','exists','having','union',
    'inner','left','right','outer','cross','on','as','case','when',
    'then','else','end','if','while','for','begin','commit','rollback'
}

_VALID_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
_VALID_SERVICE_RE = re.compile(r"^[a-z][a-z0-9\-]{0,39}$")

def validate_project_id(raw: str) -> str:
    name = raw.strip().lower()
    if not _VALID_RE.fullmatch(name):
        raise HTTPException(
            400,
            "Nome inválido: use letras minúsculas, números ou '_', "
            "(3–40 caracteres, começando por letra ou '_').",
        )
    if name in RESERVED_WORDS:
        raise HTTPException(400, "Nome inválido: palavra reservada SQL.")
    return name

def validate_service_name(raw: str) -> str:
    name = raw.strip().lower()
    if not _VALID_SERVICE_RE.fullmatch(name):
        raise HTTPException(
            400,
            "Nome de serviço inválido: use apenas letras minúsculas, números ou '-'.",
        )
    return name

app = FastAPI()

@app.on_event("startup")
async def startup():
    """Inicializa o pool de conexões no startup da aplicação"""
    global db_pool
    db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=10)
    await ensure_identity_schema(db_pool)
    print("✅ Database pool initialized")

@app.on_event("shutdown")
async def shutdown():
    """Fecha o pool de conexões no shutdown da aplicação"""
    global db_pool
    if db_pool:
        await db_pool.close()
        print("✅ Database pool closed")

@app.middleware("http")
async def validate_shared_token(request: Request, call_next):
    """
    Valida que a requisição vem do Nginx através do token compartilhado.
    Esta é uma camada adicional de segurança.
    O Traefik já valida o header, mas validamos novamente aqui.
    """
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

class NewProject(BaseModel):
    name: str

class DuplicateProject(BaseModel):
    original_name: str
    new_name: str
    copy_data: bool = False


class UserSyncPayload(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None = None
    groups: List[str] = Field(default_factory=list)
    is_active: bool = True
    source: str = "studio_sync"


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
    header_user_id = parse_uuid_value(request.headers.get("X-User-Id"))
    if header_user_id is None:
        raise HTTPException(401, "X-User-Id ausente ou inválido")

    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            """
            SELECT id, authelia_username, display_name, authelia_groups, is_active
            FROM users
            WHERE id = $1
            """,
            header_user_id,
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

    groups = normalize_groups(user_row["authelia_groups"])
    return {
        "db_user_id": user_row["id"],
        "user_id_text": str(user_row["id"]),
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
        "SELECT id, owner_id, owner_uuid FROM projects WHERE name = $1",
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
          AND (user_uuid = $2 OR user_id = $3)
        ORDER BY CASE WHEN user_uuid = $2 THEN 0 ELSE 1 END
        LIMIT 1
        """,
        project_id,
        auth_user["db_user_id"],
        auth_user["user_id_text"],
    )


async def get_project_member_row(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    user_uuid: uuid.UUID | None,
    user_key: str | None,
) -> asyncpg.Record | None:
    return await conn.fetchrow(
        """
        SELECT user_id, user_uuid, role
        FROM project_members
        WHERE project_id = $1
          AND (user_uuid = $2 OR user_id = $3)
        ORDER BY
            CASE WHEN user_uuid = $2 THEN 0 ELSE 1 END,
            CASE WHEN user_id = $3 THEN 0 ELSE 1 END
        LIMIT 1
        """,
        project_id,
        user_uuid,
        user_key,
    )


async def upsert_project_member(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    user_uuid: uuid.UUID,
    user_key: str,
    role: str,
) -> str | None:
    matching_rows = await conn.fetch(
        """
        SELECT user_id, user_uuid, role
        FROM project_members
        WHERE project_id = $1
          AND (user_uuid = $2 OR user_id = $3)
        ORDER BY
            CASE WHEN user_id = $3 THEN 0 ELSE 1 END,
            CASE WHEN user_uuid = $2 THEN 0 ELSE 1 END,
            user_id
        """,
        project_id,
        user_uuid,
        user_key,
    )

    if not matching_rows:
        await conn.execute(
            """
            INSERT INTO project_members(project_id, user_id, user_uuid, role)
            VALUES($1, $2, $3, $4)
            """,
            project_id,
            user_key,
            user_uuid,
            role,
        )
        return None

    canonical = matching_rows[0]
    await conn.execute(
        """
        UPDATE project_members
        SET user_id = $3,
            user_uuid = $4,
            role = $5
        WHERE project_id = $1
          AND user_id = $2
        """,
        project_id,
        canonical["user_id"],
        user_key,
        user_uuid,
        role,
    )

    stale_user_ids = [row["user_id"] for row in matching_rows[1:]]
    if stale_user_ids:
        await conn.execute(
            """
            DELETE FROM project_members
            WHERE project_id = $1
              AND user_id = ANY($2::text[])
            """,
            project_id,
            stale_user_ids,
        )

    return canonical["role"]


async def ensure_project_member_access(
    conn: asyncpg.Connection,
    *,
    project_id: str,
    auth_user: dict[str, Any],
) -> None:
    in_project = await conn.fetchval(
        """
        SELECT 1
        FROM project_members
        WHERE project_id = $1
          AND (user_uuid = $2 OR user_id = $3)
        LIMIT 1
        """,
        project_id,
        auth_user["db_user_id"],
        auth_user["user_id_text"],
    )
    if not in_project and not auth_user["is_global_admin"]:
        raise HTTPException(403, "Acesso negado: você não é membro deste projeto")


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
    target_user_id: str | None,
    old_role: str | None,
    new_role: str | None,
    action: str,
    actor_user_id: str | None,
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

@app.get("/api/projects")
async def list_projects(
    request: Request,
    pool=Depends(get_pool)
):
    auth_user = await resolve_authenticated_user(request, pool)

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.name, p.anon_key, p.config_token
            FROM projects p
            WHERE p.anon_key IS NOT NULL
              AND EXISTS (
                  SELECT 1
                  FROM project_members m
                  WHERE m.project_id = p.id
                    AND (m.user_uuid = $1 OR m.user_id = $2)
              )
            ORDER BY p.name
        """, auth_user["db_user_id"], auth_user["user_id_text"])
    result = []
    for r in rows:
        anon_token = fernet.decrypt(r["anon_key"].encode()).decode()
        config_token = fernet.decrypt(r["config_token"].encode()).decode() if r["config_token"] else None
        result.append({
            "name": r["name"], 
            "anon_token": anon_token,
            "config_token": config_token
        })
    return result

@app.post("/api/projects", status_code=202)
async def create_project(
    body: NewProject,
    tasks: BackgroundTasks,
    request: Request,
    pool=Depends(get_pool),
):
    name = validate_project_id(body.name)

    if not name:
        raise HTTPException(400, "name required")

    auth_user = await resolve_authenticated_user(request, pool)
    job_id = str(uuid.uuid4())
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
                    INSERT INTO projects(name, owner_id, owner_uuid)
                    VALUES($1, $2, $3)
                    RETURNING id
                    """,
                    name, auth_user["user_id_text"], auth_user["db_user_id"]
                )
            await conn.execute(
                    """
                    INSERT INTO project_members(project_id, user_id, user_uuid, role)
                    VALUES($1, $2, $3, 'admin')
                    """,
                    project_id, auth_user["user_id_text"], auth_user["db_user_id"]
                )
            await conn.execute(
                """INSERT INTO jobs(job_id, project, owner_id, status)
                   VALUES($1, $2, $3, 'queued')""",
                job_id, name, auth_user["user_id_text"]
            )

    tasks.add_task(_provision_and_store_keys, job_id, name, auth_user["user_id_text"])
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/projects/duplicate", status_code=202)
async def duplicate_project(
    body: DuplicateProject,
    tasks: BackgroundTasks,
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
                INSERT INTO projects(name, owner_id, owner_uuid)
                VALUES($1, $2, $3) RETURNING id
            """, new_name, auth_user["user_id_text"], auth_user["db_user_id"])

            await conn.execute("""
                INSERT INTO project_members(project_id, user_id, user_uuid, role)
                VALUES($1, $2, $3, 'admin')
            """, project_id, auth_user["user_id_text"], auth_user["db_user_id"])

            job_id = str(uuid.uuid4())
            await conn.execute(
                """INSERT INTO jobs(job_id, project, owner_id, status)
                   VALUES($1, $2, $3, 'queued')""",
                job_id, new_name, auth_user["user_id_text"]
            )

    tasks.add_task(
        _duplicate_and_store_keys,
        job_id,
        original,
        new_name,
        auth_user["user_id_text"],
        body.copy_data,
    )

    return {"job_id": job_id, "status": "queued"}


async def _duplicate_and_store_keys(job_id: str, original_name: str, new_name: str, owner_id: str, copy_data: bool):
    pool = await get_pool()
    async def set_status(st: str):
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE jobs SET status=$1, updated_at=now() WHERE job_id=$2",
                st, job_id
            )

    await set_status("running")

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
            await set_status("failed")
            print(stdout.decode())
            await rollback_project_from_db(pool, new_name)
            return

        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), new_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            await set_status("failed")
            print(err2.decode())
            await rollback_project_from_db(pool, new_name)
            return

        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        config_token = kv.get("CONFIG_TOKEN_PROJETO")
        if not anon or not service or not config_token:
            await set_status("failed")
            print("Missing tokens")
            await rollback_project_from_db(pool, new_name)
            return

        anon_enc = fernet.encrypt(anon.encode()).decode()
        svc_enc  = fernet.encrypt(service.encode()).decode()
        config_enc = fernet.encrypt(config_token.encode()).decode()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE projects
                   SET anon_key=$1, service_role=$2, config_token=$3
                   WHERE name=$4 AND owner_id=$5""",
                anon_enc, svc_enc, config_enc, new_name, owner_id
            )

        await set_status("done")

    except Exception as e:
        await set_status("failed")
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


async def _delete_project_impl(
    project_name: str,
    pool,
    *,
    current_job_id: str | None = None,
) -> dict:
    errors: list[str] = []
    db_name = f"_supabase_{project_name}"

    project_uuid = get_project_uuid_from_env(project_name)
    tenant_external_id = project_uuid if project_uuid else project_name

    if project_uuid:
        print(f"Deletando projeto com UUID: {project_uuid}")
    else:
        print(f"Deletando projeto antigo (sem UUID), usando project_name: {project_name}")

    paused_services: list[str] = []
    for service_name in ("realtime-dev.supabase-realtime", "supabase-pooler"):
        code, _, stderr = await _run_command("docker", "pause", service_name)
        if code == 0:
            paused_services.append(service_name)
        elif "already paused" not in stderr.lower():
            errors.append(
                f"Erro ao pausar {service_name}: {stderr or f'codigo {code}'}"
            )

    try:
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

        await asyncio.sleep(1)

        async with pool.acquire() as conn:
            deleted_ext = await conn.execute(
                'DELETE FROM _realtime.extensions WHERE tenant_external_id = $1',
                tenant_external_id,
            )
            deleted_tenant = await conn.execute(
                'DELETE FROM _realtime.tenants WHERE external_id = $1',
                tenant_external_id,
            )

            print(f"Realtime cleanup: extensions={deleted_ext}, tenants={deleted_tenant}")

            await asyncio.sleep(10)

            await conn.execute(
                """
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
                """,
                db_name,
            )

            await asyncio.sleep(2)
            slot_errors = await drop_supabase_replication_slots(conn, project_name)
            if slot_errors:
                errors.extend(slot_errors)

            try:
                await conn.execute(
                    'DROP DATABASE IF EXISTS ' + '"' + db_name.replace('"', '""') + '"'
                )
            except Exception as drop_error:
                errors.append(f"Erro ao dropar banco {db_name}: {drop_error}")

            project_id = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1",
                project_name,
            )
            if project_id:
                await conn.execute(
                    "DELETE FROM project_members WHERE project_id = $1",
                    project_id,
                )
                if current_job_id:
                    await conn.execute(
                        "DELETE FROM jobs WHERE project = $1 AND job_id <> $2",
                        project_name,
                        current_job_id,
                    )
                else:
                    await conn.execute(
                        "DELETE FROM jobs WHERE project = $1",
                        project_name,
                    )
                await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
            else:
                errors.append(
                    f"Projeto {project_name} não encontrado para limpeza final."
                )

            await conn.execute(
                'DELETE FROM _supavisor.users WHERE tenant_external_id = $1',
                project_name,
            )
            await conn.execute(
                'DELETE FROM _supavisor.tenants WHERE external_id = $1',
                project_name,
            )
    finally:
        for service_name in paused_services:
            code, _, stderr = await _run_command("docker", "unpause", service_name)
            if code != 0 and "not paused" not in stderr.lower():
                errors.append(
                    f"Erro ao despausar {service_name}: {stderr or f'codigo {code}'}"
                )

    success, stdout, stderr = await execute_delete_script(project_name)
    if not success:
        detail = stderr.strip() or stdout.strip() or "erro desconhecido"
        errors.append(f"Erro ao excluir diretórios: {detail}")

    async with pool.acquire() as conn:
        db_exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name,
        )
        if db_exists:
            errors.append(f"Banco {db_name} ainda existe")

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

        await _set_job_status(job_id, "done", message=message)
    except Exception as exc:
        message = f"Falha ao excluir projeto: {exc}"
        await _set_job_status(job_id, "failed", message=message)
        print(f"[delete_project] {project_name}: background task failed: {exc}")

def get_project_uuid_from_env(project_name: str) -> Optional[str]:
    """
    Tenta ler o PROJECT_UUID do .env do projeto.
    Retorna None se não encontrar (projeto antigo).
    
    Dentro do Docker, os projetos estão montados em /docker/projects
    """
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
    tasks: BackgroundTasks,
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
        auth_user["user_id_text"],
        message="Exclusão iniciada em segundo plano.",
    )
    tasks.add_task(_delete_project_background, job_id, project_name)
    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "queued",
            "message": "Exclusão iniciada em segundo plano.",
        },
    )


class AddMember(BaseModel):
    user_id: str
    role: str = 'member'


@app.post("/api/projects/{project_name}/rotate-key")
async def rotate_project_key(
    project_name: str,
    request: Request,
    pool=Depends(get_pool),
):
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
        detail = stderr_text or stdout_text or "rotate script exited with no output"
        raise HTTPException(500, f"Rotate failed: {detail}")

    lines = stdout.decode().splitlines()
    kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
    anon = kv.get("ANON_KEY_PROJETO")
    service = kv.get("SERVICE_ROLE_KEY_PROJETO")
    if not anon or not service:
        raise HTTPException(500, "Keys not returned from script")

    anon_enc = fernet.encrypt(anon.encode()).decode()
    svc_enc  = fernet.encrypt(service.encode()).decode()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET anon_key=$1, service_role=$2 WHERE name=$3",
            anon_enc, svc_enc, project_name
        )

    return {
        "project": project_name,
        "anon_key": anon,
        "status": "rotated"
    }


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
                user_uuid=target_user["id"],
                user_key=str(target_user["id"]),
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
            "SELECT user_id, user_uuid, role FROM project_members "
            "WHERE project_id=$1",
            pid,
        )
    return [
        {
            "user_id": str(r["user_uuid"]) if r["user_uuid"] else r["user_id"],
            "user_uuid": str(r["user_uuid"]) if r["user_uuid"] else None,
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
        target_key = str(target_member["id"]) if target_member else member_id.strip()
        old_member_row = await get_project_member_row(
            conn,
            project_id=project_id,
            user_uuid=target_uuid,
            user_key=target_key,
        )
        old_role = old_member_row["role"] if old_member_row else None
        target_uuid = old_member_row["user_uuid"] if old_member_row and old_member_row["user_uuid"] else target_uuid

        await conn.execute(
            """
            DELETE FROM project_members
            WHERE project_id = $1
              AND (user_uuid = $2 OR user_id = $3)
            """,
            project_id,
            target_uuid,
            target_key,
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


@app.get("/api/projects/status/{job_id}")
async def project_status(job_id: str, pool=Depends(get_pool)):
    row = await pool.fetchrow(
        "SELECT status FROM jobs WHERE job_id=$1", job_id
    )
    details = JOB_DETAILS.get(job_id, {})
    return {
        "job_id": job_id,
        "status": row["status"] if row else "unknown",
        "message": details.get("message"),
    }

@app.get("/api/projects/internal/enc-key/{ref}")
async def enc_key(
    ref: str,
    pool=Depends(get_pool)
):
    ref = validate_project_id(ref)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT service_role FROM projects WHERE name=$1", ref
        )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"enc_service_key": row["service_role"]}

async def _provision_and_store_keys(job_id: str, project_name: str, user: str):
    pool = await get_pool()
    async def set_status(st: str):
        await pool.execute(
          "UPDATE jobs SET status=$1, updated_at=now() WHERE job_id=$2",
          st, job_id
        )

    await set_status("running")

    try:
        project_uuid = str(uuid.uuid4())
        
        proc = await asyncio.create_subprocess_exec(
            "bash", str(SCRIPT), project_name, project_uuid,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            await set_status("failed")
            print(stdout.decode())
            await rollback_project_from_db(pool, project_name)
            return

        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            await set_status("failed")
            print(err2.decode())
            await rollback_project_from_db(pool, project_name)
            return

        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        config_token = kv.get("CONFIG_TOKEN_PROJETO")
        if not anon or not service or not config_token:
            await set_status("failed")
            print("Missing tokens")
            await rollback_project_from_db(pool, project_name)
            return

        anon_enc = fernet.encrypt(anon.encode()).decode()
        svc_enc  = fernet.encrypt(service.encode()).decode()
        config_enc = fernet.encrypt(config_token.encode()).decode()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE projects
                   SET anon_key=$1, service_role=$2, config_token=$3
                   WHERE name=$4 AND owner_id=$5""",
                anon_enc, svc_enc, config_enc, project_name, user
            )

        await set_status("done")

    except Exception as e:
        await set_status("failed")
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
        "logflare_api_key": root_env.get("LOGFLARE_API_KEY", ""),
    }


def _sync_project_nginx_generated_files(project_name: str) -> None:
    project_dir = _get_project_dir(project_name)
    if not project_dir.exists():
        raise RuntimeError(f"Diretório do projeto '{project_name}' não encontrado")

    script_dir = BASE_DIR / "scripts"
    replacements = _get_project_template_replacements(project_name)

    _render_generated_template(
        script_dir / "nginxtemplate",
        project_dir / "nginx" / f"nginx_{project_name}.conf",
        replacements,
    )
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
) -> dict:
    stopped_containers: list[str] = []
    errors: list[str] = []

    for container in _sort_project_containers(containers):
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
    )
    try:
        result = await _stop_project_containers(project_name, containers)
        if result["errors"]:
            message = "\n".join(result["errors"])
            await _set_job_status(job_id, "failed", message=message)
            print(
                f"[stop_project] {project_name}: "
                + " | ".join(result["errors"])
            )
            return

        await _set_job_status(
            job_id,
            "done",
            message="Projeto parado com sucesso.",
        )
    except Exception as exc:
        message = f"Falha ao parar projeto: {exc}"
        await _set_job_status(job_id, "failed", message=message)
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
    )
    try:
        result = await _recreate_project_services_impl(project_name, services)
        if result["errors"]:
            message = "\n".join(result["errors"])
            await _set_job_status(job_id, "failed", message=message)
            print(
                f"[recreate_project_services] {project_name}: "
                + " | ".join(result["errors"])
            )
            return

        await _set_job_status(
            job_id,
            "done",
            message=f"Servicos recriados: {', '.join(services)}",
        )
    except Exception as exc:
        message = f"Falha ao recriar servicos: {exc}"
        await _set_job_status(job_id, "failed", message=message)
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
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    status_info = await get_project_status(project_name)
    return status_info

@app.post("/api/projects/{project_name}/stop")
async def stop_project(
    project_name: str,
    tasks: BackgroundTasks,
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

    if _containers_touch_project_nginx(containers):
        job_id = await _create_project_job(
            pool,
            project_name,
            auth_user["user_id_text"],
            message="Parada iniciada em segundo plano.",
        )
        tasks.add_task(
            _stop_project_containers_background,
            job_id,
            project_name,
            containers,
        )
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "message": "Parada iniciada em segundo plano.",
            },
        )

    return await _stop_project_containers(project_name, containers)

@app.post("/api/projects/{project_name}/start")
async def start_project(
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

    started_containers = []
    errors = []

    sorted_containers = _sort_project_containers(containers)

    for container in sorted_containers:
        container_name = container.get("Names", "")
        container_status = container.get("State", "")

        try:
            if container_status != "running":
                proc = await asyncio.create_subprocess_exec(
                    "docker", "start", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    started_containers.append(container_name)
                    await asyncio.sleep(2)
                else:
                    errors.append(f"Error starting {container_name}: {stderr.decode()}")
            else:
                started_containers.append(f"{container_name} (already running)")
        except Exception as e:
            errors.append(f"Error starting {container_name}: {str(e)}")

    return {
        "project": project_name,
        "started_containers": started_containers,
        "errors": errors,
        "success": len(errors) == 0
    }

@app.post("/api/projects/{project_name}/restart")
async def restart_project(
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

    sorted_containers = _sort_project_containers(containers)

    restarted_containers: list[str] = []
    errors: list[str] = []

    for cont in sorted_containers:
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
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                restarted_containers.append(name)
                await asyncio.sleep(2)
            else:
                errors.append(f"Error restarting {name}: {stderr.decode().strip()}")
        except Exception as exc:
            errors.append(f"Error restarting {name}: {exc}")

    return {
        "project": project_name,
        "restarted_containers": restarted_containers,
        "errors": errors,
        "success": len(errors) == 0,
    }

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
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

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
            stderr=asyncio.subprocess.PIPE
        )
        stdout_logs, stderr_logs = await proc_logs.communicate()

        if proc_logs.returncode != 0:
            raise HTTPException(500, f"Error getting logs: {stderr_logs.decode()}")

        container_info = json.loads(stdout_check.decode())[0]
        c_status = container_info.get("State", {}).get("Status", "unknown")

        return {
            "container": container_name,
            "logs": stdout_logs.decode('utf-8'),
            "status": c_status
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error accessing container: {str(e)}")

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
    target_hash = uid.strip().lower()

    if target_uuid is None and not re.fullmatch(r"[0-9a-f]{64}", target_hash):
        raise HTTPException(400, "user_id inválido")

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT p.name
            FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE (m.user_uuid = $1 OR m.user_id = $2)
            AND m.role = 'admin'
        """, target_uuid, target_hash)

        projects = []
        for r in rows:
            project_status = await get_project_status(r["name"])
            projects.append({
                "name": r["name"],
                "status": project_status["status"],
                "running_containers": project_status["running"],
                "total_containers": project_status["total"]
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
            "SELECT user_id, user_uuid, role FROM project_members WHERE project_id=$1",
            project["id"],
        )

    return {
        "project_name": name,
        "project_id": project["id"],
        "current_members": [
            {
                "user_id": str(m["user_uuid"]) if m["user_uuid"] else m["user_id"],
                "user_uuid": str(m["user_uuid"]) if m["user_uuid"] else None,
                "role": m["role"],
                "status": "member"
            } for m in current_members
        ],
        "cache_users_needed": True,
        "nginx_route": f"/api/projects/{name}/all-users"
    }

class TransferBody(BaseModel):
    new_owner_id: str

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
            current_owner_uuid = proj_row["owner_uuid"]

            if current_owner_uuid == new_owner_user["id"] or current_owner == str(new_owner_user["id"]):
                return {"status": "noop", "detail": "Já é o proprietário"}

            await conn.execute(
                "UPDATE projects SET owner_id = $1, owner_uuid = $2 WHERE id = $3",
                str(new_owner_user["id"]), new_owner_user["id"], project_id,
            )

            previous_target_role = await upsert_project_member(
                conn,
                project_id=project_id,
                user_uuid=new_owner_user["id"],
                user_key=str(new_owner_user["id"]),
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
                  AND (user_uuid = $2 OR user_id = $3)
                  AND role       = 'admin'
                """,
                project_id, current_owner_uuid, current_owner,
            )
            if current_owner:
                await audit_project_member_change(
                    conn,
                    project_id=project_id,
                    target_user_id=current_owner_uuid,
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
    """Creates a direct asyncpg connection to _supabase_{ref} using same credentials as main pool."""
    import urllib.parse
    dsn = urllib.parse.urlparse(DB_DSN)
    db_name = f"_supabase_{project_ref}"
    return await asyncpg.connect(
        host=dsn.hostname,
        port=dsn.port,
        user=dsn.username,
        password=dsn.password,
        database=db_name
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
              AND p.prokind IN ('f', 'p')
              AND obj_description(p.oid, 'pg_proc') ILIKE '%[AI]%'
            ORDER BY p.proname
        """)
        await proj_conn.close()
    except Exception as e:
        raise HTTPException(503, f"Cannot connect to project database: {str(e)}")

    functions = []
    for r in rows:
        comment = r["comment"] or ""
        clean_desc = comment.replace("[AI]", "").strip()
        functions.append({
            "name": r["name"],
            "argument_types": r["argument_types"] or "",
            "return_type": r["return_type"] or "void",
            "comment": comment,
            "schema": "public",
        })
    return functions

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
        await ensure_project_member_access(conn, project_id=project_row["id"], auth_user=auth_user)

    proj_conn = None
    try:
        proj_conn = await get_project_conn(ref)
        
        func_info = await proj_conn.fetchrow("""
            SELECT 
                p.proname as name,
                pg_get_function_arguments(p.oid) as args,
                obj_description(p.oid, 'pg_proc') as comment
            FROM pg_proc p
            JOIN pg_namespace n ON p.pronamespace = n.oid
            WHERE n.nspname = 'public' 
            AND p.proname = $1
        """, function_name)
        
        if not func_info:
            raise HTTPException(404, f"Function '{function_name}' not found in public schema")
        
        comment = func_info['comment'] or ""
        ai_tags = ["[ai]", "@ai-tool", "@ai", "#ai"]
        has_ai_tag = any(tag in comment.lower() for tag in ai_tags)
        
        if not has_ai_tag:
            raise HTTPException(403, f"Function '{function_name}' is not tagged as [AI] and cannot be executed")
        
        func_args = func_info['args'] or ""
        param_names = []
        optional_params = []

        for arg in func_args.split(','):
            arg = arg.strip()
            if not arg:
                continue
            parts = arg.split()
            if not parts:
                continue
            param_name = parts[0]
            if 'DEFAULT' in arg.upper():
                optional_params.append(param_name)
            else:
                param_names.append(param_name)

        for param_name in param_names:
            if param_name not in arguments:
                raise HTTPException(400, f"Missing required parameter: {param_name}")

        ordered_args = []
        for param_name in param_names:
            ordered_args.append(arguments[param_name])
        for param_name in optional_params:
            if param_name in arguments:
                ordered_args.append(arguments[param_name])
        
        placeholders = ", ".join(f"${i+1}" for i in range(len(ordered_args)))
        query = f"SELECT {function_name}({placeholders}) as result"
        
        rows = await proj_conn.fetch(query, *ordered_args)
        
        return [dict(r) for r in rows]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Function execution error: {str(e)}")
    finally:
        if proj_conn:
            await proj_conn.close()

SETTINGS_WHITELIST = {
    "DISABLE_SIGNUP",
    "ENABLE_EMAIL_SIGNUP",
    "ENABLE_EMAIL_AUTOCONFIRM",
    "ENABLE_ANONYMOUS_USERS",
    "ENABLE_PHONE_SIGNUP",
    "ENABLE_PHONE_AUTOCONFIRM",
    "JWT_EXPIRY",
    "GOTRUE_MAILER_OTP_EXP",
    "GOTRUE_PASSWORD_MIN_LENGTH",
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED",
    "PGRST_DB_SCHEMAS",
    "PGRST_DB_MAX_ROWS",
    "PGRST_DB_POOL",
    "PGRST_DB_POOL_TIMEOUT",
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT",
    "FILE_SIZE_LIMIT",
    "ENABLE_IMAGE_TRANSFORMATION",
}

SETTING_TO_SERVICES: dict[str, list[str]] = {
    "DISABLE_SIGNUP":                          ["auth"],
    "ENABLE_EMAIL_SIGNUP":                     ["auth"],
    "ENABLE_EMAIL_AUTOCONFIRM":                ["auth"],
    "ENABLE_ANONYMOUS_USERS":                  ["auth"],
    "ENABLE_PHONE_SIGNUP":                     ["auth"],
    "ENABLE_PHONE_AUTOCONFIRM":                ["auth"],
    "JWT_EXPIRY":                              ["auth", "rest"],
    "GOTRUE_MAILER_OTP_EXP":                   ["auth"],
    "GOTRUE_PASSWORD_MIN_LENGTH":              ["auth"],
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED":   ["auth"],
    "PGRST_DB_SCHEMAS":                        ["rest"],
    "PGRST_DB_MAX_ROWS":                       ["rest"],
    "PGRST_DB_POOL":                           ["rest"],
    "PGRST_DB_POOL_TIMEOUT":                   ["rest"],
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT":       ["rest"],
    "FILE_SIZE_LIMIT":                         ["storage", "nginx"],
    "ENABLE_IMAGE_TRANSFORMATION":             ["storage"],
}

def _read_env_whitelisted(env_path: pathlib.Path) -> dict[str, str]:
    all_values = _read_env_file(env_path)
    return {k: value for k, value in all_values.items() if k in SETTINGS_WHITELIST}


def _write_env_whitelisted(env_path: pathlib.Path, updates: dict[str, str]) -> None:
    with open(env_path, "r") as f:
        lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates and key in SETTINGS_WHITELIST:
                value = updates[key]
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys and key in SETTINGS_WHITELIST:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


def _get_affected_services(changed_keys: list[str]) -> list[str]:
    services: set[str] = set()
    for key in changed_keys:
        for svc in SETTING_TO_SERVICES.get(key, []):
            services.add(svc)
    return sorted(services)


class UpdateSettings(BaseModel):
    settings: Dict[str, str]


class RecreateServices(BaseModel):
    services: List[str]


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

    return {
        "settings": settings,
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

    invalid_keys = set(body.settings.keys()) - SETTINGS_WHITELIST
    if invalid_keys:
        raise HTTPException(
            400,
            f"Variáveis não permitidas: {', '.join(sorted(invalid_keys))}",
        )

    if not body.settings:
        raise HTTPException(400, "Nenhuma configuração enviada")

    env_path = _get_project_env_path(project_name)
    if not env_path.exists():
        raise HTTPException(404, f"Arquivo .env não encontrado para o projeto '{project_name}'")

    _write_env_whitelisted(env_path, body.settings)

    affected = _get_affected_services(list(body.settings.keys()))

    return {
        "status": "updated",
        "updated_keys": list(body.settings.keys()),
        "affected_services": affected,
        "message": f"Configurações salvas. Serviços afetados: {', '.join(affected)}. Recrie-os para aplicar.",
    }


ALLOWED_RECREATE_SERVICES = {"auth", "rest", "storage", "imgproxy", "nginx", "meta"}

@app.post("/api/projects/{project_name}/recreate-services")
async def recreate_project_services(
    project_name: str,
    body: RecreateServices,
    tasks: BackgroundTasks,
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
    if _services_touch_project_nginx(services):
        job_id = await _create_project_job(
            pool,
            project_name,
            auth_user["user_id_text"],
            message="Recriacao iniciada em segundo plano.",
        )
        tasks.add_task(
            _recreate_project_services_background,
            job_id,
            project_name,
            services,
        )
        return JSONResponse(
            status_code=202,
            content={
                "job_id": job_id,
                "status": "queued",
                "message": "Recriacao iniciada em segundo plano.",
            },
        )

    return await _recreate_project_services_impl(project_name, services)
