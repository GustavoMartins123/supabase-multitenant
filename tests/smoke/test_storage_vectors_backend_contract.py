from __future__ import annotations

import pathlib
import re
import subprocess
import unittest

from tests.smoke.common import bash_path, git_compatible_bash

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENV_TEMPLATE = ROOT / "servidor/generateProject/.envtemplate"
CREATE_TEMPLATE_SCRIPT = ROOT / "servidor/volumes/db/create_template.sh"
MIGRATE_SHARED_STORAGE = ROOT / "servidor/generateProject/migrate_shared_storage.sh"
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

    def test_project_nginx_enforces_strict_vector_sigv4_method_path_and_cors(self) -> None:
        gateway = (ROOT / "servidor/generateProject/nginxtemplate").read_text(encoding="utf-8")

        sigv4_regex = (
            r"^AWS4-HMAC-SHA256 Credential=[^/,\s]+/[0-9]{8}/[^/,\s]+/s3vectors/aws4_request,"
            r"\s*SignedHeaders=[^,\s]+,\s*Signature=[0-9a-fA-F]{64}$"
        )
        date_regex = r"^[0-9]{8}T[0-9]{6}Z$"

        self.assertIn("variables_hash_max_size 2048;", gateway)
        self.assertIn("map $http_authorization $has_sigv4_header", gateway)
        self.assertIn(f'"~{sigv4_regex}" 1;', gateway)
        self.assertIn("map $http_x_amz_date $has_amz_date", gateway)
        self.assertIn(f'"~{date_regex}" 1;', gateway)
        self.assertIn('map "$has_sigv4_header:$has_amz_date" $is_sigv4_auth', gateway)
        self.assertIn("map $http_authorization $is_sigv4_scheme", gateway)
        self.assertIn('map "$is_sigv4_auth:$is_sigv4_scheme:$has_apikey:$has_authorization" $vector_auth_status', gateway)
        self.assertIn('"1:1:0:1" 200;', gateway)
        self.assertIn('"1:1:1:1" 200;', gateway)
        self.assertIn('"0:0:1:0" 200;', gateway)
        self.assertIn('"0:0:1:1" 200;', gateway)
        self.assertIn('"0:0:0:0" 401;', gateway)

        sigv4_re = re.compile(sigv4_regex)
        date_re = re.compile(date_regex)
        valid_sig = "a" * 64
        for accepted in (
            f"AWS4-HMAC-SHA256 Credential=ak123/20261126/us-east-1/s3vectors/aws4_request, SignedHeaders=content-type;host;x-amz-date, Signature={valid_sig}",
            f"AWS4-HMAC-SHA256 Credential=ak123/20261126/sa-east-1/s3vectors/aws4_request,SignedHeaders=host;x-amz-date,Signature={valid_sig.upper()}",
        ):
            self.assertIsNotNone(sigv4_re.fullmatch(accepted))
        for rejected in (
            "AWS4-HMAC-SHA256 garbage",
            f"AWS4-HMAC-SHA256 Credential=ak123/20261126/us-east-1/s3/aws4_request, SignedHeaders=host, Signature={valid_sig}",
            f"AWS4-HMAC-SHA256 Credential=ak123/20261126/us-east-1/s3vectors/aws4_request, SignedHeaders=host, Signature={'a' * 63}",
            f"AWS4-HMAC-SHA256 Credential=ak123/20261126/us-east-1/s3vectors/aws4_request, SignedHeaders=host, Signature={'g' * 64}",
            "Bearer some-jwt",
            "",
        ):
            with self.subTest(sigv4=rejected):
                self.assertIsNone(sigv4_re.fullmatch(rejected))

        self.assertIsNotNone(date_re.fullmatch("20261126T120000Z"))
        for bad_date in ("", "2026-11-26T12:00:00Z", "20261126T120000", "garbage"):
            with self.subTest(amz_date=bad_date):
                self.assertIsNone(date_re.fullmatch(bad_date))

        public_vector_block = gateway.split("location ^~ /storage/v1/vector/ {", 1)[1].split(
            "location /storage/v1/ {", 1
        )[0]
        storage_block = gateway.split("location /storage/v1/ {", 1)[1].split(
            "location /vector/ {", 1
        )[0]
        vector_8080_block = gateway.split("location /vector/ {", 1)[1].split("\n        }", 1)[0]

        for required in (
            "set $opaque_target_service storage;",
            "auth_request /_internal/opaque-key-authorize;",
            "if ($request_method != 'POST') {\n                return 405;\n            }",
            'if ($uri !~ "^/storage/v1/vector/[A-Za-z]+$") {\n                return 404;\n            }',
            "if ($vector_auth_status = 401)",
            "if ($vector_auth_status != 200)",
            "client_max_body_size 25m;",
            "rewrite ^/storage/v1/(.*)$ /$1 break;",
            "proxy_set_header Host $http_host;",
            'proxy_set_header X-Forwarded-Host "{{project_uuid}}.storage.internal";',
            'proxy_set_header X-Forwarded-Prefix "/{{project_public_ref}}/storage/v1";',
            'proxy_set_header Forwarded "";',
            "proxy_set_header apikey $opaque_upstream_apikey;",
            "proxy_set_header Authorization $opaque_upstream_authorization;",
        ):
            self.assertIn(required, public_vector_block)

        self.assertIn('proxy_set_header Forwarded "";', storage_block)
        for header in ("x-amz-date", "x-amz-content-sha256", "x-amz-security-token", "x-amz-target"):
            self.assertEqual(public_vector_block.count(header), 2)
            self.assertEqual(storage_block.count(header), 2)

        for required in (
            "if ($request_method != POST) { return 405; }",
            'if ($uri !~ "^/vector/[A-Za-z]+$") { return 404; }',
            "if ($is_sigv4_auth != 1) { return 403; }",
            "client_max_body_size 25m;",
            'proxy_set_header Forwarded "";',
        ):
            self.assertIn(required, vector_8080_block)

        public_op_re = re.compile(r"^/storage/v1/vector/[A-Za-z]+$")
        internal_op_re = re.compile(r"^/vector/[A-Za-z]+$")
        self.assertIsNotNone(public_op_re.fullmatch("/storage/v1/vector/ListVectorBuckets"))
        self.assertIsNotNone(internal_op_re.fullmatch("/vector/ListVectorBuckets"))
        for bad_suffix in ("", "ListVectorBuckets/", "ListVectorBuckets/extra", "../bucket", "%2e%2e/bucket", "123"):
            with self.subTest(suffix=bad_suffix):
                self.assertIsNone(public_op_re.fullmatch(f"/storage/v1/vector/{bad_suffix}"))
                self.assertIsNone(internal_op_re.fullmatch(f"/vector/{bad_suffix}"))

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
        create_wrappers = script.index("CREATE EXTENSION IF NOT EXISTS wrappers SCHEMA extensions")
        create_template = script.index("CREATE DATABASE _supabase_template")
        restore_template = script.index("Fazendo pg_dump do DB principal")

        self.assertLess(create_vector, create_template)
        self.assertLess(create_wrappers, create_template)
        self.assertLess(create_template, restore_template)
        self.assertIn("pgvector >= 0.7.0 required for Storage Vectors", script)
        self.assertIn("wrappers >= 0.5.7 required for s3_vectors_fdw", script)
        self.assertIn("ARRAY[0, 5, 7]::int[]", script)

    def test_database_template_validates_the_inherited_extension(self) -> None:
        script = CREATE_TEMPLATE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("--dbname _supabase_template", script)
        self.assertIn("_supabase_template was created without pgvector", script)
        self.assertIn("installed_schema <> 'public'", script)
        self.assertIn("_supabase_template requires pgvector >= 0.7.0", script)
        self.assertIn("_supabase_template was created without wrappers", script)
        self.assertIn("installed_schema <> 'extensions'", script)
        self.assertIn("wrappers must be installed in extensions for s3_vectors_fdw", script)
        self.assertIn("_supabase_template requires wrappers >= 0.5.7", script)
        self.assertIn(
            "ALTER ROLE supabase_storage_admin IN DATABASE _supabase_template SET search_path = storage, public;",
            script,
        )
        self.assertIn(
            'ALTER ROLE supabase_storage_admin IN DATABASE :"target_db" SET search_path = storage, public;',
            script,
        )

    def test_shared_storage_migration_ensures_wrappers_and_storage_admin_search_path(self) -> None:
        migration = MIGRATE_SHARED_STORAGE.read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS wrappers SCHEMA extensions;", migration)
        self.assertIn("ARRAY[0, 5, 7]::int[]", migration)
        self.assertIn("wrappers must be installed in extensions for s3_vectors_fdw", migration)
        self.assertIn(
            'ALTER ROLE supabase_storage_admin IN DATABASE \\"$database\\" SET search_path = storage, public;',
            migration,
        )
        self.assertGreaterEqual(
            migration.count('ensure_project_vector_database_prerequisites "_supabase_$project"'),
            2,
        )

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
            MIGRATE_SHARED_STORAGE,
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
