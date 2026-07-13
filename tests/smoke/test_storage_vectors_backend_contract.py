from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
ENABLE_SCRIPT = ROOT / "servidor/generateProject/enable_vector_storage.sh"
CREATE_TEMPLATE_SCRIPT = ROOT / "servidor/volumes/db/create_template.sh"


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

    def test_database_template_installs_vector_before_it_is_created(self) -> None:
        script = CREATE_TEMPLATE_SCRIPT.read_text(encoding="utf-8")

        create_vector = script.index("CREATE EXTENSION IF NOT EXISTS vector SCHEMA public")
        create_template = script.index("CREATE DATABASE _supabase_template")
        restore_template = script.index("Fazendo pg_dump do DB principal")

        self.assertLess(create_vector, create_template)
        self.assertLess(create_template, restore_template)
        self.assertIn("pgvector >= 0.7.0 required for Storage Vectors", script)

    def test_database_template_validates_the_inherited_extension(self) -> None:
        script = CREATE_TEMPLATE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('--dbname _supabase_template', script)
        self.assertIn("_supabase_template was created without pgvector", script)
        self.assertIn("installed_schema <> 'public'", script)
        self.assertIn("_supabase_template requires pgvector >= 0.7.0", script)

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
        for script in (ENABLE_SCRIPT, CREATE_TEMPLATE_SCRIPT):
            subprocess.run(["bash", "-n", str(script)], check=True)


if __name__ == "__main__":
    unittest.main()
