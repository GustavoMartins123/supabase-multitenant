from __future__ import annotations

import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ROUTER = ROOT / "studio/nginx/lua/proxy_rewrites/storage_platform_router.lua"
REWRITE = ROOT / "studio/nginx/lua/proxy_rewrites/storage.lua"
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
        self.assertIn('set_json_body({})', rewrite)

    def test_json_body_is_initialized_before_replacing_a_get_body(self) -> None:
        rewrite = REWRITE.read_text(encoding="utf-8")
        function_start = rewrite.index("local function set_json_body")
        function_end = rewrite.index("local original_uri", function_start)
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

        for path in (ROUTER, REWRITE):
            subprocess.run([compiler, "-p", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
