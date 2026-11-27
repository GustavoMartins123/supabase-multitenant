"""Smoke and Lua runtime contracts for Studio S3/Vectors gateway compatibility."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
NGINX = ROOT / "studio" / "nginx" / "nginx.conf"
COMPOSE = ROOT / "studio" / "docker-compose.yml"
ENV_EXAMPLE = ROOT / "studio" / ".env.example"
LUA = ROOT / "studio" / "nginx" / "lua"
PROJECT_CONTEXT_RESPONSE = LUA / "studio_compat" / "project_context_response.lua"
S3_KEYS_ACCESS = LUA / "security" / "studio_s3_keys_access.lua"


def lua_runtime() -> str | None:
    return shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")


class StudioVectorCompatContractTest(unittest.TestCase):
    def test_nginx_declares_storage_region_variables_hash_and_accept_encoding(self) -> None:
        nginx = NGINX.read_text(encoding="utf-8")
        compose = COMPOSE.read_text(encoding="utf-8")
        env_example = ENV_EXAMPLE.read_text(encoding="utf-8")

        self.assertIn("env STORAGE_S3_REGION;", nginx)
        self.assertIn("variables_hash_max_size 2048;", nginx)
        self.assertIn("STORAGE_S3_REGION: ${STORAGE_S3_REGION:-us-east-1}", compose)
        self.assertIn("STORAGE_S3_REGION=us-east-1", env_example)

        storage_start = nginx.index("location /api/platform/storage {")
        storage_end = nginx.index("\n        }", storage_start)
        storage_block = nginx[storage_start:storage_end]
        self.assertIn('proxy_set_header Accept-Encoding "";', storage_block)

    def test_deployment_mode_location_returns_json_with_auth_and_headers(self) -> None:
        nginx = NGINX.read_text(encoding="utf-8")
        start = nginx.index("location = /api/platform/deployment-mode {")
        end = nginx.index("\n        }", start)
        block = nginx[start:end]

        self.assertNotIn("auth_request off;", block)
        self.assertIn("snippets/security_headers.conf;", block)
        self.assertIn('add_header Cache-Control "no-store" always;', block)
        self.assertIn('ngx.req.get_method() ~= "GET"', block)
        self.assertIn('ngx.header["Allow"] = "GET"', block)
        self.assertIn('ngx.say(\'{"is_cli_mode":false}\')', block)
        self.assertNotIn('"is_cli_mode":true', block)
        self.assertIn('application/json; charset=utf-8', block)

    def test_s3_keys_has_dedicated_location_before_projects_catch_all(self) -> None:
        nginx = NGINX.read_text(encoding="utf-8")
        s3_marker = 'location ~ "^/api/projects/(?<s3_keys_ref>[a-z]{20})/storage/s3-keys$"'
        catch_all_marker = "location ~ ^/api/projects(/.*)?$"

        s3_start = nginx.index(s3_marker)
        catch_all_start = nginx.index(catch_all_marker)
        self.assertLess(s3_start, catch_all_start)

        s3_end = nginx.index("\n        }", s3_start)
        block = nginx[s3_start:s3_end]
        self.assertIn("security/studio_s3_keys_access.lua;", block)
        self.assertIn("snippets/backend_tls_headers.conf;", block)
        self.assertIn("snippets/security_headers.conf;", block)
        self.assertIn('add_header Cache-Control "no-store, max-age=0" always;', block)
        self.assertIn('add_header Pragma "no-cache" always;', block)
        self.assertIn('proxy_set_header Cookie "";', block)
        self.assertIn('proxy_set_header Authorization "";', block)
        self.assertIn(
            "proxy_pass $server_domain/api/projects/$s3_keys_ref/storage/s3-keys$is_args$args;",
            block,
        )

    def test_project_context_response_has_no_hardcoded_local_region(self) -> None:
        source = PROJECT_CONTEXT_RESPONSE.read_text(encoding="utf-8")
        self.assertNotIn('region = "local"', source)
        self.assertEqual(source.count("region = storage_s3_region(),"), 4)
        self.assertIn('os.getenv("STORAGE_S3_REGION")', source)

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
    def test_project_context_response_uses_storage_s3_region_at_runtime(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        script = f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local encoded_payload
package.loaded["cjson"] = {{
    array_mt = {{}},
    encode = function(value)
        encoded_payload = value
        return "{{}}"
    end,
}}
package.loaded["security.project_access"] = {{
    enforce = function()
        return {{
            ref = "abcdefghijklmnopqrst",
            display_name = "Demo",
            project_uuid = "11111111-1111-4111-8111-111111111111",
            tenant_uuid = "22222222-2222-4222-8222-222222222222",
            anon_key = "anon-fixture",
            file_size_limit = 52428800,
        }}
    end,
}}

local function run_uri(uri)
    encoded_payload = nil
    _G.ngx = {{
        HTTP_OK = 200,
        HTTP_NOT_FOUND = 404,
        HTTP_METHOD_NOT_ALLOWED = 405,
        ctx = {{}},
        var = {{ uri = uri, authelia_email = "user@example.test" }},
        header = {{}},
        req = {{
            get_method = function() return "GET" end,
            get_headers = function() return {{}} end,
        }},
        say = function() end,
        exit = function(code) return code end,
    }}
    local chunk = assert(loadfile("{PROJECT_CONTEXT_RESPONSE.as_posix()}"))
    chunk()
    return encoded_payload
end

local expected = arg[1]
local detail = run_uri("/api/platform/projects/abcdefghijklmnopqrst")
assert(detail.region == expected, "detail region=" .. tostring(detail.region))
local settings = run_uri("/api/platform/projects/abcdefghijklmnopqrst/settings")
assert(settings.region == expected, "settings region=" .. tostring(settings.region))
local props = run_uri("/api/platform/props/project/abcdefghijklmnopqrst/api")
assert(props.project.region == expected, "props region=" .. tostring(props.project.region))
local dbs = run_uri("/api/platform/projects/abcdefghijklmnopqrst/databases")
assert(dbs[1].region == expected, "databases region=" .. tostring(dbs[1].region))
'''
        for raw_env, expected in (
            (None, "us-east-1"),
            ("   ", "us-east-1"),
            ("  sa-east-1  ", "sa-east-1"),
        ):
            env = os.environ.copy()
            if raw_env is None:
                env.pop("STORAGE_S3_REGION", None)
            else:
                env["STORAGE_S3_REGION"] = raw_env
            with self.subTest(storage_s3_region=raw_env):
                subprocess.run(
                    [runtime, "-", expected],
                    input=script,
                    text=True,
                    check=True,
                    env=env,
                )

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
    def test_studio_s3_keys_access_guards_at_runtime(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        script = f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
package.loaded["cjson.safe"] = {{
    encode = function(tbl) return tbl.error or "err" end,
}}

local REF = "abcdefghijklmnopqrst"
local OTHER = "bcdefghijklmnopqrstu"
local state

local function run_case(opts)
    state = {{
        set_headers = {{}},
        cleared_headers = {{}},
        enforced_ref = nil,
        signed = false,
        exited = nil,
    }}

    package.loaded["security.admin_groups"] = {{
        is_admin = function(groups)
            return groups == "admin"
        end,
    }}
    package.loaded["security.project_access"] = {{
        enforce = function(expected_ref)
            state.enforced_ref = expected_ref
            local hdr = _G.ngx.var.http_x_studio_project_ref
            if hdr ~= expected_ref then
                _G.ngx.status = 409
                state.exited = 409
                return nil
            end
            return {{ ref = expected_ref, role = opts.role or "admin" }}
        end,
    }}
    package.loaded["security.projects_api_signer"] = {{
        enforce = function()
            state.signed = true
            return true
        end,
    }}

    _G.ngx = {{
        HTTP_BAD_REQUEST = 400,
        HTTP_UNAUTHORIZED = 401,
        HTTP_FORBIDDEN = 403,
        HTTP_NOT_ALLOWED = 405,
        ERR = 3,
        status = 200,
        header = {{}},
        ctx = {{ canonical_groups = opts.groups or "" }},
        var = {{
            uri = opts.uri or ("/api/projects/" .. REF .. "/storage/s3-keys"),
            request_uri = opts.request_uri or ("/api/projects/" .. REF .. "/storage/s3-keys"),
            args = opts.args,
            s3_keys_ref = opts.s3_keys_ref ~= nil and opts.s3_keys_ref or REF,
            authelia_email = opts.email ~= nil and opts.email or "admin@example.test",
            http_x_studio_project_ref = opts.header_ref,
        }},
        req = {{
            get_method = function() return opts.method or "GET" end,
            set_header = function(k, v)
                state.set_headers[k] = v
                if k == "X-Studio-Project-Ref" then
                    _G.ngx.var.http_x_studio_project_ref = v
                end
            end,
            clear_header = function(k) state.cleared_headers[k] = true end,
        }},
        say = function(msg) state.said = msg end,
        exit = function(code) state.exited = code; return code end,
        log = function() end,
    }}

    local chunk = assert(loadfile("{S3_KEYS_ACCESS.as_posix()}"))
    chunk()
    return state
end

-- 1. POST rejected with 405 and Allow: GET
local res = run_case({{ method = "POST" }})
assert(res.exited == 405 and _G.ngx.header["Allow"] == "GET" and not res.signed)

-- 2. Query string rejected with 400
res = run_case({{ args = "foo=1", request_uri = "/api/projects/" .. REF .. "/storage/s3-keys?foo=1" }})
assert(res.exited == 400 and not res.signed)

-- 3. Bare trailing '?' rejected with 400
res = run_case({{ args = "", request_uri = "/api/projects/" .. REF .. "/storage/s3-keys?" }})
assert(res.exited == 400 and not res.signed)

-- 4. Path normalization mismatch rejected with 400
res = run_case({{ request_uri = "/api/projects/" .. REF .. "/storage/../storage/s3-keys" }})
assert(res.exited == 400 and not res.signed)

-- 5. Unauthenticated rejected with 401
res = run_case({{ email = "" }})
assert(res.exited == 401 and not res.signed)

-- 6. Mismatched X-Studio-Project-Ref header rejected with 409
res = run_case({{ header_ref = OTHER }})
assert(res.exited == 409 and not res.signed)

-- 7. Non-admin project member rejected with 403
res = run_case({{ role = "member", groups = "active" }})
assert(res.exited == 403 and not res.signed)

-- 8. Project admin without tab header succeeds, strips Cookie/Authorization, and signs
res = run_case({{ role = "admin", groups = "active" }})
assert(res.exited == nil and res.enforced_ref == REF and res.signed)
assert(res.set_headers["X-Studio-Project-Ref"] == REF)
assert(res.cleared_headers["Cookie"] and res.cleared_headers["Authorization"] and res.cleared_headers["Proxy-Authorization"])

-- 9. Global admin succeeds even when project_members role is member
res = run_case({{ role = "member", groups = "admin", header_ref = REF }})
assert(res.exited == nil and res.enforced_ref == REF and res.signed)
'''
        subprocess.run([runtime, "-e", script], check=True)


if __name__ == "__main__":
    unittest.main()
