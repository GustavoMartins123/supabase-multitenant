from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "servidor/traefik/migrate_project_guard.py"
spec = importlib.util.spec_from_file_location("migrate_project_guard", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class MigrationTests(unittest.TestCase):
    def test_migration_is_idempotent_and_uses_project_uuid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            projects = Path(tmp) / "projects"
            project = projects / "meu_projeto"
            project.mkdir(parents=True)
            (project / ".env").write_text(
                "PROJECT_ID=meu_projeto\nPROJECT_UUID=11111111-2222-3333-4444-555555555555\n",
                encoding="utf-8",
            )
            compose = project / "docker-compose.yml"
            compose.write_text(
                """services:
  nginx:
    labels:
      - "traefik.http.middlewares.nginx-meu_projeto-stripprefix.stripprefix.prefixes=/meu_projeto"
      - "traefik.http.routers.supabase-nginx-meu_projeto.middlewares=rate-limit@file,security-headers@file,nginx-meu_projeto-stripprefix@docker"
""",
                encoding="utf-8",
            )

            changed = module.migrate_projects(projects, apply=True)
            self.assertEqual([compose], changed)
            result = compose.read_text(encoding="utf-8")
            self.assertIn("scope=11111111-2222-3333-4444-555555555555", result)
            self.assertIn(
                "middlewares=rate-limit@file,supabase-guard-meu_projeto@docker,security-headers@file,nginx-meu_projeto-stripprefix@docker",
                result,
            )
            self.assertTrue(compose.with_suffix(".yml.before-supabaseguard").exists())
            self.assertEqual([], module.migrate_projects(projects, apply=True))


if __name__ == "__main__":
    unittest.main()
