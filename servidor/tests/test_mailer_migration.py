"""Server 60 imports active templates and preserves custom verification pages."""

from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generateProject"))
import migrate_mailer_templates as migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "projects/idr_campo_prod"
        self.project.mkdir(parents=True)
        (self.project / "nginx").mkdir()
        self.auth = self.project / "auth"
        self.auth.mkdir()
        (self.root / "auth_template").mkdir()
        (self.root / ".env").write_text("HOST_PROJECT_ROOT=" + str(self.root) + "\n")
        (self.root / "projects/.gitkeep").write_text("")
        self.tenant = str(uuid.uuid4())
        (self.project / ".env").write_text(
            f"PROJECT_UUID={self.tenant}\nKEEP_SETTING=unchanged\n"
        )
        (self.project / "Dockerfile").write_text(
            "FROM nginx:1.31.8\nCOPY nginx/nginx_idr_campo_prod.conf /etc/nginx/nginx.conf\n"
        )
        (self.project / ".dockerignore").write_text(
            "**\n!Dockerfile\n!nginx/\n!nginx/nginx_*.conf\n"
        )
        self.nginx = self.project / "nginx/nginx_idr_campo_prod.conf"
        self.nginx.write_text(
            "events {}\nhttp { server { listen 8080; location = /redefinir-senha.html { root /usr/share/nginx/html; } location /magiclink.html { allow 172.20.0.0/16; deny all; root /usr/share/nginx/html; } } }\n"
        )
        self.configured = [
            "recovery",
            "invite",
            "confirmation",
            "email_change",
            "magic_link",
        ]
        for kind in self.configured:
            name = migration.FILES[kind]
            (self.auth / name).write_text(
                "<h1>IDR Campo " + kind + " {{ .Token }}</h1>\n"
            )
            (self.root / "auth_template" / name).write_text(
                "<h1>Plataforma " + kind + " {{ .Token }}</h1>\n"
            )
        for name in [
            "verify-success.html",
            "verify-success.js",
            "redefinir-senha.html",
            "email_change_current.html",
        ]:
            (self.auth / name).write_text("IDR Campo preservado: " + name + "\n")
        (self.auth / "assets").mkdir()
        (self.auth / "assets/logo.png").write_bytes(b"\x89PNG\r\nIDR-CAMPO")
        self.environment = {
            "GOTRUE_MAILER_TEMPLATES_"
            + kind.upper(): "http://supabase-nginx-idr_campo_prod:8080/"
            + migration.FILES[kind]
            for kind in self.configured
        }
        environment = "".join(
            "      " + key + ": " + value + "\n"
            for key, value in self.environment.items()
        )
        self.compose = self.project / "docker-compose.yml"
        self.compose.write_text(
            'name: supabase\nservices:\n  nginx:\n    image: nginx:1.31.8\n    volumes:\n      - ${HOST_PROJECT_ROOT}/projects/idr_campo_prod/auth:/usr/share/nginx/html:ro\n      - ./other:/other:ro\n    networks: [rede-supabase]\n    labels:\n      traefik.enable: "true"\n  auth:\n    image: supabase/gotrue:v2.197.0\n    environment:\n'
            + environment
            + "      GOTRUE_JWT_EXP: 900\n      GOTRUE_SMTP_HOST: smtp.private\n  rest:\n    image: postgrest/postgrest:v16.5\nnetworks:\n  rede-supabase:\n    external: true\n"
        )
        self.document = {
            "services": {
                "nginx": {
                    "container_name": "supabase-nginx-idr_campo_prod",
                    "build": {"context": str(self.project), "dockerfile": "Dockerfile"},
                    "volumes": [
                        {
                            "type": "bind",
                            "source": str(self.auth),
                            "target": migration.TARGET,
                            "read_only": True,
                        },
                        {
                            "type": "bind",
                            "source": str(self.project / "other"),
                            "target": "/other",
                        },
                    ],
                },
                "auth": {"environment": self.environment},
                "rest": {},
            }
        }
        self.rows = {
            kind: {
                "kind": kind,
                "version": 0,
                "default_body": "<p>Default {{ .Token }}</p>",
                "body": "<p>Default {{ .Token }}</p>",
                "published_body": "<p>Default {{ .Token }}</p>",
                "has_draft": False,
                "published_version": 0,
                "source": "default",
            }
            for kind in migration.FILES
        }
        self.imports = []
        (self.root / "secrets/mailer").mkdir(parents=True)
        (self.root / "secrets/mailer/URL_SECRET").write_text("a" * 64)

    def plan(self, document=None):
        return migration.inspect_project(
            self.root, self.project, document or self.document
        )

    def rpc(self, root, tenant, suffix="", method="GET", body=None):
        self.assertEqual(tenant, self.tenant)
        self.assertEqual(method, "GET")
        return {"templates": list(deepcopy(self.rows).values())}

    def importer(self, root, projects):
        for project, tenant, plan, _ in projects:
            for kind, name in plan["templates"].items():
                body = plan["assets"][name].decode()
                self.imports.append((kind, body))
                self.rows[kind].update(
                    version=1,
                    published_version=1,
                    has_draft=False,
                    source="override",
                    body=body,
                    published_body=body,
                )
        return {"imported": len(self.imports), "projects": len(projects)}

    def published(self):
        for kind in self.configured:
            body = (self.auth / migration.FILES[kind]).read_text()
            self.rows[kind].update(
                version=1,
                published_version=1,
                has_draft=False,
                source="override",
                body=body,
                published_body=body,
            )
        return {"templates": list(self.rows.values())}

    def rendered(self, root, project):
        text = self.compose.read_text()
        result = deepcopy(self.document)
        if ":/usr/share/nginx/html" not in text:
            result["services"]["nginx"]["volumes"] = [
                v
                for v in result["services"]["nginx"]["volumes"]
                if v["target"] != migration.TARGET
            ]
        for kind in self.configured:
            match = re.search(
                r"^      GOTRUE_MAILER_TEMPLATES_" + kind.upper() + r": (.*)$",
                text,
                re.M,
            )
            result["services"]["auth"]["environment"][
                "GOTRUE_MAILER_TEMPLATES_" + kind.upper()
            ] = match[1].replace("${PROJECT_UUID}", self.tenant)
        return result

    def preserved_configs(self):
        return {
            name: (self.project / name).read_bytes()
            for name in [
                ".env",
                "docker-compose.yml",
                "Dockerfile",
                "nginx/nginx_idr_campo_prod.conf",
            ]
        }

    def checkpoint(self, plan):
        migration.persist_preparation(self.root, self.project, self.tenant, plan)
        path = migration.checkpoint_path(self.root, self.project)
        state = json.loads(path.read_text())
        state["prepared"] = True
        path.write_text(json.dumps(state))

    def test_apply_imports_active_content_then_changes_urls_and_is_repeatable(self):
        original = self.preserved_configs()
        with (
            patch.object(migration, "compose_document", side_effect=self.rendered),
            patch.object(migration, "service_request", side_effect=self.rpc),
            patch.object(migration, "import_legacy", side_effect=self.importer),
            patch.object(migration, "verify_runtime") as verify,
        ):
            migration.migrate(self.root, apply=True, only="idr_campo_prod")
            migration.migrate(self.root, apply=True, only="idr_campo_prod")
        self.assertEqual(
            self.nginx.read_bytes(), original["nginx/nginx_idr_campo_prod.conf"]
        )
        self.assertNotIn("/auth:/usr/share/nginx/html", self.compose.read_text())
        self.assertIn("http://template-service:18020/mailer/", self.compose.read_text())
        verify.assert_called_once()
        self.assertEqual(len(self.imports), 5)
        self.assertTrue(all("IDR Campo" in body for _, body in self.imports))
        state = json.loads(
            migration.checkpoint_path(self.root, self.project).read_text()
        )
        self.assertEqual(state["source"], str(self.auth))
        self.assertEqual(len(state["assets"]), 10)
        self.assertTrue(state["activated"])
        for name, data in original.items():
            self.assertEqual(
                (self.root / state["backup"] / "config" / name).read_bytes(), data
            )
        for name in [
            "verify-success.html",
            "verify-success.js",
            "redefinir-senha.html",
            "email_change_current.html",
            "assets/logo.png",
        ]:
            self.assertEqual(
                (self.root / state["backup"] / "static" / name).read_bytes(),
                (self.auth / name).read_bytes(),
            )

    def test_failed_database_import_does_not_change_runtime_configuration(self):
        original = self.preserved_configs()
        with (
            patch.object(migration, "compose_document", return_value=self.document),
            patch.object(
                migration,
                "import_legacy",
                side_effect=RuntimeError("Studio já contém outro template"),
            ),
        ):
            for _ in range(2):
                with self.assertRaisesRegex(
                    RuntimeError, "Studio já contém outro template"
                ):
                    migration.migrate(self.root, apply=True, only="idr_campo_prod")
        self.assertEqual(original, self.preserved_configs())
        self.assertEqual(self.imports, [])
        state = json.loads(
            migration.checkpoint_path(self.root, self.project).read_text()
        )
        self.assertFalse(state.get("prepared", False))

    def test_global_mount_wins_over_a_stale_project_auth_directory(self):
        document = deepcopy(self.document)
        document["services"]["nginx"]["volumes"][0]["source"] = str(
            self.root / "auth_template"
        )
        plan = self.plan(document)
        self.assertTrue(
            all(
                b"Plataforma" in plan["assets"][name]
                for name in plan["templates"].values()
            )
        )
        with patch.object(migration, "run_service", return_value={}) as run:
            migration.import_legacy(
                self.root, [(self.project, self.tenant, plan, document)]
            )
        payload = run.call_args.args[2]
        self.assertTrue(
            all(value is None for value in payload["projects"][0]["templates"].values())
        )
        self.assertIn("Plataforma", payload["defaults"]["magic_link"])

    def test_custom_mount_is_registered_with_the_correct_project_and_exact_bodies(self):
        plan = self.plan()
        with patch.object(migration, "run_service", return_value={}) as run:
            migration.import_legacy(
                self.root, [(self.project, self.tenant, plan, self.document)]
            )
        payload = run.call_args.args[2]
        project = payload["projects"][0]
        self.assertEqual(
            (project["tenant"], project["name"]), (self.tenant, "idr_campo_prod")
        )
        for kind in self.configured:
            self.assertEqual(
                project["templates"][kind],
                (self.auth / migration.FILES[kind]).read_text(),
            )
        self.assertIsNone(project["templates"]["reauthentication"])
        self.assertEqual(run.call_args.args[1], ["python", "legacy_migration.py"])

    def test_activation_refuses_unimported_content_without_editing_compose_or_nginx(
        self,
    ):
        plan = self.plan()
        self.checkpoint(plan)
        original = self.preserved_configs()
        with self.assertRaisesRegex(RuntimeError, "banco ainda não corresponde"):
            migration.activate_project(
                self.root,
                self.project,
                self.tenant,
                plan,
                self.document,
                {"templates": list(self.rows.values())},
            )
        self.assertEqual(original, self.preserved_configs())

    def test_activation_copies_every_file_and_keeps_nginx_and_other_services(self):
        plan = self.plan()
        self.checkpoint(plan)
        original_nginx = self.nginx.read_bytes()
        saved = self.published()
        with (
            patch.object(migration, "verify_runtime"),
            patch.object(migration, "compose_document", side_effect=self.rendered),
        ):
            migration.activate_project(
                self.root, self.project, self.tenant, plan, self.document, saved
            )
        self.assertEqual(self.nginx.read_bytes(), original_nginx)
        for name, data in plan["assets"].items():
            self.assertEqual(
                (self.project / migration.ASSET_DIRECTORY / name).read_bytes(), data
            )
        compose = self.compose.read_text()
        self.assertNotIn("/auth:/usr/share/nginx/html", compose)
        self.assertIn("./other:/other:ro", compose)
        self.assertIn("GOTRUE_JWT_EXP: 900", compose)
        self.assertIn("GOTRUE_SMTP_HOST: smtp.private", compose)
        self.assertIn("postgrest/postgrest:v16.5", compose)
        self.assertNotIn("GOTRUE_MAILER_TEMPLATES_REAUTHENTICATION", compose)
        recipe = (self.project / "Dockerfile").read_text()
        self.assertIn("COPY nginx/mailer-static-assets/", recipe)
        self.assertNotIn("USER ", recipe)
        self.assertTrue(self.auth.is_dir())

    def test_source_changes_after_prepare_block_activation(self):
        plan = self.plan()
        self.checkpoint(plan)
        original = self.preserved_configs()
        (self.auth / "verify-success.js").write_text("changed after preparation")
        with self.assertRaisesRegex(RuntimeError, "Arquivos mudaram"):
            migration.activate_project(
                self.root,
                self.project,
                self.tenant,
                self.plan(),
                self.document,
                self.published(),
            )
        self.assertEqual(self.preserved_configs(), original)

    def test_failed_validation_restores_configs_and_never_recreates_containers(self):
        plan = self.plan()
        self.checkpoint(plan)
        original = self.preserved_configs()
        with (
            patch.object(migration, "verify_runtime"),
            patch.object(migration, "compose_document", return_value=self.document),
            patch.object(migration.subprocess, "run") as process,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "arquivos anteriores restaurados"
            ):
                migration.activate_project(
                    self.root,
                    self.project,
                    self.tenant,
                    plan,
                    self.document,
                    self.published(),
                    restart=True,
                )
            process.assert_not_called()
        self.assertEqual(self.preserved_configs(), original)

    def test_runtime_fallback_or_wrong_html_blocks_cutover(self):
        plan = self.plan()
        self.checkpoint(plan)
        original = self.preserved_configs()
        with patch.object(
            migration,
            "verify_runtime",
            side_effect=RuntimeError("Conteúdo servido não corresponde"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Conteúdo servido"):
                migration.activate_project(
                    self.root,
                    self.project,
                    self.tenant,
                    plan,
                    self.document,
                    self.published(),
                )
        self.assertEqual(self.preserved_configs(), original)

    def test_long_mount_syntax_removes_only_the_html_target(self):
        text = self.compose.read_text().replace(
            "      - ${HOST_PROJECT_ROOT}/projects/idr_campo_prod/auth:/usr/share/nginx/html:ro\n",
            "      - type: bind\n        source: ${HOST_PROJECT_ROOT}/projects/idr_campo_prod/auth\n        target: /usr/share/nginx/html\n        read_only: true\n",
        )
        changed, count = migration.remove_static_mount(text)
        self.assertEqual(count, 1)
        self.assertNotIn("target: /usr/share/nginx/html", changed)
        self.assertIn("./other:/other:ro", changed)

    def test_missing_used_template_does_not_fall_back_to_the_global_directory(self):
        (self.auth / "magiclink.html").unlink()
        with self.assertRaisesRegex(RuntimeError, "não está na raiz estática"):
            self.plan()

    def test_symbolic_assets_and_path_traversal_are_denied(self):
        (self.auth / "linked.html").symlink_to(
            self.root / "auth_template/magiclink.html"
        )
        with self.assertRaisesRegex(RuntimeError, "contém um link"):
            self.plan()
        with self.assertRaisesRegex(RuntimeError, "Projeto inválido"):
            migration.migrate(self.root, only="../idr_campo_prod")

    def test_plan_can_run_before_credentials_or_template_service_exist(self):
        original = self.preserved_configs()
        with (
            patch.object(migration, "compose_document", return_value=self.document),
            patch.object(migration, "service_request") as rpc,
        ):
            migration.migrate(self.root, only="idr_campo_prod")
            rpc.assert_not_called()
        self.assertEqual(original, self.preserved_configs())
        self.assertFalse((self.root / ".migration").exists())
