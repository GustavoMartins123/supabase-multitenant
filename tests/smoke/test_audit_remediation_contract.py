from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal" / "app"


def bash(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [shutil.which("bash") or "bash", "-c", script],
        capture_output=True,
        text=True,
    )


class F01FunctionsDsn(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (
            ROOT / "servidor/volumes/functions/main/index.ts"
        ).read_text()

    def test_tenant_env_has_no_db_url_and_no_root_password(self) -> None:
        self.assertNotIn("SUPABASE_DB_URL", self.source)
        self.assertNotIn("POSTGRES_PASSWORD", self.source)
        self.assertNotIn("POSTGRES_USER", self.source)

    def test_tenant_env_keeps_only_safe_keys(self) -> None:
        for key in (
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "JWT_SECRET",
            "PROJECT_REF",
        ):
            with self.subTest(key=key):
                self.assertIn(key, self.source)

    def test_compose_functions_dsn_stays_pooler_scoped(self) -> None:
        compose = (ROOT / "servidor/docker-compose.yml").read_text()
        block = compose.split("SUPABASE_DB_URL:", 1)[1].split("\n", 1)[0]
        self.assertIn("${FUNCTIONS_DB_USER}", block)
        self.assertIn("${POSTGRES_POOLER}", block)
        self.assertNotIn("@${POSTGRES_HOST}", block)


class F02SharedPasswordScope(unittest.TestCase):
    def test_project_dsns_go_through_the_pooler_with_scoped_roles(self) -> None:
        template = (ROOT / "servidor/generateProject/dockercomposetemplate").read_text()
        self.assertIn("${AUTH_DB_USER}.{{project_id}}:${POSTGRES_PASSWORD}@${POSTGRES_POOLER}", template)
        self.assertIn("${POSTGREST_DB_USER}.{{project_id}}:${POSTGRES_PASSWORD}@${POSTGRES_POOLER}", template)

    def test_tenant_databases_revoke_public_and_grant_roles(self) -> None:
        source = (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh"
        ).read_text()
        self.assertIn("REVOKE CONNECT, TEMPORARY ON DATABASE $db FROM PUBLIC", source)
        for role in ("pgbouncer", "authenticator", "supabase_storage_admin", "supabase_auth_admin"):
            with self.subTest(role=role):
                self.assertIn(f"TO {role};", source)

    def test_generated_passwords_are_url_safe(self) -> None:
        setup = (ROOT / "setup.sh").read_text()
        body = setup.split("generate_postgres_password() {", 1)[1].split("}", 1)[0]
        self.assertIn("openssl rand -base64 32", body)
        self.assertIn("tr '/+' '_-'", body)


class F03SetupReRunGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.setup = (ROOT / "setup.sh").read_text()

    def test_existing_env_files_are_never_overwritten(self) -> None:
        for path in (
            "servidor/.env",
            "servidor/.analytics.env",
            "servidor/.storage.env",
            "studio/.env",
            "studio/.analytics.env",
        ):
            example = path.replace(".env", ".env.example")
            with self.subTest(path=path):
                self.assertIn(f"if [ ! -f {path} ]; then cp {example} {path}; fi", self.setup)

    def test_secrets_are_preserved_from_existing_env(self) -> None:
        self.assertIn("env_secret() {", self.setup)
        for key, generator in (
            ("PROJECT_SECRETS_MASTER_KEY", "generate_fernet_key"),
            ("POSTGRES_PASSWORD", "generate_postgres_password"),
            ("JWT_SECRET", "generate_jwt_secret"),
            ("PROJECT_DELETE_PASSWORD", "generate_jwt_secret"),
            ("PLATFORM_READER_DB_PASSWORD", "generate_key_authorizer_password"),
            ("POSTGRES_NGINX_PASSWORD", "generate_postgres_password"),
            ("NGINX_HMAC_SECRET", "generate_hmac_secret"),
            ("HOST_AGENT_HMAC_SECRET", "generate_hmac_secret"),
        ):
            with self.subTest(key=key):
                self.assertIsNotNone(
                    re.search(
                        rf"(?m)^\s*[A-Z_]+=\$\(env_secret \S+ {key} {generator}\)",
                        self.setup,
                    )
                )


class F04RestoreTableValidation(unittest.TestCase):
    def test_manifest_tables_are_whitelisted_before_sql(self) -> None:
        source = (
            ROOT / "servidor/generateProject/lib/restore_project_impl.sh"
        ).read_text()
        block = source.split("REALTIME_TABLES=", 1)[1].split("ALTER PUBLICATION", 1)[0]
        self.assertIn("local_table_re='^[A-Za-z_][A-Za-z0-9_]*(\\.[A-Za-z_][A-Za-z0-9_]*)?$'", block)
        self.assertIn('die "Tabela realtime invalida no manifest', block)


class F05F13Umask(unittest.TestCase):
    def test_lifecycle_and_backup_scripts_default_to_private_files(self) -> None:
        for rel in (
            "servidor/generateProject/lib/backup_core.sh",
            "servidor/generateProject/lib/restore_project_impl.sh",
            "servidor/generateProject/lib/generate_project_impl.sh",
            "servidor/generateProject/lib/duplicate_project_impl.sh",
            "servidor/generateProject/lib/rename_project_impl.sh",
        ):
            source = (ROOT / rel).read_text()
            with self.subTest(script=rel):
                head = "\n".join(source.splitlines()[:6])
                self.assertIn("umask 077", head)


class F06SlotNaming(unittest.TestCase):
    def test_short_projects_keep_the_legacy_slot_name(self) -> None:
        result = bash(
            f'source "{ROOT}/servidor/generateProject/lib/realtime_slots.sh"; '
            'realtime_slot_candidates_unique "abc"'
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            [
                "supabase_realtime_messages_replication_slot_abc",
                "supabase_realtime_replication_slot_abc",
            ],
            result.stdout.split(),
        )

    def test_long_projects_never_collide_after_truncation(self) -> None:
        result = bash(
            f'source "{ROOT}/servidor/generateProject/lib/realtime_slots.sh"; '
            'a=$(realtime_primary_slot "$(printf \'x%.0s\' {1..30})AAAA$(printf \'1%.0s\' {1..20})"); '
            'b=$(realtime_primary_slot "$(printf \'x%.0s\' {1..30})AAAA$(printf \'2%.0s\' {1..20})"); '
            'echo "$a"; echo "$b"; '
            '[ "$a" != "$b" ] && [ ${#a} -le 63 ] && [ ${#b} -le 63 ] && '
            'echo OK'
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("OK", result.stdout)
        names = result.stdout.split()
        for name in names[:2]:
            self.assertRegex(name, r"^supabase_realtime_replication_slot_[a-z0-9_]{1,63}$")

    def test_primary_slot_is_the_replication_one(self) -> None:
        result = bash(
            f'source "{ROOT}/servidor/generateProject/lib/realtime_slots.sh"; '
            'realtime_primary_slot "meu_projeto"'
        )
        self.assertEqual(
            "supabase_realtime_replication_slot_meu_projeto", result.stdout.strip()
        )

    def test_lifecycle_scripts_share_the_naming_lib(self) -> None:
        for rel in (
            "servidor/generateProject/lib/generate_project_impl.sh",
            "servidor/generateProject/lib/duplicate_project_impl.sh",
            "servidor/generateProject/lib/rename_project_impl.sh",
        ):
            with self.subTest(script=rel):
                self.assertIn("realtime_slots.sh", (ROOT / rel).read_text())


class F07NextStaticSplit(unittest.TestCase):
    def test_only_build_assets_are_public(self) -> None:
        conf = (ROOT / "studio/nginx/nginx.conf").read_text()
        static_at = conf.index("location ^~ /_next/static/")
        generic_at = conf.find("location ^~ /_next/", static_at + 10)
        self.assertGreater(generic_at, static_at)
        static_block = conf[static_at:conf.index("\n        }", static_at)]
        generic_block = conf[generic_at:conf.index("\n        }", generic_at)]
        self.assertIn("auth_request off", static_block)
        self.assertNotIn("auth_request off", generic_block)


class F08SignupHardening(unittest.TestCase):
    def test_public_signup_routes_are_rate_limited(self) -> None:
        conf = (ROOT / "studio/nginx/nginx.conf").read_text()
        self.assertIn("limit_req_zone $binary_remote_addr zone=studio_signup", conf)
        for marker in (
            "location = /api/bootstrap/admin {",
            "location ~ ^/api/admin/users/signup/?$ {",
        ):
            block = conf.split(marker, 1)[1].split("}", 1)[0]
            with self.subTest(location=marker):
                self.assertIn("limit_req zone=studio_signup", block)

    def test_argon2_runs_after_the_cheap_existence_checks(self) -> None:
        lua = (
            ROOT / "studio/nginx/lua/admin_api/user_signup.lua"
        ).read_text()
        first_check = lua.index("Initial admin already exists")
        first_hash = lua.index("generate_argon2_hash(password)")
        self.assertLess(first_check, first_hash)


class F09WebsecureGuard(unittest.TestCase):
    def test_anti_abuse_routers_cover_tls_entrypoint(self) -> None:
        yml = (ROOT / "servidor/traefik/middlewares.yml").read_text()
        self.assertEqual(4, yml.count("        - websecure\n"))

    def test_guard_defaults_to_enforce(self) -> None:
        source = (
            ROOT / "servidor/traefik/render_dynamic_config.py"
        ).read_text()
        self.assertIn('settings.get("TRAEFIK_GUARD_PROJECT_MODE", "enforce")', source)


class F10PartialDeleteAggregation(unittest.TestCase):
    def test_steps_continue_and_aggregate_errors(self) -> None:
        main = (APP / "main.py").read_text()
        for marker in (
            'errors.append("containers: "',
            'errors.append(f"storage: {detail}")',
            'errors.append(f"tenants globais: {exc}")',
            'errors.append(f"metadata global: {exc}")',
            'errors.append(f"database: {exc}")',
            'errors.append(f"arquivos: {detail}")',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, main)

    def test_control_plane_row_survives_partial_deletions(self) -> None:
        main = (APP / "main.py").read_text()
        guard_at = main.index("Exclusao parcial de ")
        control_at = main.index('"Removendo registros do control plane..."')
        self.assertLess(guard_at, control_at)
        self.assertIn("O registro permaneceu no control plane", main)

    def test_fail_fast_raises_are_gone(self) -> None:
        main = (APP / "main.py").read_text()
        self.assertNotIn('raise ProjectDeletionError("; ".join(container_errors))', main)
        self.assertNotIn('raise ProjectDeletionError(f"Erro ao excluir diretórios: {detail}")', main)


class F11ClientHeaderHygiene(unittest.TestCase):
    def test_internal_proxies_stop_forwarding_client_identity_headers(self) -> None:
        conf = (ROOT / "studio/nginx/nginx.conf").read_text()
        self.assertNotIn("$http_x_user_display_name", conf)
        self.assertNotIn("$http_remote_groups", conf)


class F12OpaqueHeaderClears(unittest.TestCase):
    def test_client_supplied_opaque_headers_are_cleared_per_backend(self) -> None:
        template = (ROOT / "servidor/generateProject/nginxtemplate").read_text()
        for header in (
            "X-Opaque-Key-Role",
            "X-Opaque-Key-Present",
            "X-Opaque-Key-Id",
            "X-Opaque-Key-Preserve-Authorization",
            "X-Project-Gateway-Token",
        ):
            with self.subTest(header=header):
                self.assertEqual(2, template.count(f'proxy_set_header {header} "";'))


class F14ExtractTokenValidation(unittest.TestCase):
    SCRIPT = "servidor/generateProject/extract_token.sh"

    def test_source_validates_the_project_name(self) -> None:
        source = (ROOT / self.SCRIPT).read_text()
        self.assertRegex(
            source,
            r'\[\[ "\$PROJECT_NAME" =~ \^\[a-z0-9\]\[a-z0-9_-\]\{0,62\}\$\ \]\]',
        )

    def test_malformed_names_are_rejected_before_any_file_access(self) -> None:
        script = ROOT / self.SCRIPT
        for bad in ("../etc", "foo bar", "-x", "$(id)", "A" * 80):
            with self.subTest(name=bad):
                result = bash(f"bash '{script}' '{bad}'")
                self.assertNotEqual(0, result.returncode)
                self.assertIn("nome de projeto invalido", result.stderr)

    def test_valid_name_reaches_the_fixed_path(self) -> None:
        result = bash(f"bash '{ROOT / self.SCRIPT}' projeto_ok")
        self.assertNotEqual(0, result.returncode)
        self.assertNotIn("nome de projeto invalido", result.stderr)


class F15AdminModeGate(unittest.TestCase):
    def test_admin_listing_requires_a_platform_admin(self) -> None:
        lua = (
            ROOT / "studio/nginx/lua/admin_api/available_users.lua"
        ).read_text()
        gate_at = lua.index('admin_groups.is_admin(ngx.var.authelia_groups or "")')
        downgrade_at = lua.index('mode = "owner"')
        branch_at = lua.index('if mode == "admin" then')
        self.assertLess(gate_at, branch_at)
        self.assertLess(downgrade_at, branch_at)


class P3DocsAndDeadCode(unittest.TestCase):
    def test_runbook_matches_the_real_route(self) -> None:
        docs = (ROOT / "docs/12-opaque-api-key-operations.md").read_text()
        self.assertIn("/api/projects/{project}/api-key-slots/{slot_id}/rotation", docs)
        self.assertNotIn("/internal/projects/{project}/api-key-slots", docs)

    def test_runbook_uses_versioned_migration_names(self) -> None:
        docs = (ROOT / "docs/12-opaque-api-key-operations.md").read_text()
        self.assertIn("`0003_opaque_api_key_optional_expiration.sql`", docs)
        self.assertIn("`0002_step_up_grants.sql`", docs)
        self.assertNotIn("20260812_", docs)

    def test_acme_json_is_ignored(self) -> None:
        ignored = (ROOT / ".gitignore").read_text()
        self.assertIn("servidor/traefik/acme.json", ignored)

    def test_dead_pooler_script_is_gone(self) -> None:
        self.assertFalse(
            (ROOT / "servidor/volumes/pooler/init-tenant-realtime.sh").exists()
        )


if __name__ == "__main__":
    unittest.main()
