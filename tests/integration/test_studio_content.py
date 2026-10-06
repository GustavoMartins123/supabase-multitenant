"""Studio content contracts against a disposable PostgreSQL database."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "servidor/api-internal"))
sys.path.insert(0, str(ROOT / "tests/smoke"))
sys.path.insert(0, str(ROOT / "tools"))
DSN = os.environ.get("CONTROL_PLANE_TEST_DSN", "")


class ImportedIdentityTest(unittest.TestCase):
    def test_filesystem_root_uses_original_javascript_identity(self):
        from migrate_studio_content import filesystem_root_id
        root = '11111111-1111-4111-8111-111111111111__22222222-2222-4222-8222-222222222222'
        self.assertEqual(str(filesystem_root_id(root)), 'c3d5a6ae-ca99-43c7-a2a0-d341f10c3888')

    def test_offline_ids_match_original_openresty_vectors(self):
        from migrate_studio_content import imported_id
        root = '11111111-1111-4111-8111-111111111111__22222222-2222-4222-8222-222222222222'
        vectors = [
            ([root], 'b0349028-bc2e-45ff-9a02-b874c2ccfdb9'),
            ([root, 'Consultas rápidas'], '4066d4d7-5b94-4e28-998e-d4b538774754'),
            (['00000000-0000-4000-8000-000000000001', 'Ação e relatório.sql'], '28131c6d-b6d7-4e99-b33f-bb363945d60d'),
            (['00000000-0000-4000-8000-000000000001', 'New query.sql'], 'df79a55f-7350-45ec-ad65-d49b9de92ffe'),
        ]
        for parts, expected in vectors:
            with self.subTest(parts=parts):
                self.assertEqual(str(imported_id(parts)), expected)


@unittest.skipUnless(DSN, "Disposable CONTROL_PLANE_TEST_DSN required")
class StudioContentTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import asyncpg
        import httpx
        from fastapi import FastAPI, HTTPException
        from test_authorization_behavior import _seed_environment
        _seed_environment()
        from app.schema_migrations import apply_migrations
        from app.routers import studio_content as routes
        self.routes = routes
        self.database = "content_test_" + secrets.token_hex(6)
        self.admin = await asyncpg.connect(DSN)
        await self.admin.execute(f'CREATE DATABASE "{self.database}"')
        self.dsn = DSN.rsplit("/", 1)[0] + "/" + self.database
        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=4)
        async with self.pool.acquire() as conn:
            await apply_migrations(conn)
        self.users = [uuid.uuid4() for _ in range(3)]
        self.projects = [uuid.uuid4() for _ in range(2)]
        self.refs = ["abcdefghijklmnopqrst", "bcdefghijklmnopqrstu"]
        await self.pool.executemany("INSERT INTO users(id,authelia_username) VALUES($1,$2)",
                                   [(identity, "test" + str(index)) for index, identity in enumerate(self.users)])
        await self.pool.executemany("INSERT INTO projects(id,name,display_name,public_ref,owner_id) VALUES($1,$2,$2,$3,$4)",
            [(identity, "project" + str(index), self.refs[index], self.users[0]) for index, identity in enumerate(self.projects)])
        await self.pool.executemany("INSERT INTO project_members(project_id,user_id,role) VALUES($1,$2,'member')",
                                   [(project, user) for project in self.projects for user in self.users[:2]])
        app = FastAPI()
        app.include_router(routes.router)
        app.dependency_overrides[routes.get_pool] = lambda: self.pool
        @app.middleware("http")
        async def service(request, call_next):
            request.state.internal_service = request.headers.get("X-Test-Service")
            return await call_next(request)
        async def identity(request, pool):
            value = request.headers.get("X-Test-User")
            if not value:
                raise HTTPException(401, "Authentication required")
            return {"db_user_id": uuid.UUID(value), "is_global_admin": request.headers.get("X-Test-Admin") == "true"}
        self.identity_patch = patch.object(routes, "resolve_authenticated_user", side_effect=identity)
        self.identity_patch.start()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        self.identity_patch.stop()
        await self.pool.close()
        await self.admin.execute(f'DROP DATABASE "{self.database}" WITH (FORCE)')
        await self.admin.close()

    def payload(self, *, id=None, name="Untitled query", sql="", folder=None):
        id = str(id or uuid.uuid4())
        return {"id": id, "type": "sql", "name": name, "visibility": "user", "folder_id": folder,
                "content": {"content_id": id, "schema_version": "1.0", "sql": sql}}

    async def request(self, method, suffix="", *, body=None, user=0, project=0, service="studio-nginx", headers=None):
        result = await self.client.request(method, f"/api/projects/{self.refs[project]}/content{suffix}", json=body,
            headers={"X-Test-User": str(self.users[user]), "X-Test-Service": service, **(headers or {})})
        return result

    async def save(self, body, **kwargs):
        result = await self.request("PUT", body=body, **kwargs)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["id"], body["id"])
        self.assertEqual(result.json()["content"]["content_id"], body["id"])
        return result.json()

    async def test_empty_drafts_and_duplicate_titles_have_independent_persisted_ids(self):
        bodies = [self.payload() for _ in range(3)]
        for body in bodies:
            await self.save(body)
        result = await self.request("GET")
        self.assertEqual({item["id"] for item in result.json()["data"]}, {body["id"] for body in bodies})
        self.assertTrue(all("content" not in item for item in result.json()["data"]))
        for body in bodies:
            fetched = await self.request("GET", "/item/" + body["id"])
            self.assertEqual(fetched.json()["content"]["sql"], "")
        self.assertEqual(result.headers["Cache-Control"], "no-store")

    async def test_rename_and_move_preserve_snippet_and_content_identity(self):
        body = self.payload(sql="select 42")
        original = await self.save(body)
        folder = (await self.request("POST", "/folders", body={"name": "Queries"})).json()
        body.update(name="Renamed / title", folder_id=folder["id"], favorite=True)
        changed = await self.save(body)
        self.assertEqual(changed["inserted_at"], original["inserted_at"])
        self.assertEqual((await self.request("GET", "/folders/" + folder["id"])).json()["data"]["contents"][0]["id"], body["id"])
        renamed = await self.request("PATCH", "/folders/" + folder["id"], body={"name": "Changed folder"})
        self.assertEqual(renamed.json()["id"], folder["id"])
        self.assertEqual((await self.request("GET", "?favorite=true")).json()["data"][0]["id"], body["id"])
        body["folder_id"] = None
        await self.save(body)
        self.assertEqual((await self.request("GET", "/item/" + body["id"])).json()["content"]["sql"], "select 42")

    async def test_save_and_read_do_not_execute_sql(self):
        body = self.payload(sql="DROP TABLE public.users;")
        await self.save(body)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM users"), 3)
        body["content"]["sql"] = ""
        await self.save(body)
        self.assertEqual((await self.request("GET", "/item/" + body["id"])).json()["content"]["sql"], "")

    async def test_private_isolation_and_id_collision_are_fail_closed(self):
        body = self.payload(sql="select 1")
        await self.save(body)
        for kwargs in ({"user": 1}, {"project": 1}, {"user": 1, "headers": {"X-Test-Admin": "true"}}):
            self.assertEqual((await self.request("GET", "/item/" + body["id"], **kwargs)).status_code, 404)
            self.assertEqual((await self.request("PUT", body=body, **kwargs)).status_code, 409)
            self.assertEqual((await self.request("DELETE", "?ids=" + body["id"], **kwargs)).status_code, 404)
        self.assertEqual((await self.request("GET", user=1)).json()["data"], [])

    async def test_folder_ownership_is_not_taken_from_request_body(self):
        folder = (await self.request("POST", "/folders", body={"name": "Private"}, user=1)).json()
        body = self.payload(folder=folder["id"])
        body.update(owner_id=str(self.users[1]), project_id=str(self.projects[1]))
        self.assertEqual((await self.request("PUT", body=body)).status_code, 404)
        body["folder_id"] = None
        saved = await self.save(body)
        self.assertEqual(saved["owner_uuid"], str(self.users[0]))
        self.assertEqual(saved["project_uuid"], str(self.projects[0]))

    async def test_bulk_delete_rolls_back_if_any_id_is_not_owned(self):
        own, other = self.payload(), self.payload()
        await self.save(own)
        await self.save(other, user=1)
        self.assertEqual((await self.request("DELETE", "?ids=" + own["id"] + "," + other["id"])).status_code, 404)
        self.assertEqual((await self.request("GET", "/item/" + own["id"])).status_code, 200)
        deleted = await self.request("DELETE", "?ids=" + own["id"])
        self.assertEqual(deleted.json(), [{"id": own["id"]}])
        self.assertEqual((await self.request("GET", "/item/" + own["id"])).status_code, 404)

    async def test_folder_deletion_only_cascades_its_own_snippets(self):
        folder = (await self.request("POST", "/folders", body={"name": "Private"})).json()
        own, root = self.payload(folder=folder["id"]), self.payload()
        await self.save(own)
        await self.save(root)
        self.assertEqual((await self.request("DELETE", "/folders?ids=" + folder["id"], user=1)).status_code, 404)
        self.assertEqual((await self.request("DELETE", "/folders?ids=" + folder["id"])).status_code, 200)
        self.assertEqual((await self.request("GET", "/item/" + own["id"])).status_code, 404)
        self.assertEqual((await self.request("GET", "/item/" + root["id"])).status_code, 200)

    async def test_pagination_search_and_count_share_scope(self):
        bodies = [self.payload(name="Same") for _ in range(5)]
        for body in bodies:
            await self.save(body)
        await self.save(self.payload(name="Same"), user=1)
        found, cursor = [], None
        while True:
            query = "?limit=2&sort_by=name&sort_order=asc" + ("&cursor=" + cursor if cursor else "")
            page = (await self.request("GET", query)).json()
            found.extend(item["id"] for item in page["data"])
            cursor = page["cursor"]
            if not cursor:
                break
        self.assertEqual(set(found), {body["id"] for body in bodies})
        self.assertEqual(len(found), 5)
        self.assertEqual((await self.request("GET", "/count")).json()["private"], 5)
        self.assertEqual((await self.request("GET", "/count?name=sam")).json(), {"count": 5})
        self.assertEqual((await self.request("GET", "?name=sam")).json()["data"].__len__(), 5)

    async def test_invalid_cursor_and_query_are_not_substituted(self):
        own, other = self.payload(), self.payload()
        await self.save(own)
        await self.save(other, user=1)
        for query in ("?cursor=" + other["id"], "?cursor=" + str(uuid.uuid4()), "?limit=0", "?sort_by=wrong", "?limit=1&limit=2", "?unknown=1"):
            self.assertEqual((await self.request("GET", query)).status_code, 400)

    async def test_invalid_identity_or_nested_folder_is_rejected(self):
        body = self.payload()
        body["content"]["content_id"] = str(uuid.uuid4())
        self.assertEqual((await self.request("PUT", body=body)).status_code, 422)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_sql_snippets"), 0)
        self.assertEqual((await self.request("POST", "/folders", body={"name": "Nested", "parentId": str(uuid.uuid4())})).status_code, 422)

    async def test_membership_and_gateway_are_required(self):
        self.assertEqual((await self.request("GET", user=2)).status_code, 403)
        self.assertEqual((await self.request("GET", service="untrusted")).status_code, 403)
        self.assertEqual((await self.request("PUT", body=self.payload(), user=2)).status_code, 403)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_sql_snippets"), 0)

    async def test_project_display_name_and_public_reference_do_not_change_snippet_identity(self):
        body = self.payload()
        await self.save(body)
        new_ref = "cdefghijklmnopqrstuv"
        await self.pool.execute("UPDATE projects SET display_name='Changed',public_ref=$2 WHERE id=$1", self.projects[0], new_ref)
        self.assertEqual((await self.request("GET", "/item/" + body["id"])).status_code, 404)
        self.refs[0] = new_ref
        self.assertEqual((await self.request("GET", "/item/" + body["id"])).json()["id"], body["id"])

    async def test_offline_import_preserves_ids_sql_and_originals(self):
        from migrate_studio_content import import_snapshot, imported_id, filesystem_root_id
        from migration_files import digest
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            name = str(self.users[0]) + "__" + str(self.projects[0])
            namespace = root / name
            namespace.mkdir()
            (namespace / "Query.sql").write_text("select 42", encoding="utf-8")
            child = root / (name + "__Reports")
            child.mkdir()
            (child / "Query.sql").write_text("", encoding="utf-8")
            before = digest(root)
            async with self.pool.acquire() as conn:
                self.assertEqual(await import_snapshot(conn, root), (1, 2))
            root_id = imported_id([str(filesystem_root_id(name)), "Query.sql"])
            child_id = imported_id([str(imported_id([name, "Reports"])), "Query.sql"])
            self.assertEqual((await self.request("GET", "/item/" + str(root_id))).json()["content"]["sql"], "select 42")
            self.assertEqual((await self.request("GET", "/item/" + str(child_id))).json()["content"]["sql"], "")
            self.assertEqual(digest(root), before)
            async with self.pool.acquire() as conn:
                with self.assertRaises(RuntimeError):
                    await import_snapshot(conn, root)

    async def test_offline_import_is_atomic_for_unknown_namespaces(self):
        from migrate_studio_content import import_snapshot
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            good = root / (str(self.users[0]) + "__" + str(self.projects[0]))
            good.mkdir()
            (good / "Query.sql").write_text("select 1", encoding="utf-8")
            (root / "unattributed").mkdir()
            async with self.pool.acquire() as conn:
                with self.assertRaises(RuntimeError):
                    await import_snapshot(conn, root)
            self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM studio_sql_snippets"), 0)

    async def test_database_constraint_requires_the_same_content_id(self):
        import asyncpg
        with self.assertRaises(asyncpg.CheckViolationError):
            await self.pool.execute("INSERT INTO studio_sql_snippets(id,project_id,owner_id,name,content) VALUES($1,$2,$3,'Query',$4::jsonb)",
                uuid.uuid4(), self.projects[0], self.users[0], json.dumps({"sql": "", "content_id": str(uuid.uuid4())}))
