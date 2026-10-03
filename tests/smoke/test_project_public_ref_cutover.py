from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import migrate_snippet_namespaces as snippets
import migrate_project_public_refs as servers
from migration_files import digest

USER = "11111111-1111-4111-8111-111111111111"
PROJECT = "22222222-2222-4222-8222-222222222222"
TENANT = "33333333-3333-4333-8333-333333333333"
REF = "abcdefghijklmnopqrst"
CATALOG = [{"id": PROJECT, "tenant_uuid": TENANT, "name": "technical_project",
            "public_ref": REF, "legacy_names": ["old_project"]}]


class SnippetCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def folder(self, scope, sql="select 1;"):
        folder = self.root / (USER + "__" + scope)
        folder.mkdir()
        (folder / "query.sql").write_text(sql)
        (folder / "query.sql").chmod(0o600)
        return folder

    def test_dry_run_has_no_writes(self):
        self.folder("old_project")
        before = digest(self.root)
        self.assertTrue(snippets.migrate(self.root, CATALOG))
        self.assertEqual(digest(self.root), before)

    def test_merge_preserves_sql_modes_and_subfolders(self):
        self.folder("technical_project")
        self.folder("old_project")
        self.folder("old_project__folder", "select 2;")
        snippets.migrate(self.root, CATALOG, apply=True)
        self.assertEqual((self.root / (USER + "__" + PROJECT) / "query.sql").read_text(), "select 1;")
        self.assertEqual((self.root / (USER + "__" + PROJECT + "__folder") / "query.sql").read_text(), "select 2;")
        self.assertFalse((self.root / snippets.JOURNAL).exists())
        self.assertEqual(snippets.migrate(self.root, CATALOG, apply=True), {})

    def test_conflict_fails_before_mutation(self):
        self.folder("technical_project")
        self.folder("old_project", "select 9;")
        before = digest(self.root)
        with self.assertRaisesRegex(RuntimeError, "Conflicting SQL"):
            snippets.migrate(self.root, CATALOG, apply=True)
        self.assertEqual(digest(self.root), before)
        with self.assertRaises(ValueError):
            snippets.mapping([*CATALOG, {**CATALOG[0], "id": TENANT}])

    def test_unknown_namespace_fails(self):
        self.folder("unknown_project")
        before = digest(self.root)
        with self.assertRaisesRegex(RuntimeError, "Unknown"):
            snippets.migrate(self.root, CATALOG, apply=True)
        self.assertEqual(digest(self.root), before)

    @unittest.skipIf(os.name == "nt", "Linux symlink permissions")
    def test_symlinks_fail_closed(self):
        folder = self.folder("old_project")
        (folder / "link.sql").symlink_to(folder / "query.sql")
        with self.assertRaises(RuntimeError):
            snippets.migrate(self.root, CATALOG, apply=True)

    def test_interrupted_move_rolls_back_every_original(self):
        self.folder("technical_project")
        self.folder("old_project__folder", "select 2;")
        before = digest(self.root)
        replace = os.replace
        def interrupted(source, target):
            if Path(source).parent.name == "stage":
                raise RuntimeError("injected move failure")
            return replace(source, target)
        with patch.object(snippets.os, "replace", interrupted):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                snippets.migrate(self.root, CATALOG, apply=True)
        self.assertEqual(digest(self.root), before)


class ServerCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.directory = self.root / "projects/technical_project"
        (self.directory / "nginx").mkdir(parents=True)
        shutil.copytree(ROOT / "servidor/generateProject", self.root / "generateProject")
        (self.root / ".env").write_text("SERVER_URL=api.example.test\nSERVER_PROTO=https\nHOST_PROJECT_ROOT=/srv/example\n")
        (self.directory / ".env").write_text(
            f"PROJECT_ID=technical_project\nPROJECT_UUID={TENANT}\n"
            f"CONFIG_TOKEN_PROJETO={'a' * 64}\nAPI_GATEWAY_TOKEN_PROJETO={'b' * 64}\n"
            f"JWT_SECRET_PROJETO={'c' * 43}\nANON_KEY_PROJETO=header.payload.sig\n"
            "SERVICE_ROLE_KEY_PROJETO=header.payload.sig\nPRIVATE_SECRET=unchanged\n"
            "API_EXTERNAL_URL=https://api.example.test/technical_project/auth/v1\n"
            "SITE_URL=https://app.example.test/welcome\n"
            "ADDITIONAL_REDIRECT_URLS=https://api.example.test/technical_project/verify-success.html,myapp://callback\n")
        for name in ("Dockerfile", "docker-compose.yml", ".dockerignore", "nginx/nginx_technical_project.conf"):
            (self.directory / name).write_text("original " + name)

    def test_prepare_and_apply_preserve_identity_and_custom_urls(self):
        before = digest(self.directory)
        self.assertEqual(servers.prepare(self.root, CATALOG), ["technical_project"])
        self.assertEqual(digest(self.directory), before)
        with patch.object(servers, "require_stopped"):
            servers.prepare(self.root, CATALOG, apply=True)
        env = (self.directory / ".env").read_text()
        for required in ["PROJECT_ID=technical_project", "PROJECT_UUID=" + TENANT,
                         "PROJECT_PUBLIC_REF=" + REF, "PRIVATE_SECRET=unchanged",
                         "SITE_URL=https://app.example.test/welcome",
                         "API_EXTERNAL_URL=https://api.example.test/" + REF + "/auth/v1",
                         "/verify-success.html,myapp://callback"]:
            self.assertIn(required, env)
        nginx = (self.directory / "nginx/nginx_technical_project.conf").read_text()
        self.assertIn("/" + REF, nginx)
        self.assertIn("supabase-auth-technical_project", nginx)

    def test_active_functions_projection_is_migrated_transactionally(self):
        directory = self.root / ".functions-tenants"
        directory.mkdir()
        projection = directory / "technical_project.json"
        projection.write_text(json.dumps({"project_ref": "technical_project", "project_uuid": TENANT}))
        with patch.object(servers, "require_stopped"):
            servers.prepare(self.root, CATALOG, apply=True)
        data = json.loads(projection.read_text())
        self.assertEqual(set(data), {"project_ref", "technical_name", "project_uuid", "anon_key", "service_role_key", "jwt_secret"})
        self.assertEqual(data["project_ref"], REF)
        self.assertEqual(data["technical_name"], "technical_project")
        self.assertEqual(data["project_uuid"], TENANT)

    def test_failed_render_restores_exact_files(self):
        before = digest(self.directory)
        with patch.object(servers, "require_stopped"), patch.object(
                servers, "sync_project_generated_files", side_effect=RuntimeError("injected render failure")):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                servers.prepare(self.root, CATALOG, apply=True)
        self.assertEqual(digest(self.directory), before)
        self.assertFalse((self.root / servers.JOURNAL).exists())

    def test_active_services_prevent_all_writes(self):
        before = digest(self.directory)
        with patch.object(servers, "require_stopped", side_effect=RuntimeError("running")):
            with self.assertRaisesRegex(RuntimeError, "running"):
                servers.prepare(self.root, CATALOG, apply=True)
        self.assertEqual(digest(self.directory), before)


if __name__ == "__main__":
    unittest.main()
