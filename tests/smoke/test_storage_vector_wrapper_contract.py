from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
VECTOR_LIBRARY = ROOT / "servidor/generateProject/lib/vector_lifecycle.sh"
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

        self.assertIn("openssl rand -hex 16", library)
        self.assertIn("openssl rand -hex 32", library)
        self.assertIn("^[0-9a-fA-F]{32}$", library)
        self.assertIn("^[0-9a-fA-F]{64}$", library)
        self.assertNotIn('echo "$S3_PROTOCOL_ACCESS_KEY_SECRET"', library)

    def test_wrapper_matches_the_studio_naming_and_extension_contract(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('print(f"{value}_fdw")', script)
        self.assertIn('print(f"{value}_fdw_server")', script)
        self.assertIn("Wrappers >= 0.5.6 obrigatorio", script)
        self.assertIn("s3_vectors_fdw_handler", script)
        self.assertIn("s3_vectors_fdw_validator", script)

    def test_wrapper_uses_vault_and_the_tenant_internal_endpoint(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS supabase_vault CASCADE", script)
        self.assertIn("vault.create_secret", script)
        self.assertIn("vault.update_secret", script)
        self.assertIn(
            'VECTOR_ENDPOINT="http://${STORAGE_CONTAINER}:5000/vector"', script
        )
        self.assertIn("vault_access_key_id", script)
        self.assertIn("vault_secret_access_key", script)
        self.assertNotIn("host.docker.internal", script)

    def test_wrapper_validates_real_bucket_and_import_foreign_schema(self) -> None:
        script = WRAPPER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("/vector/GetVectorBucket", script)
        self.assertIn("IMPORT FOREIGN SCHEMA", script)
        self.assertIn("OPTIONS (strict 'true')", script)
        self.assertNotIn("enable_vector_storage.sh", script)
        self.assertNotIn('indexes = {}', script)
        self.assertNotIn('vectorBuckets = {}', script)

    def test_shell_syntax(self) -> None:
        for script in (VECTOR_LIBRARY, WRAPPER_SCRIPT):
            subprocess.run(["bash", "-n", str(script)], check=True)


if __name__ == "__main__":
    unittest.main()
