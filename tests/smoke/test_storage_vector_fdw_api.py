"""Tests for Storage Vector Buckets FDW guard, Vault grants, SSRF pinning, and SQL rewrites."""

from __future__ import annotations

import ast
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
import uuid

import asyncpg
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
import httpx

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "servidor" / "api-internal"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import control_plane_roles, storage_policies
from app.tenant_meta_identity import (
    tenant_meta_credentials,
    tenant_storage_policy_key,
    tenant_vector_fdw_key,
)

TENANT = "11111111-1111-4111-8111-111111111111"
PROJECT_NAME = "alpha_proj"
EXPECTED_ENDPOINT = f"http://supabase-nginx-{PROJECT_NAME}:8081/vector"


class StorageVectorFdwSqlRewriteTests(unittest.TestCase):
    def test_studio_vector_fdw_flows_rewrite_and_pin_ssrf_safely(self) -> None:
        tenant_uuid = uuid.UUID(TENANT)

        # (a) CREATE EXTENSION wrappers -> safe pre-install check; non-wrappers untouched; wrong schema rejected.
        for sql in (
            "CREATE EXTENSION wrappers SCHEMA extensions VERSION '0.6.3';",
            "CREATE EXTENSION IF NOT EXISTS wrappers WITH SCHEMA extensions;",
            "CREATE EXTENSION IF NOT EXISTS wrappers;",
        ):
            with self.subTest(sql=sql):
                prepared = storage_policies.prepare_policy_statements(
                    sql, project_id=PROJECT_NAME
                )
                self.assertIsNotNone(prepared)
                rewritten = storage_policies.rewrite_policy_statements(
                    prepared,
                    tenant_uuid,
                    project_id=PROJECT_NAME,
                    key=b"a" * 32,
                    now=100,
                )
                self.assertNotIn("CREATE EXTENSION", rewritten.upper())
                self.assertIn("pg_catalog.pg_extension", rewritten)
                self.assertIn("'wrappers'", rewritten)

        self.assertIsNone(
            storage_policies.prepare_policy_statements(
                "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
            )
        )
        with self.assertRaises(storage_policies.StoragePolicyError):
            storage_policies.prepare_policy_statements(
                "CREATE EXTENSION wrappers SCHEMA public;", project_id=PROJECT_NAME
            )

        # (b) & (c) CREATE / DROP FOREIGN DATA WRAPPER -> HMAC-signed studio_vector_fdw_guard calls
        # including digit-leading vector bucket names such as "2026_docs_fdw".
        for sql, fn_name, expected_fdw in (
            (
                "CREATE FOREIGN DATA WRAPPER my_docs_fdw HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator;",
                "ensure_s3_vectors_fdw",
                "my_docs_fdw",
            ),
            (
                'CREATE FOREIGN DATA WRAPPER "2026_docs_fdw" HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator;',
                "ensure_s3_vectors_fdw",
                "2026_docs_fdw",
            ),
            (
                "BEGIN; CREATE FOREIGN DATA WRAPPER my_docs_fdw HANDLER extensions.s3_vectors_fdw_handler VALIDATOR extensions.s3_vectors_fdw_validator; COMMIT;",
                "ensure_s3_vectors_fdw",
                "my_docs_fdw",
            ),
            (
                "DROP FOREIGN DATA WRAPPER IF EXISTS my_docs_fdw CASCADE;",
                "drop_s3_vectors_fdw",
                "my_docs_fdw",
            ),
            (
                'DROP FOREIGN DATA WRAPPER IF EXISTS "2026_docs_fdw" CASCADE;',
                "drop_s3_vectors_fdw",
                "2026_docs_fdw",
            ),
            (
                "DROP FOREIGN DATA WRAPPER my_docs_fdw;",
                "drop_s3_vectors_fdw",
                "my_docs_fdw",
            ),
        ):
            with self.subTest(sql=sql):
                prepared = storage_policies.prepare_policy_statements(
                    sql, project_id=PROJECT_NAME
                )
                self.assertIsNotNone(prepared)
                rewritten = storage_policies.rewrite_policy_statements(
                    prepared,
                    tenant_uuid,
                    project_id=PROJECT_NAME,
                    key=b"a" * 32,
                    now=100,
                )
                expected_role = f"tenant_meta_{tenant_uuid.hex}"
                expected_key = storage_policies.vector_fdw_delegation_key(
                    tenant_uuid, base_key=b"a" * 32
                )
                expected_proof = hmac.new(
                    expected_key,
                    f"{fn_name}\n{expected_role}\n160\n{expected_fdw}".encode(),
                    hashlib.sha256,
                ).hexdigest()
                self.assertIn(
                    f"SELECT studio_vector_fdw_guard.{fn_name}('{expected_fdw}',160,'{expected_proof}')",
                    rewritten,
                )
                self.assertNotIn("FOREIGN DATA WRAPPER", rewritten.upper())

        # Digit-leading server/FDW identifiers stay properly quoted on static CREATE SERVER.
        digit_server_sql = (
            'CREATE SERVER "2026_docs_fdw_server" FOREIGN DATA WRAPPER "2026_docs_fdw" '
            "OPTIONS (vault_access_key_id 'id1', aws_region 'local', endpoint_url 'https://evil.example');"
        )
        rewritten_digit_server = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                digit_server_sql, project_id=PROJECT_NAME
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
            storage_s3_region="us-east-1",
        )
        self.assertIn(
            'CREATE SERVER "2026_docs_fdw_server" FOREIGN DATA WRAPPER "2026_docs_fdw"',
            rewritten_digit_server,
        )
        self.assertIn(f"endpoint_url '{EXPECTED_ENDPOINT}'", rewritten_digit_server)
        self.assertIn("aws_region 'us-east-1'", rewritten_digit_server)
        self.assertNotIn("evil.example", rewritten_digit_server)

        for bad_fdw in (
            "CREATE FOREIGN DATA WRAPPER evil_fdw HANDLER postgres_fdw_handler VALIDATOR postgres_fdw_validator;",
            "CREATE FOREIGN DATA WRAPPER evil_fdw HANDLER file_fdw_handler;",
            'CREATE FOREIGN DATA WRAPPER "Bad-Name" HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator;',
            "DROP FOREIGN DATA WRAPPER a, b CASCADE;",
            "ALTER FOREIGN DATA WRAPPER my_docs_fdw HANDLER postgres_fdw_handler;",
        ):
            with self.subTest(bad_fdw=bad_fdw), self.assertRaises(
                storage_policies.StoragePolicyError
            ):
                storage_policies.prepare_policy_statements(
                    bad_fdw, project_id=PROJECT_NAME
                )

        # (d) SSRF pinning on static CREATE/ALTER SERVER and Studio DO $$ execute format(...).
        static_create = (
            "CREATE SERVER my_docs_fdw_server FOREIGN DATA WRAPPER my_docs_fdw "
            "OPTIONS (vault_access_key_id 'id1', vault_secret_access_key 'id2', aws_region 'local', endpoint_url 'http://169.254.169.254/latest');"
        )
        rewritten = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                static_create, project_id=PROJECT_NAME, storage_s3_region="us-east-1"
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
            storage_s3_region="us-east-1",
        )
        self.assertIn(f"endpoint_url '{EXPECTED_ENDPOINT}'", rewritten)
        self.assertIn("aws_region 'us-east-1'", rewritten)
        self.assertNotIn("169.254.169.254", rewritten)

        omitted_endpoint = (
            "CREATE SERVER my_docs_fdw_server FOREIGN DATA WRAPPER my_docs_fdw "
            "OPTIONS (vault_access_key_id 'id1');"
        )
        rewritten_omitted = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                omitted_endpoint, project_id=PROJECT_NAME
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
            storage_s3_region="sa-east-1",
        )
        self.assertIn(f"endpoint_url '{EXPECTED_ENDPOINT}'", rewritten_omitted)
        self.assertIn("aws_region 'sa-east-1'", rewritten_omitted)

        # Fail closed when rewriting a server statement without project_id.
        with self.assertRaises(storage_policies.StoragePolicyError):
            storage_policies.rewrite_policy_statements(
                storage_policies.prepare_policy_statements(omitted_endpoint),
                tenant_uuid,
                storage_s3_region="us-east-1",
            )

        alter_srv = (
            "ALTER SERVER my_docs_fdw_server OPTIONS "
            "(SET endpoint_url 'http://storage:5001', ADD aws_region 'eu-west-1', SET supabase_target_schema 'my_vec');"
        )
        rewritten_alter = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                alter_srv, project_id=PROJECT_NAME
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
            storage_s3_region="us-east-1",
        )
        self.assertIn(f"SET endpoint_url '{EXPECTED_ENDPOINT}'", rewritten_alter)
        self.assertIn("ADD aws_region 'us-east-1'", rewritten_alter)
        self.assertIn("SET supabase_target_schema 'my_vec'", rewritten_alter)
        self.assertNotIn("storage:5001", rewritten_alter)

        for bad_ssrf in (
            "ALTER SERVER my_docs_fdw_server OPTIONS (DROP endpoint_url);",
            "ALTER SERVER my_docs_fdw_server OPTIONS (DROP aws_region);",
            "DO $$ BEGIN EXECUTE 'CREATE SERVER s FOREIGN DATA WRAPPER f OPTIONS (endpoint_url ''http://storage:5001'')'; END $$;",
            "DO $$ BEGIN EXECUTE format('ALTER SERVER s OPTIONS (SET endpoint_url %L)', 'http://storage:5001'); END $$;",
            "DO $$ BEGIN CREATE FOREIGN DATA WRAPPER f HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; END $$;",
            "CREATE FUNCTION public.sneaky() RETURNS void LANGUAGE plpgsql AS $$ BEGIN EXECUTE 'CREATE SERVER s FOREIGN DATA WRAPPER f'; END $$;",
            "DO $$ BEGIN EXECUTE format('create server s foreign data wrapper f options (vault_access_key_id %L, endpoint_url %L)', pg_read_file('/etc/passwd'), 'http://x'); END $$;",
            "DROP SCHEMA studio_vector_fdw_guard;",
            "SELECT * FROM studio_vector_fdw_guard.authorities;",
            "SELECT studio_vector_fdw_guard.ensure_s3_vectors_fdw('my_fdw', 9999999999, '0000000000000000000000000000000000000000000000000000000000000000');",
            "DROP FUNCTION studio_vector_fdw_guard.ensure_s3_vectors_fdw(text, bigint, text);",
            "DROP EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint;",
            "ALTER EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint DISABLE;",
            "CREATE SCHEMA foo AUTHORIZATION supabase_admin;",
            "CREATE SCHEMA AUTHORIZATION postgres;",
            "CREATE SCHEMA studio_vector_fdw_guard AUTHORIZATION postgres;",
            "ALTER SCHEMA my_vectors OWNER TO postgres;",
        ):
            with self.subTest(bad_ssrf=bad_ssrf), self.assertRaises(
                storage_policies.StoragePolicyError
            ):
                storage_policies.prepare_policy_statements(
                    bad_ssrf, project_id=PROJECT_NAME
                )

        # (e) CREATE SCHEMA AUTHORIZATION postgres -> strips AUTHORIZATION postgres.
        for sql, expected_sql in (
            ("CREATE SCHEMA my_vectors AUTHORIZATION postgres;", "CREATE SCHEMA my_vectors;"),
            (
                'CREATE SCHEMA IF NOT EXISTS "my-vectors" AUTHORIZATION "postgres";',
                'CREATE SCHEMA IF NOT EXISTS "my-vectors";',
            ),
        ):
            rewritten_schema = storage_policies.rewrite_policy_statements(
                storage_policies.prepare_policy_statements(
                    sql, project_id=PROJECT_NAME
                ),
                tenant_uuid,
                project_id=PROJECT_NAME,
            )
            self.assertEqual(rewritten_schema, expected_sql)

        # (f) Upstream Studio CreateVectorTable (ei) IMPORT FOREIGN SCHEMA rewrite.
        ei_sql = (
            "IMPORT FOREIGN SCHEMA my_vectors FROM SERVER my_docs_fdw_server "
            "INTO my_vectors OPTIONS (bucket_name 'my-docs', strict 'true');"
        )
        rewritten_ei = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(ei_sql, project_id=PROJECT_NAME),
            tenant_uuid,
            project_id=PROJECT_NAME,
        )
        self.assertEqual(
            rewritten_ei,
            'IMPORT FOREIGN SCHEMA "my-docs" FROM SERVER my_docs_fdw_server INTO my_vectors OPTIONS (strict \'true\');',
        )
        ei_quoted_bucket = (
            "IMPORT FOREIGN SCHEMA my_vectors FROM SERVER my_docs_fdw_server "
            'INTO my_vectors OPTIONS (bucket_name \'a"b\', strict \'true\', other_opt \'val\');'
        )
        rewritten_quoted = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                ei_quoted_bucket, project_id=PROJECT_NAME
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
        )
        self.assertEqual(
            rewritten_quoted,
            'IMPORT FOREIGN SCHEMA "a""b" FROM SERVER my_docs_fdw_server INTO my_vectors OPTIONS (strict \'true\', other_opt \'val\');',
        )
        # Already-correct wrappers >= 0.5.7 form without bucket_name stays untouched.
        self.assertIsNone(
            storage_policies.prepare_policy_statements(
                'IMPORT FOREIGN SCHEMA "my-docs" FROM SERVER my_docs_fdw_server INTO my_vectors OPTIONS (strict \'true\');'
            )
        )

        # Full Studio v19/v20 tf transaction (drop + vault delete + create fdw + vault create + DO execute format).
        studio_tf_sql = """begin;
drop foreign data wrapper if exists "2026_docs_fdw" cascade;
do $$
begin
  delete from vault.secrets where name = '2026_docs_fdw_vault_access_key_id';
end $$;
create foreign data wrapper "2026_docs_fdw"
handler s3_vectors_fdw_handler
validator s3_vectors_fdw_validator;
do $$
begin
  perform vault.create_secret(new_secret := 'secret-val', new_name := '2026_docs_fdw_vault_access_key_id');
end $$;
do $$
declare
  v_vault_access_key_id text;
  v_vault_secret_access_key text;
begin
  select id into v_vault_access_key_id from vault.secrets where name = '2026_docs_fdw_vault_access_key_id' limit 1;
  select id into v_vault_secret_access_key from vault.secrets where name = '2026_docs_fdw_vault_secret_access_key' limit 1;
  execute format(
    E'create server "2026_docs_fdw_server" foreign data wrapper "2026_docs_fdw" options (vault_access_key_id ''%s'',vault_secret_access_key ''%s'',aws_region %L,endpoint_url %L,supabase_target_schema %L);',
    v_vault_access_key_id,v_vault_secret_access_key,'local','https://host.docker.internal:8000/storage/v1/vector','my_vectors'
  );
end $$;
commit;"""
        prepared_tf = storage_policies.prepare_policy_statements(
            studio_tf_sql, project_id=PROJECT_NAME, storage_s3_region="us-east-1"
        )
        self.assertIsNotNone(prepared_tf)
        self.assertEqual(sum(delegated for _, delegated in prepared_tf), 2)
        rewritten_tf = storage_policies.rewrite_policy_statements(
            prepared_tf,
            tenant_uuid,
            project_id=PROJECT_NAME,
            key=b"a" * 32,
            now=100,
            storage_s3_region="us-east-1",
        )
        self.assertIn(
            "SELECT studio_vector_fdw_guard.drop_s3_vectors_fdw('2026_docs_fdw',160,'",
            rewritten_tf,
        )
        self.assertIn(
            "SELECT studio_vector_fdw_guard.ensure_s3_vectors_fdw('2026_docs_fdw',160,'",
            rewritten_tf,
        )
        self.assertIn(
            'CREATE SERVER "2026_docs_fdw_server" FOREIGN DATA WRAPPER "2026_docs_fdw"',
            rewritten_tf,
        )
        self.assertIn(EXPECTED_ENDPOINT, rewritten_tf)
        self.assertIn("'us-east-1'", rewritten_tf)
        self.assertIn("'my_vectors'", rewritten_tf)
        self.assertIn("v_vault_access_key_id", rewritten_tf)
        self.assertIn("v_vault_secret_access_key", rewritten_tf)
        self.assertNotIn("host.docker.internal", rewritten_tf)
        self.assertNotIn("'local'", rewritten_tf)

        # Format-string SQL injection via %% -> % inside DO $$ execute format(...) header/option names is neutralized.
        fmt_inj_sql = """DO $$
DECLARE
  v text := 'x'' ); CREATE ' || 'SERVER evil FOREIGN DATA WRAPPER my_fdw OPTIONS (endpoint_' || 'url ''http://storage:5001''); --';
BEGIN
  execute format(
    E'create server "a%%1$s" type ''t%%1$s'' version ''v%%1$s'' foreign data wrapper "f%%1$s" options ("opt%%1$s" %L, endpoint_url %L);',
    v, 'http://evil'
  );
END $$;"""
        rewritten_fmt_inj = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                fmt_inj_sql, project_id=PROJECT_NAME, storage_s3_region="us-east-1"
            ),
            tenant_uuid,
            project_id=PROJECT_NAME,
            storage_s3_region="us-east-1",
        )
        self.assertIn('"a%%1$s"', rewritten_fmt_inj)
        self.assertIn("''t%%1$s''", rewritten_fmt_inj)
        self.assertIn("''v%%1$s''", rewritten_fmt_inj)
        self.assertIn('"f%%1$s"', rewritten_fmt_inj)
        self.assertIn('"opt%%1$s" %L', rewritten_fmt_inj)
        self.assertNotIn('"a%1$s"', rewritten_fmt_inj)
        self.assertNotIn('"opt%1$s"', rewritten_fmt_inj)
        self.assertIn(EXPECTED_ENDPOINT, rewritten_fmt_inj)

    def test_region_and_project_id_validation_and_root_env_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_env = Path(tmpdir) / ".env"
            root_env.write_text("STORAGE_S3_REGION=sa-east-1\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STORAGE_S3_REGION", None)
                self.assertEqual(
                    storage_policies.resolve_storage_s3_region(root_env_path=root_env),
                    "sa-east-1",
                )
            with patch.dict(os.environ, {"STORAGE_S3_REGION": "eu-west-1"}):
                self.assertEqual(
                    storage_policies.resolve_storage_s3_region(root_env_path=root_env),
                    "eu-west-1",
                )

            # Missing file falls back to us-east-1.
            missing = Path(tmpdir) / "missing.env"
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STORAGE_S3_REGION", None)
                self.assertEqual(
                    storage_policies.resolve_storage_s3_region(root_env_path=missing),
                    "us-east-1",
                )

            # Symlink root .env is ignored safely.
            sym = Path(tmpdir) / "link.env"
            sym.symlink_to(root_env)
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("STORAGE_S3_REGION", None)
                self.assertEqual(
                    storage_policies.resolve_storage_s3_region(root_env_path=sym),
                    "us-east-1",
                )

        # Invalid project_id or region fails closed.
        for bad_project in ("", "ab", "UPPER", "../evil", "alpha-dash", "alpha:8081/x"):
            with self.subTest(bad_project=bad_project), self.assertRaises(
                storage_policies.StoragePolicyError
            ):
                storage_policies.vector_fdw_endpoint_url(bad_project)

        for bad_region in ("-bad", "us_east_1", "us-east-1;drop", "a" * 64):
            with self.subTest(bad_region=bad_region), self.assertRaises(
                storage_policies.StoragePolicyError
            ):
                storage_policies.normalize_storage_s3_region(bad_region)


class MetaProxyVectorFdwWiringTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.project = {
            "id": uuid.uuid4(),
            "tenant_uuid": uuid.UUID(TENANT),
            "name": PROJECT_NAME,
            "public_ref": "aaaaaaaaaaaaaaaaaaaa",
        }
        self.conn = Mock(fetchval=AsyncMock(return_value="encrypted"))

        @asynccontextmanager
        async def connection():
            yield self.conn

        self.conn.transaction = connection
        self.pool = Mock(acquire=connection)

        async def get_pool():
            return self.pool

        namespace = {
            "Request": Request,
            "Depends": Depends,
            "get_pool": get_pool,
            "validate_project_ref": lambda value: value,
            "resolve_authenticated_user": AsyncMock(return_value={"id": "admin"}),
            "get_public_project_row": AsyncMock(return_value=self.project),
            "ensure_project_member_access": AsyncMock(),
            "decrypt_project_secret": AsyncMock(return_value="service-key"),
            "get_project_meta_connection_string": lambda *args: "postgres://tenant:p@db/project",
            "_extract_project_admin_apikey": lambda request: request.headers.get("apikey", ""),
            "PG_META_INTERNAL_URL": "http://metadata",
            "PG_META_CRYPTO_KEY": "key",
            "postgres_meta_authorization": lambda key: "Bearer metadata-key",
            "encrypt_postgres_meta_uri": lambda *args: "encrypted-dsn",
            "hmac": hmac,
            "json": json,
            "httpx": httpx,
            "storage_policies": storage_policies,
            "HTTPException": HTTPException,
            "Response": Response,
        }
        tree = ast.parse(
            (API_ROOT / "app/routers/project_insights.py").read_text(encoding="utf-8")
        )
        handler = next(
            node
            for node in tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "proxy_project_meta"
        )
        handler.decorator_list = []
        exec(
            compile(ast.Module(body=[handler], type_ignores=[]), "project_insights.py", "exec"),
            namespace,
        )
        app = FastAPI()
        app.add_api_route(
            "/meta/{meta_path:path}",
            namespace["proxy_project_meta"],
            methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        )
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://api"
        )
        self.addAsyncCleanup(self.client.aclose)
        self.forwarded: list[httpx.Request] = []
        factory = httpx.AsyncClient

        def upstream(request: httpx.Request) -> httpx.Response:
            self.forwarded.append(request)
            return httpx.Response(200, json=[])

        for p in (
            patch.object(
                httpx,
                "AsyncClient",
                side_effect=lambda **kwargs: factory(
                    transport=httpx.MockTransport(upstream), **kwargs
                ),
            ),
            patch.object(storage_policies, "delegation_key", return_value=b"a" * 32),
        ):
            p.start()
            self.addCleanup(p.stop)

    async def test_meta_query_rewrites_vector_fdw_with_project_endpoint_and_root_env_region(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root_env = Path(tmpdir) / ".env"
            root_env.write_text("STORAGE_S3_REGION=sa-east-1\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=False),
                patch.object(storage_policies, "ROOT_ENV_PATH", root_env),
            ):
                os.environ.pop("STORAGE_S3_REGION", None)
                sql = (
                    "CREATE FOREIGN DATA WRAPPER docs_fdw HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator; "
                    "CREATE SERVER docs_fdw_server FOREIGN DATA WRAPPER docs_fdw "
                    "OPTIONS (vault_access_key_id 'k1', aws_region 'local', endpoint_url 'http://169.254.169.254');"
                )
                response = await self.client.post(
                    "/meta/query?ref=aaaaaaaaaaaaaaaaaaaa",
                    headers={"apikey": "service-key"},
                    json={"query": sql},
                )
        self.assertEqual(response.status_code, 200, response.text)
        forwarded_sql = json.loads(self.forwarded[0].content)["query"]
        self.assertIn("studio_vector_fdw_guard.ensure_s3_vectors_fdw('docs_fdw',", forwarded_sql)
        self.assertIn(f"endpoint_url '{EXPECTED_ENDPOINT}'", forwarded_sql)
        self.assertIn("aws_region 'sa-east-1'", forwarded_sql)
        self.assertNotIn("169.254.169.254", forwarded_sql)

    async def test_meta_query_blocks_ssrf_and_dynamic_server_bypass_with_400(self) -> None:
        for sql in (
            "ALTER SERVER docs_fdw_server OPTIONS (DROP endpoint_url);",
            "DO $$ BEGIN EXECUTE 'CREATE SERVER s FOREIGN DATA WRAPPER f OPTIONS (endpoint_url ''http://storage:5001'')'; END $$;",
            "SELECT studio_vector_fdw_guard.ensure_s3_vectors_fdw('docs_fdw', 9999999999, '0000000000000000000000000000000000000000000000000000000000000000');",
        ):
            with self.subTest(sql=sql):
                response = await self.client.post(
                    "/meta/query?ref=aaaaaaaaaaaaaaaaaaaa",
                    headers={"apikey": "service-key"},
                    json={"query": sql},
                )
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(self.forwarded, [])


class VectorFdwProvisioningAndSqlContractsTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_tenant_meta_roles_provisions_fdw_guard_atomically(self) -> None:
        control_conn = MagicMock()
        control_conn.fetch = AsyncMock(side_effect=[[], []])
        control_conn.fetchval = AsyncMock(return_value="postgres")
        control_conn.execute = AsyncMock()

        @asynccontextmanager
        async def control_tx():
            yield

        control_conn.transaction = control_tx

        @asynccontextmanager
        async def acquire():
            yield control_conn

        pool = MagicMock()
        pool.acquire = acquire
        tenant = uuid.UUID(TENANT)
        pool.fetch = AsyncMock(
            return_value=[{"name": PROJECT_NAME, "tenant_uuid": tenant}]
        )

        tenant_conn = MagicMock()
        tenant_conn.fetchval = AsyncMock(return_value=True)
        tenant_conn.execute = AsyncMock()
        tenant_conn.close = AsyncMock()
        tenant_conn.transaction = control_tx

        master = "m" * 48
        with tempfile.TemporaryDirectory() as tmpdir:
            root_env = Path(tmpdir) / ".env"
            root_env.write_text("STORAGE_S3_REGION=sa-east-1\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {}, clear=False),
                patch.object(storage_policies, "ROOT_ENV_PATH", root_env),
                patch.object(
                    control_plane_roles.asyncpg,
                    "connect",
                    AsyncMock(return_value=tenant_conn),
                ),
            ):
                os.environ.pop("STORAGE_S3_REGION", None)
                await control_plane_roles.ensure_tenant_meta_roles(
                    pool,
                    admin_dsn="postgres://supabase_admin:pw@db/postgres",
                    password=master,
                )

        calls = [call.args for call in tenant_conn.execute.await_args_list]
        self.assertEqual(len(calls), 3)
        keys_call = calls[1]
        self.assertIn("platform.storage_policy_key", keys_call[0])
        self.assertIn("platform.vector_fdw_key", keys_call[0])
        self.assertIn("platform.vector_fdw_endpoint_url", keys_call[0])
        self.assertIn("platform.vector_fdw_aws_region", keys_call[0])
        self.assertEqual(keys_call[1], tenant_storage_policy_key(tenant, master).hex())
        self.assertEqual(keys_call[2], tenant_vector_fdw_key(tenant, master).hex())
        self.assertNotEqual(keys_call[1], keys_call[2])
        self.assertEqual(keys_call[3], EXPECTED_ENDPOINT)
        self.assertEqual(keys_call[4], "sa-east-1")
        self.assertIn("studio_storage_guard", calls[2][0])
        self.assertIn("studio_vector_fdw_guard", calls[2][0])

    def test_sql_guard_and_tenant_role_and_asgi_contracts(self) -> None:
        guard_sql = (API_ROOT / "app/studio_vector_fdw_guard.sql").read_text(encoding="utf-8")
        tenant_sql = (API_ROOT / "app/tenant_meta_role.sql").read_text(encoding="utf-8")
        storage_sql = (API_ROOT / "app/studio_storage_policies.sql").read_text(encoding="utf-8")
        asgi_py = (API_ROOT / "app/asgi.py").read_text(encoding="utf-8")

        guard_sql_no_comments = "\n".join(
            line.split("--", 1)[0] for line in guard_sql.splitlines()
        )
        # Exactly 2 callable VOID SECURITY DEFINER functions + 1 uncallable event_trigger SECURITY DEFINER function.
        self.assertEqual(
            guard_sql_no_comments.upper().count("RETURNS VOID LANGUAGE PLPGSQL SECURITY DEFINER"),
            2,
        )
        self.assertEqual(
            guard_sql_no_comments.upper().count("RETURNS EVENT_TRIGGER LANGUAGE PLPGSQL SECURITY DEFINER"),
            1,
        )
        self.assertIn("studio_vector_fdw_guard.ensure_s3_vectors_fdw", guard_sql)
        self.assertIn("studio_vector_fdw_guard.drop_s3_vectors_fdw", guard_sql)
        self.assertIn("studio_vector_fdw_guard.enforce_vector_server_endpoint", guard_sql)
        self.assertIn("CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint", guard_sql)
        self.assertIn("WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')", guard_sql)
        self.assertIn("SET search_path = pg_catalog, extensions", guard_sql)
        self.assertIn(
            "HANDLER extensions.s3_vectors_fdw_handler VALIDATOR extensions.s3_vectors_fdw_validator",
            guard_sql,
        )
        self.assertIn("^tenant_meta_[0-9a-f]{32}$", guard_sql)
        self.assertIn("^http://supabase-nginx-[a-z_][a-z0-9_]{2,39}:8081/vector$", guard_sql)
        self.assertIn("^[a-z0-9_]{1,63}$", guard_sql)
        self.assertIn("set_config('platform.vector_fdw_key', '', false)", guard_sql)
        self.assertIn("set_config('platform.vector_fdw_endpoint_url', '', false)", guard_sql)
        self.assertIn("set_config('platform.vector_fdw_aws_region', '', false)", guard_sql)

        # studio_storage_guard remains strictly non-superuser.
        self.assertIn("NOSUPERUSER NOCREATEDB NOCREATEROLE", storage_sql)

        # Tenant role keeps NOSUPERUSER/NOINHERIT and gets guarded Vault privileges.
        self.assertIn("NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT", tenant_sql)
        self.assertIn("WHERE nspname = 'vault'", tenant_sql)
        self.assertIn("GRANT USAGE ON SCHEMA vault TO %I", tenant_sql)
        self.assertIn("GRANT SELECT, DELETE ON vault.secrets TO %I", tenant_sql)
        self.assertIn("GRANT SELECT ON vault.decrypted_secrets TO %I", tenant_sql)
        self.assertIn("('create_secret', 'update_secret', '_crypto_aead_det_decrypt')", tenant_sql)

        # s3-keys route rejects unexpected query parameters.
        s3_route = asgi_py.split("async def get_project_s3_vector_keys(", 1)[1].split(
            "app.include_router(", 1
        )[0]
        self.assertIn("if request.query_params:", s3_route)
        self.assertIn("Query parameters are not allowed", s3_route)


@unittest.skipUnless(
    os.getenv("STUDIO_POLICY_TEST_DSN"), "Disposable PostgreSQL required"
)
class VectorFdwGuardDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.dsn = os.environ["STUDIO_POLICY_TEST_DSN"]
        self.admin = await asyncpg.connect(self.dsn)
        self.project = {
            "name": "vecfdw_" + uuid.uuid4().hex[:12],
            "tenant_uuid": uuid.uuid4(),
        }
        self.database = "_supabase_" + self.project["name"]
        self.control_database = "vecfdwcp_" + uuid.uuid4().hex[:12]
        self.master = "m" * 48
        await self.admin.execute(
            """DO $$ BEGIN
            IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='supabase_storage_admin') THEN
                CREATE ROLE supabase_storage_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'storage-test-only';
                CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'auth-test-only';
                CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN;
                CREATE ROLE service_role NOLOGIN BYPASSRLS;
            END IF; END $$;"""
        )
        await self.admin.execute('CREATE DATABASE "' + self.database + '"')
        await self.admin.execute('CREATE DATABASE "' + self.control_database + '"')
        self.control = await asyncpg.create_pool(
            self.dsn, database=self.control_database, min_size=1, max_size=2
        )
        await self.control.execute("CREATE TABLE projects(name text, tenant_uuid uuid)")
        await self.control.execute(
            "INSERT INTO projects VALUES($1, $2)",
            self.project["name"],
            self.project["tenant_uuid"],
        )
        self.owner = await asyncpg.connect(self.dsn, database=self.database)
        await self.owner.execute(
            """CREATE SCHEMA IF NOT EXISTS extensions;
            CREATE SCHEMA storage AUTHORIZATION supabase_storage_admin;
            CREATE TABLE storage.buckets(id text PRIMARY KEY, name text, public boolean);
            CREATE TABLE storage.objects(id int PRIMARY KEY, bucket_id text, name text);
            ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
            ALTER TABLE storage.objects OWNER TO supabase_storage_admin;
            CREATE FUNCTION extensions.s3_vectors_fdw_handler() RETURNS fdw_handler LANGUAGE internal IMMUTABLE STRICT AS 'postgresql_fdw_validator';
            CREATE FUNCTION extensions.s3_vectors_fdw_validator(text[], oid) RETURNS void LANGUAGE plpgsql AS $$ BEGIN RETURN; END; $$;
            CREATE FOREIGN DATA WRAPPER cli_vec_fdw HANDLER extensions.s3_vectors_fdw_handler VALIDATOR extensions.s3_vectors_fdw_validator;
            CREATE SERVER cli_vec_srv FOREIGN DATA WRAPPER cli_vec_fdw OPTIONS (aws_region 'us-east-1', endpoint_url 'http://supabase-nginx-"""
            + self.project["name"]
            + """:8081/vector');
            CREATE FOREIGN DATA WRAPPER other_preexisting_fdw;
            CREATE SERVER other_preexisting_srv FOREIGN DATA WRAPPER other_preexisting_fdw;
            CREATE SCHEMA vault;
            REVOKE ALL ON SCHEMA vault FROM PUBLIC;
            CREATE TABLE vault.secrets(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text UNIQUE, secret text, description text);
            REVOKE ALL ON vault.secrets FROM PUBLIC;
            CREATE VIEW vault.decrypted_secrets AS SELECT id, name, secret AS decrypted_secret, description FROM vault.secrets;
            REVOKE ALL ON vault.decrypted_secrets FROM PUBLIC;
            CREATE FUNCTION vault.create_secret(new_secret text, new_name text DEFAULT NULL, new_description text DEFAULT '')
            RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER AS $$
            DECLARE sid uuid := gen_random_uuid();
            BEGIN
                INSERT INTO vault.secrets(id, name, secret, description) VALUES (sid, new_name, new_secret, new_description);
                RETURN sid;
            END $$;
            CREATE FUNCTION vault.update_secret(secret_id uuid, new_secret text DEFAULT NULL, new_name text DEFAULT NULL, new_description text DEFAULT NULL)
            RETURNS void LANGUAGE plpgsql SECURITY DEFINER AS $$
            BEGIN
                UPDATE vault.secrets SET secret = coalesce(new_secret, secret), name = coalesce(new_name, name), description = coalesce(new_description, description) WHERE id = secret_id;
            END $$;
            CREATE FUNCTION vault._crypto_aead_det_decrypt(message bytea, additional bytea, key_id bigint, context bytea DEFAULT '\\x'::bytea, nonce bytea DEFAULT NULL)
            RETURNS bytea LANGUAGE sql SECURITY DEFINER AS $$ SELECT message $$;
            REVOKE ALL ON ALL FUNCTIONS IN SCHEMA vault FROM PUBLIC;"""
        )
        self.env_patch = patch.dict(
            os.environ,
            {
                "META_ADMIN_DSN": "postgresql://platform_meta_admin:" + self.master + "@db/postgres",
                "STORAGE_S3_REGION": "us-east-1",
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        await control_plane_roles.ensure_tenant_meta_roles(
            self.control, admin_dsn=self.dsn, password=self.master
        )
        self.role, password = tenant_meta_credentials(
            self.project["tenant_uuid"], self.master
        )
        self.tenant = await asyncpg.connect(
            self.dsn, database=self.database, user=self.role, password=password
        )

    async def asyncTearDown(self) -> None:
        await self.tenant.close()
        await self.owner.close()
        await self.admin.execute('DROP DATABASE "' + self.database + '" WITH (FORCE)')
        await self.control.close()
        await self.admin.execute('DROP DATABASE "' + self.control_database + '" WITH (FORCE)')
        for prefix in ("tenant_storage_policy_", "tenant_ai_reader_", "tenant_meta_"):
            await self.admin.execute(
                'DROP ROLE IF EXISTS "' + prefix + self.project["tenant_uuid"].hex + '"'
            )
        await self.admin.close()

    async def test_guard_enforces_hmac_handler_event_trigger_vault_and_clone_rebind_live(
        self,
    ) -> None:
        # Verify ONLY 2 callable SECURITY DEFINER functions (+ 1 event trigger function) exist in studio_vector_fdw_guard.
        callable_secdef_fns = await self.owner.fetch(
            """SELECT p.proname
                 FROM pg_proc p
                 JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'studio_vector_fdw_guard'
                  AND p.prosecdef
                  AND p.prorettype <> 'event_trigger'::regtype
                ORDER BY 1"""
        )
        self.assertEqual(
            [row["proname"] for row in callable_secdef_fns],
            ["drop_s3_vectors_fdw", "ensure_s3_vectors_fdw"],
        )

        # Verify tenant_meta role keeps NOSUPERUSER, NOINHERIT, zero role memberships, and Vault grants work.
        role_attrs = await self.admin.fetchrow(
            "SELECT rolsuper, rolinherit, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = $1",
            self.role,
        )
        self.assertTrue(all(value is False for value in role_attrs.values()))
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT count(*) FROM pg_auth_members WHERE member = current_user::regrole"
            ),
            0,
        )
        secret_id = await self.tenant.fetchval(
            "SELECT vault.create_secret('s3-secret-1', 'my_docs_fdw_vault_access_key_id', 'desc')"
        )
        await self.tenant.execute(
            "SELECT vault.update_secret($1, 's3-secret-2', 'my_docs_fdw_vault_access_key_id', 'desc2')",
            secret_id,
        )
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT decrypted_secret FROM vault.decrypted_secrets WHERE id = $1",
                secret_id,
            ),
            "s3-secret-2",
        )
        self.assertEqual(
            await self.tenant.fetchval(
                "SELECT vault._crypto_aead_det_decrypt('\\x01'::bytea, '\\x'::bytea, 1)"
            ),
            b"\x01",
        )
        await self.tenant.execute(
            "DELETE FROM vault.secrets WHERE id = $1", secret_id
        )

        # Tenant cannot read authorities/server_policy tables or call signature helper.
        for sql in (
            "SELECT * FROM studio_vector_fdw_guard.authorities",
            "SELECT * FROM studio_vector_fdw_guard.server_policy",
            "SELECT studio_vector_fdw_guard.signature(decode(repeat('00',32),'hex'), 'x'::bytea)",
        ):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(sql)

        # Forged / expired / wrong-action HMAC proofs fail.
        for exp, proof in (
            (int(time.time()) + 60, "0" * 64),
            (
                int(time.time()) - 10,
                hmac.new(
                    tenant_vector_fdw_key(self.project["tenant_uuid"], self.master),
                    f"ensure_s3_vectors_fdw\n{self.role}\n{int(time.time()) - 10}\nmy_docs_fdw".encode(),
                    hashlib.sha256,
                ).hexdigest(),
            ),
            (
                int(time.time()) + 60,
                hmac.new(
                    tenant_vector_fdw_key(self.project["tenant_uuid"], self.master),
                    f"drop_s3_vectors_fdw\n{self.role}\n{int(time.time()) + 60}\nmy_docs_fdw".encode(),
                    hashlib.sha256,
                ).hexdigest(),
            ),
        ):
            with self.assertRaises(asyncpg.InsufficientPrivilegeError):
                await self.tenant.execute(
                    "SELECT studio_vector_fdw_guard.ensure_s3_vectors_fdw('my_docs_fdw', $1, $2)",
                    exp,
                    proof,
                )

        # Pre-existing CLI-created s3_vectors_fdw wrapper & server get USAGE granted to tenant_meta,
        # while non-vector FDWs/servers stay untouched.
        self.assertTrue(
            await self.owner.fetchval(
                "SELECT has_foreign_data_wrapper_privilege($1, 'cli_vec_fdw', 'USAGE')",
                self.role,
            )
        )
        self.assertTrue(
            await self.owner.fetchval(
                "SELECT has_server_privilege($1, 'cli_vec_srv', 'USAGE')",
                self.role,
            )
        )
        self.assertFalse(
            await self.owner.fetchval(
                "SELECT has_foreign_data_wrapper_privilege($1, 'other_preexisting_fdw', 'USAGE')",
                self.role,
            )
        )
        self.assertFalse(
            await self.owner.fetchval(
                "SELECT has_server_privilege($1, 'other_preexisting_srv', 'USAGE')",
                self.role,
            )
        )

        # Digit-leading bucket wrapper name works cleanly.
        ensure_digit_sql = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                'CREATE FOREIGN DATA WRAPPER "2026_docs_fdw" HANDLER s3_vectors_fdw_handler VALIDATOR s3_vectors_fdw_validator;',
                project_id=self.project["name"],
            ),
            self.project["tenant_uuid"],
            project_id=self.project["name"],
        )
        await self.tenant.execute(ensure_digit_sql)

        # Format-string %%1$s smuggling inside DO $$ execute format(...) cannot escape CREATE SERVER or break out of quotes.
        fmt_smuggle_sql = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                """DO $$
                DECLARE
                  v text := 'ignored" FOREIGN DATA WRAPPER "2026_docs_fdw" OPTIONS (endpoint_' || 'url ''http://storage:5001'', aws_region ''us-east-1''); --';
                BEGIN
                  execute format(
                    E'create server "srv_%%1$s" foreign data wrapper "2026_docs_fdw" options (vault_access_key_id %L, endpoint_url %L);',
                    v, 'http://evil'
                  );
                END $$;""",
                project_id=self.project["name"],
            ),
            self.project["tenant_uuid"],
            project_id=self.project["name"],
        )
        await self.tenant.execute(fmt_smuggle_sql)
        self.assertEqual(
            await self.owner.fetchval(
                "SELECT count(*) FROM pg_foreign_server WHERE srvname = 'srv_%1$s'"
            ),
            1,
        )
        smuggled_opts = await self.owner.fetchval(
            "SELECT srvoptions FROM pg_foreign_server WHERE srvname = 'srv_%1$s'"
        )
        self.assertIn(
            f"endpoint_url=http://supabase-nginx-{self.project['name']}:8081/vector",
            smuggled_opts,
        )
        self.assertNotIn("endpoint_url=http://storage:5001", smuggled_opts)

        # Dynamic SQL string-concatenation SSRF bypasses inside DO $$ and CREATE FUNCTION are blocked by EVENT TRIGGER.
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(
                "DO $$ BEGIN EXECUTE 'CREATE ' || 'SERVER evil_srv FOREIGN DATA WRAPPER \"2026_docs_fdw\" "
                "OPTIONS (endpoint_' || 'url ''http://storage:5001'', aws_region ''us-east-1'')'; END $$;"
            )
        await self.tenant.execute(
            "CREATE FUNCTION public.ssrf_concat() RETURNS void LANGUAGE plpgsql AS $$ "
            "BEGIN EXECUTE 'CREATE ' || 'SERVER evil_fn FOREIGN DATA WRAPPER \"2026_docs_fdw\" "
            "OPTIONS (endpoint_' || 'url ''http://169.254.169.254'', aws_region ''us-east-1'')'; END $$;"
        )
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute("SELECT public.ssrf_concat()")

        # Valid pinned server succeeds, then dynamic ALTER SERVER hijacking endpoint_url or aws_region fails.
        valid_srv_sql = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                'CREATE SERVER "2026_docs_fdw_server" FOREIGN DATA WRAPPER "2026_docs_fdw" '
                "OPTIONS (aws_region 'local', endpoint_url 'https://evil.example');",
                project_id=self.project["name"],
            ),
            self.project["tenant_uuid"],
            project_id=self.project["name"],
        )
        await self.tenant.execute(valid_srv_sql)
        for hijack_sql in (
            "DO $$ BEGIN EXECUTE 'ALTER ' || 'SERVER \"2026_docs_fdw_server\" OPTIONS (SET endpoint_' || 'url ''http://storage:5001'')'; END $$;",
            "DO $$ BEGIN EXECUTE 'ALTER ' || 'SERVER \"2026_docs_fdw_server\" OPTIONS (SET aws_' || 'region ''eu-west-1'')'; END $$;",
            "DO $$ BEGIN EXECUTE 'ALTER ' || 'SERVER \"2026_docs_fdw_server\" OPTIONS (DROP endpoint_' || 'url)'; END $$;",
        ):
            with self.subTest(hijack_sql=hijack_sql), self.assertRaises(
                asyncpg.InsufficientPrivilegeError
            ):
                await self.tenant.execute(hijack_sql)

        # Signed drop works for s3_vectors FDW and cannot drop non-vector FDWs.
        await self.owner.execute("CREATE FOREIGN DATA WRAPPER other_system_fdw")
        drop_other_sql = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                "DROP FOREIGN DATA WRAPPER IF EXISTS other_system_fdw CASCADE;",
                project_id=self.project["name"],
            ),
            self.project["tenant_uuid"],
            project_id=self.project["name"],
        )
        with self.assertRaises(asyncpg.InsufficientPrivilegeError):
            await self.tenant.execute(drop_other_sql)
        self.assertEqual(
            await self.owner.fetchval(
                "SELECT count(*) FROM pg_foreign_data_wrapper WHERE fdwname = 'other_system_fdw'"
            ),
            1,
        )

        drop_vec_sql = storage_policies.rewrite_policy_statements(
            storage_policies.prepare_policy_statements(
                'DROP FOREIGN DATA WRAPPER IF EXISTS "2026_docs_fdw" CASCADE;',
                project_id=self.project["name"],
            ),
            self.project["tenant_uuid"],
            project_id=self.project["name"],
        )
        await self.tenant.execute(drop_vec_sql)
        self.assertEqual(
            await self.owner.fetchval(
                "SELECT count(*) FROM pg_foreign_data_wrapper WHERE fdwname = '2026_docs_fdw'"
            ),
            0,
        )

        # Legacy clone rebinds authorities + pinned endpoint_url and revokes source tenant.
        clone = {"name": "vecclone_" + uuid.uuid4().hex[:12], "tenant_uuid": uuid.uuid4()}
        clone_db = "_supabase_" + clone["name"]
        await self.tenant.close()
        await self.owner.close()
        await self.admin.execute(f'CREATE DATABASE "{clone_db}" TEMPLATE "{self.database}"')
        self.owner = await asyncpg.connect(self.dsn, database=self.database)
        _, password = tenant_meta_credentials(self.project["tenant_uuid"], self.master)
        self.tenant = await asyncpg.connect(
            self.dsn, database=self.database, user=self.role, password=password
        )
        await self.control.execute(
            "INSERT INTO projects VALUES($1, $2)", clone["name"], clone["tenant_uuid"]
        )
        try:
            await control_plane_roles.ensure_tenant_meta_roles(
                self.control, admin_dsn=self.dsn, password=self.master
            )
            clone_owner = await asyncpg.connect(self.dsn, database=clone_db)
            try:
                clone_role, _ = tenant_meta_credentials(clone["tenant_uuid"], self.master)
                self.assertEqual(
                    await clone_owner.fetchval(
                        "SELECT role_name FROM studio_vector_fdw_guard.authorities"
                    ),
                    clone_role,
                )
                self.assertEqual(
                    await clone_owner.fetchval(
                        "SELECT endpoint_url FROM studio_vector_fdw_guard.server_policy"
                    ),
                    f"http://supabase-nginx-{clone['name']}:8081/vector",
                )
                self.assertFalse(
                    await clone_owner.fetchval(
                        "SELECT has_schema_privilege($1, 'studio_vector_fdw_guard', 'USAGE')",
                        self.role,
                    )
                )
                # Clone grants USAGE on pre-existing CLI vector FDW/server to clone role and revokes from source role,
                # while keeping non-vector FDW/server untouched.
                self.assertTrue(
                    await clone_owner.fetchval(
                        "SELECT has_foreign_data_wrapper_privilege($1, 'cli_vec_fdw', 'USAGE')",
                        clone_role,
                    )
                )
                self.assertTrue(
                    await clone_owner.fetchval(
                        "SELECT has_server_privilege($1, 'cli_vec_srv', 'USAGE')",
                        clone_role,
                    )
                )
                self.assertFalse(
                    await clone_owner.fetchval(
                        "SELECT has_foreign_data_wrapper_privilege($1, 'cli_vec_fdw', 'USAGE')",
                        self.role,
                    )
                )
                self.assertFalse(
                    await clone_owner.fetchval(
                        "SELECT has_server_privilege($1, 'cli_vec_srv', 'USAGE')",
                        self.role,
                    )
                )
                self.assertFalse(
                    await clone_owner.fetchval(
                        "SELECT has_foreign_data_wrapper_privilege($1, 'other_preexisting_fdw', 'USAGE')",
                        clone_role,
                    )
                )
                self.assertFalse(
                    await clone_owner.fetchval(
                        "SELECT has_server_privilege($1, 'other_preexisting_srv', 'USAGE')",
                        clone_role,
                    )
                )
            finally:
                await clone_owner.close()
        finally:
            await self.control.execute("DELETE FROM projects WHERE name = $1", clone["name"])
            await self.admin.execute(f'DROP DATABASE "{clone_db}" WITH (FORCE)')
            for prefix in ("tenant_storage_policy_", "tenant_ai_reader_", "tenant_meta_"):
                await self.admin.execute(
                    f'DROP ROLE IF EXISTS "{prefix}{clone["tenant_uuid"].hex}"'
                )


if __name__ == "__main__":
    unittest.main()
