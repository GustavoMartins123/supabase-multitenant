"""Contratos dos hardenings de seguranca e resiliencia do gateway Lua."""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
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


class ProjectCookieRemovalTest(unittest.TestCase):
    def test_legacy_cookie_is_only_expired_and_never_resolves_context(self) -> None:
        resolver = read(LUA / "project_context" / "project_ref_resolver.lua")
        cleanup = read(LUA / "project_context" / "cookie_cleanup.lua")

        self.assertFalse((LUA / "project_context" / "set_project.lua").exists())
        self.assertNotIn("cookie_supabase_project", resolver)
        self.assertNotIn("http_referer", resolver)
        self.assertIn("; HttpOnly; Secure;", cleanup)
        self.assertIn("Max-Age=0", cleanup)


class ConstantTimeHmacTest(unittest.TestCase):
    def test_all_hmac_validators_share_constant_time_compare(self) -> None:
        compare = read(LUA / "security" / "secure_compare.lua")
        self.assertIn("bit.bxor", compare)
        self.assertIn("difference == 0", compare)

        validators = (
            LUA / "security" / "check_push_worker.lua",
            LUA / "security" / "internal_hmac.lua",
            LUA / "resty" / "fernet.lua",
        )
        for validator in validators:
            with self.subTest(validator=validator.name):
                source = read(validator)
                self.assertIn('require("security.secure_compare")', source)
                self.assertIn("secure_compare.equals", source)

        storage_limit = read(LUA / "security" / "storage_upload_limit.lua")
        self.assertNotIn("cookie_supabase_storage_limit", storage_limit)
        self.assertIn("context.file_size_limit", storage_limit)

        fernet = read(LUA / "resty" / "fernet.lua")
        self.assertNotIn("mac_a ~= mac_b", fernet)

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
    def test_constant_time_compare_runtime_contract(self) -> None:
        runtime = lua_runtime()
        if runtime is None or subprocess.run(
            [runtime, "-e", 'require("bit")'], capture_output=True
        ).returncode:
            raise unittest.SkipTest("runtime LuaJIT/OpenResty (bit) nao esta disponivel")
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

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
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
        outbound_tls = read(LUA / "utils" / "outbound_tls.lua")
        self.assertIn(
            "lua_ssl_trusted_certificate /var/run/studio-ca-bundle.pem;",
            nginx,
        )
        self.assertIn(
            'M.verify_internal = true',
            outbound_tls,
        )
        self.assertIn("options.ssl_verify = M.verify_internal", outbound_tls)
        self.assertIn("outbound_tls.apply_internal", client)

    def test_backend_tls_identity_dispatch_runs_in_lua(self) -> None:
        runtime = lua_runtime()
        if runtime is None:
            raise unittest.SkipTest("runtime Lua nao esta instalado")
        subprocess.run(
            [runtime, str(ROOT / "tests/smoke/test_backend_tls_identity.lua")],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

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

    @unittest.skipIf(sys.platform == "win32", "requires a working Lua 5.1 runtime (Linux-only)")
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
        self.assertIn("directory.read_locked(false)", source)
        self.assertIn('cache:set("__yaml_user_keys"', source)
        self.assertLess(
            source.index("for _, user in ipairs(snapshot.users) do"),
            source.index("for _, key in ipairs(old) do"),
        )

    def test_user_enumerators_ignore_internal_snapshot_keys(self) -> None:
        for relative in (
            "admin_api/all_users.lua",
            "admin_api/users_list.lua",
        ):
            with self.subTest(relative=relative):
                source = read(LUA / relative)
                self.assertIn(':match("^__")', source)
                self.assertNotIn('~= "__mtime"', source)

    def test_available_users_is_proxied_to_canonical_backend_directory(self) -> None:
        source = read(ROOT / "studio/nginx/nginx.conf")
        self.assertIn("proxy_pass $server_domain/api/projects/$slug/available-users$is_args$args;", source)
        self.assertNotIn("admin_api/available_users.lua", source)


class GatewayOptimizationAndHardeningContractTest(unittest.TestCase):
    def test_entrypoint_avoids_world_writable_and_world_readable_state_modes(self) -> None:
        entrypoint = read(ROOT / "studio" / "nginx" / "docker-entrypoint.sh")
        self.assertIn("chmod 750 /config", entrypoint)
        self.assertIn('chmod 600 "$file"', entrypoint)
        self.assertIn("chmod 644 /config/configuration.runtime.yml", entrypoint)
        self.assertNotIn("chmod 777", entrypoint)
        self.assertNotIn("chmod 666", entrypoint)

    def test_argon2_hashing_uses_bounded_ngx_pipe_stdin_with_ffi_fallback(self) -> None:
        argon2 = read(LUA / "security" / "argon2_password.lua")
        self.assertIn('pcall(require, "ngx.pipe")', argon2)
        self.assertIn("local MAX_ARGON2_CONCURRENCY = 4", argon2)
        self.assertIn("argon2_inflight", argon2)
        self.assertIn("proc:write(plain_password)", argon2)
        self.assertIn("function M.hash_password_ffi(plain_password, salt)", argon2)

    def test_proxy_rewrites_use_isolated_json_instance_and_spooled_body_reader(self) -> None:
        json_mod = read(LUA / "utils" / "json.lua")
        self.assertIn("cjson_safe.new()", json_mod)
        self.assertIn("decode_array_with_array_mt(true)", json_mod)
        self.assertIn("encode_empty_table_as_object(true)", json_mod)
        self.assertIn("encode_escape_forward_slash(false)", json_mod)

        for rel in (
            "proxy_rewrites/pg_meta.lua",
            "proxy_rewrites/storage.lua",
            "proxy_rewrites/storage_public_url.lua",
            "proxy_rewrites/storage_body_filter.lua",
        ):
            src = read(LUA / rel)
            self.assertIn('require("utils.json")', src, rel)
            self.assertNotIn("encode_escape_forward_slash", src, rel)

        for rel in (
            "proxy_rewrites/storage.lua",
            "proxy_rewrites/storage_public_url.lua",
        ):
            src = read(LUA / rel)
            self.assertIn("internal_hmac.read_current_body()", src, rel)
            self.assertNotIn("ngx.req.get_body_data", src, rel)

    def test_logs_sanitize_pii_and_configure_studio_safe_format(self) -> None:
        nginx_src = read(NGINX)
        self.assertIn("log_format studio_safe ", nginx_src)
        self.assertGreaterEqual(nginx_src.count("access_log /var/log/studio_access.log studio_safe;"), 2)

        for rel in (
            "admin_api/all_users.lua",
            "security/check_admin_with_email.lua",
            "security/check_admin.lua",
            "security/studio_project_admin_access.lua",
            "studio_compat/mock_organizations.lua",
            "studio_compat/mock_subscription.lua",
            "proxy_rewrites/analytics.lua",
        ):
            src = read(LUA / rel)
            self.assertNotIn("ngx.INFO", src, rel)
            for line in src.splitlines():
                if "ngx.log(" not in line:
                    continue
                lower = line.lower()
                self.assertNotIn("email", lower, f"{rel}: {line}")
                self.assertNotIn("cookie", lower, f"{rel}: {line}")
                self.assertNotIn("request_uri", lower, f"{rel}: {line}")

    def test_dockerfile_pins_used_deps_and_removes_unused_rocks_and_packages(self) -> None:
        dockerfile = read(ROOT / "studio" / "Dockerfile")
        for removed in (
            "inotify-tools",
            "jkeys089/lua-resty-hmac",
            "lua-resty-string-0.09",
            "lua-erento-hmac",
            "lua-resty-fernet",
            "lua-resty-crypto",
            "luaossl",
            "pgmoon",
        ):
            self.assertNotIn(removed, dockerfile)

        for kept in (
            "ledgetech/lua-resty-http=0.17.1",
            "luafilesystem-1.8.0-1.rockspec",
            "lyaml-6.2.8-1.rockspec",
            "lua-resty-openssl-1.7.1-1.rockspec",
            "libargon2-1",
            "libvips-tools",
        ):
            self.assertIn(kept, dockerfile)

        self.assertFalse((LUA / "security" / "inject_service_key_apikey.lua").exists())

    def test_nginx_rewrite_phase_runs_before_access_and_method_checks_stay_in_lua(self) -> None:
        nginx_src = read(NGINX)
        expected_pairs = (
            ("proxy_rewrites/rest_v1.lua", "security/inject_service_key.lua"),
            ("proxy_rewrites/graphql.lua", "security/inject_service_key_graphql.lua"),
            ("proxy_rewrites/analytics.lua", "security/studio_project_admin_access.lua"),
        )
        rewrite_lines = [line for line in nginx_src.splitlines() if "rewrite_by_lua_file" in line and "server_rewrite_by_lua_file" not in line]
        self.assertEqual(len(rewrite_lines), len(expected_pairs))
        for rewrite_mod, access_mod in expected_pairs:
            self.assertLess(nginx_src.index(rewrite_mod), nginx_src.index(access_mod), rewrite_mod)
        # Storage JSON rewrite runs inside access phase after project_access.enforce_storage()
        storage_access = read(LUA / "security" / "inject_service_key_storage.lua")
        self.assertLess(
            storage_access.index('require("security.project_access").enforce_storage()'),
            storage_access.index('require("proxy_rewrites.storage").rewrite()'),
        )


if __name__ == "__main__":
    unittest.main()
