from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class UserAvatarThumbnailTests(unittest.TestCase):
    def test_cache_loads_picture_from_authelia(self) -> None:
        source = (ROOT / "studio/nginx/lua/init/init_worker.lua").read_text(encoding="utf-8")
        self.assertIn('picture = attr.picture or ""', source)

    def test_authenticated_directory_can_serve_any_active_user(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('uri:match("^/api/users/([^/]+)/avatar$")', source)
        self.assertIn("target.is_active ~= true", source)
        self.assertIn("target.user_uuid ~= canonical", source)
        self.assertNotIn("project_members", source)

    def test_avatar_routes_keep_mutation_under_user_me(self) -> None:
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        handler = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('location ~ "^/api/users/[^/]+/avatar$"', nginx)
        self.assertIn('uri ~= "/api/user/me/avatar"', handler)
        self.assertEqual(handler.count('uri:match("^/api/users/'), 1)
        self.assertIn('if not requested_user_id then', handler)

    def test_lua_owns_bounded_image_normalization(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        dockerfile = (ROOT / "studio/Dockerfile").read_text(encoding="utf-8")
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")

        self.assertIn('require("ngx.pipe")', source)
        self.assertIn('pipe.spawn(args, {', source)
        self.assertIn('"/usr/bin/vipsheader"', source)
        self.assertIn('"/usr/bin/vipsthumbnail"', source)
        self.assertIn('output_path .. "[Q=85,strip]"', source)
        self.assertIn('image_field(input_path, "n-pages")', source)
        self.assertIn("width * height > MAX_PIXELS", source)
        self.assertIn("width > MAX_SOURCE_EDGE", source)
        self.assertIn("MAX_PROCESS_CONCURRENCY", source)
        self.assertIn("libvips-tools", dockerfile)
        self.assertNotIn("avatar-processor", compose)
        self.assertIn("worker_processes auto", nginx)
        self.assertIn("lua_shared_dict avatar_processing 1m", nginx)

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
