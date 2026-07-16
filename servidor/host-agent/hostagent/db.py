"""Acesso do host-agent ao Postgres do control plane.

O agent nao cria schema: as tabelas ``host_agent_commands``,
``host_agent_workers`` e ``project_container_state`` sao criadas pela
Projects API no startup (``app/host_agent.py``).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import asyncpg


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=1, max_size=5)


async def register_worker(pool: asyncpg.Pool, worker_id: str, hostname: str, pid: int, version: str) -> None:
    await pool.execute(
        """
        INSERT INTO host_agent_workers(worker_id, hostname, pid, version)
        VALUES($1, $2, $3, $4)
        ON CONFLICT (worker_id) DO UPDATE
        SET last_heartbeat_at = now(), stopped_at = NULL
        """,
        worker_id,
        hostname,
        pid,
        version,
    )


async def heartbeat_worker(pool: asyncpg.Pool, worker_id: str) -> None:
    await pool.execute(
        "UPDATE host_agent_workers SET last_heartbeat_at = now() WHERE worker_id = $1",
        worker_id,
    )


async def mark_worker_stopped(pool: asyncpg.Pool, worker_id: str) -> None:
    await pool.execute(
        "UPDATE host_agent_workers SET stopped_at = now() WHERE worker_id = $1",
        worker_id,
    )


async def lease_next_command(
    pool: asyncpg.Pool,
    worker_id: str,
    lease_seconds: int,
    busy_projects: set[str],
) -> asyncpg.Record | None:
    """Faz o lease atomico do proximo comando elegivel.

    ``FOR UPDATE SKIP LOCKED`` serializa multiplos agents; a subquery
    tambem pula projetos com comando em execucao (local ou remoto) para
    manter a serializacao por projeto.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT id
                FROM host_agent_commands c
                WHERE c.status = 'queued'
                  AND NOT (c.project = ANY($1::text[]))
                  AND NOT EXISTS (
                      SELECT 1 FROM host_agent_commands r
                      WHERE r.project = c.project
                        AND r.status = 'running'
                        AND r.lease_expires_at > now()
                  )
                ORDER BY c.created_at
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """,
                sorted(busy_projects),
            )
            if row is None:
                return None
            return await conn.fetchrow(
                """
                UPDATE host_agent_commands
                SET status = 'running',
                    worker_id = $2,
                    lease_seconds = $3::integer,
                    lease_expires_at = now() + make_interval(secs => $3::integer),
                    heartbeat_at = now(),
                    started_at = COALESCE(started_at, now()),
                    updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                row["id"],
                worker_id,
                lease_seconds,
            )


async def heartbeat_command(
    pool: asyncpg.Pool,
    command_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int,
    *,
    stdout_tail: str | None = None,
    stderr_tail: str | None = None,
    progress: int | None = None,
    current_step: str | None = None,
    message: str | None = None,
) -> None:
    await pool.execute(
        """
        UPDATE host_agent_commands
        SET lease_expires_at = now() + make_interval(secs => $3::integer),
            heartbeat_at = now(),
            stdout_tail = COALESCE($4, stdout_tail),
            stderr_tail = COALESCE($5, stderr_tail),
            progress = COALESCE($6, progress),
            current_step = COALESCE($7, current_step),
            message = COALESCE($8, message),
            updated_at = now()
        WHERE id = $1 AND worker_id = $2 AND status = 'running'
        """,
        command_id,
        worker_id,
        lease_seconds,
        stdout_tail,
        stderr_tail,
        progress,
        current_step,
        message,
    )


async def finish_command(
    pool: asyncpg.Pool,
    command_id: uuid.UUID,
    worker_id: str,
    *,
    status: str,
    exit_code: int | None = None,
    error_code: str | None = None,
    stdout_tail: str | None = None,
    stderr_tail: str | None = None,
    result: dict[str, Any] | None = None,
    message: str | None = None,
) -> bool:
    """Finaliza o comando; no-op se a API ja o marcou como expirado."""
    outcome = await pool.execute(
        """
        UPDATE host_agent_commands
        SET status = $3,
            exit_code = $4,
            error_code = $5,
            stdout_tail = COALESCE($6, stdout_tail),
            stderr_tail = COALESCE($7, stderr_tail),
            result = COALESCE($8::jsonb, result),
            message = COALESCE($9, message),
            progress = CASE WHEN $3 = 'done' THEN 100 ELSE progress END,
            finished_at = now(),
            updated_at = now()
        WHERE id = $1 AND worker_id = $2 AND status = 'running'
        """,
        command_id,
        worker_id,
        status,
        exit_code,
        error_code,
        stdout_tail,
        stderr_tail,
        json.dumps(result) if result is not None else None,
        message,
    )
    return outcome.endswith("1")


async def reject_command(
    pool: asyncpg.Pool,
    command_id: uuid.UUID,
    worker_id: str,
    error_code: str,
    message: str,
) -> None:
    await pool.execute(
        """
        UPDATE host_agent_commands
        SET status = 'failed',
            error_code = $3,
            message = $4,
            finished_at = now(),
            updated_at = now()
        WHERE id = $1 AND worker_id = $2 AND status = 'running'
        """,
        command_id,
        worker_id,
        error_code,
        message,
    )


async def load_authorization_context(
    pool: asyncpg.Pool,
    *,
    project: str,
    requested_by: uuid.UUID | None,
) -> dict[str, Any]:
    """Carrega do banco os fatos usados pela matriz de autorizacao."""
    context: dict[str, Any] = {
        "user_exists": False,
        "user_active": False,
        "is_global_admin": False,
        "is_owner": False,
        "member_role": None,
        "project_row_exists": False,
        "project_id": None,
    }
    async with pool.acquire() as conn:
        if requested_by is not None:
            user_row = await conn.fetchrow(
                """
                SELECT
                    u.is_active,
                    EXISTS (
                        SELECT 1 FROM user_groups g
                        WHERE g.user_id = u.id AND g.group_name = 'admin'
                    ) AS is_global_admin
                FROM users u
                WHERE u.id = $1
                """,
                requested_by,
            )
            if user_row:
                context["user_exists"] = True
                context["user_active"] = bool(user_row["is_active"])
                context["is_global_admin"] = bool(user_row["is_global_admin"])

        project_row = await conn.fetchrow(
            "SELECT id, owner_id FROM projects WHERE name = $1",
            project,
        )
        if project_row:
            context["project_row_exists"] = True
            context["project_id"] = project_row["id"]
            if requested_by is not None:
                context["is_owner"] = project_row["owner_id"] == requested_by
                context["member_role"] = await conn.fetchval(
                    """
                    SELECT role FROM project_members
                    WHERE project_id = $1 AND user_id = $2
                    """,
                    project_row["id"],
                    requested_by,
                )
    return context


async def fetch_project_names(pool: asyncpg.Pool) -> list[str]:
    rows = await pool.fetch("SELECT name FROM projects")
    return [row["name"] for row in rows]


async def replace_container_state(
    pool: asyncpg.Pool,
    entries: list[dict[str, str]],
) -> None:
    """Substitui o snapshot de containers por projeto de forma atomica."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM project_container_state")
            if entries:
                await conn.executemany(
                    """
                    INSERT INTO project_container_state(
                        container_name, project, state, status, image,
                        ports, created_at_text, refreshed_at
                    )
                    VALUES($1, $2, $3, $4, $5, $6, $7, now())
                    """,
                    [
                        (
                            entry["container_name"],
                            entry["project"],
                            entry.get("state"),
                            entry.get("status"),
                            entry.get("image"),
                            entry.get("ports"),
                            entry.get("created_at_text"),
                        )
                        for entry in entries
                    ],
                )
