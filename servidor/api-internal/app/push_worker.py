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
SUPPORTED_PLATFORMS = ("android", "ios")

if not PUSH_WORKER_TOKEN:
    raise RuntimeError("Missing PUSH_WORKER_TOKEN environment variable")

def build_ssl_context() -> ssl.SSLContext:
    if not PUSH_VERIFY_TLS:
        return ssl._create_unverified_context()

    if PUSH_CA_FILE:
        return ssl.create_default_context(cafile=PUSH_CA_FILE)

    return ssl.create_default_context()

SSL_CONTEXT = build_ssl_context()


def is_missing_database_error(exc: Exception) -> bool:
    if isinstance(exc, asyncpg.exceptions.InvalidCatalogNameError):
        return True

    message = str(exc).lower()
    return "database" in message and "does not exist" in message


async def close_connection(conn: asyncpg.Connection | None) -> None:
    if conn is None or conn.is_closed():
        return

    try:
        await conn.close()
    except Exception:
        pass

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


async def get_pending_notifications(conn: asyncpg.Connection):
    query = """
        SELECT id, user_id, body
        FROM notifications
        WHERE status = 'pendente'
        ORDER BY created_at
        LIMIT 10
        FOR UPDATE SKIP LOCKED
    """
    return await conn.fetch(query)


async def get_user_push_tokens(conn: asyncpg.Connection, user_id):
    query = """
        SELECT DISTINCT token, platform
        FROM push_tokens
        WHERE user_id = $1
          AND platform = ANY($2::text[])
    """
    return await conn.fetch(query, user_id, list(SUPPORTED_PLATFORMS))

async def poll_tenant(db_name: str):
    project_name = db_name.replace("_supabase_", "")
    tenant_dsn = get_tenant_dsn(BASE_DSN, db_name)
    
    print(f"✅ Iniciando monitoramento HÍBRIDO para o projeto: {project_name}")
    
    wakeup_event = asyncio.Event()

    def acordar_python(connection, pid, channel, payload):
        wakeup_event.set()

    while True:
        conn = None
        try:
            conn = await asyncpg.connect(tenant_dsn)
            await conn.add_listener('new_push', acordar_python)

            while True:
                try:
                    async with conn.transaction():
                        rows = await get_pending_notifications(conn)
                        
                        for row in rows:
                            token_rows = await get_user_push_tokens(conn, row["user_id"])

                            if not token_rows:
                                print(f"[{project_name}] ⚠️ Usuário {row['user_id']} sem token. Marcando como erro.")
                                await conn.execute("UPDATE notifications SET status = 'sem_token' WHERE id = $1", row['id'])
                                continue

                            success_count = 0
                            for token_row in token_rows:
                                sucesso = await send_to_api(token_row["token"], row["body"], project_name)
                                if sucesso:
                                    success_count += 1

                            if success_count > 0:
                                await conn.execute("UPDATE notifications SET status = 'enviado' WHERE id = $1", row['id'])
                                if success_count == len(token_rows):
                                    print(f"[{project_name}] Push enviado com sucesso para {success_count} dispositivo(s)!")
                                else:
                                    print(
                                        f"[{project_name}] Push enviado parcialmente "
                                        f"({success_count}/{len(token_rows)} dispositivo(s))."
                                    )
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
                    await close_connection(conn)
                    conn = None
                    await asyncio.sleep(3600)
                    break

        except asyncio.CancelledError:
            print(f"[{project_name}] Monitoramento encerrado.")
            raise
        except Exception as e:
            if is_missing_database_error(e):
                print(f"[{project_name}] Banco ausente. Encerrando monitoramento do worker.")
                return
            print(f"[{project_name}] Erro de conexão, tentando reconectar... {e}")
            await asyncio.sleep(5)
        finally:
            await close_connection(conn)

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

            finished_dbs = [
                db_name for db_name, task in active_tasks.items() if task.done()
            ]
            for db_name in finished_dbs:
                task = active_tasks.pop(db_name)
                try:
                    task.result()
                except asyncio.CancelledError:
                    pass
                except Exception as exc:
                    print(f"[{db_name}] Worker encerrado com erro: {exc}")

            removed_dbs = set(active_tasks) - current_dbs
            removed_tasks = []
            for db_name in removed_dbs:
                print(f"[{db_name.replace('_supabase_', '')}] Banco removido da lista. Encerrando monitoramento.")
                task = active_tasks.pop(db_name)
                task.cancel()
                removed_tasks.append(task)

            if removed_tasks:
                await asyncio.gather(*removed_tasks, return_exceptions=True)
            
            for db_name in current_dbs:
                if db_name not in active_tasks:
                    task = asyncio.create_task(poll_tenant(db_name))
                    active_tasks[db_name] = task
                    
        except Exception as e:
            print(f"Erro ao buscar lista de databases: {e}")
            
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(worker_manager())
