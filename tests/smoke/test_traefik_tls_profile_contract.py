"""Contrato do perfil TLS de producao do Traefik (REVISAO_ARQUITETURAL #2).

O renderer e a unica fonte de rotas. Com TRAEFIK_ENABLE_TLS=true ele emite
routers websecure + redirect permanente; sem TLS habilitado, SERVER_PROTO=https
precisa falhar fechado em vez de servir HTTP assumindo HTTPS.
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TRAEFIK_DIR = ROOT / "servidor" / "traefik"


def load_renderer():
    spec = importlib.util.spec_from_file_location(
        "render_dynamic_config_tls",
        TRAEFIK_DIR / "render_dynamic_config.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class RendererTlsBehaviorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.renderer = load_renderer()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self._tmp.name)
        self.env = self.tmp / "server.env"
        self.projects = self.tmp / "projects"
        self.projects.mkdir()
        project = self.projects / "projeto_a"
        project.mkdir()
        (project / ".env").write_text(
            "PROJECT_ID=projeto_a\n"
            "PROJECT_UUID=9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_env(self, content: str) -> None:
        self.env.write_text(content, encoding="utf-8")

    def test_default_env_keeps_http_only_routers(self) -> None:
        self.write_env("PROJECTS_API_PORT=18000\n")
        output = self.renderer.render(self.env, self.projects)
        self.assertNotIn("websecure", output)
        self.assertIn("- web\n", output)
        self.assertNotIn("force-https", output)

    def test_file_mode_without_certificates_is_rejected(self) -> None:
        self.write_env(
            "PROJECTS_API_PORT=18000\nTRAEFIK_ENABLE_TLS=true\nTRAEFIK_TLS_MODE=file\n"
        )
        with self.assertRaises(ValueError):
            self.renderer.render(self.env, self.projects)

    def test_file_mode_with_certificates_emits_websecure_and_redirect(self) -> None:
        certs = self.tmp / "certs"
        certs.mkdir()
        (certs / "tls.crt").write_text("cert", encoding="utf-8")
        (certs / "tls.key").write_text("key", encoding="utf-8")
        self.write_env(
            "PROJECTS_API_PORT=18000\nTRAEFIK_ENABLE_TLS=true\nTRAEFIK_TLS_MODE=file\n"
            "TRAEFIK_HTTPS_PORT=443\n"
        )
        output = self.renderer.render(self.env, self.projects, cert_dir=certs)
        self.assertIn("- websecure", output)
        self.assertIn('"http://supabase-nginx-', output)
        self.assertNotIn("- web\n      priority: 500", output)
        self.assertIn("/certs/traefik/tls.crt", output)
        self.assertIn("/certs/traefik/tls.key", output)
        self.assertIn("force-https:", output)
        self.assertIn("force-https-redirect:", output)
        self.assertIn("permanent: true", output)
        # Redirect precisa vencer o catch-all (100) e perder dos scanners.
        self.assertGreater(
            output.index("priority: 150"), 0,
            "router force-https deve declarar prioridade 150",
        )

    def test_acme_mode_with_placeholder_email_is_rejected(self) -> None:
        self.write_env(
            "PROJECTS_API_PORT=18000\nTRAEFIK_ENABLE_TLS=true\nTRAEFIK_TLS_MODE=acme\n"
            "TRAEFIK_ACME_EMAIL=pass\n"
        )
        with self.assertRaises(ValueError):
            self.renderer.render(self.env, self.projects)

    def test_acme_mode_with_valid_email_uses_resolver(self) -> None:
        self.write_env(
            "PROJECTS_API_PORT=18000\nTRAEFIK_ENABLE_TLS=true\nTRAEFIK_TLS_MODE=acme\n"
            "TRAEFIK_ACME_EMAIL=admin@example.com\n"
        )
        output = self.renderer.render(self.env, self.projects)
        self.assertIn("certResolver: letsencrypt", output)
        self.assertIn("force-https:", output)

    def test_server_proto_https_without_tls_fails_closed(self) -> None:
        self.write_env("PROJECTS_API_PORT=18000\nSERVER_PROTO=https\n")
        with self.assertRaises(ValueError):
            self.renderer.render(self.env, self.projects)

    def test_boolean_tls_variable_is_validated(self) -> None:
        self.write_env(
            "PROJECTS_API_PORT=18000\nTRAEFIK_ENABLE_TLS=sim\n"
        )
        with self.assertRaises(ValueError):
            self.renderer.render(self.env, self.projects)


class StaticConfigAndComposeContractTest(unittest.TestCase):
    def test_static_config_declares_websecure_and_inert_acme_resolver(self) -> None:
        static = (TRAEFIK_DIR / "traefik.yml").read_text(encoding="utf-8")
        self.assertIn("websecure:", static)
        self.assertIn('address: ":443"', static)
        self.assertIn("certificatesResolvers:", static)
        self.assertIn("letsencrypt:", static)
        self.assertIn("httpChallenge:", static)
        self.assertIn("entryPoint: web", static)

    def test_compose_publishes_https_and_mounts_certs_readonly(self) -> None:
        compose = (TRAEFIK_DIR / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertRegex(compose, r'"\$\{TRAEFIK_HTTPS_PORT:-443\}:443"')
        self.assertEqual(compose.count("./certs/traefik:/certs/traefik:ro"), 2)
        self.assertIn("--tls-cert-dir", compose)
        self.assertIn("/certs/traefik", compose)

    def test_edge_protection_routers_stay_on_plain_web(self) -> None:
        middlewares = (TRAEFIK_DIR / "middlewares.yml").read_text(encoding="utf-8")
        for router in ("malicious-paths:", "block-bad-useragents:", "leaked-files:"):
            with self.subTest(router=router):
                section = middlewares.split(router, 1)[1].split("    ", 1)[0]
                self.assertNotIn("websecure", section)

    def test_env_example_documents_the_tls_profile(self) -> None:
        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        for variable in (
            "TRAEFIK_ENABLE_TLS=false",
            "TRAEFIK_TLS_MODE=file",
            "TRAEFIK_ACME_EMAIL=pass",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, example)


if __name__ == "__main__":
    unittest.main()
