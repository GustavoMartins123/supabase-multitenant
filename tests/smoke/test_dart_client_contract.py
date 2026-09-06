"""Contrato do cliente Dart gerado em studio/projects_api_client."""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLIENT = ROOT / "studio" / "projects_api_client"
APP = ROOT / "servidor" / "api-internal" / "app"


class DartClientContract(unittest.TestCase):
    def test_package_version_matches_the_api_version(self) -> None:
        version = (APP / "version.py").read_text(encoding="utf-8")
        api_version = version.split('API_VERSION = "')[1].split('"')[0]
        pubspec = (CLIENT / "pubspec.yaml").read_text(encoding="utf-8")
        self.assertIn(f"version: '{api_version}'", pubspec)

    def test_request_models_cover_the_stable_schemas(self) -> None:
        models = CLIENT / "lib" / "model"
        for name in (
            "new_project.dart",
            "duplicate_project.dart",
            "add_member.dart",
            "restore_point_create.dart",
            "update_settings.dart",
            "recreate_services.dart",
            "transfer_body.dart",
            "project_rename_request.dart",
        ):
            with self.subTest(model=name):
                self.assertTrue((models / name).is_file(), name)

    def test_api_classes_cover_every_router_tag(self) -> None:
        apis = CLIENT / "lib" / "api"
        for name in (
            "projects_api.dart",
            "project_rename_api.dart",
            "restore_points_api.dart",
            "project_keys_api.dart",
            "project_members_api.dart",
            "lifecycle_ops_api.dart",
            "project_insights_api.dart",
            "collaboration_api.dart",
            "jobs_api.dart",
            "opaque_api_keys_api.dart",
        ):
            with self.subTest(api=name):
                self.assertTrue((apis / name).is_file(), name)

    def test_regeneration_is_scripted(self) -> None:
        script = (ROOT / "tools" / "generate_dart_client.sh").read_text(encoding="utf-8")
        self.assertIn("export_openapi.py", script)
        self.assertIn("openapi-generator-cli", script)
        self.assertIn("patch_dart_client.py", script)
        self.assertIn("dart analyze", script)


if __name__ == "__main__":
    unittest.main()
