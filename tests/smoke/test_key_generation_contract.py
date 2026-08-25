import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATE = ROOT / "servidor" / "generateProject"


class KeyGenerationContractTest(unittest.TestCase):
    def test_setup_and_runtime_config_require_explicit_internal_hmac_keys(self):
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        studio_example = (ROOT / "studio" / ".env.example").read_text(encoding="utf-8")
        server_example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        runtime_tool = (ROOT / "tools" / "configure_studio_runtime.py").read_text(encoding="utf-8")
        self.assertIn("STUDIO_SERVICE_KEY_ENCRYPTION_KEY=pass", studio_example)
        self.assertNotIn("NGINX_SHARED_TOKEN", setup + studio_example + server_example)
        for key in {"STUDIO_GATEWAY_HMAC_SECRET", "PROJECTS_API_HMAC_SECRET"}:
            self.assertIn(f"{key}=", studio_example)
            self.assertIn(f"{key}=", server_example)
            self.assertIn(key, runtime_tool)
        for key in {"STUDIO_SERVICE_KEY_ENCRYPTION_KEY", "NGINX_HMAC_SECRET", "INTERNAL_HMAC_SECRET"}:
            self.assertIn(f"s|^{key}=.*|", setup)
            self.assertIn(f"assert_env_value servidor/.env {key}", setup)
            self.assertIn(f"assert_env_value studio/.env {key}", setup)

    def test_project_compose_variables_are_defined_by_env_templates(self):
        root_env = set(
            re.findall(
                r"^([A-Z][A-Z0-9_]*)=",
                (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
        project_env = set(
            re.findall(
                r"^([A-Z][A-Z0-9_]*)=",
                (GENERATE / ".envtemplate").read_text(encoding="utf-8"),
                re.MULTILINE,
            )
        )
        compose = (GENERATE / "dockercomposetemplate").read_text(encoding="utf-8")
        references = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", compose))
        # Limites de recursos nao vivem em template: sao gravados no .env do
        # projeto pelo helper lib/resource_profiles.sh (fail-closed ':?' no
        # compose). Contrato dedicado em test_project_resource_limits_contract.py.
        helper_managed = {
            "PROJECT_MEM_LIMIT",
            "PROJECT_CPUS",
            "PROJECT_PIDS_LIMIT",
        } | {"PROJECT_REST_GHC_MAX_HEAP"} | {
            f"PROJECT_{service}_{suffix}"
            for service in ("NGINX", "AUTH", "REST")
            for suffix in ("MEM_LIMIT", "CPUS", "PIDS_LIMIT")
        }
        self.assertIn("PROJECT_RESOURCE_PROFILE", root_env)
        self.assertFalse(
            helper_managed & (root_env | project_env),
            "limites resolvidos nao devem ter default em template raiz/projeto",
        )
        self.assertEqual(
            sorted(references - root_env - project_env - helper_managed),
            [],
        )

    def test_every_template_placeholder_is_rendered(self):
        generator = "\n".join(
            (
                (GENERATE / "generate_project.sh").read_text(encoding="utf-8"),
                (GENERATE / "lib/generate_project_impl.sh").read_text(
                    encoding="utf-8"
                ),
            )
        )
        placeholders = set()
        for name in {
            ".envtemplate",
            "dockercomposetemplate",
            "nginxtemplate",
            "poolertemplate",
            "Dockerfile",
        }:
            placeholders.update(
                re.findall(
                    r"\{\{([^}]+)\}\}",
                    (GENERATE / name).read_text(encoding="utf-8"),
                )
            )
        missing = [
            placeholder
            for placeholder in placeholders
            if f"{{{{{placeholder}}}}}" not in generator
        ]
        self.assertEqual(sorted(missing), [])

    def test_config_token_is_shared_but_not_used_as_admin_apikey(self):
        main = (ROOT / "servidor" / "api-internal" / "app" / "main.py").read_text(
            encoding="utf-8"
        )
        config_endpoint = main[
            main.index("async def get_project_config_token") : main.index(
                "async def get_project_queue_status"
            )
        ]
        meta_proxy = main[main.index("async def proxy_project_meta") :]
        self.assertIn("ensure_project_member_access", config_endpoint)
        self.assertIn('column="service_role"', meta_proxy)
        self.assertNotIn('column="config_token"', meta_proxy)

    def test_rotation_preserves_config_token(self):
        rotation = (GENERATE / "rotate_key.sh").read_text(encoding="utf-8")
        self.assertIn('get_env_value "CONFIG_TOKEN_PROJETO"', rotation)
        self.assertIn('get_env_value "API_GATEWAY_TOKEN_PROJETO"', rotation)
        self.assertNotRegex(rotation, r"CONFIG_TOKEN(_PROJETO)?=.*openssl rand")

    def test_rotation_fails_closed_and_never_prints_generated_keys(self):
        rotation = (GENERATE / "rotate_key.sh").read_text(encoding="utf-8")
        self.assertIn('[[ "$PROJECT_UUID" =~ ^[0-9a-fA-F]{8}', rotation)
        self.assertNotIn("usando PROJECT_ID como fallback", rotation)
        self.assertNotIn("upsert_env_value", rotation)
        self.assertIn('replace_env_value "ANON_KEY_PROJETO"', rotation)
        self.assertNotIn('echo "ANON_KEY_PROJETO=$NEW_ANON"', rotation)
        self.assertNotIn('echo "SERVICE_ROLE_KEY_PROJETO=$NEW_SERVICE"', rotation)
        self.assertIn(r'\"jti\":\"$anon_jti\"', rotation)
        self.assertIn(r'\"jti\":\"$service_jti\"', rotation)
        self.assertNotIn('url="https://$url"', rotation)
        self.assertIn('SERVER_PROTO deve ser http ou https', rotation)

    def test_generated_secret_files_are_restricted(self):
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn(
            "chmod 600 servidor/.env servidor/.analytics.env "
            "servidor/.storage.env studio/.env studio/.analytics.env",
            setup,
        )
        for script_name in {
            "lib/generate_project_impl.sh",
            "lib/duplicate_project_impl.sh",
            "rotate_key.sh",
            "lib/rename_project_impl.sh",
        }:
            source = (GENERATE / script_name).read_text(encoding="utf-8")
            self.assertRegex(source, r'chmod 600 "[^\n]*\.env"', script_name)
            self.assertIn("chmod 644", source, script_name)
            self.assertIn(".dockerignore", source, script_name)

    def test_project_lifecycle_requires_explicit_operational_inputs(self):
        generate = (GENERATE / "lib/generate_project_impl.sh").read_text(
            encoding="utf-8"
        )
        duplicate = (GENERATE / "lib/duplicate_project_impl.sh").read_text(
            encoding="utf-8"
        )
        rename = (GENERATE / "lib/rename_project_impl.sh").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('RECOVER_STALE="${3:-false}"', generate)
        self.assertNotIn('COPY_MODE="${3:-schema-only}"', duplicate)
        for source in (generate, duplicate, rename):
            self.assertNotIn('${MAX_CONCURRENT_USERS:-200}', source)
            self.assertIn(
                '[[ "$MAX_CONCURRENT_USERS" =~ ^[1-9][0-9]*$ ]]', source
            )

    def test_unprivileged_nginx_can_read_and_render_its_template(self):
        dockerfile = (GENERATE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("--chown=101:101", dockerfile)
        self.assertIn("--chmod=0400", dockerfile)
        self.assertIn("ENTRYPOINT", dockerfile)
        self.assertIn(
            "envsubst '$FILE_SIZE_LIMIT $SUPABASE_NETWORK_SUBNET "
            "$ANON_KEY_PROJETO $SERVICE_ROLE_KEY_PROJETO $CONFIG_TOKEN_PROJETO "
            "$API_GATEWAY_TOKEN_PROJETO'",
            dockerfile,
        )
        self.assertNotIn("/etc/nginx/templates/", dockerfile)

        nginx_template = (GENERATE / "nginxtemplate").read_text(encoding="utf-8")
        compose_template = (GENERATE / "dockercomposetemplate").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("allow 172.50.0.0/16", nginx_template)
        self.assertIn("allow ${SUPABASE_NETWORK_SUBNET}", nginx_template)
        self.assertIn("SUPABASE_NETWORK_SUBNET: ${SUPABASE_NETWORK_SUBNET}", compose_template)
        for key in {
            "ANON_KEY_PROJETO",
            "SERVICE_ROLE_KEY_PROJETO",
            "CONFIG_TOKEN_PROJETO",
            "API_GATEWAY_TOKEN_PROJETO",
        }:
            self.assertIn(f"${{{key}}}", nginx_template)
            self.assertIn(f"{key}: ${{{key}}}", compose_template)

        dockerignore = (GENERATE / ".dockerignore").read_text(encoding="utf-8")
        self.assertIn("**", dockerignore)
        self.assertIn("!Dockerfile", dockerignore)
        self.assertIn("!nginx/nginx_*.conf", dockerignore)

    def test_opaque_key_status_and_collaboration_tabs_are_exposed(self):
        main = (ROOT / "servidor" / "api-internal" / "app" / "main.py").read_text(
            encoding="utf-8"
        )
        dialog = (
            ROOT
            / "studio"
            / "seletor_de_projetos"
            / "lib"
            / "project_collaboration_dialog.dart"
        ).read_text(encoding="utf-8")
        card = (
            ROOT
            / "studio"
            / "seletor_de_projetos"
            / "lib"
            / "widgets"
            / "project_card.dart"
        ).read_text(encoding="utf-8")
        self.assertIn('"opaque_api_keys_status"', main)
        self.assertNotIn('"anon_token"', main)
        self.assertIn("length: 5", dialog)
        self.assertIn("text: 'Tags'", dialog)
        self.assertIn("_buildTagsTab(data)", dialog)
        self.assertIn("API KEYS OPACAS", card)
        self.assertNotIn("anonKey", card)


if __name__ == "__main__":
    unittest.main()
