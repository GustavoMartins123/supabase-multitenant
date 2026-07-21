import base64
import importlib.util
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "migrate_legacy_server.py"
SPEC = importlib.util.spec_from_file_location("migrate_legacy_server", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)


class LegacyServerMigrationTest(unittest.TestCase):
    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def parsed(self, text: str) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in text.splitlines():
            match = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", line)
            if match:
                values[match.group(1)] = match.group(2)
        return values

    def fixture(self, root: Path) -> tuple[Path, Path, Path, Path]:
        legacy = root / "legacy"
        marker = root / "must-not-exist"
        fernet = base64.urlsafe_b64encode(b"l" * 32).decode("ascii")
        self.write(
            legacy / ".env",
            "\n".join(
                (
                    "POSTGRES_HOST=172.20.200.10",
                    "POSTGRES_POOLER=172.20.200.11",
                    "POSTGRES_PORT=6755",
                    "POSTGRES_DB=postgres",
                    "POSTGRES_USER=supabase_admin",
                    "POSTGRES_PASSWORD=legacy-postgres-password",
                    "DB_ENC_KEY=legacy-db-enc",
                    "VAULT_ENC_KEY=legacy-vault-enc",
                    "SECRET_KEY_BASE=legacy-secret-key-base",
                    "JWT_SECRET=legacy-global-jwt-secret",
                    "SERVER_URL=10.0.0.25",
                    "SERVER_PROTO=http",
                    'HOST_PROJECT_ROOT="/legacy/root"',
                    "PROJECT_DELETE_PASSWORD=legacy-delete-password",
                    "DASHBOARD_USER=legacy-dashboard-user",
                    "DASHBOARD_PASSWORD=legacy-dashboard-password",
                    f"FERNET_SECRET={fernet}",
                    "LOGFLARE_API_KEY=legacy-logflare-public-token-value",
                    "PUSH_WORKER_TOKEN=obsolete-push-token",
                    "PGRST_DB_SCHEMAS=public,storage",
                    f"SMTP_PASS=$(touch {marker})",
                    "",
                )
            ),
        )
        self.write(
            legacy / "docker-compose.yml",
            """networks:
  rede-supabase:
    ipam:
      config:
        - subnet: 172.20.0.0/16
          ip_range: 172.20.0.0/18
          gateway: 172.20.0.1
""",
        )

        studio_env = root / "studio.env"
        studio_fernet = base64.urlsafe_b64encode(b"s" * 32).decode("ascii")
        self.write(
            studio_env,
            "\n".join(
                (
                    f"STUDIO_SERVICE_KEY_ENCRYPTION_KEY={studio_fernet}",
                    "NGINX_SHARED_TOKEN=studio-shared-token-value",
                    "NGINX_HMAC_SECRET=" + "a" * 64,
                    "INTERNAL_HMAC_SECRET=" + "b" * 64,
                    "SUPABASE_PUBLIC_URL=https://10.0.0.196:9091",
                    "",
                )
            ),
        )
        studio_analytics = root / "studio.analytics.env"
        self.write(
            studio_analytics,
            "LOGFLARE_PRIVATE_ACCESS_TOKEN=studio-private-token-value-0123456789\n",
        )
        host_root = root / "destination"
        host_root.mkdir()
        return legacy, studio_env, studio_analytics, host_root

    def test_migration_preserves_compatibility_keys_and_never_sources_env(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, studio_env, studio_analytics, host_root = self.fixture(root)

            result = MIGRATION.build_server_migration(
                legacy,
                studio_env=studio_env,
                studio_analytics_env=studio_analytics,
                host_project_root=host_root,
            )
            main = self.parsed(result.main_text)
            analytics = self.parsed(result.analytics_text)

            self.assertFalse((root / "must-not-exist").exists())
            self.assertEqual(main["POSTGRES_PASSWORD"], "legacy-postgres-password")
            self.assertEqual(main["JWT_SECRET"], "legacy-global-jwt-secret")
            self.assertEqual(main["SUPABASE_NETWORK_SUBNET"], "172.20.0.0/16")
            self.assertEqual(main["SUPABASE_NETWORK_IP_RANGE"], "172.20.0.0/18")
            self.assertEqual(main["SUPABASE_NETWORK_GATEWAY"], "172.20.0.1")
            self.assertEqual(main["VECTOR_FLUENTD_BIND"], "0.0.0.0")
            self.assertEqual(
                main["PROJECTS_API_ALLOWED_IP_RANGES"],
                "10.0.0.196/32,172.20.0.0/16",
            )
            self.assertEqual(
                main["PUSH_API_URL"],
                "https://10.0.0.196:9091/api/internal/push",
            )
            self.assertIn(str(host_root), main["HOST_PROJECT_ROOT"])
            self.assertNotIn("FERNET_SECRET=", result.main_text)
            self.assertIn("LEGACY_FERNET_SECRET=", result.legacy_secret_text)
            self.assertTrue(result.legacy_secret_ready)
            self.assertEqual(result.unresolved, ())
            self.assertEqual(
                analytics["LOGFLARE_PUBLIC_ACCESS_TOKEN"],
                "legacy-logflare-public-token-value",
            )
            self.assertEqual(
                analytics["LOGFLARE_PRIVATE_ACCESS_TOKEN"],
                "studio-private-token-value-0123456789",
            )

    def test_shared_keys_are_copied_from_studio_and_new_keys_have_valid_formats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, studio_env, studio_analytics, host_root = self.fixture(root)
            result = MIGRATION.build_server_migration(
                legacy,
                studio_env=studio_env,
                studio_analytics_env=studio_analytics,
                host_project_root=host_root,
            )
            main = self.parsed(result.main_text)
            studio = MIGRATION.EnvDocument.read(studio_env).values

            for key in MIGRATION.SHARED_MAIN_KEYS:
                self.assertEqual(main[key], studio[key])
            self.assertTrue(MIGRATION.is_fernet_key(main["PROJECT_SECRETS_MASTER_KEY"]))
            self.assertRegex(main["HOST_AGENT_HMAC_SECRET"], r"^[0-9a-f]{64}$")
            self.assertRegex(main["PG_META_CRYPTO_KEY"], r"^[0-9a-f]{64}$")
            self.assertEqual(main["FUNCTIONS_SUPABASE_ANON_KEY"].count("."), 2)
            self.assertEqual(
                main["FUNCTIONS_SUPABASE_SERVICE_ROLE_KEY"].count("."), 2
            )

    def test_network_mismatch_is_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, studio_env, studio_analytics, host_root = self.fixture(root)
            env_path = legacy / ".env"
            env_path.write_text(
                env_path.read_text(encoding="utf-8").replace(
                    "POSTGRES_HOST=172.20.200.10",
                    "POSTGRES_HOST=172.50.200.10",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(MIGRATION.MigrationError):
                MIGRATION.build_server_migration(
                    legacy,
                    studio_env=studio_env,
                    studio_analytics_env=studio_analytics,
                    host_project_root=host_root,
                )

    def test_secret_targets_are_ignored_and_setup_uses_restricted_modes(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("servidor/.env", ignore)
        self.assertIn("servidor/.analytics.env", ignore)
        self.assertIn("servidor/.legacy-migration.env", ignore)
        self.assertIn(
            "chmod 600 servidor/.env servidor/.analytics.env "
            "studio/.env studio/.analytics.env",
            setup,
        )

    def test_database_preflight_is_explicitly_read_only(self):
        sql = (TOOLS / "sql/preflight_legacy_server.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("BEGIN TRANSACTION READ ONLY", sql)
        self.assertNotRegex(
            sql,
            r"(?im)^\s*(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE)\b",
        )

    def test_server_build_contexts_exclude_secrets_projects_and_database_data(self):
        server_ignore = (ROOT / "servidor/.dockerignore").read_text(
            encoding="utf-8"
        )
        database_ignore = (ROOT / "servidor/volumes/db/.dockerignore").read_text(
            encoding="utf-8"
        )
        for path in {
            ".env",
            ".analytics.env",
            ".legacy-migration.env",
            "projects/",
            "certs/",
            "volumes/db/data/",
        }:
            self.assertIn(path, server_ignore)
        self.assertIn("data/", database_ignore)
        self.assertIn("wal_archives/", database_ignore)


if __name__ == "__main__":
    unittest.main()
