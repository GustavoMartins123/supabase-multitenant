"""Persistencia e serializacao dos jobs de projeto.

Este modulo concentra o ciclo de vida duravel dos jobs. Os runners de cada
acao continuam nos modulos de dominio e sao injetados na fila.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg


IDEMPOTENT_ACTIONS = frozenset({"start", "stop", "restart", "recreate_services"})
TERMINAL_STATUSES = frozenset({"done", "failed", "cancelled"})
LOG_TAIL_LIMIT = 8_000

PoolProvider = Callable[[], Awaitable[asyncpg.Pool]]
JobRunner = Callable[[], Awaitable[None]]

_pool_provider: PoolProvider | None = None


def configure_jobs(pool_provider: PoolProvider) -> None:
    global _pool_provider
    _pool_provider = pool_provider


async def _get_pool() -> asyncpg.Pool:
    if _pool_provider is None:
        raise RuntimeError("jobs subsystem is not configured")
    return await _pool_provider()


def is_action_idempotent(action: str | None) -> bool:
    return bool(action and action in IDEMPOTENT_ACTIONS)


async def ensure_jobs_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id UUID PRIMARY KEY,
                project TEXT NOT NULL,
                project_uuid UUID,
                owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                status TEXT NOT NULL,
                message TEXT,
                action TEXT NOT NULL,
                payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                progress SMALLINT NOT NULL DEFAULT 0
                    CHECK (progress BETWEEN 0 AND 100),
                current_step TEXT,
                total_steps INTEGER NOT NULL DEFAULT 1 CHECK (total_steps > 0),
                started_at TIMESTAMPTZ,
                finished_at TIMESTAMPTZ,
                stdout_tail TEXT,
                stderr_tail TEXT,
                error_code TEXT,
                is_idempotent BOOLEAN NOT NULL DEFAULT false,
                retryable BOOLEAN NOT NULL DEFAULT false,
                retry_of UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
                attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS project_uuid UUID;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_by UUID;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS message TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS action TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress SMALLINT NOT NULL DEFAULT 0;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_step TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stdout_tail TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stderr_tail TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_code TEXT;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_idempotent BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retryable BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retry_of UUID;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
            ALTER TABLE jobs ALTER COLUMN owner_id DROP NOT NULL;

            UPDATE jobs j
            SET project_uuid = p.id
            FROM projects p
            WHERE j.project_uuid IS NULL AND p.name = j.project;

            UPDATE jobs SET created_by = owner_id WHERE created_by IS NULL;

            UPDATE jobs
            SET is_idempotent = action IN ('start', 'stop', 'restart', 'recreate_services'),
                retryable = action IN ('start', 'stop', 'restart', 'recreate_services');

            CREATE INDEX IF NOT EXISTS idx_jobs_status_updated
                ON jobs(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_project_status
                ON jobs(project, status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_jobs_project_uuid_created
                ON jobs(project_uuid, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_created_by_created
                ON jobs(created_by, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_jobs_retry_of
                ON jobs(retry_of);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_active_retry
                ON jobs(retry_of)
                WHERE retry_of IS NOT NULL AND status IN ('queued', 'running');
            """
        )
        # Constraints are added separately so this migration remains safe for
        # installations whose jobs table predates these columns.
        await conn.execute(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'jobs_project_uuid_fkey'
                ) THEN
                    ALTER TABLE jobs DROP CONSTRAINT jobs_project_uuid_fkey;
                END IF;
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'jobs_owner_id_fkey' AND confdeltype <> 'n'
                ) THEN
                    ALTER TABLE jobs DROP CONSTRAINT jobs_owner_id_fkey;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'jobs_owner_id_fkey'
                ) THEN
                    ALTER TABLE jobs ADD CONSTRAINT jobs_owner_id_fkey
                        FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'jobs_created_by_fkey'
                ) THEN
                    ALTER TABLE jobs ADD CONSTRAINT jobs_created_by_fkey
                        FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'jobs_retry_of_fkey'
                ) THEN
                    ALTER TABLE jobs ADD CONSTRAINT jobs_retry_of_fkey
                        FOREIGN KEY (retry_of) REFERENCES jobs(job_id) ON DELETE SET NULL;
                END IF;
            END $$;
            """
        )


async def set_job_status(
    job_id: str,
    new_status: str,
    *,
    message: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    total_steps: int | None = None,
    stdout_tail: str | None = None,
    stderr_tail: str | None = None,
    error_code: str | None = None,
) -> None:
    if progress is not None and not 0 <= progress <= 100:
        raise ValueError("progress must be between 0 and 100")
    if total_steps is not None and total_steps < 1:
        raise ValueError("total_steps must be positive")

    assignments = ["status=$1", "updated_at=now()"]
    values: list[Any] = [new_status]

    def add_value(column: str, value: Any) -> None:
        values.append(value)
        assignments.append(f"{column}=${len(values)}")

    if message is not None:
        add_value("message", message)
    if progress is not None:
        add_value("progress", progress)
    if current_step is not None:
        add_value("current_step", current_step)
    if total_steps is not None:
        add_value("total_steps", total_steps)
    if stdout_tail is not None:
        add_value("stdout_tail", stdout_tail[-LOG_TAIL_LIMIT:])
    if stderr_tail is not None:
        add_value("stderr_tail", stderr_tail[-LOG_TAIL_LIMIT:])
    if error_code is not None:
        add_value("error_code", error_code)
    if new_status == "running":
        assignments.extend(("started_at=COALESCE(started_at, now())", "finished_at=NULL"))
    elif new_status in TERMINAL_STATUSES:
        assignments.append("finished_at=now()")
        if new_status == "done" and progress is None:
            assignments.append("progress=100")

    values.append(uuid.UUID(str(job_id)))
    pool = await _get_pool()
    await pool.execute(
        "UPDATE jobs SET " + ", ".join(assignments) + f" WHERE job_id=${len(values)}",
        *values,
    )


async def create_project_job(
    pool: asyncpg.Pool,
    project_name: str,
    user: uuid.UUID,
    *,
    message: str | None = None,
    action: str,
    payload: dict[str, Any] | None = None,
    total_steps: int = 1,
    project_uuid: uuid.UUID | None = None,
    retry_of: uuid.UUID | None = None,
    attempt: int = 1,
    connection: asyncpg.Connection | None = None,
) -> str:
    if total_steps < 1:
        raise ValueError("total_steps must be positive")
    job_id = uuid.uuid4()
    idempotent = is_action_idempotent(action)

    async def insert(conn: asyncpg.Connection) -> None:
        resolved_project_uuid = project_uuid
        if resolved_project_uuid is None:
            resolved_project_uuid = await conn.fetchval(
                "SELECT id FROM projects WHERE name = $1", project_name
            )
        await conn.execute(
            """
            INSERT INTO jobs(
                job_id, project, project_uuid, owner_id, created_by,
                status, message, action, payload, total_steps, progress,
                current_step, is_idempotent, retryable, retry_of, attempt
            )
            VALUES(
                $1, $2, $3, $4, $4, 'queued', $5, $6, $7::jsonb, $8, 0,
                'queued', $9, $9, $10, $11
            )
            """,
            job_id,
            project_name,
            resolved_project_uuid,
            user,
            message,
            action,
            json.dumps(payload or {}),
            total_steps,
            idempotent,
            retry_of,
            attempt,
        )

    if connection is not None:
        await insert(connection)
    else:
        async with pool.acquire() as conn:
            await insert(conn)
    return str(job_id)


async def create_retry_job(
    pool: asyncpg.Pool,
    source_job_id: uuid.UUID,
    created_by: uuid.UUID,
) -> asyncpg.Record:
    async with pool.acquire() as conn:
        async with conn.transaction():
            source = await conn.fetchrow(
                "SELECT * FROM jobs WHERE job_id = $1 FOR UPDATE", source_job_id
            )
            if source is None:
                raise LookupError("job_not_found")
            if source["status"] != "failed":
                raise ValueError("job_not_failed")
            if not source["is_idempotent"] or not source["retryable"]:
                raise PermissionError("job_not_retryable")

            root_id = source["retry_of"] or source["job_id"]
            # Serializa retries feitos a partir de tentativas diferentes da
            # mesma arvore, evitando corrida entre o SELECT e o INSERT.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                str(root_id),
            )
            active_retry = await conn.fetchval(
                """
                SELECT job_id FROM jobs
                WHERE retry_of = $1 AND status IN ('queued', 'running')
                LIMIT 1
                """,
                root_id,
            )
            if active_retry:
                raise RuntimeError(str(active_retry))
            attempt = await conn.fetchval(
                "SELECT COALESCE(MAX(attempt), 1) + 1 FROM jobs WHERE job_id = $1 OR retry_of = $1",
                root_id,
            )
            new_id = await create_project_job(
                pool,
                source["project"],
                created_by,
                message=f"Retry seguro da tentativa {source['attempt']}.",
                action=source["action"],
                payload=source["payload"] or {},
                total_steps=source["total_steps"],
                project_uuid=source["project_uuid"],
                retry_of=root_id,
                attempt=attempt,
                connection=conn,
            )
            return await conn.fetchrow("SELECT * FROM jobs WHERE job_id = $1", uuid.UUID(new_id))


def serialize_job(row: asyncpg.Record, *, include_output: bool = False) -> dict[str, Any]:
    def iso(column: str) -> str | None:
        value = row[column]
        return value.isoformat() if value else None

    payload = row["payload"] or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    tenant_uuid = payload.get("tenant_uuid") if isinstance(payload, dict) else None

    result = {
        "job_id": str(row["job_id"]),
        "project": row["project"],
        "project_uuid": str(row["project_uuid"]) if row["project_uuid"] else None,
        "tenant_uuid": str(tenant_uuid) if tenant_uuid else None,
        "created_by": str(row["created_by"]) if row["created_by"] else None,
        "action": row["action"],
        "status": row["status"],
        "message": row["message"],
        "progress": row["progress"],
        "current_step": row["current_step"],
        "total_steps": row["total_steps"],
        "started_at": iso("started_at"),
        "finished_at": iso("finished_at"),
        "error_code": row["error_code"],
        "is_idempotent": row["is_idempotent"],
        "retryable": row["retryable"],
        "retry_of": str(row["retry_of"]) if row["retry_of"] else None,
        "attempt": row["attempt"],
        "created_at": iso("created_at"),
        "updated_at": iso("updated_at"),
    }
    if include_output:
        result["stdout_tail"] = row["stdout_tail"]
        result["stderr_tail"] = row["stderr_tail"]
    return result


class _QueuedAction:
    __slots__ = ("job_id", "project_id", "project_name", "submitted_at", "runner")

    def __init__(self, job_id: str, project_id: uuid.UUID, project_name: str, runner: JobRunner) -> None:
        self.job_id = job_id
        self.project_id = project_id
        self.project_name = project_name
        self.submitted_at = time.time()
        self.runner = runner


class ProjectActionQueue:
    """Fila FIFO por projeto, protegida tambem por advisory lock no Postgres."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[_QueuedAction]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._current: dict[str, _QueuedAction] = {}
        self._registry_lock = asyncio.Lock()
        self._shutting_down = False

    async def _ensure_worker(self, project_name: str) -> asyncio.Queue[_QueuedAction]:
        async with self._registry_lock:
            if self._shutting_down:
                raise RuntimeError("action_queue esta em shutdown")
            queue = self._queues.get(project_name)
            if queue is None:
                queue = asyncio.Queue()
                self._queues[project_name] = queue
                self._workers[project_name] = asyncio.create_task(
                    self._worker_loop(project_name, queue), name=f"project-queue:{project_name}"
                )
            return queue

    async def _worker_loop(self, project_name: str, queue: asyncio.Queue[_QueuedAction]) -> None:
        try:
            while True:
                action = await queue.get()
                self._current[project_name] = action
                try:
                    await self._run_with_project_lock(action)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    print(f"[action_queue] job {action.job_id} falhou: {exc}")
                    try:
                        await set_job_status(
                            action.job_id,
                            "failed",
                            message="Falha interna ao executar a acao enfileirada.",
                            current_step="queue_runner_failed",
                            error_code="queue_runner_failed",
                        )
                    except Exception as status_exc:  # noqa: BLE001
                        print(f"[action_queue] falha ao persistir status: {status_exc}")
                finally:
                    self._current.pop(project_name, None)
                    queue.task_done()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[action_queue] worker de {project_name} morreu: {exc!r}")

    async def _run_with_project_lock(self, action: _QueuedAction) -> None:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            lock_key = str(action.project_id)
            await conn.execute("SELECT pg_advisory_lock(hashtextextended($1, 0))", lock_key)
            try:
                await action.runner()
            finally:
                await conn.execute("SELECT pg_advisory_unlock(hashtextextended($1, 0))", lock_key)

    async def submit(
        self,
        project_name: str,
        project_id: uuid.UUID,
        job_id: str,
        runner: JobRunner,
    ) -> int:
        queue = await self._ensure_worker(project_name)
        position = queue.qsize()
        await queue.put(_QueuedAction(job_id, project_id, project_name, runner))
        return position

    def status(self, project_name: str) -> dict[str, Any]:
        queue = self._queues.get(project_name)
        current = self._current.get(project_name)
        return {
            "project": project_name,
            "current_job_id": current.job_id if current else None,
            "current_project": current.project_name if current else None,
            "queued": queue.qsize() if queue else 0,
            "is_busy": current is not None,
        }

    def known_projects(self) -> list[str]:
        return list(self._queues)

    async def shutdown(self) -> None:
        self._shutting_down = True
        workers = list(self._workers.values())
        for task in workers:
            task.cancel()
        for task in workers:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._queues.clear()
        self._workers.clear()
        self._current.clear()


action_queue = ProjectActionQueue()


async def get_action_queue() -> ProjectActionQueue:
    return action_queue
