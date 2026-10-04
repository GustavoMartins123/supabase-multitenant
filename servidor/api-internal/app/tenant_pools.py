from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.meta_connections import (
    get_project_assistant_reader_connection_string,
    get_project_meta_connection_string,
)


class TenantPoolUnavailable(Exception):
    pass


async def reset_tenant_session(connection):
    await connection.reset()
    await connection.execute("SET SESSION AUTHORIZATION DEFAULT; RESET ROLE")


@dataclass
class TenantPools:
    dsns: dict[str, str] = field(repr=False)
    pools: dict = field(default_factory=dict)
    users: int = 0
    touched: float = field(default_factory=time.monotonic)


class TenantPoolManager:
    def __init__(self, *, size_per_role=2, max_tenants=16, max_requests=8,
                 acquire_timeout=2.0, idle_seconds=60.0, factory=asyncpg.create_pool):
        if min(size_per_role, max_tenants, max_requests, acquire_timeout, idle_seconds) <= 0:
            raise ValueError("Tenant pool limits must be positive")
        self.size_per_role = size_per_role
        self.max_tenants = max_tenants
        self.max_requests = max_requests
        self.acquire_timeout = acquire_timeout
        self.idle_seconds = idle_seconds
        self.factory = factory
        self._tenants: dict[str, TenantPools] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def _close(self, entry):
        pools = list(entry.pools.values())
        try:
            async with asyncio.timeout(5):
                await asyncio.gather(*(pool.close() for pool in pools))
        except BaseException as exc:
            for pool in pools:
                pool.terminate()
            if not isinstance(exc, TimeoutError):
                raise

    async def _reserve(self, identity, dsns, access):
        async with self._lock:
            if self._closed:
                raise TenantPoolUnavailable("Tenant pools are shutting down")
            now = time.monotonic()
            for key, entry in list(self._tenants.items()):
                if entry.users == 0 and now - entry.touched >= self.idle_seconds:
                    del self._tenants[key]
                    await self._close(entry)
            entry = self._tenants.get(identity)
            if entry and entry.dsns != dsns:
                if entry.users:
                    raise TenantPoolUnavailable("Tenant database identity changed during use")
                del self._tenants[identity]
                await self._close(entry)
                entry = None
            if entry is None:
                if len(self._tenants) >= self.max_tenants:
                    idle = [(key, value) for key, value in self._tenants.items() if not value.users]
                    if not idle:
                        raise TenantPoolUnavailable("Tenant pool capacity exhausted")
                    key, expired = min(idle, key=lambda item: item[1].touched)
                    del self._tenants[key]
                    await self._close(expired)
                entry = TenantPools(dict(dsns))
                self._tenants[identity] = entry
            if entry.users >= self.max_requests:
                raise TenantPoolUnavailable("Tenant request capacity exhausted")
            if access not in entry.pools:
                try:
                    entry.pools[access] = await self.factory(
                        dsns[access], min_size=0, max_size=self.size_per_role,
                        timeout=5, command_timeout=30, reset=reset_tenant_session,
                        max_inactive_connection_lifetime=self.idle_seconds,
                    )
                except Exception as exc:
                    raise TenantPoolUnavailable("Tenant database pool creation failed") from exc
            entry.users += 1
            return entry, entry.pools[access]

    @asynccontextmanager
    async def connection(self, tenant_uuid, dsns, access):
        identity = str(UUID(str(tenant_uuid)))
        if access not in {"reader", "admin"} or set(dsns) != {"reader", "admin"}:
            raise ValueError("Explicit reader and admin database identities required")
        try:
            async with asyncio.timeout(self.acquire_timeout):
                entry, pool = await self._reserve(identity, dsns, access)
        except TimeoutError as exc:
            raise TenantPoolUnavailable("Tenant pool admission timed out") from exc
        try:
            try:
                connection = await pool.acquire(timeout=self.acquire_timeout)
            except Exception as exc:
                raise TenantPoolUnavailable("Tenant database acquisition failed") from exc
            try:
                yield connection
            finally:
                try:
                    await pool.release(connection, timeout=self.acquire_timeout)
                except Exception as exc:
                    raise TenantPoolUnavailable("Tenant database session cleanup failed") from exc
        finally:
            async with self._lock:
                entry.users -= 1
                entry.touched = time.monotonic()

    async def close(self):
        async with self._lock:
            self._closed = True
            entries = list(self._tenants.values())
            self._tenants.clear()
        await asyncio.gather(*(self._close(entry) for entry in entries))


tenant_pools = TenantPoolManager()


@asynccontextmanager
async def tenant_connection(project, access):
    try:
        dsns = {
            "reader": get_project_assistant_reader_connection_string(project["name"], project["tenant_uuid"]),
            "admin": get_project_meta_connection_string(project["name"], project["tenant_uuid"]),
        }
        async with tenant_pools.connection(project["tenant_uuid"], dsns, access) as connection:
            yield connection
    except TenantPoolUnavailable as exc:
        raise HTTPException(503, "Tenant database pool unavailable or saturated") from exc
