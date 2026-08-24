"""Contrato da separacao de DSN da Projects API (REVISAO_ARQUITETURAL #1).

A API roda como platform_app (DML no control plane), fala com o Postgres-Meta
por platform_meta_admin e le telemetria por platform_reader. O superuser
global nao existe no ambiente da API.
"""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal" / "app"
COMPOSE = ROOT / "servidor" / "docker-compose-api.yml"


class ApiDsnSeparationContract(unittest.TestCase):
    def test_roles_provision_app_and_meta_admin(self) -> None:
        roles = (APP / "control_plane_roles.py").read_text()
        self.assertIn("CREATE ROLE platform_app WITH", roles)
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE, DELETE\n                    ON ALL TABLES IN SCHEMA public TO platform_app;",
            roles,
        )
        self.assertIn("CONNECTION LIMIT 100", roles)
        self.assertIn("GRANT supabase_admin TO platform_meta_admin;", roles)
        self.assertIn("CONNECTION LIMIT 20", roles)

    def test_api_pool_runs_as_platform_app(self) -> None:
        compose = COMPOSE.read_text()
        self.assertIn(
            "DB_DSN: postgres://platform_app:${PLATFORM_APP_DB_PASSWORD:?defina PLATFORM_APP_DB_PASSWORD}@",
            compose,
        )
        # O superuser nao chega mais ao container da API: nenhuma
        # interpolacao de POSTGRES_PASSWORD no bloco projects-api.
        api_block = compose.split("  projects-api:", 1)[1].split("\n  ", 2)[0]
        self.assertNotIn("POSTGRES_PASSWORD", api_block)

    def test_meta_uses_dedicated_admin_identity(self) -> None:
        main = (APP / "main.py").read_text()
        self.assertIn('meta_dsn = (os.getenv("META_ADMIN_DSN") or "").strip()', main)
        self.assertIn("META_ADMIN_DSN ausente", main)
        compose = COMPOSE.read_text()
        self.assertIn(
            "META_ADMIN_DSN: postgres://platform_meta_admin:${META_ADMIN_DB_PASSWORD:?defina META_ADMIN_DB_PASSWORD}@",
            compose,
        )

    def test_migrations_provision_and_require_both_passwords(self) -> None:
        source = (APP / "schema_migrations.py").read_text()
        for var in ("PLATFORM_APP_DB_PASSWORD", "META_ADMIN_DB_PASSWORD"):
            with self.subTest(var=var):
                self.assertIn(f'os.getenv("{var}")', source)
                self.assertIn(f"{var} e obrigatorio", source)

    def test_env_example_documents_both_identities(self) -> None:
        example = (ROOT / "servidor" / ".env.example").read_text()
        self.assertRegex(example, r"(?m)^PLATFORM_APP_DB_PASSWORD=pass$")
        self.assertRegex(example, r"(?m)^META_ADMIN_DB_PASSWORD=pass$")

    def test_setup_generates_both_passwords(self) -> None:
        setup = (ROOT / "setup.sh").read_text()
        self.assertIn("PLATFORM_APP_DB_PASSWORD=$(generate_key_authorizer_password)", setup)
        self.assertIn("META_ADMIN_DB_PASSWORD=$(generate_key_authorizer_password)", setup)


if __name__ == "__main__":
    unittest.main()
