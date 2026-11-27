"""Unit, contract, and mocked-runtime tests for FDW guard dump filtering & lifecycle."""
from __future__ import annotations

import gzip
import hashlib
import hmac
import importlib.util
import io
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest

from tests.smoke.common import bash_path, git_compatible_bash

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER_ROOT = ROOT / "servidor"
GENERATE_DIR = SERVER_ROOT / "generateProject"
LIB_DIR = GENERATE_DIR / "lib"

_SPEC = importlib.util.spec_from_file_location("pg_dump_filter", LIB_DIR / "pg_dump_filter.py")
assert _SPEC is not None and _SPEC.loader is not None
pg_dump_filter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pg_dump_filter)


def _write_executable(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class PgDumpFilterUnitTests(unittest.TestCase):
    def test_toc_filter_strips_only_guard_event_trigger(self) -> None:
        raw_toc = textwrap.dedent(
            """\
            ;
            ; Selected TOC Entries:
            ;
            7; 2615 16387 SCHEMA - user_schema supabase_admin
            216; 1259 16390 TABLE public items supabase_admin
            3412; 0 16390 TABLE DATA public items supabase_admin
            3267; 3466 16389 EVENT TRIGGER - my_user_event_trigger supabase_admin
            3268; 3466 16390 EVENT TRIGGER - studio_guard_system_trigger_security supabase_admin
            3269; 3466 16391 EVENT TRIGGER - studio_vector_fdw_enforce_server_endpoint_custom supabase_admin
            3266; 3466 16386 EVENT TRIGGER - studio_vector_fdw_enforce_server_endpoint supabase_admin
            3270; 3466 16392 EVENT TRIGGER - "studio_vector_fdw_enforce_server_endpoint" supabase_admin
            3415; 0 0 COMMENT - EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint supabase_admin
            3416; 0 0 COMMENT - EVENT TRIGGER my_user_event_trigger supabase_admin
            """
        )
        out = io.StringIO()
        removed = pg_dump_filter.filter_toc(io.StringIO(raw_toc), out)
        filtered = out.getvalue()

        self.assertEqual(removed, 3)
        self.assertNotIn("EVENT TRIGGER - studio_vector_fdw_enforce_server_endpoint ", filtered)
        self.assertNotIn('EVENT TRIGGER - "studio_vector_fdw_enforce_server_endpoint" ', filtered)
        self.assertNotIn("COMMENT - EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ", filtered)
        self.assertIn("EVENT TRIGGER - my_user_event_trigger supabase_admin", filtered)
        self.assertIn("COMMENT - EVENT TRIGGER my_user_event_trigger supabase_admin", filtered)
        self.assertIn("EVENT TRIGGER - studio_guard_system_trigger_security supabase_admin", filtered)
        self.assertIn("EVENT TRIGGER - studio_vector_fdw_enforce_server_endpoint_custom supabase_admin", filtered)
        self.assertIn("TABLE public items supabase_admin", filtered)

    def test_plain_sql_filter_strips_guard_trigger_and_preserves_data_and_user_triggers(self) -> None:
        raw_sql = textwrap.dedent(
            """\
            \\restrict abc123
            CREATE TABLE public.items (id int, note text);
            SELECT foo$bar$baz FROM public.items;
            SELECT E'escaped \\' quote; CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint;';
            /* outer /* nested */ comment
            CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end;
            */
            COPY public.items (id, note) FROM stdin;
            1\tCREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end;
            \\.
            CREATE FUNCTION public.doc_example() RETURNS text LANGUAGE sql AS $$
            CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end
              EXECUTE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint();
            $$;
            CREATE EVENT TRIGGER my_user_event_trigger ON ddl_command_end
               EXECUTE FUNCTION public.my_evt();
            ALTER EVENT TRIGGER my_user_event_trigger OWNER TO supabase_admin;
            CREATE EVENT TRIGGER studio_guard_system_trigger_security ON ddl_command_end
               WHEN TAG IN ('CREATE FUNCTION', 'ALTER FUNCTION', 'CREATE TRIGGER')
               EXECUTE FUNCTION studio_trigger_guard.enforce_system_trigger_security();
            CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end
                     WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')
               EXECUTE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint();
            ALTER EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint OWNER TO supabase_admin;
            COMMENT ON EVENT TRIGGER "studio_vector_fdw_enforce_server_endpoint" IS 'pinned; guard';
            \\unrestrict abc123
            """
        )
        out = io.StringIO()
        removed = pg_dump_filter.filter_plain_sql(io.StringIO(raw_sql), out)
        filtered = out.getvalue()

        self.assertEqual(removed, 3)
        self.assertIn("\\restrict abc123", filtered)
        self.assertIn("\\unrestrict abc123", filtered)
        self.assertIn("1\tCREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end;", filtered)
        self.assertIn("CREATE FUNCTION public.doc_example()", filtered)
        self.assertIn("CREATE EVENT TRIGGER my_user_event_trigger ON ddl_command_end", filtered)
        self.assertIn("ALTER EVENT TRIGGER my_user_event_trigger OWNER TO supabase_admin;", filtered)
        self.assertIn("CREATE EVENT TRIGGER studio_guard_system_trigger_security ON ddl_command_end", filtered)
        self.assertNotIn("ALTER EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint", filtered)
        self.assertNotIn('COMMENT ON EVENT TRIGGER "studio_vector_fdw_enforce_server_endpoint"', filtered)
        self.assertNotIn("WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')", filtered)

    def test_cli_modes_and_invalid_invocation(self) -> None:
        script = LIB_DIR / "pg_dump_filter.py"
        toc_res = subprocess.run(
            [sys.executable, str(script), "toc"],
            input=(
                "3266; 3466 16386 EVENT TRIGGER - studio_vector_fdw_enforce_server_endpoint supabase_admin\n"
                "3267; 3466 16389 EVENT TRIGGER - my_evt supabase_admin\n"
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(toc_res.returncode, 0, toc_res.stderr)
        self.assertNotIn("studio_vector_fdw_enforce_server_endpoint", toc_res.stdout)
        self.assertIn("my_evt", toc_res.stdout)

        sql_res = subprocess.run(
            [sys.executable, str(script), "sql"],
            input=(
                "CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end\n"
                "  EXECUTE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint();\n"
                "CREATE TABLE public.ok (id int);\n"
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(sql_res.returncode, 0, sql_res.stderr)
        self.assertNotIn("studio_vector_fdw_enforce_server_endpoint", sql_res.stdout)
        self.assertIn("CREATE TABLE public.ok (id int);", sql_res.stdout)

        bad_res = subprocess.run(
            [sys.executable, str(script), "invalid"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(bad_res.returncode, 2)


class CloneBackupRestoreGuardContractTests(unittest.TestCase):
    def test_duplicate_backup_restore_and_migration_exclude_and_filter_fdw_guard(self) -> None:
        duplicate = (LIB_DIR / "duplicate_project_impl.sh").read_text(encoding="utf-8")
        backup = (LIB_DIR / "backup_core.sh").read_text(encoding="utf-8")
        restore = (LIB_DIR / "restore_project_impl.sh").read_text(encoding="utf-8")
        migration = (GENERATE_DIR / "migrate_shared_storage.sh").read_text(encoding="utf-8")
        vector_lib = (LIB_DIR / "vector_lifecycle.sh").read_text(encoding="utf-8")

        self.assertEqual(duplicate.count("--exclude-schema=studio_vector_fdw_guard"), 2)
        self.assertIn('python3 "$SCRIPT_DIR/lib/pg_dump_filter.py" sql < "$DUMP_FILE"', duplicate)

        self.assertIn("--exclude-schema=studio_storage_guard", backup)
        self.assertIn("--exclude-schema=studio_vector_fdw_guard", backup)
        self.assertIn('python3 "$BACKUP_CORE_DIR/pg_dump_filter.py" sql', backup)

        self.assertIn('python3 "$SCRIPT_DIR/lib/pg_dump_filter.py" sql', restore)

        self.assertIn("--exclude-schema=studio_vector_fdw_guard", migration)
        self.assertIn('python3 "$SCRIPT_DIR/lib/pg_dump_filter.py" sql', migration)

        strip_block = vector_lib.split("vector_strip_copied_wrappers() {", 1)[1].split("\n}\n", 1)[0]
        drop_evt = "DROP EVENT TRIGGER IF EXISTS studio_vector_fdw_enforce_server_endpoint;"
        drop_schema = "DROP SCHEMA IF EXISTS studio_vector_fdw_guard CASCADE;"
        self.assertIn(drop_evt, strip_block)
        self.assertIn(drop_schema, strip_block)
        self.assertLess(strip_block.index(drop_evt), strip_block.index(drop_schema))

    def test_modified_shell_scripts_pass_syntax_check(self) -> None:
        for script in (
            LIB_DIR / "duplicate_project_impl.sh",
            LIB_DIR / "restore_project_impl.sh",
            LIB_DIR / "backup_core.sh",
            LIB_DIR / "vector_lifecycle.sh",
            LIB_DIR / "tenant_meta_role.sh",
            GENERATE_DIR / "migrate_shared_storage.sh",
            GENERATE_DIR / "operations/setup_vector_bucket_wrapper.sh",
            SERVER_ROOT / "volumes/db/create_template.sh",
        ):
            with self.subTest(script=script.name):
                subprocess.run(
                    [git_compatible_bash(), "-n", bash_path(script)],
                    check=True,
                )


@unittest.skipIf(sys.platform == "win32", "requires POSIX bash (Linux-only)")
class GuardExclusionRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="mt-vector-guard-test-"))
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        self.psql_log = self.tmp / "psql.log"
        self.pgdump_log = self.tmp / "pgdump.log"

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _install_fake_docker(self) -> None:
        _write_executable(
            self.bin_dir / "docker",
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                set -euo pipefail
                subcmd="${1:-}"
                shift || true
                if [[ "$subcmd" == "inspect" ]]; then
                  if [[ "${1:-}" == "-f" ]]; then
                    fmt="${2:-}"
                    target="${3:-}"
                    case "$fmt" in
                      *'Config.Image'*)
                        if [[ "$target" == "supabase-storage-global" ]]; then
                          echo "supabase/storage-api:v1.61.12"
                        else
                          echo "nginx/nginx-unprivileged:1.31.10-alpine3.24-slim"
                        fi
                        ;;
                      *'NetworkSettings.Networks'*)
                        if [[ "$target" == "supabase-storage-global" ]]; then
                          printf 'supabase-storage-control\\nsupabase-storage-data-plane\\nsupabase-imgproxy-internal\\n'
                        else
                          printf 'supabase-storage-gateways\\nsupabase-storage-data-plane\\n'
                        fi
                        ;;
                      *'State.Health'*)
                        echo "healthy"
                        ;;
                    esac
                  fi
                  exit 0
                fi
                if [[ "$subcmd" == "exec" ]]; then
                  envs=()
                  while [[ "${1:-}" == -* ]]; do
                    flag="$1"
                    shift
                    if [[ "$flag" == "-e" ]]; then
                      envs+=("$1")
                      shift
                    fi
                  done
                  container="$1"
                  shift
                  cmd="$1"
                  shift
                  if [[ "$container" == "supabase-db" && "$cmd" == "pg_dump" ]]; then
                    printf '%s\\n' "$*" >> "${MOCK_PGDUMP_LOG:?}"
                    if [[ "$*" == *"--exclude-schema=studio_vector_fdw_guard"* && -n "${MOCK_PGDUMP_SQL_FILE:-}" ]]; then
                      cat "$MOCK_PGDUMP_SQL_FILE"
                    else
                      printf -- '-- empty dump\\n'
                    fi
                    exit 0
                  fi
                  if [[ "$container" == "supabase-db" && "$cmd" == "psql" ]]; then
                    if [[ "$*" == *"SELECT tenant_uuid::text FROM public.projects"* ]]; then
                      printf '%s\\n' "${MOCK_PROJECT_UUID:-}"
                      exit 0
                    fi
                    if [[ "$*" == *"SELECT extversion FROM pg_extension WHERE extname = 'wrappers'"* ]]; then
                      printf '0.5.7\\n'
                      exit 0
                    fi
                    if [[ "$*" == *"SHOW server_version;"* ]]; then
                      printf '15.8\\n'
                      exit 0
                    fi
                    if [[ "$*" == *"pg_publication_tables"* ]]; then
                      printf '\\n'
                      exit 0
                    fi
                    {
                      printf '=== PSQL %s ===\\n' "$*"
                      for kv in "${envs[@]}"; do
                        printf 'ENV %s\\n' "$kv"
                      done
                      if [[ ! -t 0 ]]; then
                        cat
                        printf '\\n'
                      fi
                    } >> "${MOCK_PSQL_LOG:?}"
                    exit 0
                  fi
                  if [[ "$container" == "supabase-storage-global" && "$cmd" == "node" ]]; then
                    cat >/dev/null || true
                    if [[ "${MOCK_BUCKET_NAME:-}" != "" ]]; then
                      printf '{"vectorBucket":{"vectorBucketName":"%s"}}' "$MOCK_BUCKET_NAME"
                    fi
                    exit 0
                  fi
                fi
                exit 0
                """
            ),
        )

    def _base_env(self, **extra: str) -> dict[str, str]:
        env = os.environ.copy()
        env["PATH"] = f"{self.bin_dir}:{env.get('PATH', '')}"
        env["MOCK_PSQL_LOG"] = str(self.psql_log)
        env["MOCK_PGDUMP_LOG"] = str(self.pgdump_log)
        env.update(extra)
        return env

    def test_vector_strip_copied_wrappers_drops_event_trigger_before_schema(self) -> None:
        self._install_fake_docker()
        res = subprocess.run(
            [
                "bash",
                "-c",
                f'POSTGRES_USER=supabase_admin; source "{LIB_DIR / "vector_lifecycle.sh"}"; '
                "vector_strip_copied_wrappers _supabase_clone",
            ],
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        sql = self.psql_log.read_text(encoding="utf-8")
        drop_evt = "DROP EVENT TRIGGER IF EXISTS studio_vector_fdw_enforce_server_endpoint;"
        drop_schema = "DROP SCHEMA IF EXISTS studio_vector_fdw_guard CASCADE;"
        self.assertIn(drop_evt, sql)
        self.assertIn(drop_schema, sql)
        self.assertLess(sql.index(drop_evt), sql.index(drop_schema))

    def test_backup_capture_excludes_fdw_guard_schema_and_filters_event_trigger(self) -> None:
        self._install_fake_docker()
        tenant_uuid = "11111111-2222-4333-8444-555555555555"
        fake_server = self.tmp / "servidor"
        (fake_server / "volumes/storage/objects" / tenant_uuid).mkdir(parents=True)
        (fake_server / "volumes/storage/objects" / tenant_uuid / "file.txt").write_text("ok", encoding="utf-8")
        (fake_server / ".env").write_text(
            textwrap.dedent(
                """\
                STORAGE_IMAGE=supabase/storage-api:v1.61.12
                STORAGE_DATA_PLANE_PROXY_IMAGE=nginx/nginx-unprivileged:1.31.10-alpine3.24-slim
                STORAGE_BACKEND=file
                STORAGE_FILE_BACKEND_PATH=/var/lib/storage
                STORAGE_INTERNAL_BUCKET=objects
                STORAGE_TENANT_DB_USER=supabase_storage_admin
                STORAGE_TENANT_HOST_REGEXP='^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[.]storage[.]internal$'
                STORAGE_RUN_AS_USER=1000:1000
                """
            ),
            encoding="utf-8",
        )
        shutil.copytree(GENERATE_DIR / "lib", fake_server / "generateProject/lib")

        dump_fixture = self.tmp / "source_dump.sql"
        dump_fixture.write_text(
            textwrap.dedent(
                """\
                CREATE TABLE public.notes (id int, body text);
                COPY public.notes (id, body) FROM stdin;
                1\tCREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end;
                \\.
                CREATE EVENT TRIGGER my_user_trigger ON ddl_command_end
                  EXECUTE FUNCTION public.my_evt();
                CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end
                  WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')
                  EXECUTE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint();
                ALTER EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint OWNER TO supabase_admin;
                """
            ),
            encoding="utf-8",
        )
        dest_dir = self.tmp / "backup_out"
        res = subprocess.run(
            [
                "bash",
                "-c",
                f'set -euo pipefail; '
                f'PROJECT_ROOT="{fake_server}"; '
                f'PROJECT_UUID="{tenant_uuid}"; '
                f'source "{fake_server / "generateProject/lib/storage_multitenant.sh"}"; '
                f'source "{fake_server / "generateProject/lib/backup_core.sh"}"; '
                f'backup_capture demo_proj "{dest_dir}"',
            ],
            env=self._base_env(MOCK_PGDUMP_SQL_FILE=str(dump_fixture)),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

        pgdump_args = self.pgdump_log.read_text(encoding="utf-8")
        self.assertIn("--exclude-schema=studio_vector_fdw_guard", pgdump_args)
        self.assertIn("--exclude-schema=studio_storage_guard", pgdump_args)

        with gzip.open(dest_dir / "db.sql.gz", "rt", encoding="utf-8") as handle:
            captured_sql = handle.read()
        self.assertIn("1\tCREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint ON ddl_command_end;", captured_sql)
        self.assertIn("CREATE EVENT TRIGGER my_user_trigger ON ddl_command_end", captured_sql)
        self.assertNotIn("WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')", captured_sql)
        self.assertNotIn("ALTER EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint", captured_sql)

    def test_setup_vector_bucket_wrapper_targets_exact_project_uuid_tenant_meta_role(self) -> None:
        self._install_fake_docker()
        tenant_uuid_upper = "AABBCCDD-1111-4222-8333-444455556666"
        tenant_uuid_lower = tenant_uuid_upper.lower()
        expected_role = f"tenant_meta_{tenant_uuid_lower.replace('-', '')}"

        fake_server = self.tmp / "servidor_wrapper"
        (fake_server / "projects/demo_proj").mkdir(parents=True)
        shutil.copytree(GENERATE_DIR / "lib", fake_server / "generateProject/lib")
        shutil.copytree(GENERATE_DIR / "operations", fake_server / "generateProject/operations")

        (fake_server / ".env").write_text(
            textwrap.dedent(
                """\
                POSTGRES_USER=supabase_admin
                POSTGRES_DB=postgres
                STORAGE_S3_REGION=us-east-1
                STORAGE_IMAGE=supabase/storage-api:v1.61.12
                STORAGE_DATA_PLANE_PROXY_IMAGE=nginx/nginx-unprivileged:1.31.10-alpine3.24-slim
                STORAGE_BACKEND=file
                STORAGE_FILE_BACKEND_PATH=/var/lib/storage
                STORAGE_INTERNAL_BUCKET=objects
                STORAGE_TENANT_DB_USER=supabase_storage_admin
                STORAGE_TENANT_HOST_REGEXP='^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[.]storage[.]internal$'
                STORAGE_RUN_AS_USER=1000:1000
                """
            ),
            encoding="utf-8",
        )
        (fake_server / "projects/demo_proj/.env").write_text(
            textwrap.dedent(
                f"""\
                PROJECT_UUID={tenant_uuid_upper}
                SERVICE_ROLE_KEY_PROJETO=service-jwt-placeholder
                S3_PROTOCOL_CREDENTIAL_ID=11111111-1111-4111-8111-111111111111
                S3_PROTOCOL_ACCESS_KEY_ID={'a' * 32}
                S3_PROTOCOL_ACCESS_KEY_SECRET={'b' * 64}
                """
            ),
            encoding="utf-8",
        )

        res = subprocess.run(
            [
                "bash",
                str(fake_server / "generateProject/operations/setup_vector_bucket_wrapper.sh"),
                "demo_proj",
                "my-vectors",
            ],
            env=self._base_env(
                MOCK_PROJECT_UUID=tenant_uuid_lower,
                MOCK_BUCKET_NAME="my-vectors",
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        psql_text = self.psql_log.read_text(encoding="utf-8")
        self.assertIn(f"ENV SETUP_TENANT_META_ROLE={expected_role}", psql_text)
        self.assertIn(
            f"ENV SETUP_ENDPOINT=http://storage-vector-proxy:8081/fdw/{tenant_uuid_lower}/vector",
            psql_text,
        )
        self.assertIn(
            "EXECUTE format('GRANT USAGE ON FOREIGN DATA WRAPPER %I TO %I', cfg.wrapper_name, cfg.tenant_meta_role);",
            psql_text,
        )
        self.assertIn(
            "EXECUTE format('GRANT USAGE ON FOREIGN SERVER %I TO %I', cfg.server_name, cfg.tenant_meta_role);",
            psql_text,
        )

    def test_provision_tenant_meta_role_wires_vector_fdw_guard_gucs_and_hmac(self) -> None:
        self._install_fake_docker()
        tenant_uuid = "11111111-2222-4333-8444-555555555555"
        meta_admin_secret = "S" * 40
        storage_policy_key = hmac.new(
            meta_admin_secret.encode(),
            f"studio-storage-policies-v1:{tenant_uuid}".encode(),
            hashlib.sha256,
        ).hexdigest()
        expected_fdw_key = hmac.new(
            bytes.fromhex(storage_policy_key),
            b"studio-vector-fdw-v1",
            hashlib.sha256,
        ).hexdigest()

        fake_server = self.tmp / "servidor_meta"
        (fake_server / "api-internal/app").mkdir(parents=True)
        (fake_server / "api-internal/app/tenant_meta_role.sql").write_text("-- tenant_meta_role\n", encoding="utf-8")
        (fake_server / "api-internal/app/studio_storage_policies.sql").write_text("-- storage_guard\n", encoding="utf-8")
        (fake_server / "api-internal/app/studio_vector_fdw_guard.sql").write_text(
            "-- vector_fdw_guard_sentinel\n", encoding="utf-8"
        )

        res = subprocess.run(
            [
                "bash",
                "-c",
                f'set -euo pipefail; '
                f'PROJECT_ROOT="{fake_server}"; '
                f'META_ADMIN_DB_PASSWORD="{meta_admin_secret}"; '
                f'STORAGE_S3_REGION="sa-east-1"; '
                f'source "{LIB_DIR / "tenant_meta_role.sh"}"; '
                f'provision_tenant_meta_role "_supabase_demo_proj" "{tenant_uuid}"',
            ],
            env=self._base_env(),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        psql_text = self.psql_log.read_text(encoding="utf-8")
        self.assertIn(f"set_config('platform.vector_fdw_key','{expected_fdw_key}',true)", psql_text)
        self.assertIn(
            f"set_config('platform.vector_fdw_endpoint_url','http://storage-vector-proxy:8081/fdw/{tenant_uuid}/vector',true)",
            psql_text,
        )
        self.assertIn("set_config('platform.vector_fdw_aws_region','sa-east-1',true)", psql_text)
        self.assertIn("-- vector_fdw_guard_sentinel", psql_text)


if __name__ == "__main__":
    unittest.main()
