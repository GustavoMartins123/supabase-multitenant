"""Contrato dos pontos de restauração: comandos, rotas, schema e scripts."""

from __future__ import annotations

import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
AGENT_ROOT = ROOT / "servidor" / "host-agent"
API_ROOT = ROOT / "servidor" / "api-internal"
SCRIPTS_ROOT = ROOT / "servidor" / "generateProject"
NGINX_CONFIG = ROOT / "studio" / "nginx" / "nginx.conf"
SELECTOR_LIB = ROOT / "studio" / "seletor_de_projetos" / "lib"

for path in (str(AGENT_ROOT), str(API_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from hostagent import host_agent_protocol as protocol
from hostagent.commands import (
    BACKUP_PROGRESS_EVENTS,
    RunningCommandState,
    _apply_progress_events,
)


class RestorePointProtocolTest(unittest.TestCase):
    def test_commands_are_registered_with_timeouts(self) -> None:
        for command in ("backup_project", "restore_project", "delete_restore_point"):
            self.assertIn(command, protocol.HOST_AGENT_COMMANDS)
            self.assertGreater(protocol.COMMAND_TIMEOUTS[command], 0)
        self.assertGreaterEqual(protocol.COMMAND_TERM_GRACE["restore_project"], 240)

    def test_commands_are_member_accessible_not_global_admin_only(self) -> None:
        expected = {"backup_project", "restore_project", "delete_restore_point"}
        self.assertEqual(protocol.PROJECT_MEMBER_COMMANDS, expected)
        self.assertFalse(expected & protocol.GLOBAL_ADMIN_COMMANDS)
        self.assertFalse(expected & protocol.PROJECT_ROW_OPTIONAL_COMMANDS)


class RestorePointApiSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.main_source = (API_ROOT / "app" / "main.py").read_text(encoding="utf-8")

    def test_endpoints_exist(self) -> None:
        for route in (
            '@app.get("/api/projects/{project_name}/restore-points")',
            '@app.post("/api/projects/{project_name}/restore-points", status_code=202)',
            '"/api/projects/{project_name}/restore-points/{point_id}/restore"',
            '"/api/projects/{project_name}/restore-points/{point_id}"',
        ):
            self.assertIn(route, self.main_source)

    def test_endpoints_authorize_project_members_and_serialize_limit(self) -> None:
        self.assertIn("RESTORE_POINT_LIMIT = 15", self.main_source)
        self.assertIn("_count_active_restore_points", self.main_source)
        for runner in (
            "_create_restore_point_background",
            "_restore_project_background",
            "_delete_restore_point_background",
        ):
            self.assertIn(runner, self.main_source)

    def test_schema_declares_restore_points_table(self) -> None:
        schema_source = (API_ROOT / "app" / "database_schema.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("project_restore_points", schema_source)
        self.assertIn(
            "created_by UUID REFERENCES users(id) ON DELETE SET NULL",
            schema_source,
        )
        self.assertIn("ensure_restore_points_schema", schema_source)
        self.assertIn("ensure_restore_points_schema", self.main_source)

    def test_api_exposes_restore_point_creator_name(self) -> None:
        self.assertIn('"created_by_name": row["created_by_name"]', self.main_source)
        self.assertIn(
            "COALESCE(u.display_name, u.authelia_username, 'Sistema') AS created_by_name",
            self.main_source,
        )
        self.assertGreaterEqual(
            self.main_source.count("job_id, created_by, project_ref_at_creation"),
            2,
        )

    def test_delete_flow_passes_project_uuid_for_backup_cleanup(self) -> None:
        self.assertIn('{"project_uuid": project_uuid}', self.main_source)


class RestorePointScriptsTest(unittest.TestCase):
    def test_scripts_exist(self) -> None:
        for name in (
            "backup_project.sh",
            "restore_project.sh",
            "lib/backup_core.sh",
            "lib/backup_project_impl.sh",
            "lib/restore_project_impl.sh",
        ):
            self.assertTrue((SCRIPTS_ROOT / name).is_file(), name)

    def test_restore_script_emits_contract_markers(self) -> None:
        source = (SCRIPTS_ROOT / "lib" / "restore_project_impl.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("SAFETY_BACKUP_COMPLETE", source)
        self.assertIn("ROLLBACK_COMPLETE", source)
        self.assertIn("ROLLBACK_INCOMPLETE", source)
        self.assertIn("_prerestore", source)

    def test_capture_excludes_realtime_and_keeps_manifest(self) -> None:
        source = (SCRIPTS_ROOT / "lib" / "backup_core.sh").read_text(encoding="utf-8")
        self.assertIn("--exclude-schema=realtime", source)
        self.assertIn("manifest.json", source)
        self.assertIn("storage.tar.gz", source)

    def test_backup_emits_progress_for_real_capture_stages(self) -> None:
        core = (SCRIPTS_ROOT / "lib" / "backup_core.sh").read_text(encoding="utf-8")
        implementation = (SCRIPTS_ROOT / "lib" / "backup_project_impl.sh").read_text(
            encoding="utf-8"
        )
        source = core + implementation
        for marker in BACKUP_PROGRESS_EVENTS:
            event = marker.removeprefix("HOST_AGENT_PROGRESS=backup:")
            self.assertIn(f"backup_progress {event}", source)


class RestorePointProgressTest(unittest.TestCase):
    def test_host_agent_applies_each_backup_progress_event_once(self) -> None:
        state = RunningCommandState()
        seen: set[str] = set()
        database_marker = "HOST_AGENT_PROGRESS=backup:database_started"
        storage_marker = "HOST_AGENT_PROGRESS=backup:storage_archived"

        _apply_progress_events(database_marker, state, BACKUP_PROGRESS_EVENTS, seen)
        self.assertEqual((state.progress, state.current_step), (25, "backup_database"))
        self.assertTrue(state.progress_changed.is_set())

        state.progress_changed.clear()
        _apply_progress_events(database_marker, state, BACKUP_PROGRESS_EVENTS, seen)
        self.assertFalse(state.progress_changed.is_set())

        _apply_progress_events(storage_marker, state, BACKUP_PROGRESS_EVENTS, seen)
        self.assertEqual((state.progress, state.current_step), (85, "backup_storage"))


class RestorePointGatewayAndUiTest(unittest.TestCase):
    def test_nginx_routes_restore_points_with_auth(self) -> None:
        source = NGINX_CONFIG.read_text(encoding="utf-8")
        self.assertIn("/restore-points$", source)
        self.assertIn("/restore-points/(?<point_id>[^/]+)/restore$", source)
        self.assertIn("/restore-points/(?<point_id>[^/]+)$", source)

    def test_selector_exposes_restore_points_ui(self) -> None:
        repository = (SELECTOR_LIB / "data" / "project_repository.dart").read_text(
            encoding="utf-8"
        )
        for method in (
            "fetchRestorePoints",
            "createRestorePoint",
            "restoreRestorePoint",
            "deleteRestorePoint",
        ):
            self.assertIn(method, repository)
        self.assertTrue(
            (SELECTOR_LIB / "dialogs" / "restore_points_dialog.dart").is_file()
        )
        model = (SELECTOR_LIB / "models" / "restore_point.dart").read_text(
            encoding="utf-8"
        )
        dialog = (SELECTOR_LIB / "dialogs" / "restore_points_dialog.dart").read_text(
            encoding="utf-8"
        )
        self.assertIn("createdByName: json['created_by_name']", model)
        self.assertIn("Criado por ${point.creatorName}", dialog)
        card = (SELECTOR_LIB / "widgets" / "project_card.dart").read_text(
            encoding="utf-8"
        )
        self.assertIn("restore_points", card)


if __name__ == "__main__":
    unittest.main()
