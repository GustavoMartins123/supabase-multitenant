"""Comportamento e contratos da superficie Studio: conteudo, edge functions, credenciais e cache."""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import pathlib
import sys
import tempfile
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

ROOT = pathlib.Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "servidor" / "api-internal"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

os.environ.setdefault("DB_DSN", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("HOST_AGENT_HMAC_SECRET", "x" * 32)
try:
    from cryptography.fernet import Fernet

    _keys = [Fernet.generate_key().decode() for _ in range(3)]
except Exception:
    _keys = ["x" * 44, "y" * 44, "z" * 44]
os.environ.setdefault("PROJECT_SECRETS_MASTER_KEY", _keys[0])
os.environ.setdefault("PG_META_CRYPTO_KEY", _keys[1])
os.environ.setdefault("STUDIO_SERVICE_KEY_ENCRYPTION_KEY", _keys[2])
os.environ.setdefault("NGINX_HMAC_SECRET", "v" * 32)
os.environ.setdefault("STUDIO_GATEWAY_HMAC_SECRET", "u" * 32)
os.environ.setdefault("PROJECTS_API_HMAC_SECRET", "t" * 32)
os.environ.setdefault("LOGFLARE_PRIVATE_ACCESS_TOKEN", "s" * 16)

from app import service_key_cache, studio_content
from app.routers import studio_content as content_router
from app.routers import studio_edge_functions as functions_router
from app.studio_content import ContentQuery, FolderBody, SnippetBody

REF = "a" * 20
NOW = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)


class FakeConn:
    def __init__(self, rows=None, row=None):
        self.rows = rows if rows is not None else []
        self.row = row
        self.queries = []
        self.executions = []

    async def fetch(self, query, *args):
        self.queries.append(query)
        return self.rows

    async def fetchrow(self, query, *args):
        self.queries.append(query)
        if isinstance(self.row, Exception):
            raise self.row
        return self.row

    async def fetchval(self, query, *args):
        self.queries.append(query)
        return "audit-1"

    async def execute(self, query, *args):
        self.queries.append(query)
        self.executions.append((query, args))


def snippet_row(name="consulta", favorite=False, folder=None):
    return {
        "id": uuid4(), "project_id": uuid4(), "owner_id": uuid4(),
        "folder_id": folder, "name": name, "description": "d",
        "favorite": favorite, "inserted_at": NOW, "updated_at": NOW,
    }


def snippet_body(**overrides):
    identity = uuid4()
    payload = {
        "id": str(identity), "type": "sql", "name": "consulta",
        "visibility": "user", "favorite": False,
        "content": {"sql": "select 1", "content_id": str(identity), "schema_version": "1.0"},
    }
    payload.update(overrides)
    return payload


class StudioContentModelsTest(unittest.TestCase):
    def test_snippet_body_requires_matching_identities(self):
        with self.assertRaises(ValidationError):
            SnippetBody.model_validate(snippet_body(content={"sql": "select 1", "content_id": str(uuid4()), "schema_version": "1.0"}))

    def test_snippet_body_forbids_extra_fields_and_loose_types(self):
        with self.assertRaises(ValidationError):
            SnippetBody.model_validate({**snippet_body(), "injected": True})
        with self.assertRaises(ValidationError):
            SnippetBody.model_validate(snippet_body(favorite="yes"))
        with self.assertRaises(ValidationError):
            SnippetBody.model_validate(snippet_body(visibility="project"))

    def test_folder_body_is_strict_and_minimal(self):
        self.assertEqual(FolderBody.model_validate({"name": "pasta"}).name, "pasta")
        for invalid in ({"name": ""}, {"name": "x", "parentId": "outra"}, {"name": "x", "extra": 1}):
            with self.assertRaises(ValidationError):
                FolderBody.model_validate(invalid)

    def test_content_query_defaults_and_bounds(self):
        query = ContentQuery.model_validate({})
        self.assertEqual((query.type, query.visibility, query.limit, query.sort_by, query.sort_order), ("sql", "user", 100, "inserted_at", "desc"))
        for invalid in ({"limit": 0}, {"limit": 1001}, {"sort_by": "size"}, {"type": "log"}, {"surprise": 1}):
            with self.assertRaises(ValidationError):
                ContentQuery.model_validate(invalid)


class StudioContentHelpersTest(unittest.TestCase):
    def test_response_shapes_always_expose_the_studio_contract_fields(self):
        row = snippet_row()
        self.assertEqual(
            set(studio_content.snippet_response(row)),
            {"id", "type", "name", "description", "visibility", "favorite", "folder_id",
             "project_id", "owner_id", "project_uuid", "owner_uuid", "inserted_at", "updated_at"},
        )
        self.assertEqual(
            set(studio_content.folder_response(row)),
            {"id", "name", "parent_id", "project_id", "owner_id", "project_uuid", "owner_uuid"},
        )
        full = studio_content.snippet_response({**row, "content": '{"sql":"select 1"}'}, with_content=True)
        self.assertEqual(full["content"], {"sql": "select 1"})

    def test_require_folder_missing_raises_404(self):
        conn = FakeConn(row=None)
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(studio_content.require_folder(conn, "p", "u", uuid4()))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_save_snippet_conflict_maps_to_409(self):
        conn = FakeConn(row=None)
        body = SnippetBody.model_validate(snippet_body())
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(studio_content.save_snippet(conn, "p", "u", body))
        self.assertEqual(ctx.exception.status_code, 409)

    def test_get_snippet_missing_raises_404(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(studio_content.get_snippet(FakeConn(row=None), "p", "u", uuid4()))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_project_visibility_returns_empty_without_touching_the_database(self):
        conn = FakeConn()
        contents, cursor = asyncio.run(
            studio_content.list_snippets(conn, "p", "u", ContentQuery.model_validate({"visibility": "project"}))
        )
        self.assertEqual((contents, cursor), ([], None))
        self.assertEqual(conn.queries, [])
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                studio_content.list_snippets(
                    FakeConn(row=None), "p", "u", ContentQuery.model_validate({"visibility": "project", "cursor": str(uuid4())})
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_list_snippets_slices_pages_and_emits_cursor(self):
        rows = [snippet_row("a"), snippet_row("b")]
        conn = FakeConn(rows=rows)
        contents, cursor = asyncio.run(
            studio_content.list_snippets(conn, "p", "u", ContentQuery.model_validate({"limit": 1}))
        )
        self.assertEqual([item["name"] for item in contents], ["a"])
        self.assertEqual(cursor, str(rows[0]["id"]))
        self.assertIn("LIMIT $", conn.queries[-1])

    def test_list_snippets_unknown_cursor_is_rejected(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                studio_content.list_snippets(
                    FakeConn(row=None), "p", "u", ContentQuery.model_validate({"cursor": str(uuid4())})
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_list_snippets_favorite_and_name_filters_are_parameterized(self):
        conn = FakeConn(rows=[])
        asyncio.run(studio_content.list_snippets(conn, "p", "u", ContentQuery.model_validate({"favorite": True})))
        self.assertIn("favorite=$3", conn.queries[-1])
        conn = FakeConn(rows=[])
        asyncio.run(studio_content.list_snippets(conn, "p", "u", ContentQuery.model_validate({"name": "al"})))
        self.assertIn("strpos(lower(name),$3)>0", conn.queries[-1])

    def test_delete_content_requires_full_ownership_of_every_id(self):
        first, second = uuid4(), uuid4()
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(studio_content.delete_content(FakeConn(rows=[{"id": first}]), "p", "u", [first, second]))
        self.assertEqual(ctx.exception.status_code, 404)
        conn = FakeConn(rows=[{"id": first}])
        result = asyncio.run(studio_content.delete_content(conn, "p", "u", [first], folders=True))
        self.assertEqual(result, [{"id": str(first)}])
        self.assertIn("studio_sql_folders", conn.queries[0])


def request_with(query: str) -> Request:
    return Request({
        "type": "http", "method": "GET", "path": "/", "query_string": query.encode(),
        "headers": [], "server": ("test", 80), "scheme": "http", "client": ("127.0.0.1", 0),
    })


class StudioContentRouterGuardsTest(unittest.TestCase):
    def test_content_query_rejects_repeated_parameters(self):
        with self.assertRaises(HTTPException) as ctx:
            content_router.content_query(request_with("type=sql&type=sql"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_content_query_rejects_unknown_fields(self):
        with self.assertRaises(HTTPException) as ctx:
            content_router.content_query(request_with("origem=externa"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_content_query_accepts_the_documented_surface(self):
        query = content_router.content_query(request_with("type=sql&name=al&favorite=true&limit=7&sort_by=name&sort_order=asc"))
        self.assertEqual((query.name, query.favorite, query.limit, query.sort_by), ("al", True, 7, "name"))

    def test_content_ids_validation(self):
        identity = str(uuid4())
        cases = [
            ("", 400),
            ("ids=", 400),
            ("ids=não-uuid", 400),
            (f"ids={identity},{identity}", 400),
            ("ids=" + ",".join(str(uuid4()) for _ in range(1001)), 400),
            (f"ids={identity}&outro=1", 400),
        ]
        for url, status in cases:
            with self.subTest(url=url[:40]):
                with self.assertRaises(HTTPException) as ctx:
                    content_router.content_ids(request_with(url))
                self.assertEqual(ctx.exception.status_code, status)
        parsed = content_router.content_ids(request_with(f"ids={identity}"))
        self.assertEqual([str(value) for value in parsed], [identity])

    def test_folder_conflicts_surface_as_409(self):
        for method, url in (("post", "/api/projects/%s/content/folders"), ("patch", "/api/projects/%s/content/folders/%s")):
            with self.subTest(method=method):
                conn = FakeConn(row=asyncpg.UniqueViolationError())

                @asynccontextmanager
                async def fake_context(ref, request, response, pool):
                    yield conn, "p", "u"

                app = FastAPI()
                app.include_router(content_router.router)

                async def unused_pool():
                    return None

                app.dependency_overrides[content_router.get_pool] = unused_pool
                payload = {"name": "pasta"}
                with patch.object(content_router, "content_context", fake_context):
                    client = TestClient(app)
                    response = (
                        client.post(url % REF, json=payload)
                        if method == "post"
                        else client.patch(url % (REF, uuid4()), json=payload)
                    )
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["detail"], "Folder name already exists")

    def test_folder_create_returns_the_folder_contract(self):
        row = snippet_row("pasta")

        @asynccontextmanager
        async def fake_context(ref, request, response, pool):
            yield FakeConn(row=row), "p", "u"

        app = FastAPI()
        app.include_router(content_router.router)

        async def unused_pool():
            return None

        app.dependency_overrides[content_router.get_pool] = unused_pool
        with patch.object(content_router, "content_context", fake_context):
            response = TestClient(app).post(f"/api/projects/{REF}/content/folders", json={"name": "pasta"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["name"], "pasta")
        self.assertIsNone(response.json()["parent_id"])

    def test_gateway_and_store_contracts_hold(self):
        source = (APP_ROOT / "app/routers/studio_content.py").read_text(encoding="utf-8")
        self.assertIn('!= "studio-nginx"', source)
        self.assertIn('response.headers["Cache-Control"] = "no-store"', source)
        self.assertIn('ensure_project_member_access', source)


class EdgeFunctionsModelsAndGuardsTest(unittest.TestCase):
    def test_publish_body_revision_must_be_a_hash(self):
        valid = {"revision": "0" * 64, "expected_published_revision": None}
        functions_router.PublishBody.model_validate(valid)
        functions_router.PublishBody.model_validate({**valid, "expected_published_revision": "1" * 64})
        for invalid in (
            {"revision": "xyz", "expected_published_revision": None},
            {"revision": "0" * 63, "expected_published_revision": None},
            {"revision": "0" * 64},
            {"revision": "0" * 64, "expected_published_revision": None, "extra": 1},
        ):
            with self.assertRaises(ValidationError):
                functions_router.PublishBody.model_validate(invalid)

    def test_draft_body_limits_files(self):
        valid = {"expected_revision": None, "files": [{"name": "index.ts", "content": "Deno.serve(() => new Response('ok'))"}]}
        functions_router.DraftBody.model_validate(valid)
        with self.assertRaises(ValidationError):
            functions_router.DraftBody.model_validate({**valid, "files": []})
        with self.assertRaises(ValidationError):
            functions_router.DraftBody.model_validate({**valid, "files": [{"name": "", "content": "x"}]})
        with self.assertRaises(ValidationError):
            functions_router.DraftBody.model_validate({**valid, "files": [{"name": "a.ts", "content": 1}]})

    def test_slug_validation_rejects_reserved_and_malformed_names(self):
        for slug in ("main", "1comeca", "tem espaço", "diário", ""):
            with self.assertRaises(HTTPException) as ctx:
                functions_router.validate_slug(slug)
            self.assertEqual(ctx.exception.status_code, 400)
        self.assertIsNone(functions_router.validate_slug("valida-Funcao_1"))

    def test_detail_missing_function_raises_404(self):
        store = SimpleNamespace(item=lambda *args, **kwargs: None)
        with patch.object(functions_router, "store", store):
            with self.assertRaises(HTTPException) as ctx:
                functions_router.detail({"name": "p"}, {"functions": {}}, "ausente", True)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_configuration_parses_json_strings_and_missing_rows(self):
        with patch.object(functions_router, "network_hosts", lambda value: [f"parsed:{value}"]):
            disabled = asyncio.run(functions_router.configuration(FakeConn(row=None), "p"))
            self.assertEqual(disabled, {"enabled": False, "network_allowlist": []})
            as_text = asyncio.run(
                functions_router.configuration(FakeConn(row={"enabled": True, "network_allowlist": '["h:443"]'}), "p")
            )
            self.assertEqual(as_text, {"enabled": True, "network_allowlist": ["parsed:['h:443']"]})
            as_list = asyncio.run(
                functions_router.configuration(FakeConn(row={"enabled": True, "network_allowlist": ["h:443"]}), "p")
            )
            self.assertEqual(as_list["network_allowlist"], ["parsed:['h:443']"])

    def test_settings_values_stringify_for_the_settings_api(self):
        row = {"enabled": True, "network_allowlist": ["a:1", "b:2"]}
        with patch.object(functions_router, "network_hosts", lambda value: value):
            values = asyncio.run(functions_router.settings_values(FakeConn(row=row), "p"))
        self.assertEqual(values, {"EDGE_FUNCTIONS_ENABLED": "true", "FUNCTIONS_ALLOWED_NETWORK_HOSTS": "a:1,b:2"})

    def test_management_context_rejects_non_gateway_callers(self):
        request = SimpleNamespace(state=SimpleNamespace(internal_service=None), query_params={})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._enter(request, REF))
        self.assertEqual(ctx.exception.status_code, 403)

    def test_management_context_rejects_query_parameters(self):
        request = SimpleNamespace(state=SimpleNamespace(internal_service="studio-nginx"), query_params={"ref": "x"})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._enter(request, REF))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_management_context_rejects_malformed_refs(self):
        request = SimpleNamespace(state=SimpleNamespace(internal_service="studio-nginx"), query_params={})
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(self._enter(request, "NAO-REF"))
        self.assertEqual(ctx.exception.status_code, 400)

    async def _enter(self, request, ref):
        async with functions_router.management_context(ref, request, None, None):
            pass

    def test_publication_routes_keep_their_disabled_semantics(self):
        source = (APP_ROOT / "app/routers/studio_edge_functions.py").read_text(encoding="utf-8")

        def route_block(name):
            start = source.index(f"async def {name}")
            following = source.find("\n@router", start)
            return source[start:following if following != -1 else None]

        publish = route_block("function_publish")
        self.assertIn("Edge Functions are disabled by the project administrator", publish)
        for route in ("function_unpublish", "function_delete"):
            self.assertNotIn("disabled by the project administrator", route_block(route))
        context = source[source.index("async def management_context"):source.index("\ndef identity")]
        self.assertIn("response.headers['Cache-Control'] = 'no-store'", context)
        self.assertIn("Project identity changed while waiting", context)
        self.assertIn("edge_functions.withdraw(ROOT, project['name'])", context)


class FakePublicationStore:
    def __init__(self, failures=()):
        self.calls = []
        self.failures = set(failures)
        self.scratch = Path(tempfile.mkdtemp(prefix="studio-store-"))

    def directory(self, root, name, identity):
        return self.scratch

    def validate_transition(self, root, previous, proposed, action):
        self.calls.append(("validate_transition", action))
        if "validate_transition" in self.failures:
            raise RuntimeError("Function operation must change exactly one function")

    def begin_publication(self, root, previous, proposed, context, *, action="publish"):
        self.calls.append(("begin_publication", action))
        if "begin_publication" in self.failures:
            raise OSError("disk full")

    def atomic_json(self, path, value):
        self.calls.append(("atomic_json", path.name, value))

    def finish_publication(self, root, name, identity):
        self.calls.append(("finish_publication",))


class FakeRuntime:
    def __init__(self, previous=None):
        self.previous = previous
        self.calls = []

    def read_context(self, root, name, identity):
        self.calls.append(("read_context", name))
        return self.previous

    def activate_context(self, root, context):
        self.calls.append(("activate_context", context))

    def withdraw(self, root, name):
        self.calls.append(("withdraw", name))


class CommitChangeTest(unittest.TestCase):
    def setUp(self):
        self.project = {"id": "pid", "name": "meu_projeto", "tenant_uuid": "uuid", "public_ref": REF}
        self.state = {"project": "meu_projeto", "uuid": "uuid", "functions": {"fn": {"draft": "d" * 64, "published": None}}}
        self.proposed = {"project": "meu_projeto", "uuid": "uuid", "functions": {"fn": {"draft": "d" * 64, "published": "d" * 64}}}
        self.conn = FakeConn()
        self.outcomes = []
        self.prepared = []

    def _run(self, config, store, runtime):
        async def drive():
            await functions_router.commit_change(
                self.conn, self.project, "actor", config, self.state, self.proposed, "fn", "d" * 64, "publish"
            )

        with patch.object(functions_router, "store", store), \
                patch.object(functions_router, "edge_functions", runtime), \
                patch.object(functions_router, "audit", self._fake_audit), \
                patch.object(functions_router, "outcome", self._record_outcome), \
                patch.object(functions_router, "prepare", self._fake_prepare):
            asyncio.run(drive())

    async def _fake_audit(self, conn, project, actor, action, slug=None, revision=None):
        return "audit-1"

    async def _record_outcome(self, conn, audit_id, result):
        self.outcomes.append(result)

    async def _fake_prepare(self, conn, project, state, config):
        self.prepared.append(state)
        return {"context": True}

    def test_enabled_publication_commits_and_finalizes(self):
        store, runtime = FakePublicationStore(), FakeRuntime(previous={"previous": True})
        self._run({"enabled": True, "network_allowlist": []}, store, runtime)
        self.assertEqual(self.outcomes, ["completed"])
        self.assertEqual(self.prepared, [self.proposed])
        self.assertEqual(store.calls[0], ("validate_transition", "publish"))
        self.assertIn(("begin_publication", "publish"), store.calls)
        self.assertEqual(runtime.calls, [("read_context", "meu_projeto"), ("activate_context", {"context": True})])
        atomic = [call for call in store.calls if call[0] == "atomic_json"]
        self.assertEqual(atomic[-1][2], self.proposed)
        self.assertIn(("finish_publication",), store.calls)

    def test_failure_restores_the_previous_runtime_and_state(self):
        store = FakePublicationStore(failures={"begin_publication"})
        runtime = FakeRuntime(previous={"previous": True})
        with self.assertRaises(OSError):
            self._run({"enabled": True, "network_allowlist": []}, store, runtime)
        self.assertEqual(self.outcomes, ["failed"])
        self.assertIn(("activate_context", {"previous": True}), runtime.calls)
        atomic = [call for call in store.calls if call[0] == "atomic_json"]
        self.assertEqual(atomic[-1][2], self.state)
        self.assertIn(("finish_publication",), store.calls)

    def test_failure_without_previous_context_withdraws(self):
        store = FakePublicationStore(failures={"begin_publication"})
        runtime = FakeRuntime(previous=None)
        with self.assertRaises(OSError):
            self._run({"enabled": True, "network_allowlist": []}, store, runtime)
        self.assertIn(("withdraw", "meu_projeto"), runtime.calls)
        self.assertEqual(self.outcomes, ["failed"])

    def test_disabled_publication_withdraws_without_preparing_credentials(self):
        store, runtime = FakePublicationStore(), FakeRuntime()
        self._run({"enabled": False, "network_allowlist": []}, store, runtime)
        self.assertEqual(self.prepared, [])
        self.assertIn(("withdraw", "meu_projeto"), runtime.calls)
        self.assertEqual(self.outcomes, ["completed"])
        atomic = [call for call in store.calls if call[0] == "atomic_json"]
        self.assertEqual(atomic[-1][2], self.proposed)


class CanonicalEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="studio-root-"))
        self.addCleanup(lambda: self._remove(self.root))
        self.secret = "jwt-" + "s" * 20

    @staticmethod
    def _remove(path):
        import shutil

        shutil.rmtree(path, ignore_errors=True)

    def _project(self, name="meu_projeto", uuid_value="uuid", ref=REF, secret=None, url="https://api.example.test/auth/v1"):
        secret = secret if secret is not None else self.secret
        folder = self.root / "projects" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ".env").write_text(
            f"PROJECT_ID={name}\nPROJECT_UUID={uuid_value}\nPROJECT_PUBLIC_REF={ref}\n"
            f"JWT_SECRET_PROJETO={secret}\nAPI_EXTERNAL_URL={url}\n"
        )
        (self.root / ".functions-tenants").mkdir(exist_ok=True)
        (self.root / ".functions-tenants" / f"{name}.json").write_text(
            f'{{"technical_name":"{name}","project_uuid":"{uuid_value}","project_ref":"{ref}","jwt_secret":"{secret}"}}'
        )
        return {"name": name, "tenant_uuid": uuid_value, "public_ref": ref}

    def _run(self, project):
        with patch.object(functions_router, "ROOT", self.root):
            return functions_router.canonical_environment(project)

    def test_returns_the_canonical_secret_and_public_url(self):
        secret, url = self._run(self._project())
        self.assertEqual((secret, url), (self.secret, "https://api.example.test"))

    def test_environment_identity_mismatch_is_refused(self):
        project = self._project()
        env = self.root / "projects" / "meu_projeto" / ".env"
        env.write_text(env.read_text().replace("PROJECT_ID=meu_projeto", "PROJECT_ID=outro"))
        with self.assertRaises(RuntimeError):
            self._run(project)

    def test_divergent_lifecycle_projection_is_refused(self):
        project = self._project()
        projection = self.root / ".functions-tenants" / "meu_projeto.json"
        projection.write_text(projection.read_text().replace(self.secret, "outro-secret"))
        with self.assertRaises(RuntimeError):
            self._run(project)

    def test_missing_public_url_is_refused(self):
        project = self._project(url="")
        with self.assertRaises(RuntimeError):
            self._run(project)

    def test_symlinked_project_environment_is_refused(self):
        self._project()
        real = self.root / "projects" / "meu_projeto"
        real.rename(self.root / "projects" / "real")
        (self.root / "projects" / "meu_projeto").symlink_to(self.root / "projects" / "real")
        with self.assertRaises(RuntimeError):
            self._run({"name": "meu_projeto", "tenant_uuid": "uuid", "public_ref": REF})


class AdministrativeKeyTest(unittest.TestCase):
    def _run(self, conn):
        with patch.object(
            studio_administrative_keys_module(),
            "generate_opaque_key",
            lambda project_id, kind: SimpleNamespace(token=f"opaco-{kind}", digest=b"d" * 32),
        ), patch.object(
            studio_administrative_keys_module(), "encrypt_project_material", self._encrypt
        ), patch.object(
            studio_administrative_keys_module(), "decrypt_project_material", self._decrypt
        ):
            return asyncio.run(
                studio_administrative_keys_module().get_studio_administrative_key(conn, project_id="pid")
            )

    async def _encrypt(self, conn, *, project_id, purpose, plaintext):
        self.assertEqual(purpose, "studio-administrative-key")
        return "ciphertext:" + plaintext

    async def _decrypt(self, conn, *, project_id, purpose, ciphertext):
        self.assertEqual(purpose, "studio-administrative-key")
        return ciphertext.removeprefix("ciphertext:")

    def test_first_use_provisions_under_the_project_lock(self):
        conn = FakeConn(row=None)
        token = self._run(conn)
        self.assertEqual(token, "opaco-secret")
        self.assertIn("FOR UPDATE", conn.queries[0])
        self.assertIn("INSERT INTO project_studio_keys", conn.queries[-1])

    def test_active_key_is_returned_verbatim(self):
        conn = FakeConn(row={"is_active": True, "secret_ciphertext": "ciphertext:existente"})
        self.assertEqual(self._run(conn), "existente")
        self.assertNotIn("INSERT INTO project_studio_keys", "".join(conn.queries))

    def test_revoked_key_is_refused(self):
        conn = FakeConn(row={"is_active": False, "secret_ciphertext": "ciphertext:revogada"})
        with self.assertRaises(HTTPException) as ctx:
            self._run(conn)
        self.assertEqual(ctx.exception.status_code, 403)


def studio_administrative_keys_module():
    from app import studio_administrative_keys

    return studio_administrative_keys


class QueueResponse:
    def __init__(self, outcome):
        self.outcome = outcome

    def raise_for_status(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome


class RecordingClient:
    queue: list = []
    calls: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, content=None):
        type(self).calls.append({"url": url, "headers": dict(headers or {}), "content": content})
        return QueueResponse(type(self).queue.pop(0))


class ServiceKeyCacheTest(unittest.TestCase):
    def setUp(self):
        RecordingClient.queue = []
        RecordingClient.calls = []
        self.fake_httpx = SimpleNamespace(
            AsyncClient=RecordingClient,
            HTTPError=type("HTTPError", (Exception,), {}),
            TimeoutException=type("TimeoutException", (Exception,), {}),
        )

    def _run(self, ref=REF, version=3):
        with patch.object(service_key_cache, "httpx", self.fake_httpx), \
                patch.object(service_key_cache, "STUDIO_CACHE_INVALIDATION_URL", "https://cache.internal"), \
                patch.object(service_key_cache, "PROJECTS_API_HMAC_SECRET", "t" * 32), \
                patch.object(service_key_cache, "build_studio_cache_ssl_context", lambda: None):
            asyncio.run(service_key_cache.invalidate_service_key_cache(ref, version))

    def test_invalidates_once_the_gateway_acknowledges(self):
        RecordingClient.queue = [None]
        self._run()
        call = RecordingClient.calls[0]
        self.assertEqual(call["url"], f"https://cache.internal/internal/cache/service-key/{REF}")
        self.assertEqual(call["content"], b'{"project_key_version":3}')
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["headers"]["X-Internal-Service"], "projects-api")
        self.assertIn("X-Internal-Signature", call["headers"])

    def test_retries_transient_failures_before_giving_up(self):
        RecordingClient.queue = [self.fake_httpx.HTTPError(), self.fake_httpx.TimeoutException(), None]
        self._run(version=1)
        self.assertEqual(len(RecordingClient.calls), 3)
        self.assertEqual(RecordingClient.calls[0]["url"], RecordingClient.calls[2]["url"])
        self.assertEqual(RecordingClient.calls[0]["content"], RecordingClient.calls[2]["content"])

    def test_raises_after_three_failed_attempts(self):
        RecordingClient.queue = [self.fake_httpx.HTTPError()] * 3
        with self.assertRaises(RuntimeError) as ctx:
            self._run()
        self.assertIn("3 attempts", str(ctx.exception))
        self.assertEqual(len(RecordingClient.calls), 3)

    def test_rejects_malformed_refs_before_any_network_call(self):
        with self.assertRaises(ValueError):
            self._run(ref="SHORT")
        self.assertEqual(RecordingClient.calls, [])


if __name__ == "__main__":
    unittest.main()
