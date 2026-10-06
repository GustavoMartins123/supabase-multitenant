from __future__ import annotations

import pathlib
import subprocess
import unittest

from tests.smoke.common import bash_path, git_compatible_bash

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
VECTOR_LIBRARY = ROOT / "servidor/generateProject/lib/vector_lifecycle.sh"
STORAGE_LIBRARY = ROOT / "servidor/generateProject/lib/storage_multitenant.sh"
WRAPPER_SCRIPT = (
    ROOT / "servidor/generateProject/operations/setup_vector_bucket_wrapper.sh"
)


class StorageVectorWrapperContractTests(unittest.TestCase):
    def test_project_template_renders_sigv4_credentials(self) -> None:
        env = ENV_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("S3_PROTOCOL_ENABLED=true", env)
        self.assertIn(
            "S3_PROTOCOL_ACCESS_KEY_ID={{s3_protocol_access_key_id}}", env
        )
        self.assertIn(
            "S3_PROTOCOL_ACCESS_KEY_SECRET={{s3_protocol_access_key_secret}}", env
        )

    def test_lifecycle_generates_and_validates_per_project_sigv4_keys(self) -> None:
        library = VECTOR_LIBRARY.read_text(encoding="utf-8")
        storage = STORAGE_LIBRARY.read_text(encoding="utf-8")

        self.assertIn("storage_create_s3_credentials", storage)
        self.assertIn('POST "/s3/$tenant_id/credentials"', storage)
        self.assertIn("getS3CredentialsByAccessKey", (
            ROOT / "docs/architecture/storage-vectors-lifecycle.md"
        ).read_text(encoding="utf-8"))
        self.assertIn("^[0-9a-fA-F]{32}$", library)
        self.assertIn("^[0-9a-fA-F]{64}$", library)
        self.assertNotIn('echo "$S3_PROTOCOL_ACCESS_KEY_SECRET"', library)

    def test_wrapper_matches_the_studio_naming_and_extension_contract(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('print(f"{value}_fdw")', script)
        self.assertIn('print(f"{value}_fdw_server")', script)
        self.assertIn("Wrappers >= 0.5.7 obrigatorio", script)
        self.assertIn("s3_vectors_fdw_handler", script)
        self.assertIn("s3_vectors_fdw_validator", script)

    def test_wrapper_uses_vault_and_the_tenant_internal_endpoint(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS supabase_vault CASCADE", script)
        self.assertIn("vault.create_secret", script)
        self.assertIn("vault.update_secret", script)
        self.assertIn(
            'VECTOR_ENDPOINT="http://supabase-nginx-${PROJECT_ID}:8081/vector"',
            script,
        )
        self.assertIn("vault_access_key_id", script)
        self.assertIn("vault_secret_access_key", script)
        self.assertNotIn("host.docker.internal", script)

    def test_internal_vector_listener_only_accepts_sigv4_and_has_no_public_port(self) -> None:
        nginx = (ROOT / 'servidor/generateProject/nginxtemplate').read_text()
        internal = nginx.split('listen 8081;', 1)[1]
        self.assertIn('allow ${SUPABASE_NETWORK_SUBNET};', internal)
        self.assertIn('deny all;', internal)
        self.assertIn('if ($request_method != POST) { return 405; }', internal)
        self.assertIn('if ($http_authorization !~ "^AWS4-HMAC-SHA256 ") { return 403; }', internal)
        self.assertIn('proxy_set_header apikey "";', internal)
        self.assertIn('proxy_set_header X-Forwarded-Host "{{project_uuid}}.storage.internal";', internal)
        self.assertNotIn('ports:', (ROOT / 'servidor/generateProject/dockercomposetemplate').read_text())

    def test_probe_is_transactional_and_uses_only_the_canonical_import_protocol(self) -> None:
        script = WRAPPER_SCRIPT.read_text()
        probe = script.split('PROBE_SCHEMA="vector_wrapper_probe_', 1)[1]
        self.assertIn('BEGIN;', probe)
        self.assertIn('COMMIT;', probe)
        self.assertIn('IMPORT FOREIGN SCHEMA :"probe_bucket"', probe)
        self.assertNotIn('OPTIONS (bucket_name', probe)

    def test_wrapper_validates_real_bucket_and_import_foreign_schema(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        library = STORAGE_LIBRARY.read_text(encoding="utf-8")
        self.assertIn('storage_vector_request "$tenant_id" "$service_key" GetVectorBucket', library)
        self.assertIn('`http://127.0.0.1:5000/vector/${operation}`', library)
        self.assertIn("IMPORT FOREIGN SCHEMA", script)
        self.assertIn("OPTIONS (strict 'true')", script)
        self.assertNotIn("enable_vector_storage.sh", script)
        self.assertNotIn('indexes = {}', script)
        self.assertNotIn('vectorBuckets = {}', script)

    def test_shell_syntax(self) -> None:
        for script in (VECTOR_LIBRARY, WRAPPER_SCRIPT):
            subprocess.run(
                [git_compatible_bash(), "-n", bash_path(script)], check=True
            )

    def test_invalid_identity_fails_even_in_a_conditional_shell_call(self) -> None:
        prefix = f'source "{bash_path(VECTOR_LIBRARY)}"; '
        valid = {
            'S3_PROTOCOL_CREDENTIAL_ID': 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',
            'S3_PROTOCOL_ACCESS_KEY_ID': 'a' * 32,
            'S3_PROTOCOL_ACCESS_KEY_SECRET': 'b' * 64,
        }
        for field in valid:
            assignments = '; '.join(f'{key}="{value if key != field else "invalid"}"'
                                    for key, value in valid.items())
            result = subprocess.run([git_compatible_bash(), '-c', prefix + assignments +
                                     '; if vector_validate_s3_credentials; then exit 7; fi'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(field, result.stderr)
        result = subprocess.run([git_compatible_bash(), '-c', prefix +
                                 'POSTGRES_USER=""; if vector_validate_database nonexistent; then exit 7; fi'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('POSTGRES_USER ausente', result.stderr)


if __name__ == "__main__":
    unittest.main()
