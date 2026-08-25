from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlparse

import asyncpg

try:
    from app.internal_hmac import build_internal_hmac_headers as sign_internal_request
except ModuleNotFoundError:
    from internal_hmac import build_internal_hmac_headers as sign_internal_request


BASE_DSN = os.getenv("DB_DSN")
API_URL = os.getenv("PUSH_API_URL")
INTERNAL_HMAC_SECRET = os.getenv("INTERNAL_HMAC_SECRET")


def env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(os.getenv(name, str(default))))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc


def env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


PUSH_REQUEST_TIMEOUT = env_float("PUSH_REQUEST_TIMEOUT", 10.0, minimum=0.1)
PUSH_VERIFY_TLS = os.getenv("PUSH_VERIFY_TLS", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
PUSH_CA_FILE = os.getenv("PUSH_CA_FILE", "/docker/push-certs/ca.pem")
PUSH_BATCH_SIZE = env_int("PUSH_BATCH_SIZE", 10)
PUSH_MAX_ATTEMPTS = env_int("PUSH_MAX_ATTEMPTS", 8)
PUSH_REQUEST_RETRIES = env_int("PUSH_REQUEST_RETRIES", 2)
PUSH_RETRY_BASE_SECONDS = env_float("PUSH_RETRY_BASE_SECONDS", 2.0)
PUSH_MAX_RETRY_SECONDS = env_float("PUSH_MAX_RETRY_SECONDS", 60.0)
PUSH_NOTIFICATION_LEASE_SECONDS = env_float(
    "PUSH_NOTIFICATION_LEASE_SECONDS",
    900.0,
    minimum=30.0,
)
PUSH_SCHEMA_RETRY_SECONDS = env_float("PUSH_SCHEMA_RETRY_SECONDS", 60.0)
PUSH_DB_CONNECT_TIMEOUT = env_float("PUSH_DB_CONNECT_TIMEOUT", 10.0, minimum=0.1)
PUSH_MAX_TENANT_CONNECTIONS = env_int("PUSH_MAX_TENANT_CONNECTIONS", 32)
PUSH_IDLE_WAKEUP_SECONDS = env_float("PUSH_IDLE_WAKEUP_SECONDS", 300.0)
SUPPORTED_PLATFORMS = ("android", "ios")

if not BASE_DSN:
    raise RuntimeError("Missing DB_DSN environment variable")
if not API_URL:
    raise RuntimeError("Missing PUSH_API_URL environment variable")
if not INTERNAL_HMAC_SECRET:
    raise RuntimeError("Missing INTERNAL_HMAC_SECRET environment variable")

PUSH_API_SCHEME = urlparse(API_URL).scheme.lower()
if PUSH_API_SCHEME not in ("http", "https"):
    raise RuntimeError("PUSH_API_URL must use http or https")
if PUSH_API_SCHEME == "https" and not PUSH_VERIFY_TLS:
    raise RuntimeError("PUSH_VERIFY_TLS must remain enabled for HTTPS")


def build_internal_hmac_headers(method: str, url: str, body: bytes) -> dict[str, str]:
    return sign_internal_request(
        INTERNAL_HMAC_SECRET,
        method,
        url,
        body,
    )


def build_ssl_context() -> ssl.SSLContext:
    if PUSH_API_SCHEME == "https" and PUSH_CA_FILE:
        return ssl.create_default_context(cafile=PUSH_CA_FILE)

    return ssl.create_default_context()


SSL_CONTEXT = build_ssl_context()


@dataclass(frozen=True)
class PushResult:
    succeeded: bool
    retryable: bool
    status_code: int | None
    detail: str


class NotificationSchemaUnavailable(RuntimeError):
    pass


def truncate_detail(value: str, limit: int = 500) -> str:
    value = value.replace("\n", " ").strip()
    return value if len(value) <= limit else value[:limit] + "..."


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


def idempotency_key(project_name: str, notification_id: str, token: str) -> str:
    material = f"{project_name}\0{notification_id}\0{token}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


async def send_to_api(
    token_fcm: str,
    body: str,
    project_name: str,
    delivery_key: str,
) -> PushResult:
    payload = {
        "project": project_name,
        "token": token_fcm,
        "body": body,
        "idempotency_key": delivery_key,
    }
    request_body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        **build_internal_hmac_headers("POST", API_URL, request_body),
    }

    req = urllib.request.Request(
        API_URL,
        data=request_body,
        headers=headers,
        method="POST",
    )

    response = None
    try:
        response = await asyncio.to_thread(
            urllib.request.urlopen,
            req,
            timeout=PUSH_REQUEST_TIMEOUT,
            context=SSL_CONTEXT,
        )
        status = int(response.status)
        detail = truncate_detail(response.read().decode("utf-8", errors="replace"))
        if 200 <= status < 300:
            return PushResult(True, False, status, detail)

        return PushResult(
            False,
            status in (408, 425, 429) or status >= 500,
            status,
            detail or f"HTTP {status}",
        )
    except urllib.error.HTTPError as exc:
        detail = truncate_detail(exc.read().decode("utf-8", errors="replace"))
        retryable = exc.code in (408, 425, 429) or exc.code >= 500
        print(f"[{project_name}] Push HTTP {exc.code}: {detail}")
        return PushResult(False, retryable, exc.code, detail or f"HTTP {exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        detail = truncate_detail(str(exc))
        print(f"[{project_name}] Falha transitória ao avisar a API: {detail}")
        return PushResult(False, True, None, detail)
    except Exception as exc:
        detail = truncate_detail(str(exc))
        print(f"[{project_name}] Erro inesperado ao avisar a API: {detail}")
        return PushResult(False, True, None, detail)
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass


async def send_with_retries(
    token_fcm: str,
    body: str,
    project_name: str,
    delivery_key: str,
) -> PushResult:
    result = await send_to_api(token_fcm, body, project_name, delivery_key)
    for attempt in range(1, PUSH_REQUEST_RETRIES + 1):
        if result.succeeded or not result.retryable:
            break

        delay = min(
            PUSH_MAX_RETRY_SECONDS,
            PUSH_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
        )
        delay += random.uniform(0, delay * 0.25)
        print(
            f"[{project_name}] Retry HTTP do push "
            f"({attempt}/{PUSH_REQUEST_RETRIES}) em {delay:.1f}s"
        )
        await asyncio.sleep(delay)
        result = await send_to_api(token_fcm, body, project_name, delivery_key)

    return result


async def validate_notification_schema(conn: asyncpg.Connection) -> None:
    try:
        await conn.fetchval(
            """
            SELECT 1
            FROM notifications n
            WHERE n.available_at IS NULL
               OR n.attempts IS NULL
               OR n.locked_at IS NULL
               OR n.last_error IS NULL
            LIMIT 1
            """
        )
        await conn.fetchval(
            "SELECT 1 FROM notification_deliveries LIMIT 1"
        )
    except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError) as exc:
        raise NotificationSchemaUnavailable(
            "notification resilience schema is missing; apply the documented tenant migration"
        ) from exc


async def claim_notifications(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    async with conn.transaction():
        return await conn.fetch(
            """
            WITH candidates AS (
                SELECT id
                FROM notifications
                WHERE (
                    status = 'pendente'
                    AND (available_at IS NULL OR available_at <= now())
                ) OR (
                    status = 'processando'
                    AND (
                        locked_at IS NULL
                        OR locked_at < now() - ($1::double precision * interval '1 second')
                    )
                )
                ORDER BY created_at, id
                LIMIT $2
                FOR UPDATE SKIP LOCKED
            )
            UPDATE notifications AS n
            SET status = 'processando',
                locked_at = now(),
                attempts = COALESCE(n.attempts, 0) + 1,
                last_error = NULL
            FROM candidates AS c
            WHERE n.id = c.id
            RETURNING n.id, n.user_id, n.body, n.attempts
            """,
            PUSH_NOTIFICATION_LEASE_SECONDS,
            PUSH_BATCH_SIZE,
        )


async def create_delivery_rows(
    conn: asyncpg.Connection,
    notification_id,
    user_id,
) -> None:
    await conn.execute(
        """
        INSERT INTO notification_deliveries(notification_id, token, platform)
        SELECT $1, token, platform
        FROM push_tokens
        WHERE user_id = $2
          AND platform = ANY($3::text[])
          AND token <> ''
        ON CONFLICT (notification_id, token) DO NOTHING
        """,
        notification_id,
        user_id,
        list(SUPPORTED_PLATFORMS),
    )


async def claim_deliveries(conn: asyncpg.Connection, notification_id) -> list[asyncpg.Record]:
    async with conn.transaction():
        return await conn.fetch(
            """
            WITH candidates AS (
                SELECT notification_id, token
                FROM notification_deliveries
                WHERE notification_id = $1
                  AND (
                      (
                          status = 'pendente'
                          AND (available_at IS NULL OR available_at <= now())
                      ) OR (
                          status = 'processando'
                          AND (
                              locked_at IS NULL
                              OR locked_at < now() - ($2::double precision * interval '1 second')
                          )
                      )
                  )
                ORDER BY token
                FOR UPDATE SKIP LOCKED
            )
            UPDATE notification_deliveries AS d
            SET status = 'processando',
                locked_at = now(),
                attempts = COALESCE(d.attempts, 0) + 1
            FROM candidates AS c
            WHERE d.notification_id = c.notification_id
              AND d.token = c.token
            RETURNING d.notification_id, d.token, d.platform, d.attempts
            """,
            notification_id,
            PUSH_NOTIFICATION_LEASE_SECONDS,
        )


async def mark_delivery_success(conn: asyncpg.Connection, notification_id, token: str) -> None:
    await conn.execute(
        """
        UPDATE notification_deliveries
        SET status = 'enviado',
            delivered_at = now(),
            locked_at = NULL,
            last_error = NULL
        WHERE notification_id = $1 AND token = $2
        """,
        notification_id,
        token,
    )


async def mark_delivery_failure(
    conn: asyncpg.Connection,
    notification_id,
    token: str,
    attempt: int,
    result: PushResult,
) -> None:
    terminal = not result.retryable or attempt >= PUSH_MAX_ATTEMPTS
    if terminal:
        status = "erro"
        backoff_seconds = None
    else:
        status = "pendente"
        backoff_seconds = min(
            PUSH_MAX_RETRY_SECONDS,
            PUSH_RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)),
        )

    await conn.execute(
        """
        UPDATE notification_deliveries
        SET status = $3,
            available_at = CASE
                WHEN $5::double precision IS NULL THEN now()
                ELSE now() + ($5::double precision * interval '1 second')
            END,
            locked_at = NULL,
            last_error = $4
        WHERE notification_id = $1 AND token = $2
        """,
        notification_id,
        token,
        status,
        truncate_detail(result.detail),
        backoff_seconds,
    )


async def finalize_notification(conn: asyncpg.Connection, notification_id) -> None:
    summary = await conn.fetchrow(
        """
        SELECT
            COUNT(*) FILTER (WHERE status IN ('pendente', 'processando')) AS open_count,
            COUNT(*) FILTER (WHERE status = 'processando') AS processing_count,
            COUNT(*) FILTER (WHERE status = 'enviado') AS sent_count,
            COUNT(*) FILTER (WHERE status = 'erro') AS error_count,
            MIN(available_at) FILTER (WHERE status = 'pendente') AS next_attempt_at
        FROM notification_deliveries
        WHERE notification_id = $1
        """,
        notification_id,
    )

    if not summary or (
        summary["open_count"] == 0
        and summary["sent_count"] == 0
        and summary["error_count"] == 0
    ):
        await conn.execute(
            """
            UPDATE notifications
            SET status = 'sem_token', locked_at = NULL, last_error = 'no valid device token'
            WHERE id = $1
            """,
            notification_id,
        )
        return

    if summary["open_count"] > 0:
        if summary["processing_count"] > 0:
            await conn.execute(
                "UPDATE notifications SET status = 'processando', locked_at = now() WHERE id = $1",
                notification_id,
            )
        else:
            await conn.execute(
                """
                UPDATE notifications
                SET status = 'pendente',
                    available_at = COALESCE($2, now()),
                    locked_at = NULL
                WHERE id = $1
                """,
                notification_id,
                summary["next_attempt_at"],
            )
        return

    if summary["error_count"] == 0:
        status = "enviado"
    elif summary["sent_count"] > 0:
        status = "enviado_parcial"
    else:
        status = "erro"

    await conn.execute(
        """
        UPDATE notifications
        SET status = $2, locked_at = NULL, last_error = CASE WHEN $2 = 'erro' THEN 'all deliveries failed' ELSE NULL END
        WHERE id = $1
        """,
        notification_id,
        status,
    )


async def process_notification(
    conn: asyncpg.Connection,
    project_name: str,
    row: asyncpg.Record,
) -> None:
    await create_delivery_rows(conn, row["id"], row["user_id"])
    deliveries = await claim_deliveries(conn, row["id"])

    for delivery in deliveries:
        key = idempotency_key(project_name, str(row["id"]), delivery["token"])
        result = await send_with_retries(
            delivery["token"],
            row["body"],
            project_name,
            key,
        )
        if result.succeeded:
            await mark_delivery_success(conn, row["id"], delivery["token"])
        else:
            await mark_delivery_failure(
                conn,
                row["id"],
                delivery["token"],
                int(delivery["attempts"]),
                result,
            )

    await finalize_notification(conn, row["id"])


async def poll_tenant(db_name: str, connection_slots: asyncio.Semaphore) -> None:
    project_name = db_name.removeprefix("_supabase_")
    tenant_dsn = get_tenant_dsn(BASE_DSN, db_name)

    async with connection_slots:
        print(f"[{project_name}] Iniciando monitoramento híbrido")
        wakeup_event = asyncio.Event()

        def wake_worker(connection, pid, channel, payload):
            wakeup_event.set()

        while True:
            conn = None
            try:
                conn = await asyncpg.connect(
                    tenant_dsn,
                    timeout=PUSH_DB_CONNECT_TIMEOUT,
                )
                await validate_notification_schema(conn)
                await conn.add_listener("new_push", wake_worker)

                while True:
                    rows = await claim_notifications(conn)
                    for row in rows:
                        await process_notification(conn, project_name, row)

                    if rows:
                        wakeup_event.clear()
                        continue

                    wakeup_event.clear()
                    try:
                        await asyncio.wait_for(
                            wakeup_event.wait(),
                            timeout=PUSH_IDLE_WAKEUP_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        pass

            except asyncio.CancelledError:
                print(f"[{project_name}] Monitoramento encerrado.")
                raise
            except NotificationSchemaUnavailable as exc:
                print(f"[{project_name}] {exc}; tentando novamente em {PUSH_SCHEMA_RETRY_SECONDS:g}s")
                await asyncio.sleep(PUSH_SCHEMA_RETRY_SECONDS)
            except (asyncpg.exceptions.UndefinedTableError, asyncpg.exceptions.UndefinedColumnError) as exc:
                print(f"[{project_name}] Schema de notificações incompleto: {exc}")
                await asyncio.sleep(PUSH_SCHEMA_RETRY_SECONDS)
            except Exception as exc:
                if is_missing_database_error(exc):
                    print(f"[{project_name}] Banco ausente; encerrando monitoramento.")
                    return
                print(f"[{project_name}] Erro de conexão/processamento; reconectando: {exc}")
                await asyncio.sleep(min(PUSH_SCHEMA_RETRY_SECONDS, 5.0))
            finally:
                await close_connection(conn)


async def worker_manager() -> None:
    active_tasks: dict[str, asyncio.Task] = {}
    connection_slots = asyncio.Semaphore(PUSH_MAX_TENANT_CONNECTIONS)

    while True:
        conn = None
        try:
            conn = await asyncpg.connect(BASE_DSN, timeout=PUSH_DB_CONNECT_TIMEOUT)
            databases = await conn.fetch(
                """
                SELECT datname
                FROM pg_database
                WHERE datname LIKE '_supabase_%'
                  AND datname NOT IN ('_supabase', '_supabase_template')
                """
            )
            current_dbs = {record["datname"] for record in databases}

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
                project_name = db_name.removeprefix("_supabase_")
                print(f"[{project_name}] Banco removido; encerrando monitoramento.")
                task = active_tasks.pop(db_name)
                task.cancel()
                removed_tasks.append(task)

            if removed_tasks:
                await asyncio.gather(*removed_tasks, return_exceptions=True)

            for db_name in current_dbs:
                if db_name not in active_tasks:
                    active_tasks[db_name] = asyncio.create_task(
                        poll_tenant(db_name, connection_slots)
                    )
        except asyncio.CancelledError:
            for task in active_tasks.values():
                task.cancel()
            await asyncio.gather(*active_tasks.values(), return_exceptions=True)
            raise
        except Exception as exc:
            print(f"Erro ao buscar lista de databases: {exc}")
        finally:
            await close_connection(conn)

        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(worker_manager())
