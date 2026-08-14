"""Contratos estaticos da arquitetura de Storage compartilhado.

Os testes ativos de isolamento ficam em ``test_shared_storage_tenant_integration``.
Este modulo impede que templates e lifecycles voltem a materializar Storage ou
imgproxy por projeto quando Docker nao esta disponivel no ambiente de CI.
"""

from __future__ import annotations

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "servidor"
SCRIPTS = SERVER / "generateProject"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


class SharedStorageTopologyContractTest(unittest.TestCase):
    def test_global_compose_has_exactly_one_storage_and_one_imgproxy(self) -> None:
        global_compose = read(SERVER / "docker-compose.yml")
        project_compose = read(SCRIPTS / "dockercomposetemplate")

        self.assertEqual(global_compose.count("container_name: supabase-storage-global"), 1)
        self.assertEqual(global_compose.count("container_name: supabase-imgproxy-global"), 1)
        self.assertEqual(global_compose.count("container_name: shared-storage-data-plane"), 1)
        self.assertNotRegex(project_compose, r"(?m)^\s+(storage|imgproxy):\s*$")
        self.assertNotIn("supabase-storage-{{project_id}}", project_compose)
        self.assertNotIn("supabase-imgproxy-{{project_id}}", project_compose)

    def test_storage_uses_official_multitenant_file_contract(self) -> None:
        compose = read(SERVER / "docker-compose.yml")
        env = read(SERVER / ".env.example")
        admin_env = read(SERVER / ".storage.env.example")

        for contract in (
            'MULTI_TENANT: "true"',
            "DATABASE_MULTITENANT_URL:",
            "REQUEST_X_FORWARDED_HOST_REGEXP:",
            "STORAGE_BACKEND: ${STORAGE_BACKEND:?defina STORAGE_BACKEND}",
            "STORAGE_FILE_BACKEND_PATH:",
            "VECTOR_BUCKET_PROVIDER: pgvector",
            "IMGPROXY_URL: http://imgproxy:5001",
            "STORAGE_DATA_PLANE_PROXY_IMAGE:",
        ):
            self.assertIn(contract, compose)
        self.assertIn("SERVER_ADMIN_API_KEYS=", admin_env)
        self.assertIn("AUTH_ENCRYPTION_KEY=", admin_env)
        self.assertIn("- .storage.env", compose)
        self.assertIn("STORAGE_BACKEND=file", env)
        self.assertIn(
            "STORAGE_DATA_PLANE_PROXY_IMAGE=nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim",
            env,
        )
        self.assertIn("STORAGE_INTERNAL_BUCKET=objects", env)
        self.assertIn("./volumes/storage:/var/lib/storage:z", compose)

    def test_admin_plane_is_not_published_or_injected_into_projects(self) -> None:
        global_compose = read(SERVER / "docker-compose.yml")
        project_compose = read(SCRIPTS / "dockercomposetemplate")
        project_env = read(SCRIPTS / ".envtemplate")

        storage_start = global_compose.index("  storage:\n")
        imgproxy_start = global_compose.index("\n  imgproxy:\n", storage_start) + 1
        storage_service = global_compose[storage_start:imgproxy_start]
        self.assertNotIn("ports:", storage_service)
        self.assertIn("SERVER_ADMIN_PORT: 5001", storage_service)
        self.assertNotIn("SERVER_ADMIN_API_KEYS", project_compose + project_env)
        self.assertNotIn("AUTH_ENCRYPTION_KEY", project_compose + project_env)
        self.assertNotIn("rede-supabase", storage_service)

        gateway_start = global_compose.index("  storage-data-plane:\n")
        analytics_start = global_compose.index("\n  analytics:\n", gateway_start)
        gateway_service = global_compose[gateway_start:analytics_start]
        gateway_config = read(SERVER / "volumes" / "storage-proxy" / "nginx.conf")
        self.assertIn("shared-storage-data-plane", gateway_service)
        self.assertIn("hostname: supabase-storage-global", gateway_service)
        self.assertIn("supabase-storage-global", gateway_service)
        self.assertIn("storage-gateways", gateway_service)
        self.assertIn("storage-data-plane", gateway_service)
        self.assertNotIn("rede-supabase", gateway_service)
        self.assertIn("name: supabase-storage-gateways", global_compose)
        self.assertIn("server storage:5000;", gateway_config)
        self.assertNotIn("5001", gateway_config)
        self.assertIn("proxy_set_header Host $http_host;", gateway_config)
        self.assertIn(
            "proxy_set_header X-Forwarded-Host $http_x_forwarded_host;",
            gateway_config,
        )
        self.assertIn(
            "map $http_x_forwarded_host $storage_tenant_host_valid",
            gateway_config,
        )
        self.assertIn("return 421;", gateway_config)
        self.assertIn("location = /status", gateway_config)
        self.assertIn('"uri":"$uri"', gateway_config)
        self.assertNotIn("$request_uri", gateway_config)
        self.assertNotIn("$args", gateway_config)

    def test_only_project_nginx_joins_the_storage_gateway_network(self) -> None:
        project_compose = read(SCRIPTS / "dockercomposetemplate")
        nginx_start = project_compose.index("  nginx:\n")
        auth_start = project_compose.index("\n  auth:\n", nginx_start)
        nginx_service = project_compose[nginx_start:auth_start]

        self.assertIn("- storage-gateways", nginx_service)
        self.assertEqual(project_compose.count("- storage-gateways"), 1)
        self.assertIn(
            "  storage-gateways:\n    external: true\n    name: supabase-storage-gateways",
            project_compose,
        )

    def test_project_nginx_overwrites_tenant_routing_header(self) -> None:
        nginx = read(SCRIPTS / "nginxtemplate")
        storage_location = nginx[nginx.index("location /storage/v1/") :]

        self.assertIn(
            'proxy_set_header X-Forwarded-Host "{{project_uuid}}.storage.internal";',
            storage_location,
        )
        self.assertIn('proxy_set_header X-Forwarded-Prefix "/{{project_id}}/storage/v1";', storage_location)
        self.assertNotIn("proxy_set_header X-Forwarded-Host $http_x_forwarded_host", storage_location)
        self.assertIn("supabase-storage-global:5000", nginx)

    def test_storage_gateway_logs_are_tenant_and_request_aware(self) -> None:
        vector = read(SERVER / "volumes" / "logs" / "vector.yml")

        self.assertIn('storage_gateway: \'.appname == "shared-storage-data-plane"\'', vector)
        self.assertIn("inputs: [router.storage_gateway]", vector)
        self.assertIn(".metadata.request_id = parsed.request_id", vector)
        self.assertIn(".metadata.operation = parsed.method", vector)
        self.assertIn(".metadata.tenantId = tenant", vector)
        self.assertIn("inputs: [storage_logs, storage_gateway_logs]", vector)

    def test_runtime_contains_no_old_storage_fallback(self) -> None:
        excluded = {
            SCRIPTS / "migrate_shared_storage.sh",
            SCRIPTS / "render_migrated_project_env.py",
        }
        runtime_files = [
            *SERVER.rglob("*.sh"),
            *SERVER.rglob("*.py"),
            SCRIPTS / "dockercomposetemplate",
            SCRIPTS / ".envtemplate",
            SCRIPTS / "nginxtemplate",
        ]
        forbidden = re.compile(
            r"supabase-(?:storage|imgproxy)-\{\{project_id\}\}|"
            r"STORAGE_TENANT_ID=stub|USE_LEGACY_STORAGE|storage/stub/stub"
        )
        violations: list[str] = []
        for path in runtime_files:
            if path in excluded or not path.is_file():
                continue
            if forbidden.search(read(path)):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(violations, [])


class SharedStorageLifecycleContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.storage = read(SCRIPTS / "lib" / "storage_multitenant.sh")
        cls.create = read(SCRIPTS / "lib" / "generate_project_impl.sh")
        cls.duplicate = read(SCRIPTS / "lib" / "duplicate_project_impl.sh")
        cls.rename = read(SCRIPTS / "lib" / "rename_project_impl.sh")
        cls.delete = read(SCRIPTS / "delete_storage_tenant.sh")
        cls.backup = read(SCRIPTS / "lib" / "backup_core.sh")
        cls.backup_impl = read(SCRIPTS / "lib" / "backup_project_impl.sh")
        cls.restore = read(SCRIPTS / "lib" / "restore_project_impl.sh")

    def test_create_registers_tenant_and_credentials_before_services(self) -> None:
        tenant = self.create.index("storage_provision_tenant")
        credentials = self.create.index("storage_create_s3_credentials")
        services = self.create.index("docker compose -p", credentials)
        validation = self.create.index("vector_validate_storage_api", services)
        self.assertLess(tenant, credentials)
        self.assertLess(credentials, services)
        self.assertLess(services, validation)
        self.assertIn("storage_delete_tenant", self.create[:tenant])

    def test_duplicate_creates_new_namespace_credentials_and_vector_identity(self) -> None:
        for contract in (
            '[[ "$ORIGINAL_UUID" != "$PROJECT_UUID" ]]',
            "storage_clone_tenant_namespace",
            "storage_create_empty_tenant_namespace",
            "vector_rekey_physical_tables",
            "storage_create_s3_credentials",
            "vector_strip_copied_wrappers",
            '[[ "$S3_PROTOCOL_CREDENTIAL_ID" != "$ORIGINAL_S3_CREDENTIAL_ID" ]]',
            '[[ "$S3_PROTOCOL_ACCESS_KEY_ID" != "$ORIGINAL_S3_ACCESS_KEY" ]]',
            '[[ "$S3_PROTOCOL_ACCESS_KEY_SECRET" != "$ORIGINAL_S3_SECRET_KEY" ]]',
        ):
            self.assertIn(contract, self.duplicate)

        jobs = read(SERVER / "api-internal" / "app" / "jobs.py")
        self.assertIn('if row["action"] == "duplicate":', jobs)
        self.assertIn("additional_project_ids = (original_id,)", jobs)
        self.assertIn("for project_id in action.lock_project_ids", jobs)

    def test_rename_keeps_immutable_tenant_and_only_repoints_database(self) -> None:
        self.assertIn(
            'storage_patch_tenant_connection "$PROJECT_UUID" "$NEW_NAME"',
            self.rename,
        )
        self.assertIn(
            'storage_assert_project_gateway "$PROJECT_UUID" "$NEW_NAME"',
            self.rename,
        )
        self.assertNotIn("storage_clone_tenant_namespace", self.rename)
        self.assertNotIn("storage_remove_tenant_namespace", self.rename)

    def test_delete_registry_precedes_namespace_and_project_database(self) -> None:
        self.assertLess(
            self.storage.index("storage_delete_tenant_registry"),
            self.storage.index("storage_remove_tenant_namespace", self.storage.index("storage_delete_tenant()")),
        )
        self.assertIn("storage_delete_tenant", self.delete)
        api = read(SERVER / "api-internal" / "app" / "main.py")
        self.assertLess(api.index('"delete_project_storage"'), api.index("drop_database_force", api.index("async def _delete_project_impl")))

    def test_backup_and_restore_are_bound_to_manifest_tenant(self) -> None:
        self.assertIn('storage_namespace="$(storage_assert_namespace_target "$PROJECT_UUID")"', self.backup)
        self.assertIn('format: 2', self.backup)
        self.assertIn('storage_tenant_id: $uuid', self.backup)
        self.assertIn('MANIFEST_UUID" == "$PROJECT_UUID', self.restore)
        self.assertIn('storage_extract_namespace_archive "$PROJECT_UUID"', self.restore)
        self.assertIn("storage_validate_namespace_archive", self.restore)

    def test_mutating_lifecycles_quiesce_only_the_selected_tenant(self) -> None:
        lifecycles = (self.backup_impl, self.restore, self.rename, self.duplicate)
        for lifecycle in lifecycles:
            self.assertIn("storage_quiesce_tenant", lifecycle)
            self.assertLess(lifecycle.index("_QUIESCED=1"), lifecycle.index("storage_quiesce_tenant"))
        self.assertIn("storage_data_plane_status", self.storage)
        self.assertIn("127.0.0.1:1/storage_maintenance", self.storage)
        self.assertNotIn('{"databasePoolUrl":null}', self.storage)

    def test_lifecycles_bind_project_ref_to_persisted_tenant_uuid(self) -> None:
        self.assertIn("storage_assert_project_identity()", self.storage)
        self.assertIn("SELECT tenant_uuid::text FROM public.projects", self.storage)
        guarded = (
            self.backup_impl,
            self.restore,
            self.rename,
            self.duplicate,
            self.delete,
            read(SCRIPTS / "apply_storage_settings.sh"),
            read(SCRIPTS / "rotate_key.sh"),
            read(SCRIPTS / "operations" / "setup_vector_bucket_wrapper.sh"),
        )
        for lifecycle in guarded:
            self.assertIn("storage_assert_project_identity", lifecycle)
        provision = self.storage.split("storage_provision_tenant()", 1)[1].split(
            "storage_assert_tenant_absent()", 1
        )[0]
        self.assertIn("storage_assert_project_identity", provision)

    def test_file_lifecycle_rejects_different_backend_layout_or_image(self) -> None:
        required = self.storage.split(
            "storage_require_canonical_global_config()", 1
        )[1].split("storage_assert_project_identity()", 1)[0]
        self.assertIn('[[ "$image" == "$STORAGE_SUPPORTED_IMAGE" ]]', required)
        self.assertIn(
            '[[ "$proxy_image" == "$STORAGE_SUPPORTED_DATA_PLANE_IMAGE" ]]',
            required,
        )
        self.assertIn('[[ "$backend" == "file" ]]', required)
        self.assertIn('[[ "$backend_path" == "/var/lib/storage" ]]', required)
        self.assertIn('[[ "$internal_bucket" == "objects" ]]', required)
        self.assertIn('[[ "$tenant_db_user" == "$STORAGE_SUPPORTED_TENANT_DB_USER" ]]', required)
        self.assertIn(
            '[[ "$tenant_host_regexp" == "$STORAGE_SUPPORTED_TENANT_HOST_REGEXP" ]]',
            required,
        )
        self.assertIn("Storage global nao pode estar conectado diretamente", self.storage)
        self.assertIn("proxy da data plane nao esta conectado", self.storage)
        wait = self.storage.split("storage_wait_global()", 1)[1].split(
            "storage_build_tenant_payload()", 1
        )[0]
        self.assertIn("storage_require_canonical_global_config || return 1", wait)
        self.assertIn('storage_wait_data_plane "$attempts" || return 1', wait)

    def test_invalid_guards_return_instead_of_relying_on_errexit(self) -> None:
        provision = self.storage.split("storage_provision_tenant()", 1)[1].split(
            "storage_assert_tenant_absent()", 1
        )[0]
        validate = self.storage.split("storage_validate_tenant()", 1)[1]
        for contract in (
            'storage_validate_tenant_id "$tenant_id" || return 1',
            'storage_validate_project_ref "$project_ref" || return 1',
            "storage_wait_global || return 1",
        ):
            self.assertIn(contract, provision)
        for contract in (
            'storage_run_and_assert_migrations "$tenant_id" || return 1',
            'storage_assert_tenant_health "$tenant_id" || return 1',
            'storage_assert_jwt_data_plane "$tenant_id" "$service_key" || return 1',
        ):
            self.assertIn(contract, validate)

    def test_s3_registry_delete_validates_full_credential_list(self) -> None:
        deletion = self.storage.split("storage_delete_tenant_registry()", 1)[1].split(
            "storage_tenant_namespace()", 1
        )[0]
        self.assertIn('type == "array" and all(.[].id;', deletion)
        self.assertLess(deletion.index("type == \"array\""), deletion.index("while IFS="))

    def test_copies_and_backups_reject_symlinks_or_special_files(self) -> None:
        self.assertIn("storage_validate_file_tree()", self.storage)
        clone = self.storage.split("storage_clone_tenant_namespace()", 1)[1].split(
            "storage_create_empty_tenant_namespace()", 1
        )[0]
        self.assertIn("storage_validate_file_tree", clone)
        self.assertIn("storage_validate_file_tree", self.backup)
        migration = read(SCRIPTS / "migrate_shared_storage.sh")
        self.assertIn(
            'storage_validate_file_tree "$old_namespace" "namespace Storage antigo"',
            migration,
        )

    def test_gateway_probe_uses_internal_jwt_without_presenting_it_as_opaque_key(self) -> None:
        probe = self.storage.split("storage_assert_project_gateway()", 1)[1].split(
            "storage_vector_request()", 1
        )[0]
        self.assertIn('Authorization: Bearer $key', probe)
        self.assertIn("STORAGE_DATA_PLANE_CONTAINER", probe)
        self.assertIn("storage_assert_project_gateway_container_contract", probe)
        self.assertNotIn("apikey: key", probe)

    def test_tenant_health_checks_data_s3_and_vectors(self) -> None:
        for contract in (
            "storage_run_and_assert_migrations",
            "storage_assert_tenant_health",
            "storage_assert_jwt_data_plane",
            "storage_sigv4_probe",
            "storage_assert_project_gateway",
        ):
            self.assertIn(contract, self.storage)
        self.assertIn("s3 GET /s3", self.storage)
        self.assertIn("s3vectors POST /vector/ListVectorBuckets", self.storage)

    def test_s3_credentials_are_managed_by_official_tenant_api(self) -> None:
        self.assertIn('POST "/s3/$tenant_id/credentials"', self.storage)
        self.assertIn('GET "/s3/$tenant_id/credentials"', self.storage)
        self.assertIn('DELETE "/s3/$tenant_id/credentials"', self.storage)
        vectors_doc = read(ROOT / "docs" / "architecture" / "storage-vectors-lifecycle.md")
        self.assertIn("getS3CredentialsByAccessKey", vectors_doc)

    def test_project_settings_patch_tenant_without_global_restart(self) -> None:
        apply_settings = read(SCRIPTS / "apply_storage_settings.sh")
        command_handler = read(SERVER / "host-agent" / "hostagent" / "commands.py")
        self.assertIn("storage_patch_tenant_settings", apply_settings)
        self.assertIn('compose_services = [service for service in services if service != "storage"]', command_handler)
        self.assertNotIn("restart supabase-storage-global", apply_settings)


class SharedStorageMigrationContractTest(unittest.TestCase):
    def test_one_time_migration_is_resumable_and_quiesces_runtime(self) -> None:
        migration = read(SCRIPTS / "migrate_shared_storage.sh")
        for contract in (
            "--resume",
            "quiesce_lifecycle",
            "active_lifecycle_counts",
            "docker stop --time 30 projects-api",
            "run_systemctl stop supabase-host-agent",
            'PROJECTS_API_MARKER="$RUN_DIR/projects-api.was-running"',
            'HOST_AGENT_MARKER="$RUN_DIR/host-agent.was-active"',
            "storage_clone_tenant_namespace_from_legacy",
            "migration_rekey_vector_physical_tables",
            "storage_validate_tenant",
            "ROLLBACK_INCOMPLETE",
        ):
            self.assertIn(contract, migration)
        self.assertIn("Projects API e host-agent permanecem parados", migration)

    def test_migration_restores_the_detected_api_topology(self) -> None:
        migration = read(SCRIPTS / "migrate_shared_storage.sh")
        for contract in (
            "com.docker.compose.project.config_files",
            "docker-compose.single-node.yml",
            "docker-compose.split-node.yml",
            'api_override="$(read_projects_api_override)"',
            '-f docker-compose-api.yml -f "$api_override"',
        ):
            self.assertIn(contract, migration)

    def test_runtime_renderer_rejects_obsolete_storage_keys(self) -> None:
        renderer = read(SCRIPTS / "render_project_env.py")
        self.assertIn('"STORAGE_TENANT_ID"', renderer)
        self.assertIn("configuracao Storage por projeto nao suportada", renderer)
        self.assertNotIn("setdefault", renderer)


if __name__ == "__main__":
    unittest.main()
