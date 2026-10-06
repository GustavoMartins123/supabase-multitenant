from __future__ import annotations

import pathlib
import subprocess
import unittest

from tests.smoke.common import bash_path, git_compatible_bash

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
GLOBAL_COMPOSE = ROOT / "servidor/docker-compose.yml"
STORAGE_LIBRARY = ROOT / "servidor/generateProject/lib/storage_multitenant.sh"


class StorageVectorsBackendContractTests(unittest.TestCase):
    def test_sigv4_host_is_separate_from_tenant_routing(self) -> None:
        compose = GLOBAL_COMPOSE.read_text(encoding="utf-8")
        self.assertIn("S3_PROTOCOL_NON_CANONICAL_HOST_HEADER: host", compose)
        self.assertIn('S3_ALLOW_FORWARDED_HEADER: "false"', compose)
        gateway = (ROOT / "servidor/generateProject/nginxtemplate").read_text(encoding="utf-8")
        vector = gateway.split("location /vector/ {", 1)[1].split("\n        }", 1)[0]
        self.assertIn("proxy_set_header Host $http_host;", vector)
        self.assertIn('proxy_set_header X-Forwarded-Host "{{project_uuid}}.storage.internal";', vector)
        data_plane = (ROOT / "servidor/volumes/storage-proxy/nginx.conf").read_text(encoding="utf-8")
        self.assertIn("proxy_set_header Host $http_host;", data_plane)

    def test_project_template_enables_real_pgvector_backend(self) -> None:
        env = ENV_TEMPLATE.read_text(encoding="utf-8")
        compose = GLOBAL_COMPOSE.read_text(encoding="utf-8")

        self.assertIn("VECTOR_BUCKETS_ENABLED=true", env)
        self.assertIn("VECTOR_MAX_BUCKETS=10", env)
        self.assertIn("VECTOR_MAX_INDEXES=20", env)
        self.assertNotIn("VECTOR_DATABASE_URL", env)
        self.assertIn("VECTOR_BUCKET_PROVIDER: pgvector", compose)
        self.assertIn('VECTOR_DATABASE_CREATE: "false"', compose)
        self.assertIn('VECTOR_STORE_MIGRATIONS_ENABLED: "true"', compose)
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
        storage_library = STORAGE_LIBRARY.read_text(encoding="utf-8")
        generate = GENERATE_IMPL.read_text(encoding="utf-8")
        duplicate = DUPLICATE_IMPL.read_text(encoding="utf-8")
        rotation = (ROOT / "servidor/generateProject/rotate_project_reference.py").read_text(encoding="utf-8")

        self.assertIn("storage_create_s3_credentials", storage_library)
        self.assertIn('POST "/s3/$tenant_id/credentials"', storage_library)
        self.assertIn("vector_wait_storage", library)
        self.assertIn("vector_validate_storage_api", library)

        self.assertIn("storage_provision_tenant", generate)
        self.assertIn("storage_create_s3_credentials", generate)
        self.assertIn("vector_validate_database", generate)
        self.assertIn("vector_validate_storage_api", generate)

        self.assertIn("storage_provision_tenant", duplicate)
        self.assertIn("storage_create_s3_credentials", duplicate)
        self.assertIn("vector_strip_copied_wrappers", duplicate)
        self.assertIn("vector_rekey_physical_tables", duplicate)
        self.assertIn("vector_sync_project_wrappers", duplicate)
        self.assertNotIn("ALTER DATABASE current_database()", duplicate)

        # Renames only rotate the public reference: the tenant UUID (and
        # therefore every vector/S3 identity keyed by it) is verified
        # unchanged and never rewritten by the rotation.
        self.assertIn('updates = {"PROJECT_PUBLIC_REF": self.new_ref', rotation)
        self.assertIn('("PROJECT_UUID", self.tenant_uuid)', rotation)
        self.assertNotIn("vector_rekey_physical_tables", rotation)

    def test_rename_uses_canonical_env_and_rolls_back_dependencies_in_order(self) -> None:
        rename = RENAME_IMPL.read_text(encoding="utf-8")
        rotation = (ROOT / "servidor/generateProject/rotate_project_reference.py").read_text(encoding="utf-8")

        # The shell wrapper is a thin locked entrypoint; the runner owns the
        # env handling, the journal and the rollback ordering.
        self.assertIn("rotate_project_reference.py", rename)
        self.assertIn("functions_config_lock", rename)
        self.assertNotIn("source \"$OLD_DIR/.env\"", rename)
        self.assertNotIn("source \"$NEW_DIR/.env\"", rename)

        self.assertIn("read_canonical_env_value", rotation)
        rollback_start = rotation.index("def rollback(self) -> None:")
        rollback = rotation[rollback_start:]
        withdraw_functions = rollback.index('self.functions("withdraw")')
        stop_gateway = rollback.index('self.compose("stop", "nginx", "auth")')
        swap_ref = rollback.index("self.swap(self.new_ref, self.old_ref)")
        publish_functions = rollback.index('self.functions("publish")')
        self.assertLess(withdraw_functions, stop_gateway)
        self.assertLess(stop_gateway, swap_ref)
        self.assertLess(swap_ref, publish_functions)
        self.assertIn("Rollback cannot prove the canonical reference", rotation)
        self.assertIn("Rotation journal identity does not match the requested rollback", rotation)

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
            subprocess.run(
                [git_compatible_bash(), "-n", bash_path(script)], check=True
            )


if __name__ == "__main__":
    unittest.main()
