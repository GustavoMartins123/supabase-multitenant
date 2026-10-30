"""Tenant outbox: short fenced transactions, durable per-device at-least-once delivery."""

import asyncio
import hashlib
import json
import logging
import os
import random
import ssl
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlparse

import asyncpg
import httpx

try:
    from app.internal_hmac import build_internal_hmac_headers as sign_internal_request
except ModuleNotFoundError:
    from internal_hmac import build_internal_hmac_headers as sign_internal_request

log = logging.getLogger("push")
BASE_DSN = os.getenv("DB_DSN")
API_URL = os.getenv("PUSH_API_URL")
INTERNAL_HMAC_SECRET = os.getenv("INTERNAL_HMAC_SECRET")


def env_float(name, default, *, minimum=0.0):
    try:
        value = float(os.getenv(name, str(default)))
        if not minimum <= value < float("inf"):
            raise ValueError()
        return value
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a finite number >= {minimum}") from exc


def env_int(name, default, *, minimum=1):
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


PUSH_REQUEST_TIMEOUT = env_float("PUSH_REQUEST_TIMEOUT", 75, minimum=0.1)
PUSH_VERIFY_TLS = os.getenv("PUSH_VERIFY_TLS", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)
PUSH_CA_FILE = os.getenv("PUSH_CA_FILE", "")
PUSH_BATCH_SIZE = env_int("PUSH_BATCH_SIZE", 10)
PUSH_MAX_ATTEMPTS = env_int("PUSH_MAX_ATTEMPTS", 8)
# Kept as a deployment variable for compatibility. Attempts are now exclusively
# durable; no immediate HTTP retries or sleeping while holding a claim.
PUSH_REQUEST_RETRIES = env_int("PUSH_REQUEST_RETRIES", 0, minimum=0)
PUSH_RETRY_BASE_SECONDS = env_float("PUSH_RETRY_BASE_SECONDS", 60, minimum=1)
PUSH_MAX_RETRY_SECONDS = env_float("PUSH_MAX_RETRY_SECONDS", 3600, minimum=1)
PUSH_MAX_RETRY_AFTER_SECONDS = env_float(
    "PUSH_MAX_RETRY_AFTER_SECONDS", 86400, minimum=1
)
PUSH_NOTIFICATION_LEASE_SECONDS = env_float(
    "PUSH_NOTIFICATION_LEASE_SECONDS", 900, minimum=30
)
PUSH_SCHEMA_RETRY_SECONDS = env_float("PUSH_SCHEMA_RETRY_SECONDS", 60, minimum=1)
PUSH_DB_CONNECT_TIMEOUT = env_float("PUSH_DB_CONNECT_TIMEOUT", 10, minimum=0.1)
PUSH_MAX_TENANT_CONNECTIONS = env_int("PUSH_MAX_TENANT_CONNECTIONS", 32)
PUSH_IDLE_WAKEUP_SECONDS = env_float("PUSH_IDLE_WAKEUP_SECONDS", 30, minimum=0.1)
PUSH_HTTP_CONCURRENCY = env_int("PUSH_HTTP_CONCURRENCY", 4)
PUSH_HTTP_GLOBAL_CONCURRENCY = env_int("PUSH_HTTP_GLOBAL_CONCURRENCY", 32)
PUSH_TENANT_SESSION_SECONDS = env_float("PUSH_TENANT_SESSION_SECONDS", 300, minimum=1)
SUPPORTED_PLATFORMS = ("android", "ios")
FCM_ERROR_TYPE = "type.googleapis.com/google.firebase.fcm.v1.FcmError"

if not BASE_DSN:
    raise RuntimeError("Missing DB_DSN environment variable")
if not API_URL:
    raise RuntimeError("Missing PUSH_API_URL environment variable")
if not INTERNAL_HMAC_SECRET:
    raise RuntimeError("Missing INTERNAL_HMAC_SECRET environment variable")
if urlparse(API_URL).scheme.lower() != "https":
    raise RuntimeError("PUSH_API_URL must use https")


def build_ssl_context():
    if not PUSH_VERIFY_TLS:
        raise RuntimeError(
            "PUSH_VERIFY_TLS must remain enabled for HTTPS; configure PUSH_CA_FILE instead"
        )
    context = ssl.create_default_context()
    if PUSH_CA_FILE:
        context.load_verify_locations(cafile=PUSH_CA_FILE)
    return context


SSL_CONTEXT = build_ssl_context()


def build_internal_hmac_headers(method, url, body):
    return sign_internal_request(INTERNAL_HMAC_SECRET, method, url, body)


@dataclass(frozen=True)
class PushResult:
    category: str
    status_code: int | None = None
    fcm_code: str | None = None
    retry_after: float | None = None
    operation_id: str = ""
    retryable: bool = False

    @property
    def succeeded(self):
        return self.category == "SUCCESS"

    @property
    def detail(self):
        # Never persist/log raw provider response bodies (can echo FCM tokens).
        return f"{self.category} http={self.status_code} fcm={self.fcm_code}"


class NotificationSchemaUnavailable(RuntimeError):
    pass


class ClaimLost(RuntimeError):
    pass


def event(name, **fields):
    log.info(json.dumps({"event": name, **fields}, default=str, separators=(",", ":")))


def get_tenant_dsn(base_dsn, db_name):
    return urlparse(base_dsn)._replace(path="/" + quote(db_name, safe="")).geturl()


def idempotency_key(project_name, notification_id, token):
    return hashlib.sha256(
        f"{project_name}\0{notification_id}\0{token}".encode()
    ).hexdigest()


def parse_retry_after(value):
    if not value:
        return None
    try:
        seconds = float(value)
        return seconds if 0 <= seconds < float("inf") else None
    except (TypeError, ValueError):
        try:
            return max(
                0,
                (
                    parsedate_to_datetime(value) - datetime.now(timezone.utc)
                ).total_seconds(),
            )
        except (TypeError, ValueError, OverflowError):
            return None


def classify_response(status, payload, retry_after=None, operation_id=""):
    code = None
    category = None
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            details = error.get("details", [])
            if isinstance(details, list):
                for item in details:
                    if isinstance(item, dict) and item.get("@type") == FCM_ERROR_TYPE:
                        candidate = item.get("errorCode")
                        if candidate in (
                            "UNREGISTERED",
                            "INVALID_ARGUMENT",
                            "SENDER_ID_MISMATCH",
                            "THIRD_PARTY_AUTH_ERROR",
                            "QUOTA_EXCEEDED",
                            "UNAVAILABLE",
                            "INTERNAL",
                        ):
                            code = candidate
                            break
        # Only safe, enumerated gateway metadata, never arbitrary messages.
        if payload.get("push_category") in (
            "AUTH_ERROR",
            "INVALID_REQUEST",
            "NETWORK_FAILURE",
            "TEMPORARY_FAILURE",
        ):
            category = payload["push_category"]
    if 200 <= status < 300:
        category = "SUCCESS"
    elif code == "UNREGISTERED" and status == 404:
        category = "UNREGISTERED"
    elif status in (408, 425, 500, 502, 503, 504):
        category = category or "TEMPORARY_FAILURE"
    elif status == 429:
        category = "RATE_LIMITED"
    elif code == "SENDER_ID_MISMATCH":
        category = "SENDER_ID_MISMATCH"
    elif code == "THIRD_PARTY_AUTH_ERROR" or status in (401, 403):
        category = category or "AUTH_ERROR"
    elif status == 400 or code == "INVALID_ARGUMENT":
        category = "INVALID_REQUEST"
    else:
        category = category or "UNKNOWN_ERROR"
    return PushResult(
        category,
        status,
        code,
        retry_after,
        operation_id,
        category in ("RATE_LIMITED", "TEMPORARY_FAILURE", "NETWORK_FAILURE"),
    )


def http_client():
    return httpx.AsyncClient(
        verify=SSL_CONTEXT,
        trust_env=False,
        follow_redirects=False,
        timeout=PUSH_REQUEST_TIMEOUT,
        limits=httpx.Limits(
            max_connections=PUSH_HTTP_GLOBAL_CONCURRENCY,
            max_keepalive_connections=PUSH_HTTP_GLOBAL_CONCURRENCY,
        ),
    )


async def send_to_api(token_fcm, body, project_name, delivery_key, client=None):
    if client is None:
        async with http_client() as owned_client:
            return await send_to_api(
                token_fcm, body, project_name, delivery_key, owned_client
            )
    try:
        request_body = json.dumps(
            {
                "project": project_name,
                "token": token_fcm,
                "body": body,
                "idempotency_key": delivery_key,
            }
        ).encode("utf-8")
        # Sign the exact transmitted bytes, with a fresh nonce per HTTP attempt.
        response = await client.post(
            API_URL,
            content=request_body,
            headers={
                "Content-Type": "application/json",
                **build_internal_hmac_headers("POST", API_URL, request_body),
            },
        )
        try:
            payload = response.json()
        except ValueError:
            payload = None
        return classify_response(
            response.status_code,
            payload,
            parse_retry_after(response.headers.get("Retry-After")),
            delivery_key,
        )
    except (httpx.RequestError, TimeoutError, OSError) as exc:
        # Certificate failures need intervention. Never silently bypass TLS.
        cause: BaseException | None = exc
        tls_failure = False
        while cause:
            if isinstance(cause, ssl.SSLCertVerificationError):
                tls_failure = True
                break
            cause = cause.__cause__ or cause.__context__
        return PushResult(
            "NETWORK_FAILURE", operation_id=delivery_key, retryable=not tls_failure
        )


async def close_connection(conn):
    if conn is not None and not conn.is_closed():
        try:
            await conn.close(timeout=5)
        except Exception:
            conn.terminate()


async def validate_notification_schema(conn):
    try:
        await conn.fetchval(
            """SELECT n.claim_id, n.deliveries_initialized_at, n.available_at,
            n.attempts, n.locked_at, n.last_error FROM public.notifications n LIMIT 0"""
        )
        await conn.fetchval(
            """SELECT d.push_token_id,d.push_generation,d.claim_id,d.result_category,
            d.http_status,d.fcm_code,d.retry_after_seconds,d.status,d.attempts,d.available_at,
            d.locked_at,d.last_error,d.delivered_at,d.platform,d.token,d.notification_id
            FROM public.notification_deliveries d LIMIT 0"""
        )
        await conn.fetchval(
            "SELECT id,user_id,token,platform,push_generation FROM public.push_tokens LIMIT 0"
        )
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError) as exc:
        raise NotificationSchemaUnavailable(
            "notification resilience schema is missing; apply 20261014_01_delivery_fencing.sql"
        ) from exc


async def claim_notifications(conn):
    # Claim one at a time; preclaiming a batch can expire before its HTTP starts.
    async with conn.transaction():
        return await conn.fetch(
            """
            WITH candidates AS (
                SELECT id FROM public.notifications
                WHERE (status='pendente' AND (available_at IS NULL OR available_at<=now()))
                   OR (status = 'processando' AND (locked_at IS NULL
                       OR locked_at < now()-($1::double precision*interval '1 second')))
                ORDER BY created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE public.notifications n SET status = 'processando', locked_at=now(),
                claim_id=$2, attempts=COALESCE(n.attempts,0)+1, last_error=NULL
            FROM candidates c WHERE n.id=c.id
            RETURNING n.id,n.user_id,n.body,n.attempts,n.claim_id
            """,
            PUSH_NOTIFICATION_LEASE_SECONDS,
            uuid.uuid4(),
        )


async def require_claim(conn, notification_id, claim_id):
    owned = await conn.fetchval(
        """SELECT id FROM public.notifications WHERE id=$1 AND claim_id=$2
        AND status='processando' AND locked_at>now()-($3::double precision*interval '1 second')
        FOR UPDATE""",
        notification_id,
        claim_id,
        PUSH_NOTIFICATION_LEASE_SECONDS,
    )
    if owned is None:
        raise ClaimLost()


async def renew_claim(conn, row):
    owned = await conn.fetchval(
        """UPDATE public.notifications SET locked_at=now()
        WHERE id=$1 AND claim_id=$2 AND status='processando'
        AND locked_at>now()-($3::double precision*interval '1 second') RETURNING id""",
        row["id"],
        row["claim_id"],
        PUSH_NOTIFICATION_LEASE_SECONDS,
    )
    if owned is None:
        raise ClaimLost()


async def create_delivery_rows(conn, row):
    async with conn.transaction():
        await require_claim(conn, row["id"], row["claim_id"])
        await conn.execute(
            """
            INSERT INTO public.notification_deliveries(notification_id,token,platform,push_token_id,push_generation)
            SELECT n.id,t.token,t.platform,t.id,t.push_generation
            FROM public.notifications n JOIN public.push_tokens t ON t.user_id=n.user_id
            WHERE n.id=$1 AND n.deliveries_initialized_at IS NULL
              AND t.platform=ANY($2::text[]) AND t.token<>''
            ON CONFLICT(notification_id,token) DO NOTHING
            """,
            row["id"],
            list(SUPPORTED_PLATFORMS),
        )
        await conn.execute(
            """UPDATE public.notifications SET deliveries_initialized_at=COALESCE(deliveries_initialized_at,now())
            WHERE id=$1 AND claim_id=$2""",
            row["id"],
            row["claim_id"],
        )


async def claim_deliveries(conn, row):
    async with conn.transaction():
        await require_claim(conn, row["id"], row["claim_id"])
        await conn.execute(
            """UPDATE public.notification_deliveries SET status='erro',locked_at=NULL,
            claim_id=NULL,result_category='UNKNOWN_ERROR',last_error='attempt limit reached after recovery'
            WHERE notification_id=$1 AND status IN ('pendente','processando') AND attempts>=$2""",
            row["id"],
            PUSH_MAX_ATTEMPTS,
        )
        return await conn.fetch(
            """
            WITH candidates AS (
                SELECT notification_id,token FROM public.notification_deliveries
                WHERE notification_id=$1 AND attempts<$3 AND
                  ((status='pendente' AND (available_at IS NULL OR available_at<=now())) OR status='processando')
                ORDER BY token LIMIT $4 FOR UPDATE SKIP LOCKED
            )
            UPDATE public.notification_deliveries d SET status='processando',locked_at=now(),
                claim_id=$2,attempts=d.attempts+1
            FROM candidates c WHERE d.notification_id=c.notification_id AND d.token=c.token
            RETURNING d.*
            """,
            row["id"],
            row["claim_id"],
            PUSH_MAX_ATTEMPTS,
            PUSH_HTTP_CONCURRENCY,
        )


def retry_delay(attempt, result):
    base = min(
        PUSH_MAX_RETRY_SECONDS,
        PUSH_RETRY_BASE_SECONDS * 2 ** min(max(0, attempt - 1), 30),
    )
    delay = random.uniform(base / 2, base)
    if result.category == "RATE_LIMITED":
        delay = max(60, delay)
    # Retry-After is a lower bound, not capped by exponential-backoff maximum.
    return max(delay, result.retry_after or 0)


async def record_delivery(conn, row, delivery, result):
    terminal = (
        result.succeeded
        or not result.retryable
        or delivery["attempts"] >= PUSH_MAX_ATTEMPTS
        or (
            result.retry_after is not None
            and result.retry_after > PUSH_MAX_RETRY_AFTER_SECONDS
        )
    )
    status = "enviado" if result.succeeded else "erro" if terminal else "pendente"
    delay = None if terminal else retry_delay(delivery["attempts"], result)
    invalidated = 0
    async with conn.transaction():
        await require_claim(conn, row["id"], row["claim_id"])
        changed = await conn.fetchval(
            """UPDATE public.notification_deliveries SET status=$4,
            available_at=CASE WHEN $5::double precision IS NULL THEN now()
                ELSE now()+($5::double precision*interval '1 second') END,
            locked_at=NULL,claim_id=NULL,last_error=$6,result_category=$7,http_status=$8,
            fcm_code=$9,retry_after_seconds=$10,
            delivered_at=CASE WHEN $4='enviado' THEN now() ELSE delivered_at END
            WHERE notification_id=$1 AND token=$2 AND claim_id=$3 AND status='processando'
            RETURNING notification_id""",
            row["id"],
            delivery["token"],
            row["claim_id"],
            status,
            delay,
            None if result.succeeded else result.detail,
            result.category,
            result.status_code,
            result.fcm_code,
            result.retry_after,
        )
        if changed is None:
            raise ClaimLost()
        if result.category == "UNREGISTERED" and result.fcm_code == "UNREGISTERED":
            deleted = await conn.fetchval(
                """DELETE FROM public.push_tokens
                WHERE id=$1 AND token=$2 AND push_generation=$3 AND user_id=$4 RETURNING id""",
                delivery["push_token_id"],
                delivery["token"],
                delivery["push_generation"],
                row["user_id"],
            )
            invalidated = int(deleted is not None)
    if not result.succeeded:
        event(
            (
                "RETRY_SCHEDULED"
                if not terminal
                else (
                    "AUTH_FAILURE"
                    if result.category == "AUTH_ERROR"
                    else (
                        result.category
                        if result.succeeded or result.category == "UNREGISTERED"
                        else "PERMANENT_FAILURE"
                    )
                )
            ),
            tenant=row.get("tenant"),
            notification_id=row["id"],
            operation_id=result.operation_id,
            category=result.category,
            http_status=result.status_code,
            fcm_code=result.fcm_code,
            attempt=delivery["attempts"],
            retry_seconds=delay,
            tokens_invalidated=invalidated,
        )
    return invalidated


async def finalize_notification(conn, row):
    async with conn.transaction():
        await require_claim(conn, row["id"], row["claim_id"])
        summary = await conn.fetchrow(
            """SELECT count(*) AS devices,
            count(*) FILTER(WHERE status IN ('pendente','processando')) AS open_count,
            count(*) FILTER(WHERE status='enviado') AS sent_count,
            count(*) FILTER(WHERE status='erro') AS error_count,
            min(available_at) FILTER(WHERE status='pendente') AS next_attempt_at
            FROM public.notification_deliveries WHERE notification_id=$1""",
            row["id"],
        )
        status = (
            "pendente"
            if summary["open_count"]
            else (
                "sem_token"
                if not summary["devices"]
                else (
                    "enviado"
                    if not summary["error_count"]
                    else "enviado_parcial"
                    if summary["sent_count"]
                    else "erro"
                )
            )
        )
        await conn.execute(
            """UPDATE public.notifications SET status=$3,locked_at=NULL,claim_id=NULL,
            available_at=COALESCE($4,now()),last_error=$5 WHERE id=$1 AND claim_id=$2""",
            row["id"],
            row["claim_id"],
            status,
            summary["next_attempt_at"],
            (
                None
                if status == "enviado"
                else f"devices={summary['devices']} success={summary['sent_count']} pending={summary['open_count']} failed={summary['error_count']}"
            ),
        )
    return dict(summary)


async def process_notification(conn, project_name, row, client=None, http_slots=None):
    if client is None:
        async with http_client() as owned:
            return await process_notification(
                conn, project_name, row, owned, http_slots
            )
    row = {**dict(row), "tenant": project_name}
    http_slots = http_slots or asyncio.Semaphore(PUSH_HTTP_GLOBAL_CONCURRENCY)
    started = time.monotonic()
    invalidated = 0
    await create_delivery_rows(conn, row)

    async def send(delivery):
        key = idempotency_key(project_name, str(row["id"]), delivery["token"])
        async with http_slots:
            return await send_to_api(
                delivery["token"], row["body"], project_name, key, client
            )

    while True:
        await renew_claim(conn, row)
        deliveries = await claim_deliveries(conn, row)
        if not deliveries:
            break
        tasks = {asyncio.create_task(send(d)): d for d in deliveries}
        pending = set(tasks)
        try:
            while pending:
                done, pending = await asyncio.wait(
                    pending,
                    timeout=PUSH_NOTIFICATION_LEASE_SECONDS / 3,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                await renew_claim(conn, row)
                for task in done:
                    invalidated += await record_delivery(
                        conn, row, tasks[task], task.result()
                    )
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    summary = await finalize_notification(conn, row)
    event(
        (
            "RETRY_SCHEDULED"
            if summary["open_count"]
            else (
                "PARTIAL_SUCCESS"
                if summary["sent_count"] and summary["error_count"]
                else "SUCCESS"
                if summary["sent_count"]
                else "PERMANENT_FAILURE"
            )
        ),
        tenant=project_name,
        notification_id=row["id"],
        attempt=row["attempts"],
        devices=summary["devices"],
        successes=summary["sent_count"],
        temporary_failures=summary["open_count"],
        tokens_invalidated=invalidated,
        duration_ms=round((time.monotonic() - started) * 1000),
    )
    return summary


async def next_wakeup(conn):
    value = await conn.fetchval(
        """SELECT EXTRACT(EPOCH FROM min(due)-now()) FROM (
        SELECT COALESCE(available_at,now()) AS due FROM public.notifications WHERE status='pendente'
        UNION ALL SELECT COALESCE(locked_at,now())+($1::double precision*interval '1 second')
        FROM public.notifications WHERE status='processando') s""",
        PUSH_NOTIFICATION_LEASE_SECONDS,
    )
    return (
        min(PUSH_IDLE_WAKEUP_SECONDS, max(0.1, float(value)))
        if value is not None
        else PUSH_IDLE_WAKEUP_SECONDS
    )


async def poll_tenant(db_name, connection_slots, client=None, http_slots=None):
    if client is None:
        async with http_client() as owned:
            return await poll_tenant(db_name, connection_slots, owned, http_slots)
    project_name = db_name.removeprefix("_supabase_")
    tenant_dsn = get_tenant_dsn(BASE_DSN, db_name)
    wakeup = asyncio.Event()

    def listener(connection, pid, channel, payload):
        wakeup.set()

    while True:
        conn = None
        try:
            # Rotate bounded sessions: idle tenants cannot hold every slot forever.
            async with connection_slots:
                try:
                    conn = await asyncpg.connect(
                        tenant_dsn,
                        timeout=PUSH_DB_CONNECT_TIMEOUT,
                        command_timeout=PUSH_DB_CONNECT_TIMEOUT,
                        server_settings={"application_name": "supabase-push-worker"},
                    )
                    await validate_notification_schema(conn)
                    await conn.add_listener("new_push", listener)
                    deadline = time.monotonic() + PUSH_TENANT_SESSION_SECONDS
                    while time.monotonic() < deadline:
                        wakeup.clear()  # before query, so NOTIFY during query is retained
                        rows = await claim_notifications(conn)
                        if rows:
                            for row in rows:
                                try:
                                    await process_notification(
                                        conn, project_name, row, client, http_slots
                                    )
                                except ClaimLost:
                                    event(
                                        "CLAIM_LOST",
                                        tenant=project_name,
                                        notification_id=row["id"],
                                    )
                            await asyncio.sleep(0)
                            continue
                        delay = min(
                            await next_wakeup(conn),
                            max(0.1, deadline - time.monotonic()),
                        )
                        try:
                            await asyncio.wait_for(wakeup.wait(), timeout=delay)
                        except asyncio.TimeoutError:
                            pass
                finally:
                    await close_connection(conn)
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            event("TENANT_STOPPED", tenant=project_name)
            raise
        except asyncpg.InvalidCatalogNameError:
            event("TENANT_REMOVED", tenant=project_name)
            return
        except NotificationSchemaUnavailable:
            event(
                "SCHEMA_UNAVAILABLE",
                tenant=project_name,
                migration="20261014_01_delivery_fencing.sql",
            )
            await asyncio.sleep(PUSH_SCHEMA_RETRY_SECONDS)
        except Exception as exc:
            # Driver errors may include DSNs, SQL parameter values or credentials.
            event(
                "TENANT_RECONNECT", tenant=project_name, error_type=type(exc).__name__
            )
            await asyncio.sleep(min(PUSH_SCHEMA_RETRY_SECONDS, 5))


async def reconcile_workers(
    active_tasks, current_dbs, connection_slots, client, http_slots
):
    removed = []
    for db_name in list(active_tasks):
        task = active_tasks[db_name]
        if db_name not in current_dbs or task.done():
            active_tasks.pop(db_name)
            task.cancel()
            removed.append(task)
    await asyncio.gather(*removed, return_exceptions=True)
    for db_name in sorted(current_dbs):
        if db_name not in active_tasks:
            active_tasks[db_name] = asyncio.create_task(
                poll_tenant(db_name, connection_slots, client, http_slots)
            )


async def worker_manager():
    active_tasks: dict[str, asyncio.Task] = {}
    connection_slots = asyncio.Semaphore(PUSH_MAX_TENANT_CONNECTIONS)
    http_slots = asyncio.Semaphore(PUSH_HTTP_GLOBAL_CONCURRENCY)
    async with http_client() as client:
        try:
            while True:
                conn = None
                try:
                    conn = await asyncpg.connect(
                        BASE_DSN,
                        timeout=PUSH_DB_CONNECT_TIMEOUT,
                        command_timeout=PUSH_DB_CONNECT_TIMEOUT,
                    )
                    databases = await conn.fetch(
                        """SELECT datname FROM pg_database
                        WHERE starts_with(datname,'_supabase_')
                        AND datname NOT IN ('_supabase','_supabase_template','_supabase_storage')"""
                    )
                    await reconcile_workers(
                        active_tasks,
                        {r["datname"] for r in databases},
                        connection_slots,
                        client,
                        http_slots,
                    )
                except Exception as exc:
                    event("DISCOVERY_FAILURE", error_type=type(exc).__name__)
                finally:
                    await close_connection(conn)
                await asyncio.sleep(60)
        finally:
            for task in active_tasks.values():
                task.cancel()
            await asyncio.gather(*active_tasks.values(), return_exceptions=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    asyncio.run(worker_manager())
