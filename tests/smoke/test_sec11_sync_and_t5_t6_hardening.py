"""Contract and unit tests for SEC-11 project-gateways isolation, sync tool, and T5/T6 hardening."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVER = ROOT / "servidor"
TOOLS = ROOT / "tools"


def _load_sync_tool():
    spec = importlib.util.spec_from_file_location(
        "sync_existing_projects_security",
        TOOLS / "sync_existing_projects_security.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync_tool = _load_sync_tool()


def _service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    for index, line in enumerate(lines):
        if line == f"  {service_name}:":
            block: list[str] = []
            for inner in lines[index + 1 :]:
                if inner.strip() and not inner.startswith("    "):
                    break
                block.append(inner)
            return "\n".join(block)
    raise AssertionError(f"service {service_name!r} not found")


class Sec11TopologyAndHardeningTests(unittest.TestCase):
    def test_sec11_dedicated_project_gateways_network_topology(self) -> None:
        main_compose = (SERVER / "docker-compose.yml").read_text(encoding="utf-8")
        api_compose = (SERVER / "docker-compose-api.yml").read_text(encoding="utf-8")
        traefik_compose = (SERVER / "traefik/docker-compose.yml").read_text(encoding="utf-8")
        env_example = (SERVER / ".env.example").read_text(encoding="utf-8")

        self.assertIn("PROJECT_GATEWAYS_SUBNET=172.54.0.0/23", env_example)
        self.assertIn(
            "  project-gateways:\n"
            "    name: supabase-project-gateways\n"
            "    driver: bridge\n"
            "    internal: true\n"
            "    ipam:\n"
            "      config:\n"
            "        - subnet: ${PROJECT_GATEWAYS_SUBNET:-172.54.0.0/23}",
            main_compose,
        )
        self.assertIn("name: supabase-project-gateways", api_compose)
        self.assertIn("name: supabase-project-gateways", traefik_compose)

        # Services that project gateways call or receive traffic from must join project-gateways.
        for source, name in (
            (main_compose, "realtime"),
            (main_compose, "supavisor"),
            (main_compose, "db"),
            (api_compose, "key-authorizer"),
            (api_compose, "template-service"),
            (traefik_compose, "traefik"),
        ):
            block = _service_block(source, name)
            self.assertIn("project-gateways", block, name)
            self.assertIn("rede-supabase", block, name)

        # db joins project-gateways solely for outbound S3 Vectors FDW :8081/vector and must
        # explicitly reject inbound PostgreSQL traffic from PROJECT_GATEWAYS_SUBNET.
        db_block = _service_block(main_compose, "db")
        self.assertIn("PG_HBA_DENY_CIDRS: ${PROJECT_GATEWAYS_SUBNET:-172.54.0.0/23}", db_block)

        # Sensitive control-plane and data-plane internals stay off project-gateways.
        for source, name in (
            (main_compose, "functions"),
            (main_compose, "storage"),
            (main_compose, "imgproxy"),
            (main_compose, "storage-data-plane"),
            (main_compose, "analytics"),
            (main_compose, "vector"),
            (api_compose, "projects-api"),
            (api_compose, "edge-bundler"),
            (api_compose, "postgres-meta-global"),
            (api_compose, "control-plane-migrations"),
            (api_compose, "client-configuration"),
            (api_compose, "traffic-redis"),
            (traefik_compose, "traefik-config-watcher"),
            (traefik_compose, "geoip-api"),
            (traefik_compose, "deny-service"),
        ):
            self.assertNotIn("project-gateways", _service_block(source, name), name)

    def test_sec11_pg_hba_deny_cidrs_override_auto_detected_and_allowed_cidrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_path = pathlib.Path(tmp) / "pg_hba.conf"
            proc = subprocess.run(
                ["bash", str(SERVER / "volumes/db/configure-pg-hba.sh")],
                env={
                    "PATH": "/usr/bin:/bin",
                    "PG_HBA_OUTPUT_PATH": str(out_path),
                    "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                    "PG_HBA_ALLOWED_CIDRS": "172.51.2.0/28,172.54.0.0/23",
                    "PG_HBA_DENY_CIDRS": "172.54.0.0/23",
                },
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rendered = out_path.read_text(encoding="utf-8")
            self.assertIn("172.54.0.0/23           reject", rendered)
            self.assertNotIn("172.54.0.0/23           scram-sha-256", rendered)
            self.assertLess(
                rendered.index("172.54.0.0/23           reject"),
                rendered.index("172.50.0.0/16           scram-sha-256"),
            )

    def test_sec11_storage_gateway_contract_accepts_migrated_and_rejects_dual_attach(self) -> None:
        storage_lib = (SERVER / "generateProject/lib/storage_multitenant.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("grep -Fxq 'supabase-project-gateways'", storage_lib)
        self.assertIn(
            "nao pode estar na rede geral e na rede dedicada dos gateways ao mesmo tempo",
            storage_lib,
        )

    def test_sec11_env_contract_validates_project_gateways_subnet(self) -> None:
        spec = importlib.util.spec_from_file_location(
            "check_env_contract", TOOLS / "check-env-contract.py"
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        report = mod.Report()
        mod.check_network(
            report,
            {
                "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                "SUPABASE_NETWORK_GATEWAY": "172.50.0.1",
                "SUPABASE_NETWORK_IP_RANGE": "172.50.0.0/18",
                "PROJECT_GATEWAYS_SUBNET": "172.54.0.0/99",
            },
            "test.env",
        )
        self.assertTrue(any("PROJECT_GATEWAYS_SUBNET" in err for err in report.errors))

    def test_t5_platform_reader_uses_strict_column_level_grants(self) -> None:
        helper = (SERVER / "generateProject/lib/tenant_reader_role.sh").read_text(encoding="utf-8")

        # No blanket table-level SELECT on auth.users or auth.sessions.
        self.assertNotRegex(helper, r"GRANT\s+SELECT\s+ON\s+(?:TABLE\s+)?auth\.(?:users|sessions)")

        # Revoke prior blanket grants before applying column-level grants.
        revoke_pos = helper.index(
            "REVOKE ALL ON TABLE auth.users, auth.sessions FROM platform_reader;"
        )
        users_match = re.search(
            r"GRANT\s+SELECT\s*\(([^)]+)\)\s+ON\s+auth\.users\s+TO\s+platform_reader;",
            helper,
            re.DOTALL,
        )
        sessions_match = re.search(
            r"GRANT\s+SELECT\s*\(([^)]+)\)\s+ON\s+auth\.sessions\s+TO\s+platform_reader;",
            helper,
            re.DOTALL,
        )
        self.assertIsNotNone(users_match)
        self.assertIsNotNone(sessions_match)
        assert users_match is not None and sessions_match is not None
        self.assertLess(revoke_pos, users_match.start())
        self.assertLess(revoke_pos, sessions_match.start())

        users_cols = {col.strip() for col in users_match.group(1).split(",") if col.strip()}
        sessions_cols = {col.strip() for col in sessions_match.group(1).split(",") if col.strip()}

        # Every column queried by platform_auth.py and project_telemetry.py must be granted.
        required_users_cols = {
            "id",
            "email",
            "phone",
            "email_confirmed_at",
            "created_at",
            "last_sign_in_at",
            "raw_user_meta_data",
            "is_sso_user",
        }
        required_sessions_cols = {"user_id", "created_at"}
        self.assertTrue(required_users_cols.issubset(users_cols))
        self.assertTrue(required_sessions_cols.issubset(sessions_cols))

        # Sensitive credential/token columns must NEVER be granted.
        forbidden_users_cols = {
            "encrypted_password",
            "confirmation_token",
            "recovery_token",
            "email_change_token_new",
            "email_change_token_current",
            "reauthentication_token",
            "phone_change_token",
            "phone_change",
            "email_change",
        }
        forbidden_sessions_cols = {
            "refresh_token_hmac_key",
            "refresh_token_counter",
            "factor_id",
            "ip",
            "user_agent",
        }
        self.assertTrue(users_cols.isdisjoint(forbidden_users_cols))
        self.assertTrue(sessions_cols.isdisjoint(forbidden_sessions_cols))

        # Cross-check against actual API queries to catch future column drift.
        platform_auth = (SERVER / "api-internal/app/routers/platform_auth.py").read_text(
            encoding="utf-8"
        )
        telemetry = (SERVER / "api-internal/app/project_telemetry.py").read_text(encoding="utf-8")
        for col in required_users_cols:
            self.assertIn(col, platform_auth)
        for col in ("id", "email", "phone", "last_sign_in_at"):
            self.assertIn(f"users.{col}", telemetry)
        for col in required_sessions_cols:
            self.assertIn(col, telemetry)

    def test_t6_postgres_log_min_messages_is_warning(self) -> None:
        compose = (SERVER / "docker-compose.yml").read_text(encoding="utf-8")
        db_block = _service_block(compose, "db")
        self.assertIn("- log_min_messages=warning", db_block)
        self.assertNotIn("log_min_messages=fatal", db_block)


class SyncExistingProjectsSecurityTests(unittest.TestCase):
    COMPOSE_V1 = (
        "services:\n"
        "  nginx:\n"
        "    container_name: supabase-nginx-{{project_id}}\n"
        "    environment:\n"
        "      FILE_SIZE_LIMIT: ${FILE_SIZE_LIMIT}\n"
        "      SUPABASE_NETWORK_SUBNET: ${SUPABASE_NETWORK_SUBNET}\n"
        "      POSTGRES_POOLER: ${POSTGRES_POOLER}\n"
        "      POOLER_PROXY_PORT_SESSION: ${POOLER_PROXY_PORT_SESSION}\n"
        "      POOLER_PROXY_PORT_TRANSACTION: ${POOLER_PROXY_PORT_TRANSACTION}\n"
        "      ANON_KEY_PROJETO: ${ANON_KEY_PROJETO}\n"
        "      SERVICE_ROLE_KEY_PROJETO: ${SERVICE_ROLE_KEY_PROJETO}\n"
        "      API_GATEWAY_TOKEN_PROJETO: ${API_GATEWAY_TOKEN_PROJETO}\n"
        "    networks:\n"
        "      - rede-supabase\n"
        "      - storage-gateways\n"
        "      - functions-gateways\n"
        "  auth:\n"
        "    container_name: supabase-auth-{{project_id}}\n"
        "    depends_on:\n"
        "      - nginx\n"
        "    environment:\n"
        "      GOTRUE_DB_DATABASE_URL: postgres://${AUTH_DB_USER}.{{project_id}}:${POSTGRES_PASSWORD}@${POSTGRES_POOLER}:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n"
        "      GOTRUE_MAILER_TEMPLATES_RECOVERY: http://template-service:18020/mailer/${PROJECT_UUID}/recovery\n"
        "    networks:\n"
        "      - rede-supabase\n"
        "  rest:\n"
        "    container_name: supabase-rest-{{project_id}}\n"
        "    environment:\n"
        "      PGRST_DB_URI: postgres://${POSTGREST_DB_USER}.{{project_id}}:${POSTGRES_PASSWORD}@${POSTGRES_POOLER}:${POOLER_PROXY_PORT_SESSION}/${POSTGRES_DATABASE}\n"
        "    networks:\n"
        "      - rede-supabase\n"
        "networks:\n"
        "  rede-supabase:\n"
        "    external: true\n"
        "  storage-gateways:\n"
        "    external: true\n"
        "    name: supabase-storage-gateways\n"
    )
    COMPOSE_V2 = (
        COMPOSE_V1.replace(
            "    container_name: supabase-nginx-{{project_id}}\n",
            "    container_name: supabase-nginx-{{project_id}}\n"
            "    healthcheck:\n"
            '      test: ["CMD-SHELL", "true"]\n',
        ).replace(
            "    environment:\n      GOTRUE_DB_DATABASE_URL",
            "    environment:\n      GOTRUE_SITE_URL: ${SITE_URL}\n      GOTRUE_DB_DATABASE_URL",
        )
    )
    NGINX_V1 = (
        "events {}\n"
        "http {\n"
        "    server {\n"
        "        server_name _{{project_id}};\n"
        "        # HOST_AGENT_PUBLIC_ASSETS\n"
        "        # marker-a {{project_public_ref}} {{server_url}}\n"
        "        # marker-b {{project_uuid}}\n"
        "    }\n"
        "}\n"
        "stream {\n"
        "    resolver 127.0.0.11 valid=30s ipv6=off;\n"
        '    map "" $stream_pooler_session_upstream { default "${POSTGRES_POOLER}:${POOLER_PROXY_PORT_SESSION}"; }\n'
        "}\n"
    )
    NGINX_V2 = (
        "events {}\n"
        "http {\n"
        "    server {\n"
        "        server_name _{{project_id}};\n"
        "        # HOST_AGENT_PUBLIC_ASSETS\n"
        "        # marker-a-v2 {{project_public_ref}} {{server_url}}\n"
        "        # marker-b {{project_uuid}}\n"
        "        # marker-c\n"
        "    }\n"
        "}\n"
        "stream {\n"
        "    resolver 127.0.0.11 valid=30s ipv6=off;\n"
        '    map "" $stream_pooler_session_upstream { default "supabase-pooler:${POOLER_PROXY_PORT_SESSION}"; }\n'
        "}\n"
    )
    DOCKERFILE_V1 = (
        "FROM nginx/nginx-unprivileged:1.31.10-alpine3.24-slim\n"
        "COPY nginx/nginx_{{project_id}}.conf /etc/nginx/nginx.conf.template\n"
        "COPY --chown=101:101 nginx/public/ /usr/share/nginx/html/\n"
        "CMD [\"envsubst '$POSTGRES_POOLER' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf\"]\n"
    )
    DOCKERFILE_V2 = (
        "FROM nginx/nginx-unprivileged:1.31.10-alpine3.24-slim\n"
        "COPY nginx/nginx_{{project_id}}.conf /etc/nginx/nginx.conf.template\n"
        "COPY --chown=101:101 nginx/public/ /usr/share/nginx/html/\n"
        "CMD [\"envsubst '$PROJECT_GATEWAYS_SUBNET' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf\"]\n"
    )

    def _world(self, root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, dict]:
        templates = root / "generateProject"
        templates.mkdir()
        for name, text in (
            ("dockercomposetemplate", self.COMPOSE_V2),
            ("nginxtemplate", self.NGINX_V2),
            ("Dockerfile", self.DOCKERFILE_V2),
        ):
            (templates / name).write_text(text, encoding="utf-8")
        server_env = root / ".env"
        server_env.write_text(
            "SERVER_URL=api.example.test\nSERVER_PROTO=https\nSUPABASE_NETWORK_SUBNET=172.50.0.0/16\n",
            encoding="utf-8",
        )
        history = {
            "dockercomposetemplate": [("1" * 40, self.COMPOSE_V1)],
            "nginxtemplate": [("2" * 40, self.NGINX_V1)],
            "Dockerfile": [("3" * 40, self.DOCKERFILE_V1)],
        }
        return templates, server_env, root / "projects", history

    def _make_project(
        self,
        projects: pathlib.Path,
        nginx_template_text: str,
        *,
        slug: str = "demo_proj",
        with_public_dir: bool = True,
    ) -> pathlib.Path:
        proj = projects / slug
        (proj / "nginx").mkdir(parents=True)
        if with_public_dir:
            (proj / "nginx" / "public").mkdir()
        proj_uuid = "33333333-3333-4333-8333-333333333333"
        public_ref = "abcdefghijklmnopqrst"
        (proj / ".env").write_text(
            f"PROJECT_ID={slug}\n"
            f"PROJECT_UUID={proj_uuid}\n"
            f"PROJECT_PUBLIC_REF={public_ref}\n"
            f"API_GATEWAY_TOKEN_PROJETO={'a' * 64}\n",
            encoding="utf-8",
        )
        os.chmod(proj / ".env", 0o600)
        compose = (
            self.COMPOSE_V1.replace("{{project_id}}", slug)
            .replace("    depends_on:\n      - nginx\n", "")
            .replace(
                "    environment:\n      GOTRUE_DB_DATABASE_URL",
                "    environment:\n"
                '      GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED: "true"\n'
                '      GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_URI: "pg-functions://postgres/public/custom_access_token_hook"\n'
                "      GOTRUE_DB_DATABASE_URL",
            )
            .replace(
                "    networks:\n      - rede-supabase\n      - storage-gateways\n",
                "    networks:\n      - rede-supabase\n      - observability\n      - storage-gateways\n",
            )
            .replace(
                "  storage-gateways:\n    external: true\n    name: supabase-storage-gateways\n",
                "  storage-gateways:\n    external: true\n    name: supabase-storage-gateways\n"
                "  observability:\n    external: true\n    name: observability\n",
            )
        )
        (proj / "docker-compose.yml").write_text(compose, encoding="utf-8")
        rendered_dockerfile = self.DOCKERFILE_V1.replace("{{project_id}}", slug)
        if not with_public_dir:
            rendered_dockerfile = (
                "\n".join(line for line in rendered_dockerfile.splitlines() if "nginx/public/" not in line)
                + "\n"
            )
        (proj / "Dockerfile").write_text(rendered_dockerfile, encoding="utf-8")
        rendered_nginx = (
            nginx_template_text.replace("{{project_id}}", slug)
            .replace("{{project_uuid}}", proj_uuid)
            .replace("{{project_public_ref}}", public_ref)
            .replace("{{server_url}}", "api.example.test")
        )
        (proj / "nginx" / f"nginx_{slug}.conf").write_text(rendered_nginx, encoding="utf-8")
        return proj

    def _sync(self, templates, server_env, projects, history, **overrides):
        kwargs = dict(
            projects_dir=projects,
            server_env_path=server_env,
            templates_dir=templates,
            apply=True,
            skip_compose_validate=True,
            segregate_networks=True,
            template_history=history,
        )
        kwargs.update(overrides)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            res = sync_tool.sync_projects(**kwargs)
        return res, buf.getvalue()

    def test_sync_applies_template_delta_and_preserves_project_customizations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, history = self._world(root)
            custom_nginx = self.NGINX_V1.replace(
                "        # HOST_AGENT_PUBLIC_ASSETS\n",
                "        location = /custom-reset.html { root /usr/share/nginx/html; }\n",
            ).replace(
                "        # marker-b {{project_uuid}}\n",
                "        # marker-b {{project_uuid}}\n        # custom project directive\n",
            )
            proj = self._make_project(projects, custom_nginx)
            original_compose = (proj / "docker-compose.yml").read_bytes()

            dry_res, dry_out = self._sync(
                templates, server_env, projects, history, apply=False, show_diff=True
            )
            self.assertEqual(dry_res, {"demo_proj": "NEEDS_UPDATE"})
            self.assertIn("+++ docker-compose.yml (planned)", dry_out)
            self.assertEqual((proj / "docker-compose.yml").read_bytes(), original_compose)

            res, _ = self._sync(templates, server_env, projects, history)
            self.assertEqual(res, {"demo_proj": "UPDATED"})
            compose = (proj / "docker-compose.yml").read_text(encoding="utf-8")

            # New template additions merged in.
            self.assertIn('test: ["CMD-SHELL", "true"]', compose)
            self.assertIn("GOTRUE_SITE_URL: ${SITE_URL}", compose)
            # Project customizations preserved.
            self.assertNotIn("depends_on", compose)
            self.assertIn('GOTRUE_HOOK_CUSTOM_ACCESS_TOKEN_ENABLED: "true"', compose)
            self.assertIn("- observability", compose)
            self.assertIn("name: observability", compose)
            # SEC-11 hardening applied.
            self.assertIn("traefik.docker.network=supabase-project-gateways", compose)
            self.assertIn("PROJECT_GATEWAYS_SUBNET: ${PROJECT_GATEWAYS_SUBNET:-172.54.0.0/23}", compose)
            self.assertNotIn("POSTGRES_POOLER", compose)
            self.assertIn("@supabase-nginx-demo_proj:${POOLER_PROXY_PORT_SESSION}/", compose)
            self.assertIn("http://supabase-nginx-demo_proj:18020/mailer/", compose)
            self.assertNotIn("- rede-supabase", compose)
            self.assertNotIn("  rede-supabase:", compose)

            nginx_conf = (proj / "nginx/nginx_demo_proj.conf").read_text(encoding="utf-8")
            self.assertIn("# marker-a-v2 abcdefghijklmnopqrst api.example.test", nginx_conf)
            self.assertIn("# marker-c", nginx_conf)
            self.assertIn("location = /custom-reset.html { root /usr/share/nginx/html; }", nginx_conf)
            self.assertIn("# custom project directive", nginx_conf)
            self.assertIn('default "supabase-pooler:${POOLER_PROXY_PORT_SESSION}";', nginx_conf)
            self.assertNotIn("${POSTGRES_POOLER}", nginx_conf)

            dockerfile = (proj / "Dockerfile").read_text(encoding="utf-8")
            self.assertIn("$PROJECT_GATEWAYS_SUBNET", dockerfile)
            self.assertNotIn("$POSTGRES_POOLER", dockerfile)

            updated_env = (proj / ".env").read_text(encoding="utf-8")
            self.assertIn("PROJECT_INTERNAL_SUBNET=172.52.", updated_env)
            self.assertEqual((proj / ".env").stat().st_mode & 0o777, 0o600)

            backups = list(proj.glob("docker-compose.yml.bak.*"))
            self.assertEqual([p.read_bytes() for p in backups], [original_compose])
            self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in proj.rglob("*.bak.*")))

            # Idempotent second pass.
            second_res, _ = self._sync(templates, server_env, projects, history, apply=False)
            self.assertEqual(second_res, {"demo_proj": "UP_TO_DATE"})

    def test_sync_conflict_leaves_project_untouched_until_forced(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, history = self._world(root)
            conflicting = self.NGINX_V1.replace(
                "# marker-a {{project_public_ref}} {{server_url}}",
                "# marker-a custom-conflict {{project_public_ref}} {{server_url}}",
            )
            proj = self._make_project(projects, conflicting)
            before = {p.name: p.read_bytes() for p in proj.rglob("*") if p.is_file()}

            res, _ = self._sync(templates, server_env, projects, history)
            self.assertEqual(res, {"demo_proj": "NEEDS_REVIEW"})
            after = {p.name: p.read_bytes() for p in proj.rglob("*") if p.is_file() and ".bak." not in p.name}
            self.assertEqual(after, before)

            forced_res, _ = self._sync(templates, server_env, projects, history, force_templates=True)
            self.assertEqual(forced_res, {"demo_proj": "UPDATED"})
            nginx_conf = (proj / "nginx/nginx_demo_proj.conf").read_text(encoding="utf-8")
            self.assertIn("# marker-a-v2 abcdefghijklmnopqrst api.example.test", nginx_conf)
            backups = list(proj.glob("nginx/nginx_*.conf.bak.*"))
            self.assertEqual(len(backups), 1)
            self.assertIn("custom-conflict", backups[0].read_text(encoding="utf-8"))

    def test_sync_without_history_never_guesses_on_divergent_nginx(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, _history = self._world(root)
            proj = self._make_project(projects, self.NGINX_V1)
            before = (proj / "docker-compose.yml").read_bytes()

            res, _ = self._sync(templates, server_env, projects, {})
            self.assertEqual(res, {"demo_proj": "NEEDS_REVIEW"})
            self.assertEqual((proj / "docker-compose.yml").read_bytes(), before)

    def test_sync_without_history_still_hardens_compose_when_nginx_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, _history = self._world(root)
            proj = self._make_project(projects, self.NGINX_V2)
            (proj / "Dockerfile").write_text(
                self.DOCKERFILE_V2.replace("{{project_id}}", "demo_proj"), encoding="utf-8"
            )
            res, _ = self._sync(templates, server_env, projects, {})
            self.assertEqual(res, {"demo_proj": "NEEDS_MERGE"})
            compose = (proj / "docker-compose.yml").read_text(encoding="utf-8")
            self.assertIn("traefik.docker.network=supabase-project-gateways", compose)
            self.assertIn("- observability", compose)
            self.assertNotIn("- rede-supabase", compose)
            self.assertNotIn("healthcheck", compose)

    def test_sync_keeps_shared_network_when_custom_service_uses_it(self) -> None:
        compose = self.COMPOSE_V1.replace(
            "networks:\n  rede-supabase:",
            "  worker:\n    image: busybox\n    networks: [rede-supabase]\nnetworks:\n  rede-supabase:",
        )
        hardened = sync_tool.render_project_compose(
            compose,
            "demo_proj",
            compose,
            {},
            {"PROJECT_INTERNAL_SUBNET": "172.52.1.0/28"},
            segregate_networks=True,
        )
        self.assertIn("  worker:\n    image: busybox\n    networks: [rede-supabase]\n", hardened)
        self.assertIn("  rede-supabase:\n    external: true\n", hardened)
        self.assertEqual(hardened.count("  rede-supabase:"), 1)

    def test_sync_traefik_network_label_variants(self) -> None:
        base_env = {"PROJECT_INTERNAL_SUBNET": "172.52.1.0/28"}
        tail = (
            "    networks:\n"
            "      - rede-supabase\n"
            "  auth:\n"
            "    networks:\n"
            "      - rede-supabase\n"
            "  rest:\n"
            "    networks:\n"
            "      - rede-supabase\n"
            "networks:\n"
            "  rede-supabase:\n"
            "    external: true\n"
        )

        # List variants (double quoted, unquoted, single quoted)
        for stale_line in (
            '      - "traefik.docker.network=rede-supabase"\n',
            "      - traefik.docker.network=rede-supabase\n",
            "      - 'traefik.docker.network=rede-supabase'\n",
        ):
            compose_in = (
                "services:\n"
                "  nginx:\n"
                "    labels:\n"
                '      - "traefik.enable=true"\n'
                + stale_line
                + '      - "traefik.http.routers.demo.middlewares=rate-limit@file,strip@docker"\n'
                + tail
            )
            out = sync_tool.render_project_compose(
                compose_in, "demo_proj", compose_in, {}, base_env, segregate_networks=True
            )
            self.assertEqual(out.count("traefik.docker.network="), 1)
            self.assertIn("traefik.docker.network=supabase-project-gateways", out)
            self.assertNotIn("traefik.docker.network=rede-supabase", out)
            self.assertEqual(
                sync_tool.render_project_compose(
                    out, "demo_proj", out, {}, base_env, segregate_networks=True
                ),
                out,
            )

        # Duplicate collapse
        dup_compose = (
            "services:\n"
            "  nginx:\n"
            "    labels:\n"
            '      - "traefik.docker.network=supabase-project-gateways"\n'
            '      - "traefik.docker.network=rede-supabase"\n'
            + tail
        )
        out = sync_tool.render_project_compose(
            dup_compose, "demo_proj", dup_compose, {}, base_env, segregate_networks=True
        )
        self.assertEqual(out.count("traefik.docker.network="), 1)
        self.assertNotIn("rede-supabase", out)

        # Map style (missing & stale)
        map_missing = (
            "services:\n"
            "  nginx:\n"
            "    labels:\n"
            '      traefik.enable: "true"\n'
            + tail
        )
        out = sync_tool.render_project_compose(
            map_missing, "demo_proj", map_missing, {}, base_env, segregate_networks=True
        )
        self.assertIn('      traefik.docker.network: "supabase-project-gateways"\n', out)

        map_stale = (
            "services:\n"
            "  nginx:\n"
            "    labels:\n"
            "      traefik.docker.network: rede-supabase\n"
            + tail
        )
        out = sync_tool.render_project_compose(
            map_stale, "demo_proj", map_stale, {}, base_env, segregate_networks=True
        )
        self.assertIn("      traefik.docker.network: supabase-project-gateways\n", out)

        # Inline list & inline map variants
        for inline_line, expected_sub in (
            (
                '    labels: ["traefik.enable=true", "traefik.http.routers.demo.middlewares=a,b"]\n',
                '    labels: ["traefik.enable=true", "traefik.http.routers.demo.middlewares=a,b", "traefik.docker.network=supabase-project-gateways"]\n',
            ),
            ("    labels: []\n", '    labels: ["traefik.docker.network=supabase-project-gateways"]\n'),
            (
                '    labels: {traefik.enable: "true", traefik.docker.network: rede-supabase}\n',
                '    labels: {traefik.enable: "true", traefik.docker.network: "supabase-project-gateways"}\n',
            ),
            ("    labels: {}\n", '    labels: {traefik.docker.network: "supabase-project-gateways"}\n'),
        ):
            inline_compose = "services:\n  nginx:\n" + inline_line + tail
            out = sync_tool.render_project_compose(
                inline_compose, "demo_proj", inline_compose, {}, base_env, segregate_networks=True
            )
            self.assertIn(expected_sub, out)

        # Missing labels block inserted cleanly
        no_labels = "services:\n  nginx:\n" + tail
        out = sync_tool.render_project_compose(
            no_labels, "demo_proj", no_labels, {}, base_env, segregate_networks=True
        )
        self.assertIn('    labels:\n      - "traefik.docker.network=supabase-project-gateways"\n', out)

    def test_sync_merge_rules_and_idempotency(self) -> None:
        base = ["key:\n", "  opt: 1\n", "other: a\n", "tail\n"]

        def merge(ours: list[str], theirs: list[str]) -> tuple[str, int]:
            return sync_tool.merge_template_change("".join(ours), "".join(base), "".join(theirs))

        key, opt, other, tail = base
        self.assertEqual(
            merge([key, "  opt: ours\n", other, tail], [key, opt, other, "tail-changed\n"]),
            (key + "  opt: ours\n" + other + "tail-changed\n", 0),
        )
        self.assertEqual(
            merge([key, "from-project\n", opt, other, tail], [key, "from-template\n", opt, other, tail]),
            (key + "from-template\nfrom-project\n" + opt + other + tail, 0),
        )
        self.assertEqual(merge([other, tail], [key, "  opt: 2\n", other, tail]), (other + tail, 0))
        self.assertEqual(merge([other, tail], ["new-key: yes\n", other, tail]), ("new-key: yes\n" + other + tail, 0))
        self.assertEqual(
            merge([key, "  added\n", opt, other, tail], [key, "  added\n", "  newer\n", opt, other, tail]),
            (key + "  added\n  newer\n" + opt + other + tail, 0),
        )
        self.assertEqual(merge([key, "  opt: ours\n", other, tail], [other, tail]), (key + "  opt: ours\n" + other + tail, 1))
        self.assertEqual(
            merge([key, "  opt: ours\n", other, tail], [key, "  opt: theirs\n", other, tail]),
            (key + "  opt: ours\n" + other + tail, 1),
        )
        # Adjacent-line edits remain idempotent on a second merge pass against the original base
        once, conflicts = merge([key, "  opt: ours\n", other, tail], [key, opt, "other: b\n", tail])
        self.assertEqual(conflicts, 0)
        self.assertEqual(
            merge(once.splitlines(keepends=True), [key, opt, "other: b\n", tail]),
            (once, 0),
        )
        # Shared prefix before a real conflict still flags a conflict
        self.assertEqual(
            merge([key, "  shared\n", "  opt: ours\n", other, tail], [key, "  shared\n", "  opt: theirs\n", other, tail]),
            (key + "  shared\n  opt: ours\n" + other + tail, 1),
        )

    def test_sync_allocates_distinct_subnets_and_strips_missing_public_dir_in_dockerfile(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, history = self._world(root)
            proj_a = self._make_project(projects, self.NGINX_V1, slug="proj_alpha", with_public_dir=False)
            proj_b = self._make_project(projects, self.NGINX_V1, slug="proj_beta", with_public_dir=True)

            res, _ = self._sync(templates, server_env, projects, history)
            self.assertEqual(res, {"proj_alpha": "UPDATED", "proj_beta": "UPDATED"})

            env_a, _ = sync_tool.parse_env_file(proj_a / ".env")
            env_b, _ = sync_tool.parse_env_file(proj_b / ".env")
            self.assertTrue(env_a["PROJECT_INTERNAL_SUBNET"].startswith("172.52."))
            self.assertTrue(env_b["PROJECT_INTERNAL_SUBNET"].startswith("172.52."))
            self.assertNotEqual(env_a["PROJECT_INTERNAL_SUBNET"], env_b["PROJECT_INTERNAL_SUBNET"])

            self.assertNotIn("nginx/public/", (proj_a / "Dockerfile").read_text(encoding="utf-8"))
            self.assertIn("nginx/public/", (proj_b / "Dockerfile").read_text(encoding="utf-8"))

    def test_sync_cli_dry_run_diff_and_missing_data_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            templates, server_env, projects, _history = self._world(root)
            proj = self._make_project(projects, self.NGINX_V1, slug="proj_missing")
            (proj / ".env").write_text("PROJECT_ID=proj_missing\n", encoding="utf-8")

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = sync_tool.main(
                    [
                        "--projects-dir",
                        str(projects),
                        "--server-env",
                        str(server_env),
                        "--templates-dir",
                        str(templates),
                        "--dry-run",
                        "--diff",
                        "--segregate-networks",
                        "--skip-compose-validate",
                    ]
                )
            self.assertEqual(rc, 2)
            self.assertIn("NEEDS_REVIEW", buf.getvalue())
            self.assertIn("missing-data", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
