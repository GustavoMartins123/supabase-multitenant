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
        self.assertIn(
            "PLATFORM_APP_DB_PASSWORD=$(env_secret servidor/.env PLATFORM_APP_DB_PASSWORD generate_key_authorizer_password)",
            setup,
        )
        self.assertIn(
            "META_ADMIN_DB_PASSWORD=$(env_secret servidor/.env META_ADMIN_DB_PASSWORD generate_key_authorizer_password)",
            setup,
        )


if __name__ == "__main__":
    unittest.main()


class RolePasswordApplicationContract(unittest.TestCase):
    """Regressao: ALTER ROLE ... PASSWORD via conn.execute(SELECT ...) e no-op.

    O SELECT format() apenas retorna a string; sem fetchval + execute o papel
    nasce sem senha e a API morre com InvalidPasswordError no startup.
    """

    ROLES = (
        "key_authorizer",
        "host_agent_rw",
        "platform_app",
        "platform_meta_admin",
    )

    def test_every_role_password_goes_through_fetchval_then_execute(self) -> None:
        source = (APP / "control_plane_roles.py").read_text()
        for role in self.ROLES:
            with self.subTest(role=role):
                block_match = source.find(f"ALTER ROLE {role} PASSWORD %L")
                self.assertGreaterEqual(block_match, 0, f"{role}: statement ausente")
                context = source[max(0, block_match - 160):block_match]
                self.assertIn("conn.fetchval(", context)
                # E o resultado do fetchval precisa ser executado logo depois.
                tail = source[block_match:block_match + 400]
                self.assertIn("await conn.execute(password_statement)", tail)

    def test_no_bare_execute_of_password_format_select(self) -> None:
        import re

        source = (APP / "control_plane_roles.py").read_text()
        offenders = re.findall(
            r"await conn\.execute\(\s*\"SELECT format\('ALTER ROLE (\w+) PASSWORD",
            source,
        )
        self.assertEqual(offenders, [])


class RoleConnectPrivilegeContract(unittest.TestCase):
    """O database do control plane nao tem CONNECT para PUBLIC (hardening):
    cada identidade que conecta nele precisa do GRANT CONNECT explicito,
    no mesmo padrao fetchval+execute do key_authorizer."""

    ROLES = ("key_authorizer", "host_agent_rw", "platform_app", "platform_meta_admin")

    def test_every_role_receives_explicit_connect_grant(self) -> None:
        source = (APP / "control_plane_roles.py").read_text()
        for role in self.ROLES:
            with self.subTest(role=role):
                self.assertIn(f"GRANT CONNECT ON DATABASE %I TO {role}", source)
                block = source[source.find(f"'GRANT CONNECT ON DATABASE %I TO {role}'") - 200:]
                self.assertIn("conn.fetchval(", block[:220])
                self.assertIn("await conn.execute(grant_connect)", block[:400])


class PrivilegedStatementRoutingContract(unittest.TestCase):
    """SQL fora do alcance de platform_app precisa ir pela conexao admin.

    `platform_app` so tem DML nas tabelas do schema `public`. Metadata de
    Realtime/Supavisor, `pg_terminate_backend` em backends de outros papeis,
    slots de replicacao e `DROP DATABASE` exigem `platform_meta_admin`.
    """

    PRIVILEGED_MARKERS = (
        "_realtime.",
        "_supavisor.",
        "pg_terminate_backend",
        "pg_drop_replication_slot",
        "pg_replication_slots",
        "DROP DATABASE",
    )

    def _connection_blocks(self, source: str) -> list[tuple[str, str]]:
        """Fatia o modulo em blocos `async with`, delimitados por indentacao."""
        openers = {
            "async with pool.acquire()": "pool",
            "async with global_admin_connection()": "admin",
        }
        lines = source.splitlines()
        blocks: list[tuple[str, str]] = []
        for index, line in enumerate(lines):
            stripped = line.strip()
            kind = next(
                (k for prefix, k in openers.items() if stripped.startswith(prefix)),
                None,
            )
            if kind is None:
                continue
            indent = len(line) - len(line.lstrip())
            body: list[str] = []
            for following in lines[index + 1 :]:
                if not following.strip():
                    body.append(following)
                    continue
                if len(following) - len(following.lstrip()) <= indent:
                    break
                body.append(following)
            blocks.append((kind, "\n".join(body)))
        return blocks

    def test_admin_connection_uses_the_meta_admin_dsn(self) -> None:
        deletion = (APP / "project_deletion.py").read_text()
        self.assertIn("async def global_admin_connection()", deletion)
        helper = deletion.split("async def global_admin_connection()", 1)[1]
        helper = helper.split("\nclass ", 1)[0].split("\ndef ", 1)[0]
        self.assertIn('os.getenv("META_ADMIN_DSN")', helper)
        self.assertNotIn("DB_DSN", helper)
        self.assertIn("global_admin_connection,", (APP / "main.py").read_text())

    def test_no_privileged_statement_runs_on_the_platform_app_pool(self) -> None:
        main = (APP / "main.py").read_text()
        blocks = self._connection_blocks(main)
        self.assertTrue(
            any(kind == "admin" for kind, _ in blocks),
            "o fluxo de exclusao precisa abrir a conexao administrativa",
        )
        for kind, body in blocks:
            if kind != "pool":
                continue
            for marker in self.PRIVILEGED_MARKERS:
                self.assertNotIn(
                    marker,
                    body,
                    f"{marker} exige platform_meta_admin, nao o pool da API",
                )

    def test_deletion_helpers_receive_an_admin_connection(self) -> None:
        main = (APP / "main.py").read_text()
        for helper in ("drain_database_connections", "drop_database_force"):
            with self.subTest(helper=helper):
                call = f"await {helper}(conn"
                self.assertIn(call, main)
                before = main.split(call, 1)[0]
                self.assertIn(
                    "async with global_admin_connection() as conn:",
                    before.rsplit("async with ", 1)[0]
                    + "async with "
                    + before.rsplit("async with ", 1)[1],
                )
