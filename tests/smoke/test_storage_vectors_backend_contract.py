from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
ENABLE_SCRIPT = ROOT / "servidor/generateProject/enable_vector_storage.sh"


class StorageVectorsBackendContractTests(unittest.TestCase):
    def test_project_template_enables_real_pgvector_backend(self) -> None:
        env = ENV_TEMPLATE.read_text(encoding="utf-8")

        self.assertIn("VECTOR_ENABLED=true", env)
        self.assertIn("VECTOR_BUCKET_PROVIDER=pgvector", env)
        self.assertIn("VECTOR_DATABASE_CREATE=false", env)
        self.assertIn("VECTOR_STORE_MIGRATIONS_ENABLED=true", env)
        self.assertIn(
            "VECTOR_DATABASE_URL=postgres://${STORAGE_DB_USER}:${POSTGRES_PASSWORD}"
            "@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DATABASE}",
            env,
        )

    def test_existing_project_upgrade_installs_extension_as_postgres_admin(self) -> None:
        script = ENABLE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public", script)
        self.assertIn("pgvector >= 0.7.0 obrigatorio", script)
        self.assertIn('STORAGE_DB_USER="${STORAGE_DB_USER:-supabase_storage_admin}"', script)

    def test_upgrade_validates_the_real_storage_api_response(self) -> None:
        script = ENABLE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("/vector/ListVectorBuckets", script)
        self.assertIn("Array.isArray(payload.vectorBuckets)", script)
        self.assertNotIn('vectorBuckets: []', script)
        self.assertNotIn('vectorBuckets = {}', script)

    def test_shell_syntax(self) -> None:
        subprocess.run(["bash", "-n", str(ENABLE_SCRIPT)], check=True)


if __name__ == "__main__":
    unittest.main()
