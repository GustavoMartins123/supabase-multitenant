from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_platform_router.lua"
REWRITE = ROOT / "studio/nginx/lua/proxy_rewrites/storage.lua"
VECTOR_PLATFORM = ROOT / "studio/nginx/lua/proxy_rewrites/storage_vector_platform.lua"
HEADER_FILTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_header_filter.lua"
BODY_FILTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_body_filter.lua"
KEY_INJECTOR = ROOT / "studio/nginx/lua/security/inject_service_key_storage.lua"
UPLOAD_GUARD = ROOT / "studio/nginx/lua/security/upload_route_guard.lua"
INTERNAL_HMAC = ROOT / "studio/nginx/lua/security/internal_hmac.lua"
PROJECTS_API_SIGNER = ROOT / "studio/nginx/lua/security/projects_api_signer.lua"
NGINX = ROOT / "studio/nginx/nginx.conf"


class StoragePlatformRouterTests(unittest.TestCase):
    def test_dead_object_sign_rewrite_is_removed(self) -> None:
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        self.assertNotIn("rewrite ^/object/sign$ /storage/v1/$1 break;", nginx)

    def test_vector_buckets_are_mapped_in_lua_not_nginx(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        nginx = NGINX.read_text(encoding="utf-8")

        self.assertIn('path == "/vector-buckets"', router)
        self.assertIn('/storage/v1/vector/ListVectorBuckets', router)
        self.assertIn('/storage/v1/vector/CreateVectorBucket', router)
        self.assertNotIn('vector-buckets', nginx)

    def test_object_sign_alias_is_rejected_not_normalized(self) -> None:
        nginx = NGINX.read_text(encoding="utf-8")
        guard = UPLOAD_GUARD.read_text(encoding="utf-8")

        self.assertIn("server_rewrite_by_lua_file", nginx)
        self.assertNotIn('ngx.req.set_uri("/storage/v1/object/sign", true)', guard)
        location = nginx.split('location /object/sign {', 1)[1].split('}', 1)[0]
        self.assertIn('return 410;', location)
        self.assertNotIn('proxy_pass', location)

    def test_get_is_adapted_to_the_storage_vector_post_contract(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        rewrite = REWRITE.read_text(encoding="utf-8")

        self.assertIn('method = "POST"', router)
        self.assertIn('body_mode = "vector_buckets_list"', router)
        self.assertIn('ngx.req.set_method(ngx.HTTP_POST)', rewrite)
        self.assertIn('return set_json_body(list_args)', rewrite)
        self.assertIn('ngx.req.set_uri_args({})', rewrite)

    def test_json_body_is_initialized_before_replacing_a_get_body(self) -> None:
        rewrite = REWRITE.read_text(encoding="utf-8")
        function_start = rewrite.index("local function set_json_body")
        function_end = rewrite.index("local function set_route_body", function_start)
        set_json_body = rewrite[function_start:function_end]

        self.assertIn("ngx.req.read_body()", set_json_body)
        self.assertLess(
            set_json_body.index("ngx.req.read_body()"),
            set_json_body.index("ngx.req.set_body_data(encoded)"),
        )

    def test_create_renames_the_studio_bucket_field(self) -> None:
        rewrite = REWRITE.read_text(encoding="utf-8")

        self.assertIn('local vector_bucket_name = body.bucketName', rewrite)
        self.assertIn('if body.vectorBucketName ~= nil then', rewrite)
        self.assertIn('set_json_body({ vectorBucketName = vector_bucket_name })', rewrite)

    def test_vector_bucket_detail_uses_get_vector_bucket_and_unwraps_response(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        rewrite = REWRITE.read_text(encoding="utf-8")
        header_filter = HEADER_FILTER.read_text(encoding="utf-8")
        body_filter = BODY_FILTER.read_text(encoding="utf-8")

        self.assertIn('/storage/v1/vector/GetVectorBucket', router)
        self.assertIn('body_mode = "vector_bucket_identity"', router)
        self.assertIn('response_mode = "unwrap_vector_bucket"', router)
        self.assertIn('vectorBucketName = route.vector_bucket_name', rewrite)
        self.assertIn('ngx.ctx.storage_platform_response_mode = route.response_mode', rewrite)
        self.assertIn('ngx.header.content_length = nil', header_filter)
        self.assertIn('cjson.encode(response_data.vectorBucket)', body_filter)

    def test_vector_bucket_patterns_escape_the_lua_hyphen_quantifier(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")

        self.assertIn('^/vector%-buckets/([^/]+)$', router)
        self.assertIn('^/vector%-buckets/([^/]+)/indexes$', router)
        self.assertIn('^/vector%-buckets/([^/]+)/indexes/([^/]+)$', router)
        self.assertNotIn('^/vector-buckets/([^/]+)$', router)
        self.assertNotIn('^/vector-buckets/([^/]+)/indexes$', router)

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
    def test_vector_bucket_patterns_resolve_at_runtime_when_lua_is_available(self) -> None:
        runtime = shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        lua_root = (ROOT / "studio/nginx/lua").as_posix()
        script = f'''
package.path = "{lua_root}/?.lua;{lua_root}/?/init.lua;" .. package.path
local router = require("proxy_rewrites.storage_platform_router")

local detail, detail_err = router.resolve(
    "/api/platform/storage/default/vector-buckets/rrrr",
    "GET"
)
assert(detail, detail_err and detail_err.message or "detail route missing")
assert(detail.route_name == "vector_bucket_get", detail.route_name)
assert(detail.vector_bucket_name == "rrrr", detail.vector_bucket_name)

local indexes, indexes_err = router.resolve(
    "/api/platform/storage/default/vector-buckets/rrrr/indexes",
    "GET"
)
assert(indexes, indexes_err and indexes_err.message or "indexes route missing")
assert(indexes.route_name == "vector_indexes_list", indexes.route_name)
assert(indexes.vector_bucket_name == "rrrr", indexes.vector_bucket_name)

local trailing_buckets, trailing_buckets_err = router.resolve(
    "/api/platform/storage/default/vector-buckets/",
    "GET"
)
assert(trailing_buckets, trailing_buckets_err and trailing_buckets_err.message or "trailing buckets missing")
assert(trailing_buckets.route_name == "vector_buckets_list", trailing_buckets.route_name)
assert(trailing_buckets.body_mode == "vector_buckets_list", trailing_buckets.body_mode)

local trailing_indexes, trailing_indexes_err = router.resolve(
    "/api/platform/storage/default/vector-buckets/rrrr/indexes/",
    "GET"
)
assert(trailing_indexes, trailing_indexes_err and trailing_indexes_err.message or "trailing indexes missing")
assert(trailing_indexes.route_name == "vector_indexes_list", trailing_indexes.route_name)
assert(trailing_indexes.vector_bucket_name == "rrrr", trailing_indexes.vector_bucket_name)
'''
        subprocess.run([runtime, "-e", script], check=True)

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
    def test_vector_list_query_params_arg_clearing_and_host_header_at_runtime(self) -> None:
        runtime = shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        lua_root = (ROOT / "studio/nginx/lua").as_posix()
        script = f'''
package.path = "{lua_root}/?.lua;{lua_root}/?/init.lua;" .. package.path

local function encode_value(v)
    local t = type(v)
    if t == "string" then
        return string.format("%q", v)
    elseif t == "number" or t == "boolean" then
        return tostring(v)
    elseif t == "table" then
        local mt = getmetatable(v)
        if mt and mt.__is_array then
            local items = {{}}
            for i = 1, #v do items[i] = encode_value(v[i]) end
            return "[" .. table.concat(items, ",") .. "]"
        end
        local keys = {{}}
        for k in pairs(v) do keys[#keys + 1] = k end
        table.sort(keys)
        local parts = {{}}
        for _, k in ipairs(keys) do
            parts[#parts + 1] = string.format("%q:%s", k, encode_value(v[k]))
        end
        return "{{" .. table.concat(parts, ",") .. "}}"
    end
    return "null"
end

local array_mt = {{ __is_array = true }}
local fake_cjson = {{
    array_mt = array_mt,
    null = {{}},
    encode = function(v) return encode_value(v) end,
    decode = function(raw)
        if raw == '{{"indexes":[{{"indexName":"idx1"}}],"nextToken":"tok2"}}' then
            return {{ indexes = {{ {{ indexName = "idx1" }} }}, nextToken = "tok2" }}
        end
        if raw == '{{"index":{{"indexName":"idx1","dimension":3}}}}' then
            return {{ index = {{ indexName = "idx1", dimension = 3 }} }}
        end
        return nil, "unsupported decode"
    end,
}}
package.loaded["utils.json"] = fake_cjson
package.loaded["cjson"] = fake_cjson
package.loaded["cjson.safe"] = fake_cjson
package.loaded["security.internal_hmac"] = {{
    read_current_body = function() return "" end,
}}

local state = {{}}
local function reset(uri, method, args, args_err)
    state = {{
        uri = uri,
        method = method or "GET",
        args = args or {{}},
        args_err = args_err,
        cleared_args = nil,
        body_set = nil,
        status = nil,
        said = nil,
        exited = nil,
        uri_set = nil,
        method_set = nil,
    }}
    _G.ngx = {{
        HTTP_OK = 200,
        HTTP_BAD_REQUEST = 400,
        HTTP_BAD_GATEWAY = 502,
        HTTP_INTERNAL_SERVER_ERROR = 500,
        HTTP_REQUEST_ENTITY_TOO_LARGE = 413,
        HTTP_POST = "POST",
        HTTP_PUT = "PUT",
        HTTP_DELETE = "DELETE",
        ERR = 3,
        DEBUG = 7,
        ctx = {{}},
        header = {{}},
        var = {{
            uri = state.uri,
            server_path = "https://10.0.0.10/abcdefghijklmnopqrst",
            server_hostname = "backend.internal.test",
        }},
        req = {{
            get_method = function() return state.method end,
            set_method = function(m) state.method_set = m; state.method = m end,
            get_uri_args = function() return state.args, state.args_err end,
            set_uri_args = function(a) state.cleared_args = a end,
            read_body = function() end,
            set_header = function() end,
            set_body_data = function(b) state.body_set = b end,
            set_uri = function(u) state.uri_set = u; _G.ngx.var.uri = u end,
        }},
        re = {{
            sub = function(s, pat, rep) return (s:gsub(pat, rep)) end,
            match = function(s, pat) return s:match(pat) end,
            gsub = function(s, pat, rep) return (s:gsub(pat, rep)) end,
        }},
        say = function(msg) state.said = msg end,
        exit = function(code) state.exited = code; return code end,
        log = function() end,
        thread = {{
            spawn = function(fn) return fn end,
            wait = function(fn) return true, fn() end,
        }},
    }}
end

local storage_rewrite = require("proxy_rewrites.storage")

-- 1. GET /vector-buckets forwards prefix/maxResults/nextToken and clears upstream URI args
reset(
    "/api/platform/storage/abcdefghijklmnopqrst/vector-buckets/",
    "GET",
    {{ prefix = "docs-", maxResults = "25", nextToken = "page-2" }}
)
storage_rewrite.rewrite()
assert(state.exited == nil, "unexpected exit: " .. tostring(state.said))
assert(state.uri_set == "/storage/v1/vector/ListVectorBuckets")
assert(state.method_set == "POST")
assert(type(state.cleared_args) == "table" and next(state.cleared_args) == nil, "vector query args not cleared")
assert(state.body_set == '{{"maxResults":25,"nextToken":"page-2","prefix":"docs-"}}', "unexpected body: " .. tostring(state.body_set))

-- 2. GET /vector-buckets with no params encodes empty JSON object
reset("/api/platform/storage/abcdefghijklmnopqrst/vector-buckets", "GET", {{}})
storage_rewrite.rewrite()
assert(state.exited == nil)
assert(state.body_set == "{{}}", "expected empty object, got: " .. tostring(state.body_set))
assert(type(state.cleared_args) == "table" and next(state.cleared_args) == nil)

-- 3. Invalid maxResults / prefix / nextToken / truncated args reject with 400
for _, bad in ipairs({{
    {{ args = {{ maxResults = "0" }} }},
    {{ args = {{ maxResults = "501" }} }},
    {{ args = {{ maxResults = "abc" }} }},
    {{ args = {{ maxResults = "10.5" }} }},
    {{ args = {{ prefix = {{ "a", "b" }} }} }},
    {{ args = {{ nextToken = true }} }},
    {{ args = {{ a = "1" }}, err = "truncated" }},
}}) do
    reset("/api/platform/storage/abcdefghijklmnopqrst/vector-buckets", "GET", bad.args, bad.err)
    storage_rewrite.rewrite()
    assert(state.exited == 400, "expected 400, got: " .. tostring(state.exited))
end

-- 4. Non-vector REST routes keep their query args intact
reset("/api/platform/storage/abcdefghijklmnopqrst/buckets/avatars/objects/download", "GET", {{ download = "1" }})
storage_rewrite.rewrite()
assert(state.exited == nil)
assert(state.uri_set == "/storage/v1/object/avatars")
assert(state.cleared_args == nil, "non-vector storage route must not clear query args")

-- 5. GET /vector-buckets/<name>/indexes/ forwards query args to ListIndexes and sets Host header
local captured_requests = {{}}
package.loaded["utils.outbound_tls"] = {{
    apply_internal = function(_, opts) return opts end,
}}
package.loaded["resty.http"] = {{
    new = function()
        return {{
            set_timeout = function() end,
            request_uri = function(_, url, opts)
                captured_requests[#captured_requests + 1] = {{ url = url, opts = opts }}
                if url:find("ListIndexes", 1, true) then
                    return {{
                        status = 200,
                        headers = {{ ["Content-Type"] = "application/json" }},
                        body = '{{"indexes":[{{"indexName":"idx1"}}],"nextToken":"tok2"}}',
                    }}
                end
                return {{
                    status = 200,
                    headers = {{ ["Content-Type"] = "application/json" }},
                    body = '{{"index":{{"indexName":"idx1","dimension":3}}}}',
                }}
            end,
        }}
    end,
}}

reset(
    "/api/platform/storage/abcdefghijklmnopqrst/vector-buckets/docs/indexes/",
    "GET",
    {{ prefix = "emb_", maxResults = "50", nextToken = "tok1" }}
)
storage_rewrite.rewrite()
assert(state.exited == nil, "unexpected rewrite error: " .. tostring(state.said))
assert(type(state.cleared_args) == "table" and next(state.cleared_args) == nil)
assert(_G.ngx.ctx.storage_platform_list_args.maxResults == 50)
assert(_G.ngx.ctx.storage_platform_list_args.prefix == "emb_")
assert(_G.ngx.ctx.storage_platform_list_args.nextToken == "tok1")
_G.ngx.ctx.service_key = "test-service-key"
local vector_platform = require("proxy_rewrites.storage_vector_platform")
assert(vector_platform.handle() == true)
assert(#captured_requests == 2, "expected ListIndexes + GetIndex")
assert(captured_requests[1].opts.headers["Host"] == "backend.internal.test")
assert(captured_requests[1].opts.body == '{{"maxResults":50,"nextToken":"tok1","prefix":"emb_","vectorBucketName":"docs"}}',
    "unexpected ListIndexes body: " .. tostring(captured_requests[1].opts.body))
assert(captured_requests[2].opts.headers["Host"] == "backend.internal.test")
assert(state.exited == 200)
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_vector_bucket_indexes_match_the_studio_contract(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        rewrite = REWRITE.read_text(encoding="utf-8")
        vector_platform = VECTOR_PLATFORM.read_text(encoding="utf-8")
        key_injector = KEY_INJECTOR.read_text(encoding="utf-8")

        self.assertIn('/storage/v1/vector/ListIndexes', router)
        self.assertIn('/storage/v1/vector/CreateIndex', router)
        self.assertIn('body_mode = "vector_indexes_list"', router)
        self.assertIn('body_mode = "vector_index_create"', router)
        self.assertIn('maxResults = list_args.maxResults or 100', rewrite)
        self.assertIn('maxResults = list_args.maxResults or 100', vector_platform)
        self.assertIn('headers["Host"] = host', vector_platform)
        self.assertIn('/storage/v1/vector/GetIndex', vector_platform)
        self.assertIn('payload.index', vector_platform)
        self.assertIn('indexes = indexes', vector_platform)
        self.assertIn('storage_vector_platform").handle()', key_injector)

    def test_vector_index_create_matches_the_studio_payload(self) -> None:
        rewrite = REWRITE.read_text(encoding="utf-8")

        self.assertIn('vectorBucketName = route.vector_bucket_name', rewrite)
        self.assertIn('indexName = body.indexName', rewrite)
        self.assertIn('dataType = body.dataType', rewrite)
        self.assertIn('dimension = body.dimension', rewrite)
        self.assertIn('distanceMetric = body.distanceMetric', rewrite)
        self.assertIn('nonFilterableMetadataKeys = json_array(metadata_keys)', rewrite)
        self.assertIn('if metadata_keys ~= nil and #metadata_keys > 0 then', rewrite)
        self.assertIn('storage_platform_invalid_metadata_keys', rewrite)

    def test_delete_routes_use_real_storage_vector_operations(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")

        self.assertIn('/storage/v1/vector/DeleteVectorBucket', router)
        self.assertIn('/storage/v1/vector/DeleteIndex', router)
        self.assertIn('body_mode = "vector_index_identity"', router)

    def test_vector_index_list_has_no_success_fallback_for_upstream_errors(self) -> None:
        vector_platform = VECTOR_PLATFORM.read_text(encoding="utf-8")

        self.assertIn('if list_res.status < 200 or list_res.status >= 300 then', vector_platform)
        self.assertIn('return respond_upstream(list_res)', vector_platform)
        self.assertIn('if res.status < 200 or res.status >= 300 then', vector_platform)
        self.assertNotIn('vectorBuckets = json_array({})', vector_platform)

    def test_existing_bucket_and_object_routes_are_described_by_the_router(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")

        self.assertIn('/storage/v1/bucket', router)
        for action in ('list = "list"', 'sign = "sign"', 'move = "move"'):
            self.assertIn(action, router)
        self.assertIn('"/storage/v1/object/" .. upstream_action .. "/" .. object_bucket', router)

    def test_unmapped_platform_routes_fail_with_a_diagnostic_error(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        rewrite = REWRITE.read_text(encoding="utf-8")

        self.assertIn('storage_platform_route_unmapped', router)
        self.assertIn('return reject(route_error)', rewrite)

    def test_lua_syntax_when_compiler_is_available(self) -> None:
        compiler = shutil.which("luac5.1") or shutil.which("luac")
        if compiler is None:
            self.skipTest("luac nao esta instalado")

        for path in (
            ROUTER,
            REWRITE,
            VECTOR_PLATFORM,
            HEADER_FILTER,
            BODY_FILTER,
            KEY_INJECTOR,
            UPLOAD_GUARD,
            INTERNAL_HMAC,
            PROJECTS_API_SIGNER,
        ):
            subprocess.run([compiler, "-p", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
