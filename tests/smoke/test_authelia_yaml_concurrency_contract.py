from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADMIN = ROOT / "studio/nginx/lua/admin_api"
INIT_WORKER = ROOT / "studio/nginx/lua/init/init_worker.lua"


class AutheliaYamlConcurrencyContractTests(unittest.TestCase):
    def test_all_user_mutators_share_the_same_store(self) -> None:
        for name in (
            "user_signup.lua",
            "user_activate.lua",
            "user_deactivate.lua",
            "user_profile_store.lua",
        ):
            source = (ADMIN / name).read_text(encoding="utf-8")
            self.assertIn(
                'require("admin_api.authelia_user_store")',
                source,
                name,
            )
            self.assertNotIn('io.open(yaml_path, "w")', source, name)
            self.assertNotIn("lock_dict:add(", source, name)
            self.assertNotIn('io.open(YAML_PATH, "wb")', source, name)

    def test_user_store_rereads_under_one_global_kernel_lock(self) -> None:
        source = (ADMIN / "authelia_user_store.lua").read_text(encoding="utf-8")
        file_store = (ADMIN / "authelia_file_store.lua").read_text(encoding="utf-8")

        self.assertIn('LOCK_RESOURCE = "users_database.yml"', source)
        self.assertIn("file_store.with_lock(LOCK_RESOURCE, callback)", source)
        self.assertIn("file_store.atomic_write(YAML_PATH, serialized, FILE_MODE)", source)
        self.assertIn("file_store.atomic_write(YAML_PATH, original, FILE_MODE)", source)

        self.assertIn('ffi.new("unsigned int", LOCK_FILE_MODE)', file_store)
        self.assertIn("ffi.C.open(path, flags, open_mode)", file_store)
        self.assertIn("ffi.C.flock(fd, operation)", file_store)
        self.assertIn("ffi.C.flock(fd, LOCK_UN)", file_store)
        self.assertIn("O_NOFOLLOW", file_store)
        self.assertIn("O_CLOEXEC", file_store)
        self.assertIn("O_EXCL", file_store)
        self.assertIn('clean:gsub("%.yml$", "")', file_store)
        self.assertIn("ffi.C.fsync(fd)", file_store)
        self.assertIn("fsync_parent_directory(path)", file_store)
        self.assertIn("os.rename(temp_path, path)", file_store)
        self.assertIn("ffi.C.fchmod", file_store)
        self.assertNotIn("ngx.shared.service_keys", file_store)
        self.assertNotIn('return "unlocked"', file_store)

    def test_atomic_write_fsyncs_before_rename_and_directory_after(self) -> None:
        source = (ADMIN / "authelia_file_store.lua").read_text(encoding="utf-8")
        atomic = source[source.index("function M.atomic_write") :]
        file_fsync = atomic.index("ffi.C.fsync(fd)")
        rename = atomic.index("os.rename(temp_path, path)")
        dir_fsync = atomic.index("fsync_parent_directory(path)")
        self.assertLess(file_fsync, rename)
        self.assertLess(rename, dir_fsync)
        self.assertIn("O_EXCL", atomic)
        self.assertIn("O_NOFOLLOW", atomic)

    def test_rollbacks_use_the_same_locked_store(self) -> None:
        for name in (
            "user_signup.lua",
            "user_activate.lua",
            "user_deactivate.lua",
            "user_profile_store.lua",
        ):
            source = (ADMIN / name).read_text(encoding="utf-8")
            self.assertIn("user_store.restore(original)", source, name)

    def test_business_checks_happen_inside_locked_callbacks(self) -> None:
        signup = (ADMIN / "user_signup.lua").read_text(encoding="utf-8")
        activate = (ADMIN / "user_activate.lua").read_text(encoding="utf-8")
        deactivate = (ADMIN / "user_deactivate.lua").read_text(encoding="utf-8")

        signup_locked = signup[signup.index("user_store.with_lock(function()") :]
        self.assertIn("users_have_admin(yaml_data.users)", signup_locked)
        self.assertIn("Username already exists", signup_locked)
        self.assertIn("Email already exists", signup_locked)

        activate_locked = activate[activate.index("user_store.with_lock(function()") :]
        self.assertIn('group == "active"', activate_locked)
        self.assertIn("user.display_name = user_entry.displayname or username", activate_locked)

        deactivate_locked = deactivate[deactivate.index("user_store.with_lock(function()") :]
        self.assertIn("You cannot deactivate yourself", deactivate_locked)
        self.assertIn("Cannot deactivate an admin user", deactivate_locked)
        self.assertIn("user.display_name = user_entry.displayname or username", deactivate_locked)

    def test_profile_get_cannot_publish_a_stale_cache_snapshot(self) -> None:
        source = (ADMIN / "user_profile_store.lua").read_text(encoding="utf-8")
        get_block = source[
            source.index("function M.get(email)") : source.index("function M.update")
        ]
        self.assertIn("user_store.with_lock(function()", get_block)
        self.assertIn("cache_profile(profile)", get_block)

    def test_identifier_generation_is_serialized_across_worker_and_requests(self) -> None:
        source = (ADMIN / "authelia_identifiers.lua").read_text(encoding="utf-8")
        self.assertIn('file_store.with_lock(IDS_LOCK, function()', source)
        self.assertIn('IDS_LOCK = "ids.yml"', source)
        self.assertIn("file_store.atomic_write(IDS_PATH, serialized, FILE_MODE)", source)
        self.assertIn("os.rename(tmp_path, IDS_PATH)", source)

    def test_directory_batches_fresh_identifier_reads_without_missing_file_substitution(self) -> None:
        source = (ADMIN / "directory_snapshot.lua").read_text(encoding="utf-8")
        self.assertIn("identifiers.ensure_identifiers(usernames)", source)
        self.assertNotIn("identifiers.ensure_identifier(username)", source)
        identity_source = (ADMIN / "authelia_identifiers.lua").read_text(encoding="utf-8")
        self.assertNotIn("return { identifiers = {} }", identity_source)
        self.assertNotIn("document.identifiers = {}", identity_source)
        self.assertIn('return nil, "identidade openid vazia ou duplicada"', identity_source)
        self.assertIn('return nil, nil, "username duplicado"', identity_source)
        self.assertIn("local function index_document(document)", identity_source)

    def test_periodic_full_directory_reconciliation_uses_same_lock(self) -> None:
        source = INIT_WORKER.read_text(encoding="utf-8")
        self.assertIn('require("admin_api.authelia_user_store")', source)
        self.assertIn("store.with_lock(function()", source)
        self.assertIn("directory.read_locked(false)", source)
        self.assertIn("sync.sync_directory()", source)
        self.assertIn("ngx.timer.every(5, reconcile)", source)
        self.assertNotIn("max_bootstrap_attempts", source)
        self.assertNotIn("snapshot_still_current", source)
        self.assertNotIn("cache:get_keys", source)

    def test_avatar_mutations_surface_lock_contention_as_retryable(self) -> None:
        source = (ADMIN / "user_avatar_handler.lua").read_text(encoding="utf-8")
        self.assertIn("mutation_error_status(update_err)", source)
        self.assertIn('ngx.header["Retry-After"] = "1"', source)

    def test_no_other_admin_module_directly_writes_users_database(self) -> None:
        allowed = {"authelia_user_store.lua"}
        offenders: list[str] = []
        for path in ADMIN.glob("*.lua"):
            if path.name in allowed:
                continue
            source = path.read_text(encoding="utf-8")
            if "users_database.yml" not in source:
                continue
            if 'io.open' in source and ('"w"' in source or '"wb"' in source):
                offenders.append(path.name)
        self.assertEqual(offenders, [])

    def test_directory_files_use_owner_only_mode_0600(self) -> None:
        self.assertIn("local FILE_MODE = 384", (ADMIN / "authelia_user_store.lua").read_text(encoding="utf-8"))
        self.assertIn("local FILE_MODE = 384", (ADMIN / "authelia_identifiers.lua").read_text(encoding="utf-8"))
        self.assertIn("local DEFAULT_MODE = 384", (ADMIN / "authelia_file_store.lua").read_text(encoding="utf-8"))
        self.assertIn("local SEQUENCE_MODE = 384", (ADMIN / "directory_snapshot.lua").read_text(encoding="utf-8"))

    def test_background_reconcile_and_sync_release_lock_before_http_io(self) -> None:
        init_source = INIT_WORKER.read_text(encoding="utf-8")
        self.assertIn("store.flush_republish(false)", init_source)
        lock_pos = init_source.index("store.with_lock(function()")
        sync_pos = init_source.index("sync.sync_directory()")
        self.assertLess(lock_pos, sync_pos)
        between = init_source[lock_pos:sync_pos]
        self.assertIn("end)", between)

        sync_source = (ADMIN / "user_sync.lua").read_text(encoding="utf-8")
        sync_fn = sync_source[sync_source.index("function M.sync_directory(locked)") :]
        self.assertLess(sync_fn.index("authelia_user_store\").with_lock"), sync_fn.index("request_sync(body)"))
        self.assertIn("end)", sync_fn[: sync_fn.index("request_sync(body)")])

    def test_directory_snapshot_and_identifiers_memoize_on_raw_state(self) -> None:
        snap_source = (ADMIN / "directory_snapshot.lua").read_text(encoding="utf-8")
        self.assertIn("local cached_users_raw", snap_source)
        self.assertIn("local cached_by_email", snap_source)
        for_email = snap_source[snap_source.index("function M.for_email(email)") :]
        self.assertIn("store.read_raw()", for_email)
        self.assertIn("identifiers.raw_state()", for_email)
        self.assertIn("cached_by_email[normalized]", for_email)
        self.assertIn("return store.with_lock(function()", for_email)

        id_source = (ADMIN / "authelia_identifiers.lua").read_text(encoding="utf-8")
        self.assertIn("local cached_raw", id_source)
        self.assertIn("local cached_identifiers", id_source)
        self.assertIn("function M.raw_state()", id_source)

    def test_user_store_schedules_cooldown_republish_for_mtime_granularity(self) -> None:
        store_source = (ADMIN / "authelia_user_store.lua").read_text(encoding="utf-8")
        self.assertIn('local REPUBLISH_CACHE_KEY = "__yaml_republish_after"', store_source)
        self.assertIn("function M.schedule_republish()", store_source)
        self.assertIn("function M.flush_republish(force)", store_source)
        self.assertIn("M.schedule_republish()", store_source[store_source.index("function M.write(data)") :])
        self.assertIn("M.schedule_republish()", store_source[store_source.index("function M.restore(original)") :])

    def test_password_mutations_serialize_through_locked_proxy_and_ro_mounts(self) -> None:
        proxy_source = (ADMIN / "authelia_password_proxy.lua").read_text(encoding="utf-8")
        self.assertIn("user_store.with_lock(function()", proxy_source)
        self.assertIn("/internal/authelia-password-mutation", proxy_source)
        self.assertIn("function M.reconcile_password_change(before_data, after_data)", proxy_source)
        self.assertIn("is_valid_argon2_hash", proxy_source)
        self.assertIn("user_store.restore(before_raw)", proxy_source)

        nginx_source = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        for route in ("/auth/api/change-password", "/auth/api/reset-password"):
            self.assertIn(f"location = {route}", nginx_source)
            self.assertIn("authelia_password_proxy.lua", nginx_source)
        self.assertIn("location = /internal/authelia-password-mutation", nginx_source)

        compose_source = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(
            compose_source.count("./authelia/configuration.runtime.yml:/config/configuration.runtime.yml:ro"),
            2,
        )
        self.assertGreaterEqual(
            compose_source.count("./authelia/ssl:/config/ssl:ro"),
            2,
        )
        self.assertIn("    environment:\n      - TZ=${TZ}", compose_source)


if __name__ == "__main__":
    unittest.main()
