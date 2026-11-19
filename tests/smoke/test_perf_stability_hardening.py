"""Regression and contract tests for PERF-01 through PERF-07 in supabase-multitenant."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "servidor"
STUDIO = ROOT / "studio"
API_ROOT = SERVER / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

os.environ.setdefault("DB_DSN", "postgres://postgres:test@127.0.0.1:5432/postgres")
os.environ.setdefault("FERNET_SECRET", "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE=")
os.environ.setdefault("INTERNAL_HMAC_SECRET", "a" * 64)
os.environ.setdefault("STUDIO_GATEWAY_HMAC_SECRET", "b" * 64)
os.environ.setdefault("PROJECTS_API_HMAC_SECRET", "c" * 64)
os.environ.setdefault("NGINX_HMAC_SECRET", "d" * 64)

from app import edge_functions  # noqa: E402
from app.routers import studio_edge_functions  # noqa: E402
from app.tenant_pools import TenantPoolManager  # noqa: E402


class MultitenantPerfHardeningTests(unittest.IsolatedAsyncioTestCase):
    def test_perf01_option_a_session_mode_and_supavisor_pool_size(self) -> None:
        env_example = (SERVER / ".env.example").read_text(encoding="utf-8")
        project_compose = (SERVER / "generateProject/dockercomposetemplate").read_text(encoding="utf-8")
        project_nginx = (SERVER / "generateProject/nginxtemplate").read_text(encoding="utf-8")
        gen = (SERVER / "generateProject/lib/generate_project_impl.sh").read_text(encoding="utf-8")
        dup = (SERVER / "generateProject/lib/duplicate_project_impl.sh").read_text(encoding="utf-8")

        self.assertIn("POOLER_DEFAULT_POOL_SIZE=15", env_example)
        # Option A: PostgREST stays on Session Mode (:5432 via nginx stream proxy)
        self.assertIn("POOLER_PROXY_PORT_SESSION: ${POOLER_PROXY_PORT_SESSION}", project_compose)
        self.assertIn("${POSTGRES_POOLER}:${POOLER_PROXY_PORT_SESSION}", project_nginx)
        self.assertIn("POOLER_DEFAULT_POOL_SIZE:-15", gen)
        self.assertIn("POOLER_DEFAULT_POOL_SIZE:-15", dup)

    async def test_perf01_tenant_pool_manager_per_tenant_concurrency(self) -> None:
        started_a = asyncio.Event()
        release_a = asyncio.Event()
        entered_b = asyncio.Event()

        class DummyConn:
            async def reset(self) -> None:
                return None

            async def execute(self, _sql: str) -> None:
                return None

            def terminate(self) -> None:
                return None

        class DummyPool:
            def __init__(self, dsn: str):
                self.dsn = dsn
                self.conn = DummyConn()

            async def acquire(self, timeout=None):
                return self.conn

            async def release(self, _conn, timeout=None) -> None:
                return None

            async def close(self) -> None:
                return None

            def terminate(self) -> None:
                return None

        async def fake_create_pool(dsn: str, **_kwargs):
            if "tenant_a" in dsn:
                started_a.set()
                await release_a.wait()
            else:
                entered_b.set()
            return DummyPool(dsn)

        manager = TenantPoolManager(
            factory=fake_create_pool,
            max_tenants=4,
            idle_seconds=60.0,
        )
        uuid_a = str(uuid.uuid4())
        uuid_b = str(uuid.uuid4())
        dsns_a = {"admin": "postgres://a:p@h/tenant_a", "reader": "postgres://r:p@h/tenant_a"}
        dsns_b = {"admin": "postgres://a:p@h/tenant_b", "reader": "postgres://r:p@h/tenant_b"}

        async def use_a():
            async with manager.connection(uuid_a, dsns_a, "admin") as conn:
                return conn

        task_a = asyncio.create_task(use_a())
        await asyncio.wait_for(started_a.wait(), timeout=2.0)

        async with asyncio.timeout(2.0):
            async with manager.connection(uuid_b, dsns_b, "admin") as conn_b:
                self.assertTrue(entered_b.is_set())
                self.assertIsInstance(conn_b, DummyConn)

        release_a.set()
        conn_a = await asyncio.wait_for(task_a, timeout=2.0)
        self.assertIsInstance(conn_a, DummyConn)
        await manager.close()

    def test_perf02_body_limits_and_access_phase_ordering(self) -> None:
        nginx_conf = (STUDIO / "nginx/nginx.conf").read_text(encoding="utf-8")
        internal_hmac = (STUDIO / "nginx/lua/security/internal_hmac.lua").read_text(encoding="utf-8")
        project_nginx = (SERVER / "generateProject/nginxtemplate").read_text(encoding="utf-8")

        self.assertIn("client_max_body_size 2m;", nginx_conf)
        self.assertNotIn("rewrite_by_lua_file /usr/local/openresty/lualib/proxy_rewrites/storage.lua;", nginx_conf)
        self.assertIn("request body too large", internal_hmac)
        self.assertIn("HTTP_REQUEST_ENTITY_TOO_LARGE", internal_hmac)
        functions_block = project_nginx.split("location /functions/v1/", 1)[1].split("}", 1)[0]
        self.assertIn("client_max_body_size 10m;", functions_block)

    def test_perf03_and_04_caches_indexes_and_flutter_slivers(self) -> None:
        nginx_conf = (STUDIO / "nginx/nginx.conf").read_text(encoding="utf-8")
        studio_ctx = (STUDIO / "nginx/lua/project_context/studio_context.lua").read_text(encoding="utf-8")
        csrf_lua = (STUDIO / "nginx/lua/security/csrf.lua").read_text(encoding="utf-8")
        assistant_store = (STUDIO / "assistant/store.mjs").read_text(encoding="utf-8")
        migration = (API_ROOT / "app/migrations/0035_mailer_expires_at_indexes.sql").read_text(encoding="utf-8")
        flutter_list = (STUDIO / "seletor_de_projetos/lib/project_list_page.dart").read_text(encoding="utf-8")
        flutter_card = (STUDIO / "seletor_de_projetos/lib/widgets/project_card.dart").read_text(encoding="utf-8")
        flutter_repo = (STUDIO / "seletor_de_projetos/lib/data/project_repository.dart").read_text(encoding="utf-8")

        self.assertIn("lua_shared_dict studio_context_cache 5m;", nginx_conf)
        self.assertIn("studio_context_cache", studio_ctx)
        self.assertIn("cached_origin", csrf_lua)
        self.assertIn("PRAGMA synchronous=NORMAL", assistant_store)
        self.assertIn("idx_nonces_expires_at", assistant_store)
        self.assertIn("idx_mailer_publication_grant_expires_at", migration)
        self.assertIn("idx_mailer_step_up_used_expires_at", migration)
        self.assertIn("SliverGrid(", flutter_list)
        self.assertNotIn("GridView.builder(", flutter_list)
        self.assertIn("initialStatus", flutter_card)
        self.assertIn("/api/projects?include_status=true", flutter_repo)

    def test_perf05_edge_runtime_preserves_multitenant_security_invariants(self) -> None:
        index_ts = (SERVER / "volumes/functions/main/index.ts").read_text(encoding="utf-8")
        self.assertEqual(edge_functions.PLATFORM_MAX_CONCURRENT_GLOBAL, 24)
        self.assertEqual(edge_functions.QUOTA_SPECS["max_concurrent_project"]["max"], 8)
        self.assertIn("const MAX_CONCURRENT_GLOBAL = 24", index_ts)
        self.assertIn("if (result.status === 101)", index_ts)
        self.assertIn("eszipBundles", index_ts)
        self.assertIn("forceCreate: true", index_ts)
        self.assertNotIn("Deno.env.get(", index_ts)
        self.assertNotIn("tenantCache", index_ts)

    async def test_perf06_cron_releases_advisory_lock_before_http_and_records_429_as_error(self) -> None:
        advisory_held = {"value": False}
        lock_state_during_http: list[bool] = []
        updates: list[tuple] = []

        class FakeConn:
            async def fetchval(self, sql: str, *_args):
                if "pg_try_advisory_lock" in sql:
                    if advisory_held["value"]:
                        return False
                    advisory_held["value"] = True
                    return True
                if "pg_advisory_unlock" in sql:
                    advisory_held["value"] = False
                    return True
                return None

            async def fetch(self, sql: str, *_args):
                if "FROM project_edge_function_schedules" in sql:
                    return [{
                        "id": uuid.uuid4(),
                        "project_id": uuid.uuid4(),
                        "function_name": "hello",
                        "cron": "* * * * *",
                        "method": "POST",
                        "path": "",
                        "headers_json": "{}",
                        "body": "",
                        "auth_mode": "service_role",
                        "project_name": "alpha",
                        "public_ref": "a" * 20,
                        "tenant_uuid": uuid.uuid4(),
                    }]
                return []

            async def execute(self, sql: str, *args):
                updates.append((sql, args))

        class FakePool:
            def acquire(self):
                class _Ctx:
                    async def __aenter__(self_inner):
                        return FakeConn()

                    async def __aexit__(self_inner, *_exc):
                        return False

                return _Ctx()

        async def fake_execute(*_args, **_kwargs):
            lock_state_during_http.append(advisory_held["value"])
            return (429, {}, "{}", False, 15, "req-429", None)

        now = datetime.now(timezone.utc)
        with (
            patch.object(studio_edge_functions, "configuration", new=AsyncMock(return_value={"enabled": True, "network_allowlist": []})),
            patch.object(studio_edge_functions.store, "read_state", return_value={}),
            patch.object(studio_edge_functions.store, "item", return_value={"published_revision": "a" * 64}),
            patch.object(studio_edge_functions.store, "next_cron_run", return_value=now + timedelta(minutes=1)),
            patch.object(studio_edge_functions, "canonical_projection_credentials", return_value={"jwt_secret": "j", "anon_key": "a", "service_role_key": "s"}),
            patch.object(studio_edge_functions, "internal_keys", new=AsyncMock(return_value={"publishable": "a", "secret": "s"})),
            patch.object(studio_edge_functions, "load_project_secrets", new=AsyncMock(return_value={})),
            patch.object(studio_edge_functions, "load_project_quotas", new=AsyncMock(return_value=({"worker_timeout_ms": 60000}, {}))),
            patch.object(studio_edge_functions, "_execute_function_http", side_effect=fake_execute),
        ):
            count = await studio_edge_functions.scan_edge_function_schedules(FakePool(), now=now)

        self.assertEqual(count, 1)
        self.assertEqual(lock_state_during_http, [False])
        status_updates = [args for sql, args in updates if "last_status=$2" in sql]
        self.assertEqual(len(status_updates), 1)
        self.assertEqual(status_updates[0][1], 429)
        self.assertIn("429", status_updates[0][4])

    def test_perf07_unbuffered_storage_downloads_and_realistic_limit(self) -> None:
        project_nginx = (SERVER / "generateProject/nginxtemplate").read_text(encoding="utf-8")
        env_example = (SERVER / ".env.example").read_text(encoding="utf-8")
        storage_block = project_nginx.split("location /storage/v1/", 1)[1].split("location /vector/", 1)[0]
        self.assertIn("proxy_request_buffering off;", storage_block)
        self.assertIn("proxy_buffering off;", storage_block)
        self.assertIn("STORAGE_FILE_SIZE_LIMIT=5368709120", env_example)
        self.assertIn("STORAGE_FILE_SIZE_LIMIT_STANDARD=5368709120", env_example)


if __name__ == "__main__":
    unittest.main()
