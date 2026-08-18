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

    def test_watcher_reload_uses_same_lock_and_rejects_stale_backend_sync(self) -> None:
        source = INIT_WORKER.read_text(encoding="utf-8")
        self.assertIn('require("admin_api.authelia_user_store")', source)
        self.assertIn("user_store.with_lock(load_users_locked)", source)
        self.assertIn("snapshot_still_current(payload, current_user)", source)
        self.assertIn("user_store.with_lock(function()", source)
        self.assertIn("[SYNC] Snapshot obsoleto ignorado", source)
        self.assertIn("close_write,moved_to", source)
        self.assertIn("line:sub(-#target_file) == target_file", source)
        self.assertNotIn("line:match(target_file)", source)
        self.assertNotIn("refresh_lock", source)

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


if __name__ == "__main__":
    unittest.main()
