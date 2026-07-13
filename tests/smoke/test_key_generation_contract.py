import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATE = ROOT / "servidor" / "generateProject"


class KeyGenerationContractTest(unittest.TestCase):
    def test_setup_replaces_shared_transport_secrets_by_key_name(self):
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        studio_example = (ROOT / "studio" / ".env.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("STUDIO_SERVICE_KEY_ENCRYPTION_KEY=pass", studio_example)
        for key in {
            "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
            "NGINX_SHARED_TOKEN",
            "NGINX_HMAC_SECRET",
            "INTERNAL_HMAC_SECRET",
        }:
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
        self.assertEqual(sorted(references - root_env - project_env), [])

    def test_every_template_placeholder_is_rendered(self):
        generator = (GENERATE / "generate_project.sh").read_text(encoding="utf-8")
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
        self.assertNotRegex(rotation, r"CONFIG_TOKEN(_PROJETO)?=.*openssl rand")

    def test_generated_secret_files_are_restricted(self):
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn(
            "chmod 644 servidor/.env servidor/.analytics.env "
            "studio/.env studio/.analytics.env",
            setup,
        )
        for script_name in {
            "lib/generate_project_impl.sh",
            "lib/duplicate_project_impl.sh",
            "rotate_key.sh",
            "lib/rename_project_impl.sh",
        }:
            source = (GENERATE / script_name).read_text(encoding="utf-8")
            self.assertIn("chmod 644", source, script_name)
            self.assertNotIn("chmod 600", source, script_name)

    def test_unprivileged_nginx_can_read_and_render_its_template(self):
        dockerfile = (GENERATE / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("--chown=101:101", dockerfile)
        self.assertIn("--chmod=0400", dockerfile)
        self.assertIn("ENTRYPOINT", dockerfile)
        self.assertIn("envsubst '$FILE_SIZE_LIMIT'", dockerfile)
        self.assertNotIn("/etc/nginx/templates/", dockerfile)

    def test_key_expiry_and_collaboration_tabs_are_exposed(self):
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
        self.assertIn('"key_expiring_soon"', main)
        self.assertIn("length: 5", dialog)
        self.assertIn("text: 'Tags'", dialog)
        self.assertIn("_buildTagsTab(data)", dialog)
        self.assertIn("Keys expiram", card)


if __name__ == "__main__":
    unittest.main()
