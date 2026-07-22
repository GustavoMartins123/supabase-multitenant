from __future__ import annotations

import importlib.util
import pathlib
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "servidor/traefik/render_dynamic_config.py"
spec = importlib.util.spec_from_file_location("render_dynamic_config", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class FileProviderRendererTests(unittest.TestCase):
    def test_cli_stages_middlewares_inside_the_dynamic_directory(self) -> None:
        root = ROOT / ".tmp-traefik-middleware-stage-test"
        root_env = root / "server.env"
        projects = root / "projects"
        middlewares = root / "middlewares.yml"
        output = root / "dynamic" / "routes.yml"
        projects.mkdir(parents=True, exist_ok=True)
        root_env.write_text(
            "NGINX_SHARED_TOKEN=test-token\nPROJECTS_API_PORT=18000\n",
            encoding="utf-8",
        )
        middlewares.write_text("http:\n  middlewares: {}\n", encoding="utf-8")
        try:
            arguments = [
                "render_dynamic_config.py",
                "--root-env",
                str(root_env),
                "--projects-dir",
                str(projects),
                "--middlewares-file",
                str(middlewares),
                "--output",
                str(output),
            ]
            with mock.patch("sys.argv", arguments):
                self.assertEqual(0, module.main())

            self.assertEqual(
                middlewares.read_text(encoding="utf-8"),
                (output.parent / "00-middlewares.yml").read_text(encoding="utf-8"),
            )
            self.assertTrue(output.is_file())
        finally:
            output.unlink(missing_ok=True)
            (output.parent / "00-middlewares.yml").unlink(missing_ok=True)
            output.parent.rmdir()
            middlewares.unlink(missing_ok=True)
            root_env.unlink(missing_ok=True)
            projects.rmdir()
            root.rmdir()

    def test_renderer_discovers_valid_projects_and_uses_uuid_scope(self) -> None:
        fixture_root = ROOT / ".tmp-traefik-render-test"
        projects = fixture_root / "projects"
        project = projects / "meu_projeto"
        project.mkdir(parents=True, exist_ok=True)
        root_env = fixture_root / "server.env"
        root_env.write_text(
            "NGINX_SHARED_TOKEN=test-token\n"
            "PROJECTS_API_PORT=18000\n"
            "PROJECTS_API_ALLOWED_IP_RANGES=127.0.0.1/32,172.50.0.0/16\n",
            encoding="utf-8",
        )
        (project / ".env").write_text(
            "PROJECT_ID=meu_projeto\n"
            "PROJECT_UUID=11111111-2222-3333-4444-555555555555\n",
            encoding="utf-8",
        )
        try:
            result = module.render(root_env, projects)
        finally:
            (project / ".env").unlink()
            project.rmdir()
            projects.rmdir()
            root_env.unlink()
            fixture_root.rmdir()

        self.assertIn("project-meu_projeto:", result)
        self.assertIn('scope: "11111111-2222-3333-4444-555555555555"', result)
        self.assertIn("http://supabase-nginx-meu_projeto:8080", result)
        self.assertIn("project-guard-meu_projeto", result)
        self.assertIn("project-strip-meu_projeto", result)
        self.assertIn("PathPrefix(`/api/projects`)", result)
        self.assertIn("PathPrefix(`/api/jobs`)", result)
        self.assertIn("PathPrefix(`/api/admin`)", result)
        self.assertIn("PathPrefix(`/api/internal/analytics`)", result)


if __name__ == "__main__":
    unittest.main()
