"""Contrato do perfil de recursos por projeto (criacao, edicao, protocolo)."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
APP = ROOT / "servidor" / "api-internal" / "app"


class BackendResourceProfileContract(unittest.TestCase):
    def test_migration_adds_column_with_check(self) -> None:
        sql = (APP / "migrations" / "0005_project_resource_profile.sql").read_text()
        self.assertIn("ADD COLUMN resource_profile TEXT NOT NULL DEFAULT 'medium'", sql)
        self.assertIn("resource_profile IN ('small', 'medium', 'large')", sql)

    def test_schemas_accept_only_the_three_profiles(self) -> None:
        source = (APP / "schemas.py").read_text()
        self.assertIn('ResourceProfile = Literal["small", "medium", "large"]', source)
        self.assertIn("resource_profile: ResourceProfile = \"medium\"", source)

    def test_settings_whitelist_and_derived_guard(self) -> None:
        source = (APP / "project_settings.py").read_text()
        self.assertIn('"PROJECT_RESOURCE_PROFILE"', source)
        self.assertIn("DERIVED_LIMIT_KEYS", source)
        self.assertLess(
            source.index("def _normalize_settings_updates"),
            source.index("injected = set(settings.keys()) & DERIVED_LIMIT_KEYS"),
        )

    def test_main_persists_and_passes_profile_to_agent(self) -> None:
        main = (APP / "main.py").read_text()
        self.assertIn("owner_id, resource_profile)", main)
        self.assertIn('"resource_profile": body.resource_profile,', main)
        self.assertIn("resolve_resource_limits(updates[\"PROJECT_RESOURCE_PROFILE\"])", main)

    def test_telemetry_is_fail_closed_without_reader_identity(self) -> None:
        main = (APP / "main.py").read_text()
        # Sem fallback legado: startup recusa e o endpoint responde 503.
        self.assertIn('user="platform_reader"', main)
        self.assertGreaterEqual(main.count("PLATFORM_READER_DB_PASSWORD"), 2)
        self.assertNotIn("else dsn.username", main)

    def test_compose_requires_reader_password(self) -> None:
        compose = (ROOT / "servidor" / "docker-compose-api.yml").read_text()
        self.assertIn(
            "PLATFORM_READER_DB_PASSWORD: ${PLATFORM_READER_DB_PASSWORD:?defina PLATFORM_READER_DB_PASSWORD}",
            compose,
        )

    def test_tenant_reader_role_helper_is_wired(self) -> None:
        helper = (
            ROOT / "servidor" / "generateProject" / "lib" / "tenant_reader_role.sh"
        ).read_text()
        self.assertIn("provision_platform_reader()", helper)
        self.assertIn("GRANT SELECT ON auth.users, auth.sessions TO platform_reader;", helper)
        for script in (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/duplicate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/restore_project_impl.sh",
        ):
            with self.subTest(script=script.name):
                source = script.read_text()
                self.assertIn("lib/tenant_reader_role.sh", source)
                self.assertIn("provision_platform_reader \"$", source)


class ProtocolAndAgentContract(unittest.TestCase):
    def test_protocol_validates_profiles_on_lifecycle_commands(self) -> None:
        import sys
        sys.path.insert(0, str(ROOT / "servidor" / "host-agent"))
        from hostagent import host_agent_protocol as proto
        uuid_ok = "9c8ce9f0-3b4e-4bcb-a739-2c1e8ad0e9aa"
        base = {"tenant_uuid": uuid_ok, "recover_stale": False,
                "stale_tenant_uuids": []}
        self.assertEqual(
            proto.validate_command_args("create_project", "demo",
                                        {**base, "resource_profile": "small"}),
            [],
        )
        self.assertEqual(
            proto.validate_command_args("create_project", "demo",
                                        {**base, "resource_profile": "huge"}),
            ["invalid_resource_profile"],
        )
        self.assertEqual(
            proto.validate_command_args("duplicate_project", "novo",
                                        {"original_name": "origem",
                                         "copy_mode": "schema-only",
                                         "tenant_uuid": uuid_ok,
                                         "resource_profile": "medium"}),
            [],
        )

    def test_handlers_inject_override_env(self) -> None:
        commands = (ROOT / "servidor/host-agent/hostagent/commands.py").read_text()
        self.assertEqual(commands.count("PROJECT_RESOURCE_PROFILE_OVERRIDE"), 3)

    def test_scripts_forward_override_to_helper(self) -> None:
        for name in ("generate_project_impl.sh", "duplicate_project_impl.sh",
                     "rename_project_impl.sh"):
            path = ROOT / "servidor/generateProject/lib" / name
            with self.subTest(script=name):
                self.assertIn('${PROJECT_RESOURCE_PROFILE_OVERRIDE:-}',
                              path.read_text())


class FlutterContract(unittest.TestCase):
    def test_new_dialog_has_dropdown_and_structured_result(self) -> None:
        dialog = (ROOT / "studio/seletor_de_projetos/lib/new_project_dialog.dart"
                  ).read_text()
        self.assertIn("_resourceProfile", dialog)
        self.assertIn("DropdownButtonFormField<String>", dialog)
        self.assertIn("(name: ProjectNameValidator.normalize(_ctrl.text),", dialog)

    def test_env_section_renders_select_for_profile(self) -> None:
        section = (ROOT / "studio/seletor_de_projetos/lib/widgets/"
                   "project_settings/env_settings_section.dart").read_text()
        self.assertIn("'PROJECT_RESOURCE_PROFILE'", section)
        self.assertIn("case _FieldType.select:", section)
        self.assertIn("_kSelectOptions", section)


if __name__ == "__main__":
    unittest.main()
