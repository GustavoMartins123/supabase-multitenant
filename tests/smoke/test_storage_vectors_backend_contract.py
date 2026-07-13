from __future__ import annotations

import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
CREATE_TEMPLATE_SCRIPT = ROOT / "servidor/volumes/db/create_template.sh"
VECTOR_LIBRARY = ROOT / "servidor/generateProject/lib/vector_lifecycle.sh"
GENERATE_ENTRYPOINT = ROOT / "servidor/generateProject/generate_project.sh"
DUPLICATE_ENTRYPOINT = ROOT / "servidor/generateProject/duplicate_project.sh"
RENAME_ENTRYPOINT = ROOT / "servidor/generateProject/rename_project.sh"
GENERATE_IMPL = ROOT / "servidor/generateProject/lib/generate_project_impl.sh"
DUPLICATE_IMPL = ROOT / "servidor/generateProject/lib/duplicate_project_impl.sh"
RENAME_IMPL = ROOT / "servidor/generateProject/lib/rename_project_impl.sh"
API_DOCKERFILE = ROOT / "servidor/api-internal/Dockerfile"


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
        self.assertIn("S3_PROTOCOL_ACCESS_KEY_ID={{s3_protocol_access_key_id}}", env)
        self.assertIn("S3_PROTOCOL_ACCESS_KEY_SECRET={{s3_protocol_access_key_secret}}", env)

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

        self.assertIn("--dbname _supabase_template", script)
        self.assertIn("_supabase_template was created without pgvector", script)
        self.assertIn("installed_schema <> 'public'", script)
        self.assertIn("_supabase_template requires pgvector >= 0.7.0", script)

    def test_generate_duplicate_and_rename_share_the_vector_contract(self) -> None:
        library = VECTOR_LIBRARY.read_text(encoding="utf-8")
        generate = GENERATE_IMPL.read_text(encoding="utf-8")
        duplicate = DUPLICATE_IMPL.read_text(encoding="utf-8")
        rename = RENAME_IMPL.read_text(encoding="utf-8")

        self.assertIn("openssl rand -hex 16", library)
        self.assertIn("openssl rand -hex 32", library)
        self.assertIn("vector_wait_storage", library)
        self.assertIn("vector_validate_storage_api", library)

        self.assertIn("unset S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET", generate)
        self.assertIn("vector_validate_database", generate)
        self.assertIn("vector_validate_storage_api", generate)

        self.assertIn("unset S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET", duplicate)
        self.assertIn("vector_strip_copied_wrappers", duplicate)
        self.assertIn("vector_sync_project_wrappers", duplicate)
        self.assertNotIn("ALTER DATABASE current_database()", duplicate)

        self.assertIn("vector_ensure_s3_credentials", rename)
        self.assertIn("vector_validate_database", rename)
        self.assertIn("vector_sync_project_wrappers", rename)

    def test_public_entrypoints_delegate_to_organized_implementations(self) -> None:
        expectations = {
            GENERATE_ENTRYPOINT: "lib/generate_project_impl.sh",
            DUPLICATE_ENTRYPOINT: "lib/duplicate_project_impl.sh",
            RENAME_ENTRYPOINT: "lib/rename_project_impl.sh",
        }
        for entrypoint, implementation in expectations.items():
            content = entrypoint.read_text(encoding="utf-8")
            self.assertIn(implementation, content)
            self.assertLessEqual(len(content.splitlines()), 6)

        dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")
        self.assertIn("find ./scripts -type f -name '*.sh' -exec chmod +x {} +", dockerfile)

    def test_obsolete_manual_bootstrap_was_removed(self) -> None:
        self.assertFalse((ROOT / "servidor/generateProject/enable_vector_storage.sh").exists())
        self.assertFalse((ROOT / "servidor/generateProject/setup_vector_bucket_wrapper.sh").exists())
        self.assertTrue(
            (
                ROOT
                / "servidor/generateProject/operations/setup_vector_bucket_wrapper.sh"
            ).exists()
        )

    def test_shell_syntax(self) -> None:
        scripts = (
            CREATE_TEMPLATE_SCRIPT,
            VECTOR_LIBRARY,
            GENERATE_ENTRYPOINT,
            DUPLICATE_ENTRYPOINT,
            RENAME_ENTRYPOINT,
            GENERATE_IMPL,
            DUPLICATE_IMPL,
            RENAME_IMPL,
        )
        for script in scripts:
            subprocess.run(["bash", "-n", str(script)], check=True)


if __name__ == "__main__":
    unittest.main()
