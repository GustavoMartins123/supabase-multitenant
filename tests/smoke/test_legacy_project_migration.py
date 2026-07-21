import base64
import hashlib
import hmac
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
MODULE_PATH = TOOLS / "migrate_legacy_project.py"
SPEC = importlib.util.spec_from_file_location("migrate_legacy_project", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MIGRATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MIGRATION
SPEC.loader.exec_module(MIGRATION)


class LegacyProjectMigrationTest(unittest.TestCase):
    def b64url(self, value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    def token(self, secret: str, role: str, issuer: str) -> str:
        header = self.b64url(b'{"alg":"HS256","typ":"JWT"}')
        payload = self.b64url(
            json.dumps(
                {"role": role, "iss": issuer, "iat": 1, "exp": 4_000_000_000},
                separators=(",", ":"),
            ).encode("utf-8")
        )
        signature = self.b64url(
            hmac.new(
                secret.encode("utf-8"),
                f"{header}.{payload}".encode("ascii"),
                hashlib.sha256,
            ).digest()
        )
        return f"{header}.{payload}.{signature}"

    def write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def fixture(self, root: Path) -> tuple[Path, Path, Path]:
        project_id = "alpha_project"
        project_uuid = "2ed6509f-b033-4e64-81da-218b93b713e7"
        secret = "project-jwt-secret-value"
        legacy = root / project_id
        self.write(
            legacy / ".env",
            "\n".join(
                (
                    f"PROJECT_ID={project_id}",
                    f"PROJECT_UUID={project_uuid}",
                    "POSTGRES_DATABASE=_supabase_alpha_project",
                    f"ANON_KEY_PROJETO={self.token(secret, 'anon', project_uuid)}",
                    f"SERVICE_ROLE_KEY_PROJETO={self.token(secret, 'service_role', project_uuid)}",
                    "CONFIG_TOKEN_PROJETO=" + "c" * 64,
                    f"JWT_SECRET_PROJETO={secret}",
                    "PGRST_DB_SCHEMAS=public,storage",
                    "PGRST_DB_MAX_ROWS=9876",
                    "ENABLE_EMAIL_AUTOCONFIRM=false",
                    "FILE_SIZE_LIMIT=123456",
                    "LOGFLARE_API_KEY=obsolete-project-log-key",
                    "",
                )
            ),
        )
        self.write(legacy / "storage" / "must-not-copy.txt", "data")
        server_env = root / "server.env"
        self.write(
            server_env,
            "\n".join(
                (
                    "SERVER_URL=10.0.0.25",
                    "SERVER_PROTO=http",
                    f'HOST_PROJECT_ROOT="{root / "destination-root"}"',
                    "",
                )
            ),
        )
        projects_root = root / "projects"
        return legacy, server_env, projects_root

    def parsed(self, text: str) -> dict[str, str]:
        return dict(re.findall(r"(?m)^([A-Z][A-Z0-9_]*)=(.*)$", text))

    def test_current_templates_are_rendered_while_legacy_keys_are_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, server_env, projects_root = self.fixture(root)
            result = MIGRATION.build_project_migration(
                legacy, server_env=server_env, projects_root=projects_root
            )
            env = self.parsed(result.files[".env"])

            legacy_env = MIGRATION.EnvDocument.read(legacy / ".env").values
            for key in {
                "PROJECT_UUID",
                "ANON_KEY_PROJETO",
                "SERVICE_ROLE_KEY_PROJETO",
                "CONFIG_TOKEN_PROJETO",
                "JWT_SECRET_PROJETO",
                "PGRST_DB_SCHEMAS",
                "PGRST_DB_MAX_ROWS",
                "ENABLE_EMAIL_AUTOCONFIRM",
                "FILE_SIZE_LIMIT",
            }:
                self.assertEqual(env[key], legacy_env[key])
            self.assertEqual(env["AUTH_IMAGE"], "supabase/gotrue:v2.193.0-rc.3")
            self.assertEqual(env["POSTGREST_IMAGE"], "postgrest/postgrest:v14.14")
            self.assertEqual(env["STORAGE_IMAGE"], "supabase/storage-api:v1.61.12")
            self.assertEqual(env["IMGPROXY_IMAGE"], "darthsim/imgproxy:v4.0.11")
            self.assertNotIn("LOGFLARE_API_KEY", result.files[".env"])
            self.assertIn("LOGFLARE_API_KEY", result.obsolete)
            self.assertRegex(env["S3_PROTOCOL_ACCESS_KEY_ID"], r"^[0-9a-f]{32}$")
            self.assertRegex(env["S3_PROTOCOL_ACCESS_KEY_SECRET"], r"^[0-9a-f]{64}$")
            self.assertTrue(all(a.issuer_matches_project_uuid for a in result.token_audits))
            nginx = result.files["nginx/nginx_alpha_project.conf"]
            self.assertNotIn(legacy_env["ANON_KEY_PROJETO"], nginx)
            self.assertNotIn(legacy_env["SERVICE_ROLE_KEY_PROJETO"], nginx)
            self.assertNotIn(legacy_env["CONFIG_TOKEN_PROJETO"], nginx)
            self.assertIn("${ANON_KEY_PROJETO}", nginx)
            self.assertIn(".dockerignore", result.files)
            for content in result.files.values():
                self.assertNotRegex(content, r"\{\{[^}]+\}\}")

    def test_invalid_legacy_jwt_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, server_env, projects_root = self.fixture(root)
            env_path = legacy / ".env"
            env_path.write_text(
                env_path.read_text(encoding="utf-8").replace(
                    "JWT_SECRET_PROJETO=project-jwt-secret-value",
                    "JWT_SECRET_PROJETO=wrong-secret",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(MIGRATION.MigrationError):
                MIGRATION.build_project_migration(
                    legacy, server_env=server_env, projects_root=projects_root
                )

    def test_write_is_atomic_restricted_and_does_not_copy_project_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy, server_env, projects_root = self.fixture(root)
            result = MIGRATION.build_project_migration(
                legacy, server_env=server_env, projects_root=projects_root
            )
            MIGRATION.write_project(result)

            self.assertEqual((result.target / ".env").stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                (result.target / "nginx/nginx_alpha_project.conf").stat().st_mode
                & 0o777,
                0o644,
            )
            self.assertTrue((result.target / "storage/stub/stub").is_dir())
            self.assertFalse((result.target / "storage/must-not-copy.txt").exists())
            with self.assertRaises(MIGRATION.MigrationError):
                MIGRATION.write_project(result)

            legacy_marker = result.target / "storage" / "keep-me.txt"
            legacy_marker.write_text("keep", encoding="utf-8")
            refreshed = MIGRATION.build_project_migration(
                legacy, server_env=server_env, projects_root=projects_root
            )
            MIGRATION.write_project(refreshed, refresh_config=True)
            self.assertEqual(legacy_marker.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
