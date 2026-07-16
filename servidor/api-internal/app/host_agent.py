"""Cliente da Projects API para o host-agent.

A API nao executa mais Docker nem shell: ela grava a intencao assinada em
``host_agent_commands`` e aguarda o agent
executar. Este modulo tambem cria o schema das tabelas do agent e expoe o
snapshot de containers mantido por ele.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any, Awaitable, Callable

import asyncpg

from app.host_agent_protocol import (
    COMMAND_TIMEOUTS,
    NOTIFY_CHANNEL,
    command_signature,
    validate_command_args,
)

WORKER_ALIVE_WINDOW_SECONDS = 45
OFFLINE_QUEUE_GRACE_SECONDS = 60
WAIT_EXTRA_MARGIN_SECONDS = 120
LEASE_EXPIRED_GRACE_SECONDS = 60
STATE_FRESHNESS_LIMIT_SECONDS = 60

ProgressCallback = Callable[[asyncpg.Record], Awaitable[None]]


class HostAgentError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class HostAgentOffline(HostAgentError):
    def __init__(self) -> None:
        super().__init__(
            "host_agent_offline",
            "O host-agent esta offline. Instale/inicie o servico "
            "supabase-host-agent no servidor principal.",
        )


async def ensure_host_agent_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS host_agent_workers (
                worker_id TEXT PRIMARY KEY,
                hostname TEXT,
                pid INTEGER,
                version TEXT,
                started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                stopped_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS host_agent_commands (
                id UUID PRIMARY KEY,
                job_id UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
                project TEXT NOT NULL,
                project_uuid UUID,
                command TEXT NOT NULL,
                args JSONB NOT NULL DEFAULT '{}'::jsonb,
                requested_by UUID,
                issued_at BIGINT NOT NULL,
                signature TEXT NOT NULL,
                timeout_seconds INTEGER NOT NULL CHECK (timeout_seconds > 0),
                status TEXT NOT NULL DEFAULT 'queued'
                    CHECK (status IN ('queued','running','done','failed','cancelled')),
                progress SMALLINT NOT NULL DEFAULT 0
                    CHECK (progress BETWEEN 0 AND 100),
                current_step TEXT,
                message TEXT,
                worker_id TEXT,
                lease_seconds INTEGER NOT NULL DEFAULT 60,
                lease_expires_at TIMESTAMPTZ,
                heartbeat_at TIMESTAMPTZ,
                exit_code INTEGER,
                error_code TEXT,
                stdout_tail TEXT,
                stderr_tail TEXT,
                result JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE INDEX IF NOT EXISTS idx_host_agent_commands_status_created
                ON host_agent_commands(status, created_at);
            CREATE INDEX IF NOT EXISTS idx_host_agent_commands_job
                ON host_agent_commands(job_id, command, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_host_agent_commands_project_active
                ON host_agent_commands(project)
                WHERE status IN ('queued', 'running');

            CREATE TABLE IF NOT EXISTS project_container_state (
                container_name TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                state TEXT,
                status TEXT,
                image TEXT,
                ports TEXT,
                created_at_text TEXT,
                refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            CREATE INDEX IF NOT EXISTS idx_project_container_state_project
                ON project_container_state(project);
            """
        )


async def worker_alive(pool: asyncpg.Pool) -> bool:
    return bool(
        await pool.fetchval(
            """
            SELECT 1 FROM host_agent_workers
            WHERE stopped_at IS NULL
              AND last_heartbeat_at > now() - make_interval(secs => $1)
            LIMIT 1
            """,
            WORKER_ALIVE_WINDOW_SECONDS,
        )
    )


def _hmac_secret() -> str:
    from app.runtime_config import HOST_AGENT_HMAC_SECRET

    return HOST_AGENT_HMAC_SECRET


async def submit_command(
    pool: asyncpg.Pool,
    *,
    command: str,
    project: str,
    project_uuid: uuid.UUID | None,
    requested_by: uuid.UUID | None,
    args: dict[str, Any] | None = None,
    job_id: uuid.UUID | str | None = None,
    timeout_seconds: int | None = None,
) -> uuid.UUID:
    """Grava a intencao assinada e acorda o agent via NOTIFY."""
    args = args or {}
    errors = validate_command_args(command, project, args)
    if errors:
        raise HostAgentError("invalid_args", "; ".join(errors))

    command_id = uuid.uuid4()
    issued_at = int(time.time())
    timeout = timeout_seconds or COMMAND_TIMEOUTS[command]
    signature = command_signature(
        _hmac_secret(),
        command_id=str(command_id),
        command=command,
        project=project,
        project_uuid=str(project_uuid) if project_uuid else None,
        requested_by=str(requested_by) if requested_by else None,
        args=args,
        issued_at=issued_at,
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO host_agent_commands(
                id, job_id, project, project_uuid, command, args,
                requested_by, issued_at, signature, timeout_seconds
            )
            VALUES($1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10)
            """,
            command_id,
            uuid.UUID(str(job_id)) if job_id else None,
            project,
            project_uuid,
            command,
            json.dumps(args),
            requested_by,
            issued_at,
            signature,
            timeout,
        )
        await conn.execute("SELECT pg_notify($1, $2)", NOTIFY_CHANNEL, str(command_id))
    return command_id


async def find_command_for_job(
    pool: asyncpg.Pool,
    job_id: uuid.UUID | str,
    command: str,
) -> asyncpg.Record | None:
    """Localiza a intencao mais recente de um job para religar apos restart."""
    return await pool.fetchrow(
        """
        SELECT * FROM host_agent_commands
        WHERE job_id = $1 AND command = $2
        ORDER BY created_at DESC
        LIMIT 1
        """,
        uuid.UUID(str(job_id)),
        command,
    )


async def wait_command(
    pool: asyncpg.Pool,
    command_id: uuid.UUID,
    *,
    on_progress: ProgressCallback | None = None,
    poll_interval: float = 1.0,
) -> asyncpg.Record:
    """Espera o comando terminar, espelhando progresso e vigiando o lease.

    Falha fail-closed quando o agent fica offline com o comando ainda na
    fila ou quando o lease expira sem heartbeat (agent morto no meio da
    execucao).
    """
    queued_offline_since: float | None = None
    deadline: float | None = None
    last_status: str | None = None
    last_progress_key: tuple[Any, ...] | None = None

    while True:
        row = await pool.fetchrow(
            "SELECT * FROM host_agent_commands WHERE id = $1", command_id
        )
        if row is None:
            raise HostAgentError("command_missing", "Intencao sumiu do banco.")

        if row["status"] in {"done", "failed", "cancelled"}:
            return row

        if on_progress is not None:
            progress_key = (row["status"], row["progress"], row["current_step"], row["message"])
            if progress_key != last_progress_key:
                last_progress_key = progress_key
                await on_progress(row)

        now = time.monotonic()
        if deadline is None or row["status"] != last_status:
            # Cobre tambem o tempo em fila (ex.: outro comando do mesmo
            # projeto em execucao) para a espera nunca ficar sem teto. O
            # deadline reinicia na transicao queued -> running porque o
            # timeout real e contado pelo agent a partir do inicio.
            deadline = now + row["timeout_seconds"] + WAIT_EXTRA_MARGIN_SECONDS
        last_status = row["status"]
        if row["status"] == "queued":
            if now > deadline:
                await pool.execute(
                    """
                    UPDATE host_agent_commands
                    SET status = 'cancelled',
                        error_code = 'queue_wait_timeout',
                        message = 'Comando expirou aguardando o host-agent.',
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND status = 'queued'
                    """,
                    command_id,
                )
                continue
            if await worker_alive(pool):
                queued_offline_since = None
            elif queued_offline_since is None:
                queued_offline_since = now
            elif now - queued_offline_since > OFFLINE_QUEUE_GRACE_SECONDS:
                cancelled = await pool.execute(
                    """
                    UPDATE host_agent_commands
                    SET status = 'cancelled',
                        error_code = 'host_agent_offline',
                        message = 'Nenhum host-agent ativo para executar o comando.',
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND status = 'queued'
                    """,
                    command_id,
                )
                if cancelled.endswith("1"):
                    raise HostAgentOffline()
        elif row["status"] == "running":
            expired = await pool.fetchval(
                """
                SELECT 1 FROM host_agent_commands
                WHERE id = $1
                  AND status = 'running'
                  AND lease_expires_at < now() - make_interval(secs => $2)
                """,
                command_id,
                LEASE_EXPIRED_GRACE_SECONDS,
            )
            if expired:
                await pool.execute(
                    """
                    UPDATE host_agent_commands
                    SET status = 'failed',
                        error_code = 'lease_expired',
                        message = 'Lease expirado sem heartbeat do worker.',
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND status = 'running'
                    """,
                    command_id,
                )
                continue
            if now > deadline:
                await pool.execute(
                    """
                    UPDATE host_agent_commands
                    SET status = 'failed',
                        error_code = 'api_wait_timeout',
                        message = 'Comando ultrapassou o timeout e a margem de espera.',
                        finished_at = now(),
                        updated_at = now()
                    WHERE id = $1 AND status = 'running'
                    """,
                    command_id,
                )
                continue

        await asyncio.sleep(poll_interval)


async def run_command(
    pool: asyncpg.Pool,
    *,
    command: str,
    project: str,
    project_uuid: uuid.UUID | None,
    requested_by: uuid.UUID | None,
    args: dict[str, Any] | None = None,
    job_id: uuid.UUID | str | None = None,
    timeout_seconds: int | None = None,
    on_progress: ProgressCallback | None = None,
    poll_interval: float = 1.0,
) -> asyncpg.Record:
    """Atalho sincrono: grava a intencao e espera o resultado."""
    command_id = await submit_command(
        pool,
        command=command,
        project=project,
        project_uuid=project_uuid,
        requested_by=requested_by,
        args=args,
        job_id=job_id,
        timeout_seconds=timeout_seconds,
    )
    return await wait_command(
        pool, command_id, on_progress=on_progress, poll_interval=poll_interval
    )


async def run_command_for_job(
    pool: asyncpg.Pool,
    *,
    job_id: uuid.UUID | str,
    command: str,
    project: str,
    project_uuid: uuid.UUID | None,
    requested_by: uuid.UUID | None,
    args: dict[str, Any] | None = None,
    reuse_terminal: bool = False,
    on_progress: ProgressCallback | None = None,
) -> asyncpg.Record:
    """Como ``run_command``, mas religavel apos restart da API.

    Se ja existir uma intencao para (job, comando): em andamento -> apenas
    espera; terminal -> reusa o resultado quando ``reuse_terminal`` (acoes
    nao idempotentes) ou reexecuta (acoes idempotentes).
    """
    existing = await find_command_for_job(pool, job_id, command)
    if existing is not None:
        if existing["status"] in {"queued", "running"}:
            return await wait_command(pool, existing["id"], on_progress=on_progress)
        if reuse_terminal:
            return existing
    return await run_command(
        pool,
        command=command,
        project=project,
        project_uuid=project_uuid,
        requested_by=requested_by,
        args=args,
        job_id=job_id,
        on_progress=on_progress,
    )


def command_result(row: asyncpg.Record) -> dict[str, Any]:
    raw = row["result"]
    if raw is None:
        return {}
    if isinstance(raw, str):
        return json.loads(raw)
    return dict(raw)


async def fetch_project_containers(
    pool: asyncpg.Pool,
    project: str,
) -> list[dict[str, Any]]:
    """Snapshot dos containers do projeto no formato legado do docker ps."""
    rows = await pool.fetch(
        """
        SELECT container_name, state, status, image, ports, created_at_text
        FROM project_container_state
        WHERE project = $1
        ORDER BY container_name
        """,
        project,
    )
    return [
        {
            "Names": row["container_name"],
            "State": row["state"] or "",
            "Status": row["status"] or "",
            "Image": row["image"] or "",
            "Ports": row["ports"] or "",
            "CreatedAt": row["created_at_text"] or "",
        }
        for row in rows
    ]


async def container_state_is_fresh(pool: asyncpg.Pool) -> bool:
    """Estado utilizavel: worker vivo (o snapshot pode estar vazio)."""
    return await worker_alive(pool)
