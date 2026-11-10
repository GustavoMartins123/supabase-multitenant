"""Exercise the multitenant metadata handler with real HTTP requests."""
from __future__ import annotations

import ast
from contextlib import asynccontextmanager
import hmac
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api-internal"))
from app import storage_policies


class StoragePolicyProxyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.project = {"id": uuid.uuid4(), "tenant_uuid": uuid.uuid4(), "name": "alpha"}
        self.conn = Mock(fetchval=AsyncMock(return_value="encrypted"))

        @asynccontextmanager
        async def connection():
            yield self.conn

        self.conn.transaction = connection
        self.pool = Mock(acquire=connection)

        async def get_pool():
            return self.pool

        self.authorize = AsyncMock()
        namespace = {
            "Request": Request, "Depends": Depends, "get_pool": get_pool,
            "validate_project_ref": lambda value: value,
            "resolve_authenticated_user": AsyncMock(return_value={"id": "admin"}),
            "get_public_project_row": AsyncMock(return_value=self.project),
            "ensure_project_admin_access": self.authorize,
            "decrypt_project_secret": AsyncMock(return_value="service-key"),
            "get_project_meta_connection_string": lambda *args: "postgres://tenant:p@db/project",
            "_extract_project_admin_apikey": lambda request: request.headers.get("apikey", ""),
            "PG_META_INTERNAL_URL": "http://metadata", "PG_META_CRYPTO_KEY": "key",
            "postgres_meta_authorization": lambda key: "Bearer metadata-key",
            "encrypt_postgres_meta_uri": lambda *args: "encrypted-dsn",
            "hmac": hmac, "json": json, "httpx": httpx,
            "storage_policies": storage_policies, "HTTPException": HTTPException, "Response": Response,
        }
        tree = ast.parse((ROOT / "api-internal/app/routers/project_insights.py").read_text())
        handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "proxy_project_meta")
        handler.decorator_list = []
        exec(compile(ast.Module(body=[handler], type_ignores=[]), "project_insights.py", "exec"), namespace)
        app = FastAPI()
        app.add_api_route("/meta/{meta_path:path}", namespace["proxy_project_meta"], methods=["POST"])
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api")
        self.addAsyncCleanup(self.client.aclose)
        self.forwarded = []
        factory = httpx.AsyncClient

        def upstream(request):
            self.forwarded.append(request)
            return httpx.Response(200, json=[])

        self.upstream = patch.object(httpx, "AsyncClient", side_effect=lambda **kwargs: factory(transport=httpx.MockTransport(upstream), **kwargs))
        self.upstream.start()
        self.addCleanup(self.upstream.stop)
        self.key = patch.object(storage_policies, "delegation_key", return_value=b"a" * 32)
        self.key.start()
        self.addCleanup(self.key.stop)

    async def query(self, sql):
        return await self.client.post("/meta/query?ref=aaaaaaaaaaaaaaaaaaaa", headers={"apikey": "service-key"}, json={"query": sql})

    async def test_manual_transaction_reaches_metadata_with_signed_policy_ddl(self):
        response = await self.query("BEGIN; INSERT INTO storage.buckets(id,name,public) VALUES('Manual','Manual',false); CREATE POLICY p ON storage.objects TO authenticated USING(bucket_id='Manual'); COMMIT;")
        self.assertEqual(response.status_code, 200, response.text)
        sql = json.loads(self.forwarded[0].content)["query"]
        self.assertTrue(sql.startswith("BEGIN;"))
        self.assertTrue(sql.endswith("COMMIT;"))
        self.assertIn("INSERT INTO storage.buckets", sql)
        self.assertIn("studio_storage_guard.execute_policy(", sql)
        self.assertEqual(self.forwarded[0].url.path, "/query")

    async def test_regular_queries_keep_the_existing_body(self):
        response = await self.query("SELECT 1")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(json.loads(self.forwarded[0].content)["query"], "SELECT 1")

    async def test_non_administrator_is_rejected_before_metadata(self):
        self.authorize.side_effect = HTTPException(403, "admin required")
        response = await self.query("CREATE POLICY p ON storage.objects TO authenticated USING(true)")
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.forwarded, [])

    async def test_unsafe_policy_does_not_reach_metadata(self):
        response = await self.query("CREATE POLICY p ON storage.objects TO authenticated USING(public.escalate())")
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(self.forwarded, [])

    async def test_unavailable_signing_key_does_not_reach_metadata(self):
        with patch.object(storage_policies, "delegation_key", side_effect=RuntimeError("missing key")):
            response = await self.query("CREATE POLICY p ON storage.objects TO authenticated USING(true)")
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.forwarded, [])
