"""Host regeneration preserves mailer identity, legacy pages and confinement."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "servidor/generateProject"
sys.path.insert(0, str(ROOT / "servidor/host-agent"))
sys.path.insert(0, str(SCRIPTS))
from hostagent import commands, templates
from hostagent.envfile import read_canonical_env_value
from configure_mailer_templates import project_key

NAME = "idr_campo_prod"
TENANT = "11111111-1111-4111-8111-111111111111"


class MailerRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / "projects" / NAME
        self.project.mkdir(parents=True)
        (self.root / ".env").write_text(
            "SERVER_URL=https://api.example.test\nHOST_PROJECT_ROOT=/srv/supabase\n"
        )
        (self.root / "secrets/mailer").mkdir(parents=True)
        self.secret = self.root / "secrets/mailer/URL_SECRET"
        self.secret.write_text("a" * 64)
        (self.project / ".env").write_text(
            f"PROJECT_UUID={TENANT}\nPROJECT_PUBLIC_REF=abcdefghijklmnopqrst\n"
            f"API_GATEWAY_TOKEN_PROJETO={'b' * 64}\nJWT_SECRET_PROJETO={'c' * 43}\n"
            "ANON_KEY_PROJETO=header.payload.sig\nSERVICE_ROLE_KEY_PROJETO=header.payload.sig\n"
        )

    def render(self):
        templates.sync_project_generated_files(
            root=self.root, scripts_dir=SCRIPTS, project_dir=self.project, project=NAME
        )

    def test_recreate_materializes_scoped_key_and_embedded_public_pages(self):
        self.render()
        self.assertEqual(
            read_canonical_env_value(self.project / ".env", "MAILER_TEMPLATE_KEY"),
            project_key("a" * 64, TENANT),
        )
        self.assertEqual((self.project / ".env").stat().st_mode & 0o777, 0o600)
        compose = (self.project / "docker-compose.yml").read_text()
        self.assertEqual(compose.count("http://template-service:18020/mailer/"), 6)
        self.assertIn(
            "${MAILER_TEMPLATE_KEY:?MAILER_TEMPLATE_KEY is required}", compose
        )
        self.assertNotIn("auth_template", compose)
        self.assertIn(
            "COPY --chown=101:101 nginx/public/",
            (self.project / "Dockerfile").read_text(),
        )
        self.assertEqual(
            (self.project / "nginx/public/verify-success.html").read_bytes(),
            (SCRIPTS / "public/verify-success.html").read_bytes(),
        )
        self.assertNotIn("a" * 64, compose)
        self.assertNotIn(project_key("a" * 64, TENANT), compose)

    def test_migrated_project_pages_and_assets_survive_repeated_regeneration(self):
        self.render()
        assets = self.project / "nginx/mailer-static-assets"
        (assets / "assets").mkdir(parents=True)
        preserved = {
            "verify-success.html": b"<h1>IDR Campo</h1>",
            "verify-success.js": b"/* custom */",
            "redefinir-senha.html": b"<h1>Recuperar</h1>",
            "assets/logo.png": b"project-logo",
            "magiclink.html": b"<p>{{ .Token }}</p>",
        }
        for name, content in preserved.items():
            (assets / name).write_bytes(content)
        with (self.project / "Dockerfile").open("a") as file:
            file.write(
                "\n# BEGIN IDR MAILER STATIC ASSETS\nCOPY nginx/mailer-static-assets/ /usr/share/nginx/html/\n# END IDR MAILER STATIC ASSETS\n"
            )
        for name in (".dockerignore", "Dockerfile.dockerignore"):
            (self.project / name).write_text("**\n!Dockerfile\n!nginx/nginx_*.conf\n")
        self.render()
        nginx = (self.project / "nginx" / f"nginx_{NAME}.conf").read_text()
        self.assertIn(
            "location = /redefinir-senha.html {\n            set $opaque_target_service auth;",
            nginx,
        )
        self.assertIn("location = /assets/logo.png", nginx)
        self.assertIn("location = /redefinir-senha.html", nginx.split("listen 8081;")[0])
        self.assertNotIn("location = /redefinir-senha.html", nginx.split("listen 8081;")[1])
        self.assertNotIn("location = /magiclink.html", nginx)
        for name in (".dockerignore", "Dockerfile.dockerignore"):
            self.assertIn("!nginx/public/**", (self.project / name).read_text())
        self.render()
        for name, content in preserved.items():
            self.assertEqual(
                (self.project / "nginx/public" / name).read_bytes(), content
            )
        self.assertIn(
            "location = /redefinir-senha.html",
            (self.project / "nginx" / f"nginx_{NAME}.conf").read_text(),
        )

    def test_missing_secret_preserves_existing_configuration(self):
        (self.project / "docker-compose.yml").write_text("services: {}\n")
        before = (self.project / ".env").read_bytes()
        self.secret.unlink()
        with self.assertRaisesRegex(RuntimeError, "Credencial do mailer ausente"):
            self.render()
        self.assertEqual(
            (self.project / "docker-compose.yml").read_text(), "services: {}\n"
        )
        self.assertEqual((self.project / ".env").read_bytes(), before)
        self.assertFalse((self.project / "nginx").exists())

    def test_unmigrated_urls_and_mounts_are_rejected_without_changes(self):
        for compose in (
            "services:\n  auth:\n    environment:\n      GOTRUE_MAILER_TEMPLATES_MAGIC_LINK: http://nginx:8080/magiclink.html\n",
            "services:\n  nginx:\n    volumes:\n      - ./auth:/usr/share/nginx/html:ro\n",
            "services:\n  nginx:\n    volumes:\n      - type: bind\n        source: ./auth\n        target: /usr/share/nginx/html\n",
        ):
            with self.subTest(compose=compose):
                (self.project / "docker-compose.yml").write_text(compose)
                before = (self.project / ".env").read_bytes()
                with self.assertRaisesRegex(RuntimeError, "Migre os templates legados"):
                    self.render()
                self.assertEqual(
                    (self.project / "docker-compose.yml").read_text(), compose
                )
                self.assertEqual((self.project / ".env").read_bytes(), before)
                self.assertFalse((self.project / "nginx").exists())

    def test_public_asset_symlinks_are_rejected_before_configuration_changes(self):
        public = self.project / "nginx/public"
        public.mkdir(parents=True)
        (public / "leak.html").symlink_to(self.secret)
        before = (self.project / ".env").read_bytes()
        with self.assertRaisesRegex(RuntimeError, "atravessar links"):
            self.render()
        self.assertEqual((self.project / ".env").read_bytes(), before)
        self.assertFalse((self.project / "docker-compose.yml").exists())

    def test_existing_custom_public_page_is_not_overwritten_by_defaults(self):
        public = self.project / "nginx/public"
        public.mkdir(parents=True)
        (public / "verify-success.html").write_text("<h1>Minha página</h1>")
        self.render()
        self.assertEqual(
            (public / "verify-success.html").read_text(), "<h1>Minha página</h1>"
        )


class MailerRecreateHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_auth_only_recreation_repairs_key_before_compose_and_keeps_pages(
        self,
    ):
        fixture = MailerRuntimeTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.render()
        key = project_key("a" * 64, TENANT)
        env = fixture.project / ".env"
        env.write_text(env.read_text().replace(key, "f" * 64))
        public = fixture.project / "nginx/public/verify-success.html"
        content = public.read_bytes()
        config = SimpleNamespace(
            root=fixture.root,
            projects_root=fixture.root / "projects",
            scripts_dir=SCRIPTS,
        )
        ctx = commands.CommandContext(
            config, commands.RunningCommandState(), 600, "recreate_services", None
        )

        async def compose(argv, context, **kwargs):
            self.assertEqual(read_canonical_env_value(env, "MAILER_TEMPLATE_KEY"), key)
            self.assertEqual(argv[-1], "auth")
            self.assertEqual(kwargs["cwd"], fixture.project)
            return commands.ProcessResult(0, False, set())

        with patch.object(commands, "run_process", side_effect=compose) as run:
            outcome = await commands.handle_recreate_services(
                ctx, NAME, {"services": ["auth"]}
            )
        self.assertEqual(outcome.status, "done")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(public.read_bytes(), content)
