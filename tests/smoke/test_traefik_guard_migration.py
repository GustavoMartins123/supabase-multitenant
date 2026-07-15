from __future__ import annotations

import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "servidor/traefik/render_dynamic_config.py"
spec = importlib.util.spec_from_file_location("render_dynamic_config", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class FileProviderRendererTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
