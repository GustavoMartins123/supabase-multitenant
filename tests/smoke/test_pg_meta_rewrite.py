"""Smoke and runtime tests for studio/nginx/lua/proxy_rewrites/pg_meta.lua (SEC-07a)."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PG_META_LUA = ROOT / "studio" / "nginx" / "lua" / "proxy_rewrites" / "pg_meta.lua"
PG_META_ACCESS_LUA = ROOT / "studio" / "nginx" / "lua" / "security" / "pg_meta_access.lua"
RUNTIME_SPEC = ROOT / "tests" / "smoke" / "test_pg_meta_rewrite_runtime.lua"


def lua_runtime() -> str | None:
    return shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")


class PgMetaRewriteHardeningTest(unittest.TestCase):
    def test_pg_meta_rewrite_enforces_strict_id_and_truncated_args_guards(self) -> None:
        source = PG_META_LUA.read_text(encoding="utf-8")
        access = PG_META_ACCESS_LUA.read_text(encoding="utf-8")

        self.assertIn('args_err == "truncated"', source)
        self.assertIn('id == "."', source)
        self.assertIn('id == ".."', source)
        self.assertIn('id:find("..", 1, true)', source)
        self.assertIn('id:match("^[A-Za-z0-9_.:%-]+$")', source)
        self.assertIn("ngx.escape_uri(id)", source)
        self.assertNotIn("{2,39}", source)

        self.assertIn('require("proxy_rewrites.pg_meta").rewrite(context)', access)
        self.assertIn("ngx.HTTP_BAD_REQUEST", access)

    def test_pg_meta_lua_syntax_compiles(self) -> None:
        compiler = shutil.which("luac5.1") or shutil.which("luac")
        if compiler is None:
            self.skipTest("luac nao esta instalado")
        for target in (PG_META_LUA, RUNTIME_SPEC):
            with self.subTest(target=target.name):
                subprocess.run([compiler, "-p", str(target)], check=True)

    def test_pg_meta_rewrite_runtime_rejects_traversal_and_smuggling(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            self.skipTest("runtime Lua nao esta instalado")
        for region_env in (None, "sa-east-1"):
            env = os.environ.copy()
            if region_env is None:
                env.pop("STORAGE_S3_REGION", None)
            else:
                env["STORAGE_S3_REGION"] = region_env
            with self.subTest(storage_s3_region=region_env):
                result = subprocess.run(
                    [runtime, str(RUNTIME_SPEC)],
                    cwd=ROOT,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
                self.assertIn("pg_meta rewrite runtime: ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
