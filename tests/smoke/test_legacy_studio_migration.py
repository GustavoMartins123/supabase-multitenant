import base64
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "migrate_legacy_studio.py"
SPEC = importlib.util.spec_from_file_location("migrate_legacy_studio", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)

RUNTIME_PATH = ROOT / "tools" / "configure_studio_runtime.py"
RUNTIME_SPEC = importlib.util.spec_from_file_location(
    "configure_studio_runtime", RUNTIME_PATH
)
assert RUNTIME_SPEC is not None and RUNTIME_SPEC.loader is not None
RUNTIME = importlib.util.module_from_spec(RUNTIME_SPEC)
sys.modules[RUNTIME_SPEC.name] = RUNTIME
RUNTIME_SPEC.loader.exec_module(RUNTIME)


class LegacyStudioMigrationTest(unittest.TestCase):
    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_env_migration_preserves_configuration_without_sourcing_shell(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "must-not-exist"
            legacy = root / "legacy.env"
            self.write(
                legacy,
                "\n".join(
                    (
                        "BACKEND_PROTO=http",
                        "SERVER_DOMAIN=10.20.30.40",
                        "NGINX_SHARED_TOKEN=legacy-shared-token",
                        "POSTGRES_USER=nginx_user",
                        "POSTGRES_NGINX_PASSWORD=legacy-db-password",
                        "POSTGRES_DB=nginx",
                        "DATABASE_URL=postgresql://legacy-value",
                        "OPENAI_API_KEY=$(touch %s)" % marker,
                        "FERNET_SECRET=legacy-fernet-must-not-migrate",
                        "PUSH_WORKER_TOKEN=legacy-push-must-not-migrate",
                        "",
                    )
                ),
            )

            result = MIGRATION.build_env_migration(
                legacy,
                studio_origin="https://127.0.0.1:9091",
            )

            self.assertFalse(marker.exists())
            self.assertIn("SERVER_DOMAIN=http://10.20.30.40", result.main_text)
            self.assertIn("OPENAI_API_KEY=$(touch", result.main_text)
            self.assertNotIn("legacy-fernet-must-not-migrate", result.main_text)
            self.assertNotIn("legacy-push-must-not-migrate", result.main_text)
            self.assertEqual(result.unresolved, ())
            self.assertEqual(
                set(result.deprecated), {"FERNET_SECRET", "PUSH_WORKER_TOKEN"}
            )

    def test_new_shared_secrets_are_generated_in_expected_formats(self):
        with tempfile.TemporaryDirectory() as temporary:
            legacy = Path(temporary) / "legacy.env"
            self.write(
                legacy,
                "\n".join(
                    (
                        "BACKEND_PROTO=http",
                        "SERVER_DOMAIN=http://server.internal",
                        "NGINX_SHARED_TOKEN=pass",
                        "POSTGRES_NGINX_PASSWORD=database-password",
                        "DATABASE_URL=postgresql://database-url",
                        "",
                    )
                ),
            )

            result = MIGRATION.build_env_migration(
                legacy,
                studio_origin="https://studio.internal:9091",
            )
            values = MIGRATION.EnvDocument(
                tuple(result.main_text.splitlines(keepends=True)),
                {},
            )
            parsed = {}
            for line in values.lines:
                match = MIGRATION.ASSIGNMENT.match(line.rstrip("\r\n"))
                if match:
                    parsed[match.group(1)] = match.group(2)

            decoded = base64.urlsafe_b64decode(
                parsed["STUDIO_SERVICE_KEY_ENCRYPTION_KEY"].encode("ascii")
            )
            self.assertEqual(len(decoded), 32)
            self.assertRegex(parsed["NGINX_HMAC_SECRET"], r"^[0-9a-f]{64}$")
            self.assertRegex(parsed["INTERNAL_HMAC_SECRET"], r"^[0-9a-f]{64}$")
            self.assertNotEqual(parsed["NGINX_SHARED_TOKEN"], "pass")
            self.assertIn("LOGFLARE_PRIVATE_ACCESS_TOKEN", result.generated)

    def test_blank_legacy_database_credentials_remain_an_explicit_pending_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            legacy = Path(temporary) / "legacy.env"
            self.write(
                legacy,
                "\n".join(
                    (
                        "BACKEND_PROTO=http",
                        "SERVER_DOMAIN=http://server.internal",
                        "POSTGRES_NGINX_PASSWORD=",
                        "DATABASE_URL=",
                        "",
                    )
                ),
            )

            result = MIGRATION.build_env_migration(
                legacy,
                studio_origin="https://studio.internal:9091",
            )
            self.assertIn("POSTGRES_NGINX_PASSWORD", result.unresolved)
            self.assertIn("DATABASE_URL", result.unresolved)
            self.assertIn("POSTGRES_NGINX_PASSWORD=\n", result.main_text)

    def test_atomic_write_refuses_to_replace_an_existing_env_by_default(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / ".env"
            target.write_text("KEEP=me\n", encoding="utf-8")
            with self.assertRaises(MIGRATION.MigrationError):
                MIGRATION.atomic_write(target, "REPLACE=yes\n", force=False)
            self.assertEqual(target.read_text(encoding="utf-8"), "KEEP=me\n")

    def test_setup_no_longer_generates_the_removed_cookie_secret(self):
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertNotIn("COOKIE_SIGN_SECRET", setup)
        self.assertNotIn("generate_cookie_sign_secret", setup)

    def test_authelia_secrets_are_file_backed_and_not_in_tracked_yaml(self):
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        template = (
            ROOT / "studio/authelia/configuration.yml.template"
        ).read_text(encoding="utf-8")
        ignore = (ROOT / "studio/.gitignore").read_text(encoding="utf-8")

        for key in {
            "AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE",
            "AUTHELIA_SESSION_SECRET_FILE",
            "AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE",
        }:
            self.assertIn(key, compose)
        self.assertNotRegex(template, r"(?m)^\s+jwt_secret:")
        self.assertNotRegex(template, r"(?m)^\s+secret:")
        self.assertNotRegex(template, r"(?m)^\s+encryption_key:")
        self.assertIn("authelia/configuration.runtime.yml", ignore)
        self.assertIn("secrets/", ignore)

    def test_runtime_renderer_uses_the_selected_https_origin(self):
        template = (
            ROOT / "studio/authelia/configuration.yml.template"
        ).read_text(encoding="utf-8")
        origin, host = RUNTIME.parse_origin("https://10.0.0.196:9091")
        rendered = RUNTIME.render_configuration(
            template, origin=origin, host=host
        )
        self.assertNotIn("__STUDIO_", rendered)
        self.assertIn("domain: 10.0.0.196", rendered)
        self.assertIn("https://10.0.0.196:9091/auth", rendered)
        self.assertIn("IP:10.0.0.196", RUNTIME.certificate_sans(host))

    def test_studio_build_context_excludes_local_secrets_and_state(self):
        dockerignore = (ROOT / "studio/.dockerignore").read_text(encoding="utf-8")
        for path in {
            ".env",
            ".analytics.env",
            "authelia/",
            "secrets/",
            "snippets/",
            "postgres/data/",
        }:
            self.assertIn(path, dockerignore)

        dockerfile = (ROOT / "studio/Dockerfile").read_text(encoding="utf-8")
        self.assertIn(
            "COPY nginx/nginx.conf /usr/local/openresty/nginx/conf/nginx.conf",
            dockerfile,
        )
        self.assertNotIn("COPY nginx/nginx.conf /etc/nginx/nginx.conf", dockerfile)

    def test_authelia_admin_cli_uses_runtime_config_and_legacy_wrapper_is_safe(self):
        identifiers = (
            ROOT / "studio/nginx/lua/admin_api/authelia_identifiers.lua"
        ).read_text(encoding="utf-8")
        wrapper = (ROOT / "authelia.sh").read_text(encoding="utf-8")

        self.assertIn('/config/configuration.runtime.yml', identifiers)
        self.assertNotIn('/config/configuration.yml"', identifiers)
        self.assertIn("tools/configure_studio_runtime.py", wrapper)
        self.assertNotIn("rm -rf", wrapper)

    def test_only_public_studio_certificate_is_synchronized_to_server(self):
        sync_tool = (ROOT / "tools/sync_studio_ca.py").read_text(encoding="utf-8")
        server_ignore = (ROOT / "servidor/certs/.gitignore").read_text(
            encoding="utf-8"
        )
        self.assertIn('studio" / "authelia" / "ssl" / "ca.pem"', sync_tool)
        self.assertNotIn('ca.key', sync_tool)
        self.assertIn("*", server_ignore)


if __name__ == "__main__":
    unittest.main()
