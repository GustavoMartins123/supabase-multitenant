"""Contract, unit, and live PostgreSQL 15 tests for T5 per-tenant DB credentials and platform_reader backfill."""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "servidor"
GENERATE = SERVER / "generateProject"
API_ROOT = SERVER / "api-internal"
APP = API_ROOT / "app"
TOOLS = ROOT / "tools"

if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pg_dump_filter = _load_module("t5_pg_dump_filter", GENERATE / "lib" / "pg_dump_filter.py")
sync_tool = _load_module("t5_sync_tool", TOOLS / "sync_existing_projects_security.py")


def _docker_has_postgres15() -> bool:
    if os.name == "nt" or not shutil.which("docker"):
        return False
    if os.getenv("T5_LIVE_POSTGRES") == "1":
        return True
    probe = subprocess.run(
        ["docker", "image", "inspect", "postgres:15"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class T5TemplateAndLifecycleContractTest(unittest.TestCase):
    def test_dockercomposetemplate_has_zero_postgres_password_and_uses_scoped_credentials(self) -> None:
        compose = (GENERATE / "dockercomposetemplate").read_text(encoding="utf-8")
        self.assertNotIn("POSTGRES_PASSWORD", compose)
        self.assertIn(
            "GOTRUE_DB_DATABASE_URL: postgres://${AUTH_DB_USER}.{{project_id}}:"
            "${AUTH_DB_PASSWORD:?defina AUTH_DB_PASSWORD no .env do projeto}"
            "@supabase-nginx-{{project_id}}:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}",
            compose,
        )
        self.assertIn(
            "PGRST_DB_URI: postgres://${POSTGREST_DB_USER}.{{project_id}}:"
            "${POSTGREST_DB_PASSWORD:?defina POSTGREST_DB_PASSWORD no .env do projeto}"
            "@supabase-nginx-{{project_id}}:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}",
            compose,
        )

    def test_envtemplate_declares_all_four_per_tenant_db_credential_placeholders(self) -> None:
        env_tpl = (GENERATE / ".envtemplate").read_text(encoding="utf-8")
        for line in (
            "AUTH_DB_USER={{auth_db_user}}",
            "AUTH_DB_PASSWORD={{auth_db_password}}",
            "POSTGREST_DB_USER={{postgrest_db_user}}",
            "POSTGREST_DB_PASSWORD={{postgrest_db_password}}",
        ):
            self.assertIn(line, env_tpl)
        self.assertNotIn("AUTH_DB_USER=supabase_auth_admin", env_tpl)
        self.assertNotIn("POSTGREST_DB_USER=authenticator", env_tpl)

    def test_tenant_service_roles_helper_security_invariants(self) -> None:
        helper = (GENERATE / "lib" / "tenant_service_roles.sh").read_text(encoding="utf-8")
        self.assertIn("SET LOCAL log_statement = 'none';", helper)
        self.assertIn(r"\getenv auth_pwd TENANT_AUTH_DB_PASSWORD", helper)
        self.assertIn(r"\getenv rest_pwd TENANT_REST_DB_PASSWORD", helper)
        # Passwords must never be passed as -e VAR=value in docker exec argv.
        self.assertNotRegex(helper, r"-e\s+TENANT_(?:AUTH|REST)_DB_PASSWORD=")
        self.assertIn("-e TENANT_AUTH_DB_PASSWORD", helper)
        self.assertIn("-e TENANT_REST_DB_PASSWORD", helper)
        self.assertIn(
            "LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L",
            helper,
        )
        self.assertIn(
            "LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L",
            helper,
        )
        self.assertIn("ARRAY['anon', 'authenticated', 'service_role']", helper)
        self.assertIn("GRANT supabase_auth_admin TO %I", helper)
        self.assertNotIn("GRANT authenticator TO", helper)
        self.assertIn("REVOKE CONNECT, TEMPORARY, CREATE ON DATABASE %I FROM PUBLIC", helper)
        self.assertIn("ARRAY['authenticator', 'supabase_auth_admin']", helper)
        self.assertIn("REVOKE CONNECT, TEMPORARY, CREATE ON DATABASE %I FROM %I", helper)

    def test_lifecycle_scripts_provision_reassign_and_rollback_service_roles(self) -> None:
        gen = (GENERATE / "lib" / "generate_project_impl.sh").read_text(encoding="utf-8")
        dup = (GENERATE / "lib" / "duplicate_project_impl.sh").read_text(encoding="utf-8")
        res = (GENERATE / "lib" / "restore_project_impl.sh").read_text(encoding="utf-8")

        for name, src in (("generate", gen), ("duplicate", dup), ("restore", res)):
            with self.subTest(script=name):
                self.assertIn('source "$SCRIPT_DIR/lib/tenant_service_roles.sh"', src)
                self.assertIn("provision_tenant_service_roles", src)
                self.assertIn("reassign_tenant_auth_objects_to_auth_admin", src)
                self.assertIn(
                    "REVOKE CONNECT, TEMPORARY, CREATE ON DATABASE",
                    src,
                )
                self.assertNotIn("GRANT CONNECT, TEMPORARY ON DATABASE $db TO authenticator", src)
                self.assertNotIn("GRANT CONNECT, TEMPORARY ON DATABASE $NEW_DB TO authenticator", src)
                self.assertNotIn("GRANT CONNECT, TEMPORARY ON DATABASE $DB TO authenticator", src)

        self.assertGreaterEqual(gen.count("drop_tenant_service_roles"), 3)  # rollback + old_uuid + stale loop
        self.assertIn("drop_tenant_service_roles", dup)
        self.assertIn("Clone nao pode reutilizar AUTH_DB_PASSWORD da origem", dup)
        self.assertIn("Clone nao pode reutilizar POSTGREST_DB_PASSWORD da origem", dup)
        self.assertIn('grant_platform_reader_on_tenant "$DB"', res)
        self.assertLess(
            res.index('backup_start_project_containers "$PROJECT"'),
            res.index('grant_platform_reader_on_tenant "$DB"'),
        )

        mig_sh = (GENERATE / "migrate_shared_storage.sh").read_text(encoding="utf-8")
        self.assertIn('source "$SCRIPT_DIR/lib/tenant_service_roles.sh"', mig_sh)
        self.assertIn('provision_tenant_service_roles "_supabase_$project" "$PROJECT_UUID"', mig_sh)
        self.assertLess(
            mig_sh.index('provision_tenant_service_roles "_supabase_$project" "$PROJECT_UUID"'),
            mig_sh.index('docker compose -p "$project" \\\n    --env-file ../../.env --env-file .env up --build -d'),
        )
        self.assertGreaterEqual(
            mig_sh.count('rollback_tenant_service_roles_to_legacy_db_access "_supabase_$project"'),
            2,
        )

    def test_deletion_drops_tenant_service_roles_via_bounded_security_definer(self) -> None:
        mig = (APP / "migrations" / "0036_tenant_service_role_cleanup.sql").read_text(encoding="utf-8")
        roles_py = (APP / "control_plane_roles.py").read_text(encoding="utf-8")
        deletion_py = (APP / "project_deletion.py").read_text(encoding="utf-8")
        backgrounds_py = (APP / "project_backgrounds.py").read_text(encoding="utf-8")

        self.assertIn("CREATE OR REPLACE FUNCTION public.drop_tenant_service_roles(target_tenant_uuid uuid)", mig)
        self.assertIn("SECURITY DEFINER SET search_path = pg_catalog", mig)
        self.assertIn("REVOKE ALL ON FUNCTION public.drop_tenant_service_roles(uuid) FROM PUBLIC;", mig)
        self.assertIn("USING ERRCODE = '55006'", mig)
        self.assertIn("GRANT EXECUTE ON FUNCTION public.drop_tenant_service_roles(uuid)", roles_py)
        self.assertIn("NOCREATEROLE INHERIT", roles_py)
        self.assertIn("SELECT public.drop_tenant_service_roles($1)", deletion_py)
        self.assertLess(
            backgrounds_py.index("await drop_database_force(conn, db_name)"),
            backgrounds_py.index("await drop_tenant_service_roles(conn, tenant_uuid)"),
        )

    def test_platform_reader_backfill_matches_exact_column_allowlist(self) -> None:
        roles_py = (APP / "control_plane_roles.py").read_text(encoding="utf-8")
        migrations_py = (APP / "schema_migrations.py").read_text(encoding="utf-8")
        reader_sh = (GENERATE / "lib" / "tenant_reader_role.sh").read_text(encoding="utf-8")

        self.assertIn("async def ensure_platform_reader_grants(", roles_py)
        self.assertIn("await ensure_platform_reader_grants(pool, admin_dsn=_require_dsn())", migrations_py)

        sh_users = re.search(
            r"GRANT\s+SELECT\s*\(([^)]+)\)\s+ON\s+auth\.users\s+TO\s+platform_reader;",
            reader_sh,
            re.DOTALL,
        )
        sh_sessions = re.search(
            r"GRANT\s+SELECT\s*\(([^)]+)\)\s+ON\s+auth\.sessions\s+TO\s+platform_reader;",
            reader_sh,
            re.DOTALL,
        )
        assert sh_users is not None and sh_sessions is not None
        expected_users = tuple(c.strip() for c in sh_users.group(1).split(",") if c.strip())
        expected_sessions = tuple(c.strip() for c in sh_sessions.group(1).split(",") if c.strip())

        from app.control_plane_roles import (
            PLATFORM_READER_AUTH_SESSIONS_COLUMNS,
            PLATFORM_READER_AUTH_USERS_COLUMNS,
        )

        self.assertEqual(PLATFORM_READER_AUTH_USERS_COLUMNS, expected_users)
        self.assertEqual(PLATFORM_READER_AUTH_SESSIONS_COLUMNS, expected_sessions)

    def test_secret_redaction_covers_auth_and_postgrest_db_passwords(self) -> None:
        from app.host_agent_protocol import sanitize_output

        auth_secret = "a" * 40
        rest_secret = "b" * 40
        sample = (
            f"AUTH_DB_PASSWORD={auth_secret} "
            f"POSTGREST_DB_PASSWORD={rest_secret} "
            f"postgres://tenant_auth_{'a' * 32}.proj:{auth_secret}@supabase-nginx-proj:5432/_supabase_proj"
        )
        cleaned = sanitize_output(sample)
        self.assertNotIn(auth_secret, cleaned)
        self.assertNotIn(rest_secret, cleaned)

        edge_routes = (APP / "routers" / "studio_edge_functions.py").read_text(encoding="utf-8")
        self.assertIn("'auth_db_password': str(env.get('AUTH_DB_PASSWORD') or '')", edge_routes)
        self.assertIn("'postgrest_db_password': str(env.get('POSTGREST_DB_PASSWORD') or '')", edge_routes)
        collect_fn = edge_routes.split("def _collect_sensitive_values(", 1)[1].split("\nasync def ", 1)[0]
        self.assertIn("'auth_db_password'", collect_fn)
        self.assertIn("'postgrest_db_password'", collect_fn)

    def test_pg_dump_filter_rewrites_tenant_auth_owner_and_strips_foreign_acls(self) -> None:
        old_hex = "a" * 32
        dump = (
            f"CREATE TABLE auth.identities (id uuid);\n"
            f"ALTER TABLE auth.identities OWNER TO tenant_auth_{old_hex};\n"
            f'ALTER SEQUENCE auth.refresh_tokens_id_seq OWNER TO "tenant_auth_{old_hex}";\n'
            f"ALTER DEFAULT PRIVILEGES FOR ROLE tenant_auth_{old_hex} IN SCHEMA auth\n"
            f"    GRANT SELECT, INSERT ON TABLES TO tenant_meta_{old_hex};\n"
            f"GRANT USAGE ON SCHEMA auth TO tenant_auth_{old_hex};\n"
            f"REVOKE ALL ON TABLE public.items FROM tenant_rest_{old_hex};\n"
            f"COPY public.notes (body) FROM stdin;\n"
            f"ALTER TABLE auth.identities OWNER TO tenant_auth_{old_hex};\n"
            f"\\.\n"
            f"SELECT 'ALTER TABLE auth.identities OWNER TO tenant_auth_{old_hex};';\n"
        )
        out = io.StringIO()
        removed = pg_dump_filter.filter_plain_sql(io.StringIO(dump), out)
        result = out.getvalue()
        self.assertEqual(removed, 3)
        self.assertIn("ALTER TABLE auth.identities OWNER TO supabase_auth_admin;\n", result)
        self.assertIn("ALTER SEQUENCE auth.refresh_tokens_id_seq OWNER TO supabase_auth_admin;\n", result)
        self.assertNotIn("ALTER DEFAULT PRIVILEGES FOR ROLE tenant_auth_", result)
        self.assertNotIn("GRANT USAGE ON SCHEMA auth TO tenant_auth_", result)
        self.assertNotIn("REVOKE ALL ON TABLE public.items FROM tenant_rest_", result)
        # COPY payload and SQL literal stay untouched.
        self.assertIn(f"COPY public.notes (body) FROM stdin;\nALTER TABLE auth.identities OWNER TO tenant_auth_{old_hex};\n\\.\n", result)
        self.assertIn(f"SELECT 'ALTER TABLE auth.identities OWNER TO tenant_auth_{old_hex};';\n", result)

        toc = (
            f"100; 1259 16384 TABLE public items supabase_admin\n"
            f"101; 826 16385 DEFAULT ACL auth DEFAULT PRIVILEGES FOR TABLES tenant_auth_{old_hex}\n"
            f"102; 0 0 ACL auth SCHEMA auth tenant_rest_{old_hex}\n"
        )
        toc_out = io.StringIO()
        toc_removed = pg_dump_filter.filter_toc(io.StringIO(toc), toc_out)
        self.assertEqual(toc_removed, 2)
        self.assertIn("TABLE public items", toc_out.getvalue())
        self.assertNotIn(f"tenant_auth_{old_hex}", toc_out.getvalue())
        self.assertNotIn(f"tenant_rest_{old_hex}", toc_out.getvalue())

    def test_render_env_protects_and_mints_per_tenant_db_credentials(self) -> None:
        tenant_uuid = "11111111-2222-4333-8444-555555555555"
        tenant_hex = tenant_uuid.replace("-", "")
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            old_env = base / "old.env"
            stale_auth = "x" * 40
            stale_rest = "y" * 40
            fresh_auth = "m" * 43
            fresh_rest = "n" * 43
            old_env.write_text(
                "API_EXTERNAL_URL=https://api.example.test/old/auth/v1\n"
                "SITE_URL=https://api.example.test/old/verify-success.html\n"
                "ADDITIONAL_REDIRECT_URLS=https://api.example.test/old/verify-success.html\n"
                "AUTH_DB_USER=supabase_auth_admin\n"
                "POSTGREST_DB_USER=authenticator\n"
                f"AUTH_DB_PASSWORD={stale_auth}\n"
                f"POSTGREST_DB_PASSWORD={stale_rest}\n",
                encoding="utf-8",
            )
            replacements = {
                "project_id": "demo_proj",
                "project_uuid": tenant_uuid,
                "project_public_ref": "abcdefghijklmnopqrst",
                "project_internal_subnet": "172.52.1.0/28",
                "project_root": "/srv/supabase",
                "project_public_url": "https://api.example.test/abcdefghijklmnopqrst",
                "project_auth_external_url": "https://api.example.test/abcdefghijklmnopqrst/auth/v1",
                "anon_key": "a.b.c",
                "service_role_key": "d.e.f",
                "jwt_secret": "j" * 43,
                "api_gateway_token": "f" * 64,
                "s3_protocol_credential_id": tenant_uuid,
                "s3_protocol_access_key_id": "k" * 32,
                "s3_protocol_access_key_secret": "s" * 64,
                "auth_db_password": fresh_auth,
                "postgrest_db_password": fresh_rest,
            }
            for script in ("render_project_env.py", "render_migrated_project_env.py"):
                out_path = base / f"{script}.env"
                proc = subprocess.run(
                    [sys.executable, str(GENERATE / script), str(GENERATE / ".envtemplate"), str(old_env), str(out_path)],
                    input=json.dumps(replacements),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                parsed = dict(
                    line.split("=", 1)
                    for line in out_path.read_text(encoding="utf-8").splitlines()
                    if "=" in line and not line.startswith("#")
                )
                self.assertEqual(parsed["AUTH_DB_USER"], f"tenant_auth_{tenant_hex}")
                self.assertEqual(parsed["POSTGREST_DB_USER"], f"tenant_rest_{tenant_hex}")
                self.assertEqual(parsed["AUTH_DB_PASSWORD"], replacements["auth_db_password"])
                self.assertEqual(parsed["POSTGREST_DB_PASSWORD"], replacements["postgrest_db_password"])
                self.assertEqual(out_path.stat().st_mode & 0o777, 0o600)

    def test_sync_tool_migrates_existing_project_dry_run_redacts_diff_and_applies_idempotently(self) -> None:
        tenant_uuid = "44444444-5555-4666-8777-888888888888"
        tenant_hex = tenant_uuid.replace("-", "")
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates = root / "generateProject"
            templates.mkdir()
            (templates / "dockercomposetemplate").write_text(
                (GENERATE / "dockercomposetemplate").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            server_env = root / ".env"
            server_env.write_text("SERVER_URL=api.example.test\nSERVER_PROTO=https\n", encoding="utf-8")
            projects = root / "projects"
            proj = projects / "legacy_proj"
            proj.mkdir(parents=True)
            env_path = proj / ".env"
            env_path.write_text(
                f"PROJECT_ID=legacy_proj\n"
                f"PROJECT_UUID={tenant_uuid}\n"
                f"PROJECT_PUBLIC_REF=abcdefghijklmnopqrst\n"
                f"AUTH_DB_USER=supabase_auth_admin\n"
                f"POSTGREST_DB_USER=authenticator\n"
                f"API_GATEWAY_TOKEN_PROJETO={'a' * 64}\n",
                encoding="utf-8",
            )
            os.chmod(env_path, 0o600)
            compose_path = proj / "docker-compose.yml"
            compose_path.write_text(
                "services:\n"
                "  nginx:\n"
                "    container_name: supabase-nginx-legacy_proj\n"
                "    environment:\n"
                "      ANON_KEY_PROJETO: ${ANON_KEY_PROJETO}\n"
                "      SERVICE_ROLE_KEY_PROJETO: ${SERVICE_ROLE_KEY_PROJETO}\n"
                "      API_GATEWAY_TOKEN_PROJETO: ${API_GATEWAY_TOKEN_PROJETO}\n"
                "  auth:\n"
                "    container_name: supabase-auth-legacy_proj\n"
                "    environment:\n"
                '      GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED: "true"\n'
                "      GOTRUE_DB_DATABASE_URL: postgres://${AUTH_DB_USER}.legacy_proj:${POSTGRES_PASSWORD}@supabase-nginx-legacy_proj:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n"
                "  rest:\n"
                "    container_name: supabase-rest-legacy_proj\n"
                "    environment:\n"
                "      PGRST_DB_URI: postgres://${POSTGREST_DB_USER}.legacy_proj:${POSTGRES_PASSWORD}@supabase-nginx-legacy_proj:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n",
                encoding="utf-8",
            )
            before_env = env_path.read_bytes()
            before_compose = compose_path.read_bytes()

            # 1. Dry-run with --diff must not mutate files and must redact minted passwords.
            dry_buf = io.StringIO()
            provisioned: list[tuple[str, str, str, str]] = []
            with contextlib.redirect_stdout(dry_buf):
                dry_res = sync_tool.sync_projects(
                    projects_dir=projects,
                    server_env_path=server_env,
                    templates_dir=templates,
                    apply=False,
                    skip_compose_validate=True,
                    migrate_db_credentials=True,
                    db_provisioner=lambda s, u, a, r: provisioned.append((s, u, a, r)),
                    show_diff=True,
                    template_history={},
                )
            self.assertEqual(dry_res, {"legacy_proj": "NEEDS_UPDATE"})
            self.assertEqual(provisioned, [])
            self.assertEqual(env_path.read_bytes(), before_env)
            self.assertEqual(compose_path.read_bytes(), before_compose)
            self.assertIn("+AUTH_DB_PASSWORD=<REDACTED>", dry_buf.getvalue())
            self.assertIn("+POSTGREST_DB_PASSWORD=<REDACTED>", dry_buf.getvalue())
            self.assertIn(f"+AUTH_DB_USER=tenant_auth_{tenant_hex}", dry_buf.getvalue())

            # 2. --apply invokes db_provisioner before updating live files and preserves hooks.
            apply_buf = io.StringIO()
            with contextlib.redirect_stdout(apply_buf):
                apply_res = sync_tool.sync_projects(
                    projects_dir=projects,
                    server_env_path=server_env,
                    templates_dir=templates,
                    apply=True,
                    skip_compose_validate=True,
                    migrate_db_credentials=True,
                    db_provisioner=lambda s, u, a, r: provisioned.append((s, u, a, r)),
                    template_history={},
                )
            self.assertEqual(apply_res, {"legacy_proj": "UPDATED"})
            self.assertEqual(len(provisioned), 1)
            slug_p, uuid_p, auth_pwd_p, rest_pwd_p = provisioned[0]
            self.assertEqual((slug_p, uuid_p), ("legacy_proj", tenant_uuid))
            self.assertNotEqual(auth_pwd_p, rest_pwd_p)

            env_after, _ = sync_tool.parse_env_file(env_path)
            self.assertEqual(env_after["AUTH_DB_USER"], f"tenant_auth_{tenant_hex}")
            self.assertEqual(env_after["POSTGREST_DB_USER"], f"tenant_rest_{tenant_hex}")
            self.assertEqual(env_after["AUTH_DB_PASSWORD"], auth_pwd_p)
            self.assertEqual(env_after["POSTGREST_DB_PASSWORD"], rest_pwd_p)
            self.assertEqual(env_path.stat().st_mode & 0o777, 0o600)

            compose_after = compose_path.read_text(encoding="utf-8")
            self.assertNotIn("POSTGRES_PASSWORD", compose_after)
            self.assertIn(sync_tool.AUTH_DB_PASSWORD_INTERP, compose_after)
            self.assertIn(sync_tool.POSTGREST_DB_PASSWORD_INTERP, compose_after)
            self.assertIn('GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED: "true"', compose_after)

            # 3. Second pass is idempotent (UP_TO_DATE, no extra DB provisioner calls).
            second_buf = io.StringIO()
            with contextlib.redirect_stdout(second_buf):
                second_res = sync_tool.sync_projects(
                    projects_dir=projects,
                    server_env_path=server_env,
                    templates_dir=templates,
                    apply=True,
                    skip_compose_validate=True,
                    migrate_db_credentials=True,
                    db_provisioner=lambda s, u, a, r: provisioned.append((s, u, a, r)),
                    template_history={},
                )
            self.assertEqual(second_res, {"legacy_proj": "UP_TO_DATE"})
            self.assertEqual(len(provisioned), 1)

            # 4. Missing PROJECT_UUID fails closed without mutating files.
            broken = projects / "broken_proj"
            broken.mkdir()
            (broken / ".env").write_text("PROJECT_ID=broken_proj\n", encoding="utf-8")
            (broken / "docker-compose.yml").write_bytes(before_compose)
            broken_buf = io.StringIO()
            with contextlib.redirect_stdout(broken_buf):
                broken_res = sync_tool.sync_projects(
                    projects_dir=projects,
                    server_env_path=server_env,
                    templates_dir=templates,
                    selected_projects=["broken_proj"],
                    apply=True,
                    skip_compose_validate=True,
                    migrate_db_credentials=True,
                    db_provisioner=lambda s, u, a, r: provisioned.append((s, u, a, r)),
                    template_history={},
                )
            self.assertEqual(broken_res, {"broken_proj": "NEEDS_REVIEW"})
            self.assertEqual((broken / "docker-compose.yml").read_bytes(), before_compose)

    def test_sync_tool_does_not_skip_db_provision_when_only_skip_compose_validate_is_set(self) -> None:
        from unittest import mock

        tenant_uuid = "55555555-6666-4777-8888-999999999999"
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates = root / "generateProject"
            templates.mkdir()
            (templates / "dockercomposetemplate").write_text(
                (GENERATE / "dockercomposetemplate").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            server_env = root / ".env"
            server_env.write_text("SERVER_URL=api.example.test\nSERVER_PROTO=https\n", encoding="utf-8")
            projects = root / "projects"
            proj = projects / "skip_test_proj"
            proj.mkdir(parents=True)
            (proj / ".env").write_text(
                f"PROJECT_ID=skip_test_proj\nPROJECT_UUID={tenant_uuid}\n"
                f"PROJECT_PUBLIC_REF=abcdefghijklmnopqrst\n"
                f"AUTH_DB_USER=supabase_auth_admin\nPOSTGREST_DB_USER=authenticator\n"
                f"API_GATEWAY_TOKEN_PROJETO={'a' * 64}\n",
                encoding="utf-8",
            )
            (proj / "docker-compose.yml").write_text(
                "services:\n"
                "  nginx:\n"
                "    environment:\n"
                "      ANON_KEY_PROJETO: ${ANON_KEY_PROJETO}\n"
                "      SERVICE_ROLE_KEY_PROJETO: ${SERVICE_ROLE_KEY_PROJETO}\n"
                "      API_GATEWAY_TOKEN_PROJETO: ${API_GATEWAY_TOKEN_PROJETO}\n"
                "  auth:\n"
                "    environment:\n"
                "      GOTRUE_DB_DATABASE_URL: postgres://${AUTH_DB_USER}.skip_test_proj:${POSTGRES_PASSWORD}@supabase-nginx-skip_test_proj:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n"
                "  rest:\n"
                "    environment:\n"
                "      PGRST_DB_URI: postgres://${POSTGREST_DB_USER}.skip_test_proj:${POSTGRES_PASSWORD}@supabase-nginx-skip_test_proj:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n",
                encoding="utf-8",
            )

            called: list[tuple] = []
            with mock.patch.object(
                sync_tool,
                "provision_project_db_service_roles",
                side_effect=lambda *args: called.append(args),
            ):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    res = sync_tool.sync_projects(
                        projects_dir=projects,
                        server_env_path=server_env,
                        templates_dir=templates,
                        apply=True,
                        skip_compose_validate=True,
                        migrate_db_credentials=True,
                        skip_db_provision=False,
                        template_history={},
                    )
            self.assertEqual(res, {"skip_test_proj": "UPDATED"})
            self.assertEqual(len(called), 1)
            self.assertEqual(called[0][1], "skip_test_proj")
            self.assertEqual(called[0][2], tenant_uuid)


@unittest.skipUnless(
    _docker_has_postgres15(),
    "Live disposable postgres:15 container required (pull postgres:15 or set T5_LIVE_POSTGRES=1)",
)
class T5LivePostgresIsolationTest(unittest.TestCase):
    container_name: str = ""
    port: int = 0
    admin_password: str = ""
    admin_dsn: str = ""
    reader_password: str = ""
    authenticator_password: str = ""
    auth_admin_password: str = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.container_name = f"t5-live-pg-{secrets.token_hex(6)}"
        cls.port = _free_tcp_port()
        cls.admin_password = f"AdminPass_{secrets.token_hex(16)}"
        cls.reader_password = secrets.token_urlsafe(32)
        cls.authenticator_password = secrets.token_urlsafe(24)
        cls.auth_admin_password = secrets.token_urlsafe(24)
        cls.admin_dsn = f"postgresql://supabase_admin:{cls.admin_password}@127.0.0.1:{cls.port}/postgres"

        start = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                cls.container_name,
                "-p",
                f"127.0.0.1:{cls.port}:5432",
                "-e",
                "POSTGRES_USER=supabase_admin",
                "-e",
                f"POSTGRES_PASSWORD={cls.admin_password}",
                "-e",
                "POSTGRES_DB=postgres",
                "postgres:15",
                "-c",
                "log_statement=all",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if start.returncode != 0:
            raise RuntimeError(f"Failed to start disposable postgres:15: {start.stderr}")

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    cls.container_name,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "supabase_admin",
                    "-d",
                    "postgres",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            logs = subprocess.run(
                ["docker", "logs", cls.container_name], capture_output=True, text=True, check=False
            ).stdout
            cls.tearDownClass()
            raise RuntimeError(f"Disposable postgres:15 readiness timeout:\n{logs}")

        # Seed Supabase-equivalent global roles & control-plane DB lock.
        storage_pwd = secrets.token_urlsafe(24)
        pgbouncer_pwd = secrets.token_urlsafe(24)
        cls._psql_admin(
            "postgres",
            f"""
            CREATE ROLE anon NOLOGIN;
            CREATE ROLE authenticated NOLOGIN;
            CREATE ROLE service_role NOLOGIN BYPASSRLS;
            CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD '{cls.authenticator_password}';
            GRANT anon, authenticated, service_role TO authenticator;
            ALTER ROLE authenticator SET lock_timeout = '8s';
            ALTER ROLE authenticator SET statement_timeout = '8s';
            CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE PASSWORD '{cls.auth_admin_password}';
            CREATE ROLE supabase_storage_admin LOGIN NOINHERIT CREATEROLE PASSWORD '{storage_pwd}';
            CREATE ROLE pgbouncer LOGIN PASSWORD '{pgbouncer_pwd}';
            CREATE ROLE platform_reader LOGIN PASSWORD '{cls.reader_password}';
            REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC;
            """,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        if cls.container_name:
            subprocess.run(
                ["docker", "rm", "-f", cls.container_name],
                capture_output=True,
                text=True,
                check=False,
            )

    @classmethod
    def _psql_admin(cls, database: str, sql: str) -> str:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                cls.container_name,
                "psql",
                "-X",
                "-q",
                "-t",
                "-A",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "supabase_admin",
                "-d",
                database,
            ],
            input=sql,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"Admin psql failed on {database}: {proc.stderr}")
        return proc.stdout.strip()

    @classmethod
    def _psql_as(cls, role: str, password: str, database: str, sql: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PGPASSWORD"] = password
        return subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                "-e",
                "PGPASSWORD",
                cls.container_name,
                "psql",
                "-X",
                "-q",
                "-t",
                "-A",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                "127.0.0.1",
                "-U",
                role,
                "-d",
                database,
            ],
            input=sql,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def _run_service_roles_bash(self, snippet: str, extra_env: dict[str, str] | None = None) -> None:
        env = os.environ.copy()
        env["SUPABASE_DB_CONTAINER"] = self.container_name
        env["SUPABASE_DB_ADMIN_USER"] = "supabase_admin"
        if extra_env:
            env.update(extra_env)
        helper = GENERATE / "lib" / "tenant_service_roles.sh"
        proc = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", f'source "{helper}"; {snippet}'],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, f"bash failed: {proc.stderr}\n{proc.stdout}")

    def test_end_to_end_tenant_isolation_platform_reader_backfill_and_bounded_drop(self) -> None:
        import asyncpg
        from app import control_plane_roles, schema_migrations

        uuid_a = str(uuid.uuid4())
        uuid_b = str(uuid.uuid4())
        hex_a = uuid_a.replace("-", "")
        hex_b = uuid_b.replace("-", "")
        db_a = "_supabase_t5_alpha"
        db_b = "_supabase_t5_beta"
        auth_role_a = f"tenant_auth_{hex_a}"
        rest_role_a = f"tenant_rest_{hex_a}"
        auth_role_b = f"tenant_auth_{hex_b}"
        rest_role_b = f"tenant_rest_{hex_b}"
        auth_pwd_a = "T5AuthPassA_" + secrets.token_urlsafe(24)
        rest_pwd_a = "T5RestPassA_" + secrets.token_urlsafe(24)
        auth_pwd_b = "T5AuthPassB_" + secrets.token_urlsafe(24)
        rest_pwd_b = "T5RestPassB_" + secrets.token_urlsafe(24)
        meta_admin_pwd = "MetaAdminPwd_" + secrets.token_hex(24)

        for db in (db_a, db_b):
            self._psql_admin("postgres", f'CREATE DATABASE "{db}";')
            self._psql_admin(
                db,
                """
                CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;
                CREATE TABLE auth.users (
                    id uuid PRIMARY KEY,
                    email text,
                    phone text,
                    email_confirmed_at timestamptz,
                    created_at timestamptz DEFAULT now(),
                    last_sign_in_at timestamptz,
                    raw_user_meta_data jsonb,
                    is_sso_user boolean DEFAULT false,
                    encrypted_password text,
                    confirmation_token text,
                    recovery_token text,
                    email_change_token_new text
                );
                ALTER TABLE auth.users OWNER TO supabase_auth_admin;
                INSERT INTO auth.users(id, email, encrypted_password, confirmation_token, recovery_token)
                VALUES (
                    '00000000-0000-4000-8000-000000000001',
                    'alice@example.test',
                    '$2a$10$secretbcrypt',
                    'confirm-tok-secret',
                    'recover-tok-secret'
                );
                CREATE TABLE auth.sessions (
                    id uuid PRIMARY KEY,
                    user_id uuid NOT NULL,
                    created_at timestamptz DEFAULT now(),
                    refresh_token_hmac_key text,
                    ip text,
                    user_agent text
                );
                ALTER TABLE auth.sessions OWNER TO supabase_auth_admin;
                INSERT INTO auth.sessions(id, user_id, refresh_token_hmac_key, ip, user_agent)
                VALUES (
                    '00000000-0000-4000-8000-000000000002',
                    '00000000-0000-4000-8000-000000000001',
                    'hmac-secret',
                    '10.0.0.1',
                    'curl/8'
                );
                -- Deliberately seed pre-PR-#52 blanket SELECT grant to verify backfill tightening.
                GRANT CONNECT ON DATABASE """
                + f'"{db}"'
                + """ TO platform_reader;
                GRANT USAGE ON SCHEMA auth TO platform_reader;
                GRANT SELECT ON TABLE auth.users, auth.sessions TO platform_reader;
                """,
            )

        # 1. Provision per-tenant service roles for A and B using the REAL bash helper.
        self._run_service_roles_bash(
            f'provision_tenant_service_roles "{db_a}" "{uuid_a}" "$PWD_A_AUTH" "$PWD_A_REST"',
            {"PWD_A_AUTH": auth_pwd_a, "PWD_A_REST": rest_pwd_a},
        )
        self._run_service_roles_bash(
            f'provision_tenant_service_roles "{db_b}" "{uuid_b}" "$PWD_B_AUTH" "$PWD_B_REST"',
            {"PWD_B_AUTH": auth_pwd_b, "PWD_B_REST": rest_pwd_b},
        )

        # 2. tenant_auth_A & tenant_rest_A connect to _supabase_t5_alpha cleanly.
        auth_ok = self._psql_as(auth_role_a, auth_pwd_a, db_a, "SELECT current_user, current_setting('search_path');")
        self.assertEqual(auth_ok.returncode, 0, auth_ok.stderr)
        self.assertIn(f"{auth_role_a}|auth", auth_ok.stdout)

        rest_ok = self._psql_as(
            rest_role_a,
            rest_pwd_a,
            db_a,
            "SELECT current_setting('lock_timeout'), current_setting('statement_timeout');"
            "SET ROLE anon; SELECT current_user;"
            "RESET ROLE; SET ROLE authenticated; SELECT current_user;"
            "RESET ROLE; SET ROLE service_role; SELECT current_user;",
        )
        self.assertEqual(rest_ok.returncode, 0, rest_ok.stderr)
        self.assertIn("8s|8s", rest_ok.stdout)
        self.assertIn("anon", rest_ok.stdout)
        self.assertIn("authenticated", rest_ok.stdout)
        self.assertIn("service_role", rest_ok.stdout)

        # Verify tenant_rest_A has NOINHERIT and NO membership in authenticator.
        rest_flags = self._psql_admin(
            "postgres",
            f"SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolbypassrls, "
            f"pg_has_role('{rest_role_a}', 'authenticator', 'MEMBER') "
            f"FROM pg_roles WHERE rolname = '{rest_role_a}';",
        )
        self.assertEqual(rest_flags, "t|f|f|f|f|f")

        # Verify tenant_auth_A has INHERIT, NOCREATEROLE, and membership in supabase_auth_admin.
        auth_flags = self._psql_admin(
            "postgres",
            f"SELECT rolcanlogin, rolinherit, rolsuper, rolcreaterole, rolbypassrls, "
            f"pg_has_role('{auth_role_a}', 'supabase_auth_admin', 'MEMBER') "
            f"FROM pg_roles WHERE rolname = '{auth_role_a}';",
        )
        self.assertEqual(auth_flags, "t|t|f|f|f|t")

        # 3. Cross-tenant login denial: tenant_auth_A & tenant_rest_A DENIED on _supabase_t5_beta & postgres.
        for role, pwd in ((auth_role_a, auth_pwd_a), (rest_role_a, rest_pwd_a)):
            for forbidden_db in (db_b, "postgres"):
                with self.subTest(role=role, forbidden_db=forbidden_db):
                    denied = self._psql_as(role, pwd, forbidden_db, "SELECT 1;")
                    self.assertNotEqual(denied.returncode, 0)
                    self.assertIn("permission denied for database", denied.stderr.lower())

        # Shared global roles authenticator and supabase_auth_admin are ALSO denied on tenant DBs.
        for shared_role, shared_pwd in (
            ("authenticator", self.authenticator_password),
            ("supabase_auth_admin", self.auth_admin_password),
        ):
            for tenant_db in (db_a, db_b):
                with self.subTest(shared_role=shared_role, tenant_db=tenant_db):
                    denied = self._psql_as(shared_role, shared_pwd, tenant_db, "SELECT 1;")
                    self.assertNotEqual(denied.returncode, 0)
                    self.assertIn("permission denied for database", denied.stderr.lower())

        # 4. GoTrue migration simulation: tenant_auth_A creates auth.identities -> owned by tenant_auth_A,
        # then reassign + tenant_meta_role.sql + studio_storage_policies.sql succeed cleanly!
        create_identities = self._psql_as(
            auth_role_a,
            auth_pwd_a,
            db_a,
            "CREATE TABLE auth.identities (id uuid PRIMARY KEY, user_id uuid NOT NULL);",
        )
        self.assertEqual(create_identities.returncode, 0, create_identities.stderr)
        self._run_service_roles_bash(f'reassign_tenant_auth_objects_to_auth_admin "{db_a}"')
        identities_owner = self._psql_admin(
            db_a,
            "SELECT r.rolname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='auth' AND c.relname='identities';",
        )
        self.assertEqual(identities_owner, "supabase_auth_admin")

        # 5. Control-plane migrations (including 0036) + ensure_tenant_meta_roles + ensure_platform_reader_grants.
        async def run_control_plane_checks() -> None:
            pool = await asyncpg.create_pool(self.admin_dsn, min_size=1, max_size=2)
            try:
                async with pool.acquire() as conn:
                    await schema_migrations.apply_migrations(conn)
                    owner_id = uuid.uuid4()
                    await conn.execute(
                        "INSERT INTO users(id, authelia_username) VALUES($1, 't5_owner')",
                        owner_id,
                    )
                    await conn.execute(
                        "INSERT INTO projects(id, tenant_uuid, name, display_name, owner_id, public_ref) "
                        "VALUES($1, $1, 't5_alpha', 't5_alpha', $2, 'aaaaaaaaaaaaaaaaaaaa')",
                        uuid.UUID(uuid_a),
                        owner_id,
                    )
                    await conn.execute(
                        "INSERT INTO projects(id, tenant_uuid, name, display_name, owner_id, public_ref) "
                        "VALUES($1, $1, 't5_beta', 't5_beta', $2, 'bbbbbbbbbbbbbbbbbbbb')",
                        uuid.UUID(uuid_b),
                        owner_id,
                    )
                await control_plane_roles.ensure_platform_meta_admin_role(
                    pool, password=meta_admin_pwd
                )
                await control_plane_roles.ensure_tenant_meta_roles(
                    pool, admin_dsn=self.admin_dsn, password=meta_admin_pwd
                )
                await control_plane_roles.ensure_platform_reader_grants(
                    pool, admin_dsn=self.admin_dsn
                )
            finally:
                await pool.close()

        asyncio.run(run_control_plane_checks())

        # Verify tenant_meta_A can read a brand-new table created LATER by tenant_auth_A via ALTER DEFAULT PRIVILEGES!
        later_tbl = self._psql_as(
            auth_role_a,
            auth_pwd_a,
            db_a,
            "CREATE TABLE auth.mfa_factors_t5 (id int PRIMARY KEY); INSERT INTO auth.mfa_factors_t5 VALUES (42);",
        )
        self.assertEqual(later_tbl.returncode, 0, later_tbl.stderr)
        from app.tenant_meta_identity import tenant_meta_credentials

        meta_role_a, meta_pwd_a = tenant_meta_credentials(uuid_a, meta_admin_pwd)
        meta_read = self._psql_as(meta_role_a, meta_pwd_a, db_a, "SELECT id FROM auth.mfa_factors_t5;")
        self.assertEqual(meta_read.returncode, 0, meta_read.stderr)
        self.assertEqual(meta_read.stdout.strip(), "42")

        # 6. Verify platform_reader strict column-level allowlist after backfill!
        reader_pwd = self.reader_password
        allowed_users = self._psql_as(
            "platform_reader",
            reader_pwd,
            db_a,
            "SELECT id, email, phone, email_confirmed_at, created_at, last_sign_in_at, "
            "raw_user_meta_data, is_sso_user FROM auth.users;",
        )
        self.assertEqual(allowed_users.returncode, 0, allowed_users.stderr)
        self.assertIn("alice@example.test", allowed_users.stdout)

        allowed_sessions = self._psql_as(
            "platform_reader",
            reader_pwd,
            db_a,
            "SELECT id, user_id, created_at FROM auth.sessions;",
        )
        self.assertEqual(allowed_sessions.returncode, 0, allowed_sessions.stderr)
        self.assertIn("00000000-0000-4000-8000-000000000002", allowed_sessions.stdout)

        for forbidden_query in (
            "SELECT encrypted_password FROM auth.users;",
            "SELECT confirmation_token FROM auth.users;",
            "SELECT recovery_token FROM auth.users;",
            "SELECT email_change_token_new FROM auth.users;",
            "SELECT refresh_token_hmac_key FROM auth.sessions;",
            "SELECT ip, user_agent FROM auth.sessions;",
        ):
            with self.subTest(query=forbidden_query):
                res = self._psql_as("platform_reader", reader_pwd, db_a, forbidden_query)
                self.assertNotEqual(res.returncode, 0)
                self.assertIn("permission denied", res.stderr.lower())

        # 7. Verify bounded role cleanup via platform_meta_admin (NOCREATEROLE!) after DROP DATABASE.
        meta_admin_dsn = f"postgresql://platform_meta_admin:{meta_admin_pwd}@127.0.0.1:{self.port}/postgres"

        async def test_bounded_drop() -> None:
            conn = await asyncpg.connect(meta_admin_dsn)
            try:
                # Must REFUSE while database still exists (55006).
                with self.assertRaises(asyncpg.PostgresError) as ctx_live:
                    await conn.execute(
                        "SELECT public.drop_tenant_service_roles($1)", uuid.UUID(uuid_a)
                    )
                self.assertEqual(ctx_live.exception.sqlstate, "55006")

                # Must REFUSE for unknown tenant UUID (42501).
                with self.assertRaises(asyncpg.PostgresError) as ctx_unknown:
                    await conn.execute(
                        "SELECT public.drop_tenant_service_roles($1)", uuid.uuid4()
                    )
                self.assertEqual(ctx_unknown.exception.sqlstate, "42501")

                # After DROP DATABASE WITH (FORCE), platform_meta_admin cleanly drops both roles!
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_a}" WITH (FORCE)')
                await conn.execute(
                    "SELECT public.drop_tenant_service_roles($1)", uuid.UUID(uuid_a)
                )
                # Idempotent second call succeeds cleanly.
                await conn.execute(
                    "SELECT public.drop_tenant_service_roles($1)", uuid.UUID(uuid_a)
                )
            finally:
                await conn.close()

        asyncio.run(test_bounded_drop())

        remaining_a = self._psql_admin(
            "postgres",
            f"SELECT count(*) FROM pg_roles WHERE rolname IN ('{auth_role_a}', '{rest_role_a}');",
        )
        self.assertEqual(remaining_a, "0")
        # Tenant B roles remain intact.
        remaining_b = self._psql_admin(
            "postgres",
            f"SELECT count(*) FROM pg_roles WHERE rolname IN ('{auth_role_b}', '{rest_role_b}');",
        )
        self.assertEqual(remaining_b, "2")

        # 8. Verify multi-library session_preload_libraries quoting, post-sync default privileges,
        # and rollback_tenant_service_roles_to_legacy_db_access on a live (non-dropped) DB.
        uuid_c = str(uuid.uuid4())
        hex_c = uuid_c.replace("-", "")
        db_c = "_supabase_t5_gamma"
        auth_role_c = f"tenant_auth_{hex_c}"
        rest_role_c = f"tenant_rest_{hex_c}"
        meta_role_c = f"tenant_meta_{hex_c}"
        meta_pwd_c = secrets.token_urlsafe(24)
        auth_pwd_c = "T5AuthPassC_" + secrets.token_urlsafe(24)
        rest_pwd_c = "T5RestPassC_" + secrets.token_urlsafe(24)

        self._psql_admin("postgres", f'CREATE DATABASE "{db_c}";')
        self._psql_admin(
            db_c,
            f"""
            CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;
            CREATE ROLE {meta_role_c} LOGIN PASSWORD '{meta_pwd_c}';
            GRANT CONNECT ON DATABASE "{db_c}" TO {meta_role_c};
            GRANT USAGE ON SCHEMA auth TO {meta_role_c};
            ALTER ROLE authenticator SET session_preload_libraries TO 'lib_alpha', 'lib_beta';
            """,
        )
        try:
            self._run_service_roles_bash(
                f'provision_tenant_service_roles "{db_c}" "{uuid_c}" "$PWD_C_AUTH" "$PWD_C_REST"',
                {"PWD_C_AUTH": auth_pwd_c, "PWD_C_REST": rest_pwd_c},
            )
            rest_c_preload = self._psql_admin(
                "postgres",
                f"SELECT cfg FROM pg_roles r, unnest(r.rolconfig) cfg "
                f"WHERE r.rolname = '{rest_role_c}' AND cfg LIKE 'session_preload_libraries=%';",
            )
            self.assertEqual(rest_c_preload, "session_preload_libraries=lib_alpha, lib_beta")
            self.assertNotIn('"', rest_c_preload)
        finally:
            self._psql_admin("postgres", "ALTER ROLE authenticator RESET session_preload_libraries;")

        # Without running tenant_meta_role.sql again, provision_tenant_service_roles must already
        # have configured ALTER DEFAULT PRIVILEGES FOR ROLE tenant_auth_C IN SCHEMA auth -> tenant_meta_C.
        post_sync_tbl = self._psql_as(
            auth_role_c,
            auth_pwd_c,
            db_c,
            "CREATE TABLE auth.post_sync_check (v int PRIMARY KEY); INSERT INTO auth.post_sync_check VALUES (77);",
        )
        self.assertEqual(post_sync_tbl.returncode, 0, post_sync_tbl.stderr)
        meta_c_read = self._psql_as(meta_role_c, meta_pwd_c, db_c, "SELECT v FROM auth.post_sync_check;")
        self.assertEqual(meta_c_read.returncode, 0, meta_c_read.stderr)
        self.assertEqual(meta_c_read.stdout.strip(), "77")

        # Rollback helper on live DB must reassign auth objects, restore legacy CONNECT, and drop roles cleanly.
        self._run_service_roles_bash(
            f'rollback_tenant_service_roles_to_legacy_db_access "{db_c}" "{uuid_c}"'
        )
        remaining_c = self._psql_admin(
            "postgres",
            f"SELECT count(*) FROM pg_roles WHERE rolname IN ('{auth_role_c}', '{rest_role_c}');",
        )
        self.assertEqual(remaining_c, "0")
        post_sync_owner = self._psql_admin(
            db_c,
            "SELECT r.rolname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='auth' AND c.relname='post_sync_check';",
        )
        self.assertEqual(post_sync_owner, "supabase_auth_admin")
        restored_auth_conn = self._psql_as("supabase_auth_admin", self.auth_admin_password, db_c, "SELECT 1;")
        self.assertEqual(restored_auth_conn.returncode, 0, restored_auth_conn.stderr)
        restored_rest_conn = self._psql_as("authenticator", self.authenticator_password, db_c, "SELECT 1;")
        self.assertEqual(restored_rest_conn.returncode, 0, restored_rest_conn.stderr)

        # 9. Verify ZERO tenant service passwords appear in PostgreSQL logs (even with log_statement=all!).
        pg_logs = subprocess.run(
            ["docker", "logs", self.container_name],
            capture_output=True,
            text=True,
            check=False,
        )
        combined_logs = pg_logs.stdout + pg_logs.stderr
        for secret_pwd in (auth_pwd_a, rest_pwd_a, auth_pwd_b, rest_pwd_b, auth_pwd_c, rest_pwd_c):
            self.assertNotIn(secret_pwd, combined_logs)


if __name__ == "__main__":
    unittest.main()
