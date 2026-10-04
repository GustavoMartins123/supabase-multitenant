from __future__ import annotations

import asyncio
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "servidor/api-internal"))
from app.tenant_pools import TenantPoolManager, TenantPoolUnavailable
from fastapi import HTTPException


class FakePool:
    def __init__(self, dsn, **options):
        self.dsn = dsn
        self.options = options
        self.slots = asyncio.Semaphore(options["max_size"])
        self.leases = 0
        self.closed = False

    async def acquire(self, timeout):
        await asyncio.wait_for(self.slots.acquire(), timeout)
        self.leases += 1
        return object()

    async def release(self, connection, timeout):
        self.leases -= 1
        self.slots.release()

    async def close(self):
        self.closed = True

    def terminate(self):
        self.closed = True


class TenantPoolTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.created = []

        async def factory(dsn, **options):
            await asyncio.sleep(0)
            pool = FakePool(dsn, **options)
            self.created.append(pool)
            return pool

        self.manager = TenantPoolManager(size_per_role=1, max_tenants=2, max_requests=4,
                                         acquire_timeout=.03, idle_seconds=60, factory=factory)
        self.identity = uuid.uuid4()
        self.dsns = {"reader": "reader-dsn", "admin": "admin-dsn"}
        self.addAsyncCleanup(self.manager.close)

    def connection(self, identity=None, access="reader", dsns=None):
        return self.manager.connection(identity or self.identity, dsns or self.dsns, access)

    async def test_reuses_canonical_uuid_but_keeps_roles_and_tenants_separate(self):
        for identity in (self.identity, str(self.identity).upper()):
            async with self.connection(identity):
                pass
        async with self.connection(access="admin"):
            pass
        async with self.connection(uuid.uuid4()):
            pass
        self.assertEqual(len(self.created), 3)
        self.assertEqual([p.dsn for p in self.created], ["reader-dsn", "admin-dsn", "reader-dsn"])
        self.assertTrue(all(p.options["min_size"] == 0 for p in self.created))
        self.assertTrue(all(p.options["max_size"] == 1 for p in self.created))

    async def test_saturation_is_bounded_without_overflow_and_admin_remains_separate(self):
        async with self.connection():
            with self.assertRaises(TenantPoolUnavailable):
                async with self.connection():
                    self.fail("Overflow connection")
            async with self.connection(access="admin"):
                self.assertEqual(sum(p.leases for p in self.created), 2)
        self.assertEqual(len(self.created), 2)
        self.assertEqual(self.manager._tenants[str(self.identity)].users, 0)

    async def test_concurrent_requests_create_one_pool(self):
        self.manager.acquire_timeout = 1
        async def run():
            async with self.connection():
                await asyncio.sleep(.001)
        await asyncio.gather(*(run() for _ in range(4)))
        self.assertEqual(len(self.created), 1)

    async def test_global_capacity_never_evicts_active_tenants(self):
        async with self.connection():
            async with self.connection(uuid.uuid4()):
                with self.assertRaises(TenantPoolUnavailable):
                    async with self.connection(uuid.uuid4()):
                        self.fail("Global capacity overflow")
                self.assertTrue(all(not p.closed for p in self.created))

    async def test_idle_lru_is_closed_before_replacement(self):
        for _ in range(3):
            async with self.connection(uuid.uuid4()):
                pass
        self.assertEqual(len(self.manager._tenants), 2)
        self.assertTrue(self.created[0].closed)

    async def test_changed_credentials_rejected_during_use_and_refreshed_when_idle(self):
        changed = {**self.dsns, "reader": "rotated-reader-dsn"}
        async with self.connection():
            with self.assertRaises(TenantPoolUnavailable):
                async with self.connection(dsns=changed):
                    self.fail("Stale credential reuse")
        async with self.connection(dsns=changed):
            pass
        self.assertTrue(self.created[0].closed)
        self.assertEqual(self.created[-1].dsn, changed["reader"])

    async def test_cancellation_while_waiting_or_using_releases_reservation(self):
        async def run():
            async with self.connection():
                await asyncio.sleep(10)
        async with self.connection():
            task = asyncio.create_task(run())
            await asyncio.sleep(.005)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertEqual(self.manager._tenants[str(self.identity)].users, 1)
        task = asyncio.create_task(run())
        await asyncio.sleep(.005)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.created[0].leases, 0)
        self.assertEqual(self.manager._tenants[str(self.identity)].users, 0)

    async def test_request_admission_limit(self):
        self.manager.max_requests = 1
        async with self.connection():
            with self.assertRaises(TenantPoolUnavailable):
                async with self.connection(access="admin"):
                    self.fail("Unbounded requests")
        self.assertEqual(len(self.created), 1)

    async def test_idle_expiry_and_shutdown(self):
        async with self.connection():
            pass
        self.manager._tenants[str(self.identity)].touched -= 100
        async with self.connection(uuid.uuid4()):
            pass
        self.assertTrue(self.created[0].closed)
        await self.manager.close()
        self.assertTrue(all(p.closed for p in self.created))
        with self.assertRaises(TenantPoolUnavailable):
            async with self.connection():
                self.fail("Pool after shutdown")

    async def test_pool_creation_failure_does_not_open_secondary_connection(self):
        calls = 0

        async def unavailable(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise OSError("synthetic unavailable")

        self.manager.factory = unavailable
        with self.assertRaises(TenantPoolUnavailable):
            async with self.connection():
                self.fail("Database failure ignored")
        self.assertEqual(calls, 1)
        self.assertEqual(self.manager._tenants[str(self.identity)].users, 0)

    async def test_reset_failure_is_explicit_and_clears_admission(self):
        with self.assertRaises(TenantPoolUnavailable):
            async with self.connection():
                async def failed_release(*args, **kwargs):
                    raise OSError("synthetic session cleanup failure")
                self.created[0].release = failed_release
        self.assertEqual(self.manager._tenants[str(self.identity)].users, 0)

    async def test_saturation_is_translated_to_http_503(self):
        from app import tenant_pools as module

        project = {"name": "synthetic", "tenant_uuid": self.identity}
        with patch.object(module, "tenant_pools", self.manager), \
             patch.object(module, "get_project_assistant_reader_connection_string", return_value=self.dsns["reader"]), \
             patch.object(module, "get_project_meta_connection_string", return_value=self.dsns["admin"]):
            async with module.tenant_connection(project, "reader"):
                with self.assertRaises(HTTPException) as error:
                    async with module.tenant_connection(project, "reader"):
                        self.fail("Saturated HTTP request admitted")
                self.assertEqual(error.exception.status_code, 503)
