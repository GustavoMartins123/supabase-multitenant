import os
import uuid
import subprocess
import pathlib
import asyncpg
import hmac
import asyncio, json, re
from fastapi import FastAPI, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from cryptography.fernet import Fernet
from typing import Optional, List, Dict
# ----------------------------
# Configurações & Globals
# ----------------------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "scripts" / "generate_project.sh"
DUPLICATE_SCRIPT = BASE_DIR / "scripts" / "duplicate_project.sh"
DELETE_SCRIPT = BASE_DIR / "scripts" / "delete_project.sh"
EXTRACTOR = BASE_DIR / "scripts" / "extract_token.sh"
DB_DSN = os.getenv("DB_DSN")
FERNET_SECRET = os.getenv("FERNET_SECRET")  # chave base64 de 32 bytes
APP_TOKEN = os.getenv("NGINX_SHARED_TOKEN")  # token HMAC compartilhado
DELETE_PASSWORD = os.getenv("PROJECT_DELETE_PASSWORD")
JOB_STATUS: dict[str, str] = {}  # job_id -> queued|running|failed|done


if not FERNET_SECRET:
    raise RuntimeError("Missing FERNET_SECRET environment variable")
try:
    fernet = Fernet(FERNET_SECRET.encode())
except ValueError:
    raise RuntimeError(
        "Invalid FERNET_SECRET: must be a 32-byte url-safe base64-encoded key, "
        "generated via Fernet.generate_key()."
    )
    
JOB_STATUS: dict[str, str] = {}
# ----------------------------
# Utilitários
# ----------------------------
async def get_pool():
    return await asyncpg.create_pool(DB_DSN, min_size=1, max_size=5)

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

def validate_project_id(raw: str) -> str:
    """
    Retorna o project_id sanitizado (minúsculo) ou levanta HTTP 400.
    """
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

# ----------------------------
# FastAPI & Modelos
# ----------------------------
app = FastAPI()

class NewProject(BaseModel):
    name: str


class DuplicateProject(BaseModel):
    original_name: str
    new_name: str
    copy_data: bool = False

@app.get("/api/projects")
async def list_projects(
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool)
):
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.name, p.anon_key
            FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = $1 AND p.anon_key IS NOT NULL
        """, user)
    result = []
    for r in rows:
        anon_token = fernet.decrypt(r["anon_key"].encode()).decode()
        result.append({"name": r["name"], "anon_token": anon_token})
    return result

@app.post("/api/projects", status_code=202)
async def create_project(
    body: NewProject,
    tasks: BackgroundTasks,
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool),
):
    name = validate_project_id(body.name)

    if not name:
        raise HTTPException(400, "name required")

    # Insere registro em projects + job em jobs
    job_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1",
            name
        )
        if existing:
            raise HTTPException(status_code=409, detail="Project already exists")
        project_id = await conn.fetchval(
                """INSERT INTO projects(name, owner_id)
                   VALUES($1, $2)
                   RETURNING id""",
                name, user
            )
        await conn.execute(
                """INSERT INTO project_members(project_id, user_id, role)
                   VALUES($1, $2, 'admin')""",
                project_id, user
            )
        await conn.execute(
            """INSERT INTO jobs(job_id, project, owner_id, status)
               VALUES($1, $2, $3, 'queued')""",
            job_id, name, user
        )

    tasks.add_task(_provision_and_store_keys, job_id, name, user)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/projects/duplicate", status_code=202)
async def duplicate_project(
    body: DuplicateProject,
    tasks: BackgroundTasks,
    user: str = Header(..., alias="Remote-Email"),
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
    
    async with pool.acquire() as conn:
        # Verifica se usuário tem acesso ao projeto original
        has_access = await conn.fetchval("""
            SELECT EXISTS(
                SELECT 1 FROM projects p
                JOIN project_members m ON p.id = m.project_id
                WHERE p.name = $1 AND m.user_id = $2
            )
        """, original, user)
        
        if not has_access:
            raise HTTPException(403, "Acesso negado ao projeto original")
        
        # Verifica se novo nome já existe
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM projects WHERE name = $1)",
            new_name
        )
        if exists:
            raise HTTPException(409, "Nome de projeto já existe")
        
        # Cria registro em projects
        project_id = await conn.fetchval("""
            INSERT INTO projects(name, owner_id)
            VALUES($1, $2) RETURNING id
        """, new_name, user)
        
        # Adiciona usuário como admin
        await conn.execute("""
            INSERT INTO project_members(project_id, user_id, role)
            VALUES($1, $2, 'admin')
        """, project_id, user)

        # Cria job (EXATAMENTE como no create_project)
        job_id = str(uuid.uuid4())
        await conn.execute(
            """INSERT INTO jobs(job_id, project, owner_id, status)
               VALUES($1, $2, $3, 'queued')""",
            job_id, new_name, user
        )

    # Dispara background task
    tasks.add_task(_duplicate_and_store_keys, job_id, original, new_name, user, body.copy_data)
    
    return {"job_id": job_id, "status": "queued"}


async def _duplicate_and_store_keys(job_id: str, original_name: str, new_name: str, owner_id: str, copy_data: bool):
    pool = await get_pool()
    async def set_status(st: str):
        await pool.execute(
          "UPDATE jobs SET status=$1, updated_at=now() WHERE job_id=$2",
          st, job_id
        )

    await set_status("running")

    try:
        # Define modo de cópia
        copy_mode = "with-data" if copy_data else "schema-only"
        
        # Executa script de duplicação
        proc = await asyncio.create_subprocess_exec(
            "bash", str(DUPLICATE_SCRIPT), original_name, new_name, copy_mode,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            await set_status("failed")
            print(stdout.decode())
            return

        # Extração de tokens
        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), new_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            await set_status("failed")
            print(err2.decode())
            return

        # Parse das variáveis
        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        if not anon or not service:
            await set_status("failed")
            print("Missing tokens")
            return

        # Cipher + update projetos
        anon_enc = fernet.encrypt(anon.encode()).decode()
        svc_enc  = fernet.encrypt(service.encode()).decode()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE projects
                   SET anon_key=$1, service_role=$2
                   WHERE name=$3 AND owner_id=$4""",
                anon_enc, svc_enc, new_name, owner_id
            )

        await set_status("done")

    except Exception as e:
        await set_status("failed")
        print(f"Worker error: {e}")





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

    # Nomes padronizados dos slots
    msg_slot  = f"supabase_realtime_messages_replication_slot_{project_name}"[:63]
    repl_slot = f"supabase_realtime_replication_slot_{project_name}"[:63]

    async def terminate_if_active(slot: str) -> None:
        """Encerra o backend do slot se estiver ativo."""
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
        """Tenta dropar o slot; ignora erro de inexistência."""
        try:
            await conn.execute("SELECT pg_drop_replication_slot($1)", slot)
        except Exception as exc:
            if "does not exist" not in str(exc):
                errors.append(f"drop {slot}: {exc}")

    # ---------- 1) & 2)  SLOT *messages* ----------
    await terminate_if_active(msg_slot)
    await drop_slot(msg_slot)

    # ---------- 3) & 4)  SLOT *replication* ----------
    await terminate_if_active(repl_slot)
    await drop_slot(repl_slot)

    return errors

@app.delete("/api/projects/{project_name}")
async def delete_project(
    project_name: str,
    user: str = Header(..., alias="Remote-Email"),
    x_delete_password: str = Header(..., alias="X-Delete-Password"),
    pool=Depends(get_pool)
):
    DELETE_PASSWORD = os.getenv("PROJECT_DELETE_PASSWORD")
    if not DELETE_PASSWORD:
        raise HTTPException(500, "Delete password not configured")

    if not hmac.compare_digest(x_delete_password, DELETE_PASSWORD):
        raise HTTPException(403, "Invalid delete password")

    errors = []
    db_name = f"_supabase_{project_name}"

    await asyncio.create_subprocess_exec("docker", "pause", "realtime-dev.supabase-realtime")
    await asyncio.create_subprocess_exec("docker", "pause", "supabase-pooler")
    try:
        containers = await get_project_containers(project_name)
        for container in containers:
            container_name = container.get("Names", "")
            if container_name:
                await asyncio.create_subprocess_exec("docker", "rm", "-f", container_name)
    except Exception as e:
        errors.append(f"Erro ao remover containers: {str(e)}")
    try:
        await asyncio.sleep(1)

        async with pool.acquire() as conn:

            #await conn.execute('DELETE FROM _realtime.extensions WHERE tenant_external_id = $1', project_name)
            
            await conn.execute('DELETE FROM _realtime.extensions WHERE tenant_external_id = $1', project_name)
            await conn.execute('DELETE FROM _realtime.tenants WHERE external_id = $1', project_name)

            await asyncio.sleep(10)

            await conn.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = $1 AND pid <> pg_backend_pid()
            """, db_name)

            await asyncio.sleep(2)
            slot_errors = await drop_supabase_replication_slots(conn, project_name)

            if slot_errors:
                errors.append(f"Erro ao dropar os slots {slot_errors}")
            try:
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
            except Exception as drop_error:
                errors.append(f"Erro ao dropar banco {db_name}: {drop_error}")
            project_id = await conn.fetchval("SELECT id FROM projects WHERE name = $1", project_name)
            await conn.execute("DELETE FROM project_members WHERE project_id = $1", project_id)
            await conn.execute("DELETE FROM jobs WHERE project = $1", project_name)
            await conn.execute("DELETE FROM projects WHERE id = $1", project_id)
            await conn.execute('DELETE FROM _supavisor.users WHERE tenant_external_id = $1',project_name)
            await conn.execute('DELETE FROM _supavisor.tenants WHERE external_id = $1', project_name)

    finally:
        await asyncio.create_subprocess_exec("docker", "unpause", "realtime-dev.supabase-realtime")
        await asyncio.create_subprocess_exec("docker", "unpause", "supabase-pooler")
    success, stdout, stderr = await execute_delete_script(project_name)
    if not success:
        errors.append(f"Erro ao excluir diretórios: {stderr.strip()}")

    async with pool.acquire() as conn:
        db_exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", db_name)
        if db_exists:
            errors.append(f"Banco {db_name} ainda existe")

    return {
        "project": project_name,
        "status": "success" if not errors else "partial_success",
        "message": "Projeto excluído com sucesso" if not errors else "Projeto excluído com erros",
        "errors": errors
    }


class AddMember(BaseModel):
    user_id: str
    role: str = 'member'

@app.post("/api/projects/{project_name}/members")
async def add_member(
    project_name: str,  # vem da URL
    member: AddMember,
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool),
):
    async with pool.acquire() as conn:
        # Busca o project_id pelo nome
        project_id = await conn.fetchval(
            """SELECT id FROM projects
               WHERE name = $1""", 
            project_name)
        
        if not project_id:
            raise HTTPException(404, "Project not found")
        
        # Verifica se o usuário é admin
        role = await conn.fetchval(
            """SELECT role FROM project_members
               WHERE project_id = $1 AND user_id = $2""",
            project_id, user
        )
        if role != 'admin':
            raise HTTPException(403, "Only admin can add members")
            
        # Adiciona o membro
        await conn.execute(
            """INSERT INTO project_members(project_id, user_id, role)
               VALUES($1, $2, $3)
               ON CONFLICT (project_id, user_id) DO NOTHING""",
            project_id, member.user_id, member.role
        )
    return {"ok": True}


@app.get("/api/projects/{name}/members")
async def list_members_by_ref(
    name: str,
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool),
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM projects WHERE lower(name) = lower($1)",
            name,
        )
        if not row:
            raise HTTPException(404, "project not found")

        pid = row["id"]
        in_project = await conn.fetchval(
            "SELECT 1 FROM project_members "
            "WHERE project_id=$1 AND user_id=$2",
            pid, user,
        )
        if not in_project:
            raise HTTPException(403, "not a member")

        rows = await conn.fetch(
            "SELECT user_id, role FROM project_members "
            "WHERE project_id=$1",
            pid,
        )
    return [{"user_id": r["user_id"], "role": r["role"]} for r in rows]


@app.delete(
    "/api/projects/{name}/members/{member_id}",
    status_code=200,
    response_model=dict
)
async def remove_member_by_ref(
    name: str,
    member_id: str,
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool),
):
    async with pool.acquire() as conn:
        # 1) busca project_id pelo nome (case-insensitive)
        project_row = await conn.fetchrow(
            "SELECT id FROM projects WHERE lower(name) = lower($1)",
            name
        )
        if not project_row:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")

        project_id = project_row["id"]

        # 2) verifica se quem está chamando é admin no projeto
        caller_role = await conn.fetchval(
            "SELECT role FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, user
        )
        if caller_role != "admin":
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admin can remove members")

        # 3) realiza o delete
        result = await conn.execute(
            "DELETE FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, member_id
        )

    return {"ok": True}


@app.get("/api/projects/status/{job_id}")
async def project_status(job_id: str, pool=Depends(get_pool)):
    row = await pool.fetchrow(
        "SELECT status FROM jobs WHERE job_id=$1", job_id
    )
    return {"job_id": job_id, "status": row["status"] if row else "unknown"}

@app.get("/api/projects/internal/enc-key/{ref}")
async def enc_key(
    ref: str,
    token: str = Header(None, alias="X-Shared-Token"),
    pool=Depends(get_pool)
):
    # Valida token HMAC
    if not APP_TOKEN or not hmac.compare_digest(token or "", APP_TOKEN):
        raise HTTPException(status_code=403, detail="Forbidden")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT service_role FROM projects WHERE name=$1", ref
        )
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    return {"enc_service_key": row["service_role"]}

# ----------------------------
# Worker: provisiona e extrai keys
# ----------------------------
async def _provision_and_store_keys(job_id: str, project_name: str, user: str):
    pool = await get_pool()
    async def set_status(st: str):
        await pool.execute(
          "UPDATE jobs SET status=$1, updated_at=now() WHERE job_id=$2",
          st, job_id
        )

    await set_status("running")

    try:
        # provisionamento
        proc = await asyncio.create_subprocess_exec(
            "bash", str(SCRIPT), project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            await set_status("failed")
            print(stdout.decode())
            return

        # extração de tokens
        proc2 = await asyncio.create_subprocess_exec(
            "bash", str(EXTRACTOR), project_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out2, err2 = await proc2.communicate()
        if proc2.returncode != 0:
            await set_status("failed")
            print(err2.decode())
            return

        # parse das variáveis
        lines = out2.decode().splitlines()
        kv = {k: v for k, v in (line.split("=", 1) for line in lines if "=" in line)}
        anon = kv.get("ANON_KEY_PROJETO")
        service = kv.get("SERVICE_ROLE_KEY_PROJETO")
        if not anon or not service:
            await set_status("failed")
            print("Missing tokens")
            return

        # cipher + update projetos
        anon_enc = fernet.encrypt(anon.encode()).decode()
        svc_enc  = fernet.encrypt(service.encode()).decode()
        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE projects
                   SET anon_key=$1, service_role=$2
                   WHERE name=$3 AND owner_id=$4""",
                anon_enc, svc_enc, project_name, user
            )

        await set_status("done")

    except Exception as e:
        await set_status("failed")
        print(f"Worker error: {e}")

def _name_matches(cont_json: dict, project: str) -> bool:
    patt = re.compile(rf"-{re.escape(project)}$")
    # Names pode vir como string "nginx,rest" ou lista — trate os dois
    names = cont_json.get("Names", "")
    if isinstance(names, str):
        return any(patt.search(n) for n in names.split(","))
    return any(patt.search(n) for n in names)

async def get_project_containers(project: str) -> list[dict]:
    """Retorna apenas os containers cujo nome termina em -<project>"""
    proc = await asyncio.create_subprocess_exec(
        "docker", "ps", "--format", "{{json .}}", "-a",
        stdout=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = stdout.decode().splitlines()
    containers = [json.loads(l) for l in lines if _name_matches(json.loads(l), project)]
    return containers

async def get_project_status(project_name: str) -> dict:
    """Retorna o status detalhado do projeto"""
    containers = await get_project_containers(project_name)
    
    if not containers:
        return {"status": "not_found", "containers": []}
    
    container_info = []
    running_count = 0
    
    for container in containers:
        status = container.get("State", "unknown")
        if status == "running":
            running_count += 1
            
        container_info.append({
            "name": container.get("Names", ""),
            "status": status,
            "image": container.get("Image", "unknown"),
            "created": container.get("CreatedAt", ""),
            "ports": container.get("Ports", "")
        })
    
    # Determina o status geral do projeto
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
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header("", alias="Remote-Groups"),
    pool=Depends(get_pool)
):
    """Retorna o status dos containers do projeto"""
    # Verifica se o usuário tem acesso ao projeto
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1", project_name
        )
        if not project_id:
            raise HTTPException(404, "Project not found")
        
        is_member = await conn.fetchval(
            "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, user
        )
        groups_list = [g.strip() for g in groups.split(",")]
        is_global_admin = "admin" in groups_list

        if not is_member and not is_global_admin:
            raise HTTPException(403, "Access denied")
    
    status_info = await get_project_status(project_name)
    return status_info

@app.post("/api/projects/{project_name}/stop")
async def stop_project(
    project_name: str,
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header("", alias="Remote-Groups"),
    pool=Depends(get_pool)
):
    """Para todos os containers do projeto"""
    # Verifica se o usuário é admin do projeto
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1", project_name
        )
        if not project_id:
            raise HTTPException(404, "Project not found")
        
        role = await conn.fetchval(
            "SELECT role FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, user
        )
        groups_list = [g.strip() for g in groups.split(",")]
        is_global_admin = "admin" in groups_list

        if role != "admin" and not is_global_admin:
            raise HTTPException(403, "Access denied: Admin do projeto ou administrador do sistema obrigatório")
    
    containers = await get_project_containers(project_name)
    if not containers:
        raise HTTPException(404, "No containers found for this project")
    
    stopped_containers = []
    errors = []
    
    for container in containers:
        container_name = container.get("Names", "")
        container_status = container.get("State", "")
        
        try:
            if container_status == "running":
                proc = await asyncio.create_subprocess_exec(
                    "docker", "stop", container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    stopped_containers.append(container_name)
                else:
                    errors.append(f"Error stopping {container_name}: {stderr.decode()}")
            else:
                stopped_containers.append(f"{container_name} (already stopped)")
        except Exception as e:
            errors.append(f"Error stopping {container_name}: {str(e)}")
    
    return {
        "project": project_name,
        "stopped_containers": stopped_containers,
        "errors": errors,
        "success": len(errors) == 0
    }

@app.post("/api/projects/{project_name}/start")
async def start_project(
    project_name: str,
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header("", alias="Remote-Groups"),
    pool=Depends(get_pool)
):
    """Inicia todos os containers do projeto"""
    # Verifica se o usuário é admin do projeto
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1", project_name
        )
        if not project_id:
            raise HTTPException(404, "Project not found")
        
        role = await conn.fetchval(
            "SELECT role FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, user
        )
        groups_list = [g.strip() for g in groups.split(",")]
        is_global_admin = "admin" in groups_list

        if role != "admin" and not is_global_admin:
            raise HTTPException(403, "Access denied: Admin do projeto ou administrador do sistema obrigatório")
    
    containers = await get_project_containers(project_name)
    if not containers:
        raise HTTPException(404, "No containers found for this project")
    
    started_containers = []
    errors = []
    
    # Ordem recomendada para iniciar containers Supabase
    service_order = ["meta", "auth", "rest", "imgproxy", "storage" ,"nginx"]
    
    # Ordena containers por prioridade
    def get_service_priority(container_name: str) -> int:
        for i, service in enumerate(service_order):
            if service in container_name.lower():
                return i
        return 999  # containers não reconhecidos vão por último
    
    sorted_containers = sorted(containers, key=lambda c: get_service_priority(c.get("Names", "")))
    
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
                    await asyncio.sleep(2)  # Pausa entre inicializações
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
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header("", alias="Remote-Groups"),
    pool=Depends(get_pool)
):
    """Reinicia (docker restart) todos os containers do projeto."""
    # ──────────────── 1. autorização ────────────────
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1", project_name
        )
        if not project_id:
            raise HTTPException(404, "Project not found")

        role = await conn.fetchval(
            """
            SELECT role
            FROM project_members
            WHERE project_id = $1 AND user_id = $2
            """,
            project_id, user,
        )
        groups_list = [g.strip() for g in groups.split(",")]
        is_global_admin = "admin" in groups_list

        if role != "admin" and not is_global_admin:
            raise HTTPException(403, "Access denied: Admin do projeto ou administrador do sistema obrigatório")

    # ──────────────── 2. coleta dos containers ────────────────
    containers = await get_project_containers(project_name)  # ↖ mesma helper dos outros
    if not containers:
        raise HTTPException(404, "No containers found for this project")

    # ──────────────── 3. ordem de reinício (mesma do start) ────────────────
    service_order = ["meta", "auth", "rest", "imgproxy", "storage", "nginx"]

    def get_service_priority(name: str) -> int:
        for idx, svc in enumerate(service_order):
            if svc in name.lower():
                return idx
        return 999

    sorted_containers = sorted(
        containers, key=lambda c: get_service_priority(c.get("Names", ""))
    )

    # ──────────────── 4. loop de restart ────────────────
    restarted_containers: list[str] = []
    errors: list[str] = []

    for cont in sorted_containers:
        name = cont.get("Names", "")
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker",
                "restart",
                "-t",
                "30",           # timeout para stop graceful antes de kill
                name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                restarted_containers.append(name)
                await asyncio.sleep(2)  # pequena pausa entre reinícios
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

@app.get("/api/projects/{project_name}/logs/{service}")
async def get_container_logs(
    project_name: str,
    service: str,
    user: str = Header(..., alias="Remote-Email"),
    pool=Depends(get_pool),
    lines: int = 100
):
    """Retorna os logs de um serviço específico do projeto"""
    # Verifica se o usuário tem acesso ao projeto
    async with pool.acquire() as conn:
        project_id = await conn.fetchval(
            "SELECT id FROM projects WHERE name = $1", project_name
        )
        if not project_id:
            raise HTTPException(404, "Project not found")
        
        is_member = await conn.fetchval(
            "SELECT 1 FROM project_members WHERE project_id = $1 AND user_id = $2",
            project_id, user
        )
        if not is_member:
            raise HTTPException(403, "Access denied")
    
    # Procura o container específico
    container_name = f"supabase-{service}-{project_name}"
    
    try:
        # Verifica se o container existe
        proc_check = await asyncio.create_subprocess_exec(
            "docker", "inspect", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_check, stderr_check = await proc_check.communicate()
        
        if proc_check.returncode != 0:
            raise HTTPException(404, f"Container {container_name} not found")
        
        # Pega os logs
        proc_logs = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", str(lines), "--timestamps", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout_logs, stderr_logs = await proc_logs.communicate()
        
        if proc_logs.returncode != 0:
            raise HTTPException(500, f"Error getting logs: {stderr_logs.decode()}")
        
        # Pega o status do container
        container_info = json.loads(stdout_check.decode())[0]
        status = container_info.get("State", {}).get("Status", "unknown")
        
        return {
            "container": container_name,
            "logs": stdout_logs.decode('utf-8'),
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Error accessing container: {str(e)}")

@app.post("/api/projects/admin/projects-info")
async def get_projects_for_user(
    body: Dict[str, str],  # {"user_id": "<hash>"}
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header("", alias="Remote-Groups"),
    pool=Depends(get_pool)
):
    if "admin" not in groups.split(","):
        raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

    uid = body.get("user_id")
    if not uid:
        raise HTTPException(400, "user_id é obrigatório")

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT p.name
            FROM projects p
            JOIN project_members m ON p.id = m.project_id
            WHERE m.user_id = $1
            AND m.role = 'admin'
        """, uid)

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
    user: str = Header(..., alias="Remote-Email"),
    groups: str = Header(default="", alias="Remote-Groups"),
    pool=Depends(get_pool),
):
    """
    Lista todos os usuários disponíveis para admins.
    Como a API não tem acesso ao cache, retorna uma estrutura
    que o Nginx pode completar ou usa proxy para Nginx.
    """
    
    user_groups = [g.strip() for g in groups.split(",") if g.strip()]
    is_admin = "admin" in user_groups
    
    if not is_admin:
        raise HTTPException(403, "admin access required")
    
    async with pool.acquire() as conn:
        # Verificar se projeto existe
        project = await conn.fetchrow(
            "SELECT id FROM projects WHERE lower(name) = lower($1)",
            name,
        )
        if not project:
            raise HTTPException(404, "project not found")
        
        # Buscar membros atuais (dados que a API tem)
        current_members = await conn.fetch(
            "SELECT user_id, role FROM project_members WHERE project_id=$1",
            project["id"],
        )
    
    # Como não temos acesso ao cache, retornamos o que sabemos
    # e deixamos uma indicação de que o Nginx deve completar
    return {
        "project_name": name,
        "project_id": project["id"],
        "current_members": [
            {
                "user_id": m["user_id"],
                "role": m["role"],
                "status": "member"
            } for m in current_members
        ],
        "cache_users_needed": True,  # Indica que precisa completar via Nginx
        "nginx_route": f"/api/projects/{name}/all-users"  # Rota do Nginx
    }
    
class TransferBody(BaseModel):
    new_owner_id: str

@app.post("/api/projects/{project_name}/transfer", status_code=200)
async def transfer_project(
    project_name: str,
    body: TransferBody,
    user_email: str        = Header(..., alias="Remote-Email"),
    groups: str            = Header("", alias="Remote-Groups"),
    pool                   = Depends(get_pool),
):
    # ── 1. Somente administradores globais (grupo 'admin') podem transferir
    if "admin" not in [g.strip() for g in groups.split(",")]:
        raise HTTPException(403, "Acesso negado – apenas administradores do sistema")

    new_owner = body.new_owner_id.strip().lower()
    if not new_owner:
        raise HTTPException(400, "new_owner_id é obrigatório")

    async with pool.acquire() as conn:
        # ── 2. Verifica se projeto existe
        proj_row = await conn.fetchrow(
            "SELECT id, owner_id FROM projects WHERE name = $1",
            project_name,
        )
        if not proj_row:
            raise HTTPException(404, "Project not found")

        project_id   = proj_row["id"]
        current_owner = proj_row["owner_id"]

        if new_owner == current_owner:
            return {"status": "noop", "detail": "Já é o proprietário"}

        # 5 ─── transfere
        await conn.execute(
            "UPDATE projects SET owner_id = $1 WHERE id = $2",
            new_owner, project_id,
        )

        # 6 ─── garante admin para o novo owner
        await conn.execute(
            """
            INSERT INTO project_members(project_id, user_id, role)
            VALUES($1, $2, 'admin')
            ON CONFLICT (project_id, user_id)
            DO UPDATE SET role = 'admin'
            """,
            project_id, new_owner,
        )

        # 7 ─── demota o dono antigo **só se ele ainda for admin**
        await conn.execute(
            """
            UPDATE project_members
            SET role = 'member'
            WHERE project_id = $1
              AND user_id    = $2
              AND role       = 'admin'
            """,
            project_id, current_owner,
        )


    return {
        "project": project_name,
        "new_owner_id": new_owner,
        "status": "transferred"
    }
