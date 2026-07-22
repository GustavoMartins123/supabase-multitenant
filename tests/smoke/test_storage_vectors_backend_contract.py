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

    def test_rename_reloads_env_and_rolls_back_dependencies_in_order(self) -> None:
        rename = RENAME_IMPL.read_text(encoding="utf-8")

        rollback_start = rename.index("rollback_on_error()")
        rollback_end = rename.index("trap rollback_on_error ERR")
        rollback = rename[rollback_start:rollback_end]

        restore_old_env = rollback.index('source "$OLD_DIR/.env"')
        stop_new_pool = rollback.index(
            'GET "/api/tenants/$NEW_NAME/terminate"'
        )
        delete_new_tenant = rollback.index(
            "DELETE FROM _supavisor.users WHERE tenant_external_id = '$NEW_NAME'"
        )
        restore_database = rollback.index(
            r'ALTER DATABASE \"$NEW_DB\" RENAME TO \"$OLD_DB\"'
        )
        restore_old_tenant = rollback.index(
            'PUT "/api/tenants/$OLD_NAME"'
        )
        start_old_stack = rollback.index("compose_old up -d")

        self.assertLess(restore_old_env, start_old_stack)
        self.assertLess(stop_new_pool, delete_new_tenant)
        self.assertLess(delete_new_tenant, restore_database)
        self.assertLess(restore_database, restore_old_tenant)
        self.assertLess(restore_old_tenant, start_old_stack)

        generated_env_validated = rename.index(
            'grep -qx "PROJECT_ID=$NEW_NAME" "$NEW_DIR/.env"'
        )
        load_new_env = rename.index(
            'source "$NEW_DIR/.env"', generated_env_validated
        )
        start_new_stack = rename.index("compose_new up --build -d", load_new_env)

        self.assertLess(generated_env_validated, load_new_env)
        self.assertLess(load_new_env, start_new_stack)

        forward_start = rename.index('say "Parando stack antiga..."')
        mark_realtime_mutation = rename.index("REALTIME_UPDATED=1", forward_start)
        update_realtime = rename.index(
            'PUT "/api/tenants/$PROJECT_UUID"', mark_realtime_mutation
        )
        mark_supavisor_mutation = rename.index(
            "SUPAVISOR_UPDATED=1", forward_start
        )
        update_supavisor = rename.index(
            'PUT "/api/tenants/$NEW_NAME"', mark_supavisor_mutation
        )

        self.assertLess(mark_realtime_mutation, update_realtime)
        self.assertLess(mark_supavisor_mutation, update_supavisor)

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
        self.assertNotIn("generateProject", dockerfile)
        agent_commands = (
            ROOT / "servidor/host-agent/hostagent/commands.py"
        ).read_text(encoding="utf-8")
        for script in (
            "generate_project.sh",
            "duplicate_project.sh",
            "rename_project.sh",
        ):
            self.assertIn(script, agent_commands)

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
