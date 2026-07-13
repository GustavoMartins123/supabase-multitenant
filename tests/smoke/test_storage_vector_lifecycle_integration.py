from __future__ import annotations

import ast
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "servidor/generateProject"
STUDIO_LUA = ROOT / "studio/nginx/lua"


class StorageVectorLifecycleIntegrationTests(unittest.TestCase):
    def test_public_lifecycle_entrypoints_are_stable_and_implemented(self) -> None:
        expectations = {
            "generate_project.sh": "lib/generate_project_impl.sh",
            "duplicate_project.sh": "lib/duplicate_project_impl.sh",
            "rename_project.sh": "lib/rename_project_impl.sh",
        }

        for entrypoint_name, implementation in expectations.items():
            entrypoint = GENERATOR / entrypoint_name
            content = entrypoint.read_text(encoding="utf-8")
            self.assertIn(implementation, content)
            self.assertTrue((GENERATOR / implementation).is_file())
            self.assertLessEqual(len(content.splitlines()), 6)

    def test_create_duplicate_and_rename_have_explicit_vector_semantics(self) -> None:
        create = (GENERATOR / "lib/generate_project_impl.sh").read_text(
            encoding="utf-8"
        )
        duplicate = (GENERATOR / "lib/duplicate_project_impl.sh").read_text(
            encoding="utf-8"
        )
        rename = (GENERATOR / "lib/rename_project_impl.sh").read_text(
            encoding="utf-8"
        )

        self.assertIn("vector_validate_storage_api", create)
        self.assertIn("vector_strip_copied_wrappers", duplicate)
        self.assertIn("vector_sync_project_wrappers", duplicate)
        self.assertIn("vector_sync_project_wrappers", rename)
        self.assertIn("S3_PROTOCOL_ACCESS_KEY_ID", create)
        self.assertIn("S3_PROTOCOL_ACCESS_KEY_ID", duplicate)
        self.assertIn("S3_PROTOCOL_ACCESS_KEY_ID", rename)

    def test_manual_bootstrap_scripts_were_not_left_at_the_root(self) -> None:
        self.assertFalse((GENERATOR / "enable_vector_storage.sh").exists())
        self.assertFalse((GENERATOR / "setup_vector_bucket_wrapper.sh").exists())

        operation = GENERATOR / "operations/setup_vector_bucket_wrapper.sh"
        library = GENERATOR / "lib/vector_lifecycle.sh"
        self.assertTrue(operation.is_file())
        self.assertTrue(library.is_file())
        self.assertIn(
            "operations/setup_vector_bucket_wrapper.sh",
            library.read_text(encoding="utf-8"),
        )

    def test_studio_get_s3_keys_is_project_scoped_and_admin_authorized(self) -> None:
        rewrite = (STUDIO_LUA / "security/upload_route_guard.lua").read_text(
            encoding="utf-8"
        )
        resolver = (
            STUDIO_LUA / "project_context/project_ref_resolver.lua"
        ).read_text(encoding="utf-8")
        asgi = (ROOT / "servidor/api-internal/app/asgi.py").read_text(
            encoding="utf-8"
        )
        dockerfile = (ROOT / "servidor/api-internal/Dockerfile").read_text(
            encoding="utf-8"
        )

        self.assertIn('uri == "/api/get-s3-keys"', rewrite)
        self.assertIn("project_ref_resolver", rewrite)
        self.assertIn("/storage/s3-keys", rewrite)
        self.assertIn("hmac_sha256.hex(COOKIE_SECRET", resolver)

        self.assertIn(
            '@app.get("/api/projects/{project_name}/storage/s3-keys")', asgi
        )
        self.assertIn("ensure_project_admin_access", asgi)
        self.assertIn('content={"accessKey": access_key, "secretKey": secret_key}', asgi)
        self.assertIn('"Cache-Control": "no-store, max-age=0"', asgi)
        self.assertIn('"app.asgi:app"', dockerfile)

    def test_studio_only_patches_s3_vector_wrapper_sql(self) -> None:
        pg_meta = (STUDIO_LUA / "proxy_rewrites/pg_meta.lua").read_text(
            encoding="utf-8"
        )

        self.assertIn("s3_vectors_fdw_handler", pg_meta)
        self.assertIn("s3_vectors_fdw_validator", pg_meta)
        self.assertIn("endpoint_url", pg_meta)
        self.assertIn(
            '"http://supabase-storage-" .. project_ref .. ":5000/vector"',
            pg_meta,
        )
        self.assertNotIn("host.docker.internal", pg_meta)

    def test_project_ref_resolver_rejects_all_refs_without_lua_pattern_bug(self) -> None:
        resolver = (
            STUDIO_LUA / "project_context/project_ref_resolver.lua"
        ).read_text(encoding="utf-8")
        pg_meta = (STUDIO_LUA / "proxy_rewrites/pg_meta.lua").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("{2,39}", resolver)
        self.assertNotIn("{2,39}", pg_meta)
        self.assertIn('ref:match("^[a-z_][a-z0-9_]*$")', resolver)
        self.assertIn('project_ref:match("^[a-z_][a-z0-9_]*$")', pg_meta)

    def test_project_ref_resolver_accepts_a_valid_signed_ref_at_runtime(self) -> None:
        runtime = shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")

        lua_root = STUDIO_LUA.as_posix()
        script = f'''
package.path = "{lua_root}/?.lua;{lua_root}/?/init.lua;" .. package.path
package.loaded["security.hmac_sha256"] = {{
    hex = function(key, message) return "deadbeef" end
}}
_G.COOKIE_SECRET = "test-secret"
_G.ngx = {{
    var = {{ uri = "/", cookie_supabase_project = "meu_projeto.1000000.deadbeef" }},
    time = function() return 1000000 end,
    log = function(...) end,
    header = {{}},
    WARN = "WARN",
    INFO = "INFO",
    ERR = "ERR",
}}
local resolver = require("project_context.project_ref_resolver")
local ref = resolver.resolve()
assert(ref == "meu_projeto", "esperava meu_projeto, obteve " .. tostring(ref))
'''
        subprocess.run([runtime, "-e", script], check=True)

    def test_python_and_shell_syntax(self) -> None:
        asgi_path = ROOT / "servidor/api-internal/app/asgi.py"
        ast.parse(asgi_path.read_text(encoding="utf-8"), filename=str(asgi_path))

        scripts = [
            *GENERATOR.glob("*.sh"),
            *GENERATOR.glob("lib/*.sh"),
            *GENERATOR.glob("operations/*.sh"),
            ROOT / "servidor/volumes/db/create_template.sh",
        ]
        for script in scripts:
            subprocess.run(["bash", "-n", str(script)], check=True)

    def test_lua_syntax_when_compiler_is_available(self) -> None:
        compiler = shutil.which("luac5.1") or shutil.which("luac")
        if compiler is None:
            self.skipTest("luac nao esta instalado")

        for path in (
            STUDIO_LUA / "project_context/project_ref.lua",
            STUDIO_LUA / "project_context/project_ref_resolver.lua",
            STUDIO_LUA / "security/upload_route_guard.lua",
            STUDIO_LUA / "proxy_rewrites/pg_meta.lua",
        ):
            subprocess.run([compiler, "-p", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
