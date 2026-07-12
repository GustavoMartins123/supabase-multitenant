from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class UserAvatarThumbnailTests(unittest.TestCase):
    def test_cache_loads_picture_from_authelia(self) -> None:
        source = (ROOT / "studio/nginx/lua/init/init_worker.lua").read_text(encoding="utf-8")
        self.assertIn('picture = attr.picture or ""', source)

    def test_authenticated_avatar_handler_can_serve_requested_user(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        self.assertIn("requested_path = avatar_path(requested_user_id)", source)
        self.assertNotIn('avatar access denied', source)

    def test_user_lists_expose_picture_url(self) -> None:
        for relative in (
            "studio/nginx/lua/admin_api/users_list.lua",
            "studio/nginx/lua/admin_api/available_users.lua",
            "studio/nginx/lua/admin_api/project_members.lua",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("picture_url", source, relative)

    def test_flutter_models_parse_picture_url(self) -> None:
        for relative in (
            "studio/seletor_de_projetos/lib/models/user_models.dart",
            "studio/seletor_de_projetos/lib/models/AllUsers.dart",
            "studio/seletor_de_projetos/lib/models/project_member.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("pictureUrl", source, relative)
            self.assertIn("picture_url", source, relative)

    def test_visible_user_lists_use_thumbnail_widget(self) -> None:
        for relative in (
            "studio/seletor_de_projetos/lib/widgets/admin_users/user_card.dart",
            "studio/seletor_de_projetos/lib/dialogs/addMemberDialog.dart",
            "studio/seletor_de_projetos/lib/widgets/project_settings/members_section.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("UserAvatarThumbnail", source, relative)


if __name__ == "__main__":
    unittest.main()
