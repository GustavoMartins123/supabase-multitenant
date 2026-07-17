"""Contratos dos hardenings de seguranca e resiliencia do gateway Lua."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
LUA = ROOT / "studio" / "nginx" / "lua"
NGINX = ROOT / "studio" / "nginx" / "nginx.conf"
STUDIO_ENV = ROOT / "studio" / ".env.example"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def lua_runtime() -> str | None:
    return shutil.which("lua5.1") or shutil.which("lua") or shutil.which("resty")


def run_lua(script: str, *, env: dict[str, str] | None = None) -> None:
    runtime = lua_runtime()
    if runtime is None:
        raise unittest.SkipTest("runtime Lua nao esta instalado")
    subprocess.run([runtime, "-e", script], check=True, env=env)


class ProjectCookieHardeningTest(unittest.TestCase):
    def test_project_cookies_are_always_secure(self) -> None:
        sources = {
            "set": read(LUA / "project_context" / "set_project.lua"),
            "renewal": read(
                LUA / "project_context" / "project_ref_resolver.lua"
            ),
            "cleanup": read(LUA / "project_context" / "cookie_cleanup.lua"),
        }
        self.assertEqual(sources["set"].count("; HttpOnly; Secure;"), 2)
        self.assertIn("; HttpOnly; Secure;", sources["renewal"])
        self.assertIn("; HttpOnly; Secure;", sources["cleanup"])


class ConstantTimeHmacTest(unittest.TestCase):
    def test_all_hmac_validators_share_constant_time_compare(self) -> None:
        compare = read(LUA / "security" / "secure_compare.lua")
        self.assertIn("bit.bxor", compare)
        self.assertIn("difference == 0", compare)

        validators = (
            LUA / "project_context" / "set_project.lua",
            LUA / "project_context" / "project_ref_resolver.lua",
            LUA / "project_context" / "cookie_cleanup.lua",
            LUA / "security" / "storage_upload_limit.lua",
            LUA / "security" / "check_push_worker.lua",
            LUA / "security" / "shared_token.lua",
            LUA / "resty" / "fernet.lua",
        )
        for validator in validators:
            with self.subTest(validator=validator.name):
                source = read(validator)
                self.assertIn('require("security.secure_compare")', source)
                self.assertIn("secure_compare.equals", source)

        fernet = read(LUA / "resty" / "fernet.lua")
        self.assertNotIn("mac_a ~= mac_b", fernet)

    def test_constant_time_compare_runtime_contract(self) -> None:
        run_lua(
            f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local compare = require("security.secure_compare")
assert(compare.equals("deadbeef", "deadbeef"))
assert(not compare.equals("deadbeef", "deadbeeg"))
assert(not compare.equals("short", "longer"))
'''
        )


class AdminGroupHardeningTest(unittest.TestCase):
    def test_admin_checks_use_configurable_structured_parser(self) -> None:
        parser = read(LUA / "security" / "admin_groups.lua")
        self.assertIn('os.getenv("ADMIN_GROUPS") or "admin"', parser)
        self.assertIn("trim(token):lower()", parser)
        self.assertIn("formato inesperado", parser)

        for name in ("check_admin.lua", "check_admin_with_email.lua", "user_me.lua"):
            with self.subTest(name=name):
                source = read(LUA / "security" / name)
                self.assertIn('require("security.admin_groups")', source)
                self.assertIn("admin_groups.is_admin(groups)", source)
                self.assertNotIn("groups_clean", source)

        self.assertIn("env ADMIN_GROUPS;", read(NGINX))
        self.assertIn("ADMIN_GROUPS=admin", read(STUDIO_ENV))

    def test_admin_group_parser_runtime_contract(self) -> None:
        env = dict(os.environ)
        env["ADMIN_GROUPS"] = "admin,superadmins"
        run_lua(
            f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
_G.ngx = {{
    log = function(...) end,
    ERR = "ERR",
    WARN = "WARN",
}}
local groups = require("security.admin_groups")
assert(groups.is_admin("active, ADMIN"))
assert(groups.is_admin("[active, superadmins]"))
assert(not groups.is_admin("active,admins"))
assert(not groups.is_admin("active;admin"))
''',
            env=env,
        )


class InternalServiceKeyHardeningTest(unittest.TestCase):
    def test_tls_verification_and_internal_ca_remain_enabled(self) -> None:
        nginx = read(NGINX)
        client = read(LUA / "security" / "get_service_key.lua")
        self.assertIn("lua_ssl_trusted_certificate /config/ssl/ca.pem;", nginx)
        self.assertIn('os.getenv("SERVICE_KEY_VERIFY_TLS") or "true"', client)
        self.assertIn("ssl_verify = verify_tls", client)

    def test_fernet_constructor_and_decrypt_are_both_protected(self) -> None:
        client = read(LUA / "security" / "get_service_key.lua")
        fernet = read(LUA / "resty" / "fernet.lua")
        self.assertIn("pcall(fernet.new, fernet, encryption_key)", client)
        self.assertIn("pcall(cipher.decrypt, cipher, data.enc_service_key)", client)
        self.assertNotIn("assert(urlsafe_b64decode(key))", fernet)
        self.assertIn("#decoded ~= 32", fernet)

    def test_required_version_is_monotonic_and_stale_fetch_is_rejected(self) -> None:
        versions = read(LUA / "cache" / "service_key_version.lua")
        client = read(LUA / "security" / "get_service_key.lua")
        invalidation = read(LUA / "cache" / "invalidate_service_key.lua")
        self.assertIn("with_project_lock", versions)
        self.assertIn("function M.read_cached", versions)
        self.assertIn("if candidate > current then", versions)
        self.assertIn("if version < minimum then", versions)
        self.assertIn("service_key_version.publish", client)
        self.assertIn('increment_metric("stale_fetch")', client)
        self.assertIn("service_key_version.invalidate", invalidation)

    def test_service_key_version_runtime_contract(self) -> None:
        run_lua(
            f'''
package.path = "{LUA.as_posix()}/?.lua;{LUA.as_posix()}/?/init.lua;" .. package.path
local values = {{}}
local dict = {{}}
function dict:get(key) return values[key] end
function dict:set(key, value) values[key] = value; return true end
function dict:add(key, value) if values[key] ~= nil then return nil, "exists" end; values[key] = value; return true end
function dict:delete(key) values[key] = nil end
_G.ngx = {{
    shared = {{ service_keys = dict }},
    sleep = function(...) end,
    log = function(...) end,
    ERR = "ERR",
    WARN = "WARN",
}}
local versions = require("cache.service_key_version")
assert(versions.promote("project", 2) == 2)
assert(versions.promote("project", 1) == 2)
local value, state = versions.read_cached("project")
assert(value == nil and state == "miss")
local stale, required = versions.publish("project", "old", 1, 60, 5)
assert(stale == false and required == 2)
local published = versions.publish("project", "current", 2, 60, 5)
assert(published == true)
assert(values["service_key:value:project"] == "current")
value, state = versions.read_cached("project")
assert(value == "current" and state == "hit")
assert(versions.invalidate("project", 3, 5) == 3)
assert(values["service_key:value:project"] == nil)
'''
        )

    def test_enc_key_failures_have_short_observable_backoff(self) -> None:
        client = read(LUA / "security" / "get_service_key.lua")
        metrics = read(LUA / "cache" / "service_key_metrics.lua")
        self.assertIn("SERVICE_KEY_FETCH_ERROR_TTL_SECONDS", client)
        self.assertIn('increment_metric("fetch_error_backoff")', client)
        self.assertIn("fetch_error_backoff", metrics)
        self.assertIn("stale_fetch", metrics)
        self.assertIn("SERVICE_KEY_FETCH_ERROR_TTL_SECONDS=2", read(STUDIO_ENV))


class UserCacheReloadHardeningTest(unittest.TestCase):
    def test_reload_publishes_snapshot_without_global_flush(self) -> None:
        source = read(LUA / "init" / "init_worker.lua")
        self.assertNotIn("cache:flush_all()", source)
        self.assertIn("local snapshot = {}", source)
        self.assertIn('cache:set("__yaml_user_keys"', source)
        self.assertLess(
            source.index("for key, value in pairs(snapshot) do"),
            source.index("for key in pairs(old_keys) do"),
        )

    def test_user_enumerators_ignore_internal_snapshot_keys(self) -> None:
        for relative in (
            "admin_api/all_users.lua",
            "admin_api/users_list.lua",
            "admin_api/available_users.lua",
        ):
            with self.subTest(relative=relative):
                source = read(LUA / relative)
                self.assertIn(':match("^__")', source)
                self.assertNotIn('~= "__mtime"', source)


if __name__ == "__main__":
    unittest.main()
