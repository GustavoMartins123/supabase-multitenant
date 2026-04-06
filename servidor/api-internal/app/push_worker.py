import asyncio
import os
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse
import asyncpg
import ssl

BASE_DSN = os.getenv("DB_DSN")
API_URL = os.getenv("PUSH_API_URL", "https://<SEU_IP>:4000/api/internal/push")
PUSH_WORKER_TOKEN = os.getenv("PUSH_WORKER_TOKEN")
PUSH_REQUEST_TIMEOUT = float(os.getenv("PUSH_REQUEST_TIMEOUT", "10"))
PUSH_VERIFY_TLS = os.getenv("PUSH_VERIFY_TLS", "false").lower() in ("1", "true", "yes", "on")
PUSH_CA_FILE = os.getenv("PUSH_CA_FILE", "/docker/push-certs/ca.pem")

if not PUSH_WORKER_TOKEN:
    raise RuntimeError("Missing PUSH_WORKER_TOKEN environment variable")

def build_ssl_context() -> ssl.SSLContext:
    if not PUSH_VERIFY_TLS:
        return ssl._create_unverified_context()

    if PUSH_CA_FILE:
        return ssl.create_default_context(cafile=PUSH_CA_FILE)

    return ssl.create_default_context()

SSL_CONTEXT = build_ssl_context()

def get_tenant_dsn(base_dsn: str, db_name: str) -> str:
    parsed = urlparse(base_dsn)
    new_dsn = parsed._replace(path=f"/{db_name}")
    return new_dsn.geturl()

async def send_to_api(token_fcm: str, body: str, project_name: str) -> bool:
    payload = {
        "project": project_name,
        "token": token_fcm,
        "body": body
    }
    
    req = urllib.request.Request(
        API_URL, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={
            "Content-Type": "application/json",
            "X-Push-Worker-Token": PUSH_WORKER_TOKEN,
        }, 
        method='POST'
    )
    
    try:
        response = await asyncio.to_thread(
            urllib.request.urlopen,
            req,
            timeout=PUSH_REQUEST_TIMEOUT,
            context=SSL_CONTEXT,
        )
        return response.status in (200, 201)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"[{project_name}] ❌ Push rejeitado: HTTP {e.code} - {detail}")
        return False
    except Exception as e:
        print(f"[{project_name}] ❌ Erro ao avisar a api: {e}")
        return False

async def poll_tenant(db_name: str):
    project_name = db_name.replace("_supabase_", "")
    tenant_dsn = get_tenant_dsn(BASE_DSN, db_name)
    
    print(f"✅ Iniciando monitoramento HÍBRIDO para o projeto: {project_name}")
    
    wakeup_event = asyncio.Event()

    def acordar_python(connection, pid, channel, payload):
        wakeup_event.set()

    while True:
        try:
            conn = await asyncpg.connect(tenant_dsn)
            await conn.add_listener('new_push', acordar_python)

            while True:
                try:
                    async with conn.transaction():
                        query = """
                            SELECT n.id, n.user_id, n.body, pt.token 
                            FROM notifications n
                            LEFT JOIN push_tokens pt ON n.user_id = pt.user_id AND pt.platform = 'android'
                            WHERE n.status = 'pendente' 
                            LIMIT 10 
                            FOR UPDATE OF n SKIP LOCKED
                        """
                        rows = await conn.fetch(query)
                        
                        for row in rows:
                            if not row['token']:
                                print(f"[{project_name}] ⚠️ Usuário {row['user_id']} sem token. Marcando como erro.")
                                await conn.execute("UPDATE notifications SET status = 'sem_token' WHERE id = $1", row['id'])
                                continue
                            
                            sucesso = await send_to_api(row['token'], row['body'], project_name)
                            
                            if sucesso:
                                await conn.execute("UPDATE notifications SET status = 'enviado' WHERE id = $1", row['id'])
                                print(f"[{project_name}] Push enviado com sucesso!")
                            else:
                                await conn.execute("UPDATE notifications SET status = 'erro' WHERE id = $1", row['id'])
                    
                    if rows:
                        wakeup_event.clear()
                        continue
                    
                    wakeup_event.clear()
                    try:
                        await asyncio.wait_for(wakeup_event.wait(), timeout=300)
                    except asyncio.TimeoutError:
                        pass
                        
                except asyncpg.exceptions.UndefinedTableError:
                    await conn.close()
                    await asyncio.sleep(3600)
                    break

        except Exception as e:
            print(f"[{project_name}] Erro de conexão, tentando reconectar... {e}")
            await asyncio.sleep(5)

async def worker_manager():
    active_tasks = {}
    
    while True:
        try:
            conn = await asyncpg.connect(BASE_DSN)
            
            query = """
                SELECT datname FROM pg_database 
                WHERE datname LIKE '_supabase_%' 
                AND datname NOT IN ('_supabase', '_supabase_template')
            """
            databases = await conn.fetch(query)
            await conn.close()
            
            current_dbs = {record['datname'] for record in databases}
            
            for db_name in current_dbs:
                if db_name not in active_tasks:
                    task = asyncio.create_task(poll_tenant(db_name))
                    active_tasks[db_name] = task
                    
        except Exception as e:
            print(f"Erro ao buscar lista de databases: {e}")
            
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(worker_manager())
