from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class UserAvatarThumbnailTests(unittest.TestCase):
    def test_avatar_uuid_normalization_uses_lua_patterns_correctly(self) -> None:
        runtime = shutil.which("lua5.1") or shutil.which("lua")
        if not runtime:
            self.skipTest("Lua runtime is not installed")

        lua_root = (ROOT / "studio/nginx/lua").as_posix()
        script = f'''\
package.path = "{lua_root}/?.lua;{lua_root}/?/init.lua;" .. package.path
package.preload["ngx.pipe"] = function() return {{}} end

local processor = require("admin_api.avatar_processor")
assert(processor.normalize_uuid("11111111-2222-3333-4444-555555555555")
    == "11111111-2222-3333-4444-555555555555")
assert(processor.normalize_uuid("AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE")
    == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
assert(processor.normalize_uuid("not-a-uuid") == nil)
assert(processor.normalize_uuid("11111111-2222-3333-4444-55555555555") == nil)
assert(processor.normalize_uuid("11111111-2222-3333-4444-555555555555/../x") == nil)
'''
        subprocess.run(
            [runtime, "-"],
            input=script,
            text=True,
            check=True,
            capture_output=True,
        )

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
        content = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_content.lua"
        ).read_text(encoding="utf-8")
        self.assertIn('location ~ "^/api/users/[^/]+/avatar$"', nginx)
        self.assertIn(
            "content_by_lua_file "
            "/usr/local/openresty/lualib/admin_api/user_avatar_content.lua;",
            nginx,
        )
        self.assertNotIn(
            "content_by_lua_file "
            "/usr/local/openresty/lualib/admin_api/user_avatar_handler.lua;",
            nginx,
        )
        self.assertIn(
            'return require("admin_api.user_avatar_handler").handle()',
            content,
        )
        self.assertIn('uri ~= "/api/user/me/avatar"', handler)
        self.assertEqual(handler.count('uri:match("^/api/users/'), 1)
        self.assertIn('if not requested_user_id then', handler)

    def test_avatar_content_entrypoint_invokes_the_handler(self) -> None:
        content = ROOT / "studio/nginx/lua/admin_api/user_avatar_content.lua"
        runtime = shutil.which("lua5.1") or shutil.which("lua")
        if not runtime:
            self.skipTest("Lua runtime is not installed")

        script = f'''\
local calls = 0
package.preload["admin_api.user_avatar_handler"] = function()
    return {{ handle = function() calls = calls + 1 end }}
end
dofile("{content.as_posix()}")
assert(calls == 1)
'''
        subprocess.run(
            [runtime, "-"],
            input=script,
            text=True,
            check=True,
            capture_output=True,
        )

    def test_avatar_get_flushes_the_binary_body_without_early_exit(self) -> None:
        handler_path = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        )
        source = handler_path.read_text(encoding="utf-8")
        serve_start = source.index("local function serve(path)")
        serve_end = source.index("local function upload", serve_start)
        serve = source[serve_start:serve_end]

        self.assertIn('ngx.header["Content-Length"] = #data', serve)
        self.assertIn("ngx.print(data)", serve)
        self.assertNotIn("ngx.exit(200)", serve)

        runtime = shutil.which("lua5.1") or shutil.which("lua")
        if not runtime:
            self.skipTest("Lua runtime is not installed")

        lua_root = (ROOT / "studio/nginx/lua").as_posix()
        script = f'''\
package.path = "{lua_root}/?.lua;{lua_root}/?/init.lua;" .. package.path

local user_id = "11111111-2222-3333-4444-555555555555"
local payload = "RIFF-avatar-WEBP-binary-body"
local response_body = ""
local exit_calls = 0

package.preload["cjson.safe"] = function()
    return {{
        encode = function(_) return "{{}}" end,
        decode = function(_) return {{ is_active = true, user_uuid = user_id }} end,
    }}
end
package.preload["lfs"] = function()
    return {{
        attributes = function(_, attribute)
            if attribute == "mode" then return "file" end
            return {{ modification = 123, size = #payload }}
        end,
    }}
end
package.preload["admin_api.avatar_processor"] = function()
    return {{
        normalize_uuid = function(value) return value end,
        avatar_path = function(directory, value)
            return directory .. "/" .. value .. ".avatar"
        end,
        marker_path = function(path) return path .. ".normalized-v2" end,
        read_limited_file = function(_) return payload end,
        detect_type = function(_) return "image/webp" end,
    }}
end
package.preload["admin_api.user_profile_store"] = function()
    return {{
        get = function(_)
            return {{
                user_id = user_id,
                username = "admin",
                email = "admin@example.test",
                groups = {{}},
                is_active = true,
            }}
        end,
    }}
end
package.preload["admin_api.user_sync"] = function()
    return {{ sync_user = function(_) return true end }}
end

ngx = {{
    HTTP_OK = 200,
    HTTP_SERVICE_UNAVAILABLE = 503,
    status = 0,
    header = {{}},
    var = {{
        authelia_email = "admin@example.test",
        uri = "/api/users/" .. user_id .. "/avatar",
        http_if_none_match = nil,
    }},
    req = {{ get_method = function() return "GET" end }},
    shared = {{ users_cache = {{ get = function(_, _) return "{{}}" end }} }},
    print = function(value) response_body = response_body .. value end,
    say = function(_) error("unexpected JSON response") end,
    exit = function(status)
        exit_calls = exit_calls + 1
        return status
    end,
}}

local handler = require("admin_api.user_avatar_handler")
handler.handle()

assert(ngx.status == 200)
assert(ngx.header.content_type == "image/webp")
assert(ngx.header["Content-Length"] == #payload)
assert(response_body == payload)
assert(exit_calls == 0)
'''
        subprocess.run(
            [runtime, "-"],
            input=script,
            text=True,
            check=True,
            capture_output=True,
        )

    def test_lua_owns_bounded_image_normalization(self) -> None:
        handler = (
            ROOT / "studio/nginx/lua/admin_api/user_avatar_handler.lua"
        ).read_text(encoding="utf-8")
        source = (
            ROOT / "studio/nginx/lua/admin_api/avatar_processor.lua"
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
        self.assertIn('require("admin_api.avatar_processor")', handler)
        self.assertIn('stored avatar is not normalized', handler)
        self.assertNotIn("normalize_stored_avatar", handler)
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
            "studio/seletor_de_projetos/lib/models/all_users.dart",
            "studio/seletor_de_projetos/lib/models/project_member.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("pictureUrl", source, relative)
            self.assertIn("picture_url", source, relative)

    def test_visible_user_lists_use_thumbnail_widget(self) -> None:
        for relative in (
            "studio/seletor_de_projetos/lib/widgets/admin_users/user_card.dart",
            "studio/seletor_de_projetos/lib/dialogs/add_member_dialog.dart",
            "studio/seletor_de_projetos/lib/widgets/project_settings/members_section.dart",
        ):
            source = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("UserAvatarThumbnail", source, relative)


if __name__ == "__main__":
    unittest.main()
