"""One committed-change listener per API process; snapshots remain durable in SQL."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

import asyncpg
from fastapi import HTTPException

from app.jobs import serialize_job

CHANNEL = "project_jobs_changed"
WATCH_TIMEOUT_SECONDS = 25


class JobChangeHub:
    def __init__(self):
        self._connection = None
        self._event = asyncio.Event()
        self.version = 0
        self._failed = True

    async def start(self, dsn: str):
        self._connection = await asyncpg.connect(dsn)
        try:
            self._connection.add_termination_listener(self._terminated)
            await self._connection.add_listener(CHANNEL, self._notification)
        except BaseException:
            await self.close()
            raise
        self._failed = False

    def _wake(self):
        self.version += 1
        event, self._event = self._event, asyncio.Event()
        event.set()

    def _notification(self, connection, pid, channel, payload):
        self._wake()

    def _terminated(self, connection):
        self._failed = True
        self._wake()

    def ensure_ready(self):
        if self._failed or self._connection is None or self._connection.is_closed():
            raise HTTPException(503, "Job change listener unavailable")

    async def wait(self, version: int, timeout: float):
        self.ensure_ready()
        if self.version == version:
            try:
                await asyncio.wait_for(self._event.wait(), timeout)
            except TimeoutError:
                pass
        self.ensure_ready()

    async def close(self):
        self._failed = True
        self._wake()
        if self._connection is not None:
            await self._connection.close()
            self._connection = None


job_change_hub = JobChangeHub()


async def job_snapshot(pool, auth_user: dict, watched_ids: list[uuid.UUID]) -> dict:
    rows = await pool.fetch(
        """
        SELECT j.* FROM jobs j
        WHERE (j.status IN ('queued', 'running') OR j.job_id = ANY($1::uuid[]))
          AND ($2::boolean OR j.created_by = $3 OR (
            j.created_by IS NULL AND EXISTS (
              SELECT 1 FROM projects p WHERE p.id = j.project_uuid
                AND (p.owner_id = $3 OR EXISTS (
                  SELECT 1 FROM project_members pm
                  WHERE pm.project_id = p.id AND pm.user_id = $3
                ))
            )
          ))
        ORDER BY j.created_at, j.job_id
        LIMIT 401
        """,
        watched_ids, auth_user["is_global_admin"], auth_user["db_user_id"],
    )
    if len(rows) > 400 or sum(row["status"] in ("queued", "running") for row in rows) > 200:
        raise HTTPException(409, "Too many active jobs for this subscription")
    if not set(watched_ids).issubset({row["job_id"] for row in rows}):
        raise HTTPException(403, "A watched job is unavailable or no longer authorized")
    items = [serialize_job(row) for row in rows]
    cursor = hashlib.sha256(json.dumps(items, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"items": items, "cursor": cursor}
