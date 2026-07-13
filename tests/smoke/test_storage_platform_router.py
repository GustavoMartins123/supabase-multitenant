from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_platform_router.lua"
REWRITE = ROOT / "studio/nginx/lua/proxy_rewrites/storage.lua"
VECTOR_PLATFORM = ROOT / "studio/nginx/lua/proxy_rewrites/storage_vector_platform.lua"
HEADER_FILTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_header_filter.lua"
BODY_FILTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_body_filter.lua"
KEY_INJECTOR = ROOT / "studio/nginx/lua/security/inject_service_key_storage.lua"
NGINX = ROOT / "studio/nginx/nginx.conf"


class StoragePlatformRouterTests(unittest.TestCase):
    def test_vector_buckets_are_mapped_in_lua_not_nginx(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        nginx = NGINX.read_text(encoding="utf-8")

        self.assertIn('path == "/vector-buckets"', router)
        self.assertIn('/storage/v1/vector/ListVectorBuckets', router)
        self.assertIn('/storage/v1/vector/CreateVectorBucket', router)
        self.assertNotIn('vector-buckets', nginx)

    def test_get_is_adapted_to_the_storage_vector_post_contract(self) -> None:
        router = ROUTER.read_text(encoding="utf-8")
        rewrite = REWRITE.read_text(encoding="utf-8")

        self.assertIn('method = "POST"', router)
        self.assertIn('body_mode = "empty_json_object"', router)
        self.assertIn('ngx.req.set_method(ngx.HTTP_POST)', rewrite)
        self.assertIn('return set_json_body({})', rewrite)

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

        self.assertIn('body.vectorBucketName or body.bucketName', rewrite)
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
        self.assertIn('maxResults = 100', rewrite)
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
        self.assertIn('nonFilterableMetadataKeys = metadata_keys', rewrite)

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
        ):
            subprocess.run([compiler, "-p", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
