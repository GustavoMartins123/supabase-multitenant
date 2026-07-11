import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LUA_ROOT = ROOT / "studio" / "nginx" / "lua"
NGINX_CONFIG = ROOT / "studio" / "nginx" / "nginx.conf"


class LuaArchitectureContractTest(unittest.TestCase):
    def test_responsibility_directories_exist_and_are_populated(self):
        for name in {
            "project_context",
            "security",
            "studio_compat",
            "proxy_rewrites",
            "admin_api",
            "cache",
        }:
            directory = LUA_ROOT / name
            self.assertTrue(directory.is_dir(), name)
            self.assertTrue(any(directory.glob("*.lua")), name)

    def test_nginx_lua_file_references_exist(self):
        config = NGINX_CONFIG.read_text(encoding="utf-8")
        references = re.findall(
            r"/usr/local/openresty/lualib/([^;\s]+\.lua)", config
        )
        references = [reference for reference in references if "?" not in reference]
        missing = [reference for reference in references if not (LUA_ROOT / reference).is_file()]
        self.assertEqual(missing, [])

    def test_lua_sources_are_not_one_line_or_tab_indented(self):
        invalid = []
        for path in LUA_ROOT.rglob("*.lua"):
            content = path.read_text(encoding="utf-8")
            if "\t" in content or len(content.splitlines()) <= 1:
                invalid.append(str(path.relative_to(LUA_ROOT)))
        self.assertEqual(invalid, [])

    def test_internal_requires_resolve(self):
        modules = {
            str(path.relative_to(LUA_ROOT).with_suffix("")).replace("\\", ".")
            for path in LUA_ROOT.rglob("*.lua")
        }
        external_prefixes = (
            "resty.",
            "cjson",
            "bit",
            "ffi",
            "lfs",
            "lyaml",
            "pgmoon",
            "ngx.",
        )
        missing = []
        for path in LUA_ROOT.rglob("*.lua"):
            content = path.read_text(encoding="utf-8")
            for module in re.findall(r'require\(["\']([^"\']+)["\']\)', content):
                if module not in modules and not module.startswith(external_prefixes):
                    missing.append(f"{path.relative_to(LUA_ROOT)}: {module}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
