from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class UserProfileContractTests(unittest.TestCase):
    def test_control_plane_persists_profile_projection(self) -> None:
        schema = (ROOT / "servidor/api-internal/app/database_schema.py").read_text(
            encoding="utf-8"
        )
        service = (
            ROOT / "servidor/api-internal/app/control_plane_service.py"
        ).read_text(encoding="utf-8")

        for column in (
            "email TEXT",
            "picture_url TEXT",
            "profile_data JSONB",
            "profile_version BIGINT",
            "profile_updated_at TIMESTAMPTZ",
        ):
            self.assertIn(column, schema)
        self.assertIn("normalize_user_sync_source", service)
        self.assertIn('action="user_profile_updated"', service)
        self.assertIn("PROFILE_FIELDS", service)

    def test_authelia_store_keeps_immutable_identity_and_atomic_writes(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_profile_store.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("username, email and picture are immutable", source)
        self.assertIn("os.rename(temp_path, YAML_PATH)", source)
        self.assertIn("lock_dict:add(LOCK_KEY, token, 8)", source)
        self.assertIn("authelia_identifiers.ensure_identifier(username)", source)
        self.assertIn("user.picture = value", source)

    def test_avatar_endpoint_validates_content_and_size(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("2 * 1024 * 1024", source)
        self.assertIn('return "image/png"', source)
        self.assertIn('return "image/jpeg"', source)
        self.assertIn('return "image/webp"', source)
        self.assertIn("X-Content-Type-Options", source)
        self.assertIn("store.set_picture", source)

    def test_user_me_dispatches_profile_and_avatar(self) -> None:
        content = (
            ROOT / "studio/nginx/lua/studio_compat/user_me_content.lua"
        ).read_text(encoding="utf-8")
        access = (
            ROOT / "studio/nginx/lua/security/user_me.lua"
        ).read_text(encoding="utf-8")

        self.assertIn('uri == "/api/user/me/avatar"', content)
        self.assertIn("user_profile_handler", content)
        self.assertNotIn('request_method ~= "GET"', access)

    def test_flutter_loads_profile_and_exposes_editor(self) -> None:
        main = (
            ROOT / "studio/seletor_de_projetos/lib/main.dart"
        ).read_text(encoding="utf-8")
        dialog = (
            ROOT / "studio/seletor_de_projetos/lib/user_profile_dialog.dart"
        ).read_text(encoding="utf-8")

        self.assertIn("Session().setProfile(UserProfile.fromJson(data))", main)
        self.assertIn("UserProfileLauncher", main)
        self.assertIn("http.patch", dialog)
        self.assertIn("/api/user/me/avatar", dialog)
        self.assertIn("FileUploadInputElement", dialog)
        self.assertNotIn("'email':", dialog)
        self.assertNotIn("'username':", dialog)


if __name__ == "__main__":
    unittest.main()
