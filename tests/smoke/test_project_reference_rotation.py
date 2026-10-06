from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "servidor/generateProject"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT / "servidor/host-agent"))
spec = importlib.util.spec_from_file_location(
    "reference_rotation", SCRIPTS / "rotate_project_reference.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from hostagent.templates import sync_project_generated_files  # noqa: E402

OLD = "abcdefghijklmnopqrst"
NEW = "bcdefghijklmnopqrstu"
NAME = "technical_project"
INTERNAL = "11111111-1111-4111-8111-111111111111"
TENANT = "22222222-2222-4222-8222-222222222222"


class RotationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "projects" / NAME
        self.project.mkdir(parents=True)
        shutil.copytree(
            ROOT / "servidor/host-agent/hostagent",
            self.root / "host-agent/hostagent",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copytree(
            SCRIPTS, self.root / "generateProject", ignore=shutil.ignore_patterns("__pycache__")
        )
        (self.root / ".env").write_text(
            "POSTGRES_DB=control_plane\nSERVER_URL=https://api.example.test\nHOST_PROJECT_ROOT=/srv/root\n"
        )
        self.env = (
            f"PROJECT_ID={NAME}\nPROJECT_UUID={TENANT}\nPROJECT_PUBLIC_REF={OLD}\n"
            f"API_GATEWAY_TOKEN_PROJETO={'b' * 64}\n"
            f"JWT_SECRET_PROJETO={'c' * 43}\nANON_KEY_PROJETO=header.payload.sig\nSERVICE_ROLE_KEY_PROJETO=header.payload.sig\n"
            f"API_EXTERNAL_URL=https://api.example.test/{OLD}/auth/v1\n"
            f"SITE_URL=https://api.example.test/{OLD}/verify-success.html\n"
            f"ADDITIONAL_REDIRECT_URLS=https://app.example/callback,https://api.example.test/{OLD}/verify-success.html\n"
            "S3_PROTOCOL_ACCESS_KEY_ID=keep-access\nS3_PROTOCOL_ACCESS_KEY_SECRET=keep-secret\n"
            "PROJECT_RESOURCE_PROFILE=custom\nDISABLE_SIGNUP=true\n"
        )
        (self.project / ".env").write_text(self.env)
        sync_project_generated_files(
            root=self.root, scripts_dir=SCRIPTS, project_dir=self.project, project=NAME
        )
        shutil.copyfile(SCRIPTS / ".dockerignore", self.project / ".dockerignore")
        (self.project / "data.bin").write_bytes(b"immutable data")
        self.rotation = module.ReferenceRotation(self.root, NAME, INTERNAL, TENANT, OLD, NEW, 3, 4)
        self.canonical = OLD
        self.events = []

        def sql(query):
            self.events.append(("sql", query))
            if "json_build_object" in query:
                return module.json.dumps(
                    {"name": NAME, "tenant_uuid": TENANT, "public_ref": self.canonical}
                )
            if "count(*)" in query:
                return "1"
            if f"AND public_ref='{self.canonical}'" not in query:
                return ""
            self.canonical = OLD if f"SET public_ref='{OLD}'" in query else NEW
            return self.canonical

        def compose(*args):
            self.events.append(("compose", args))
            return "auth\nnginx\nrest\nmeta" if args[0] == "ps" else ""

        def functions(action):
            self.events.append(("functions", action))

        for name, function in (("sql", sql), ("compose", compose), ("functions", functions)):
            patcher = patch.object(self.rotation, name, side_effect=function)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.before = {
            relative: (self.project / relative).read_bytes() for relative in self.rotation.files
        }

    def test_success_changes_only_public_path_and_derived_auth_defaults(self):
        self.rotation.rotate()
        self.assertEqual(self.canonical, NEW)
        env = (self.project / ".env").read_text()
        expected = self.env.replace(OLD, NEW)
        self.assertEqual(env, expected)
        self.assertEqual((self.project / "data.bin").read_bytes(), b"immutable data")
        nginx = (self.project / f"nginx/nginx_{NAME}.conf").read_text()
        self.assertIn("/" + NEW, nginx)
        self.assertNotIn("/" + OLD, nginx)
        self.assertIn(f"supabase-auth-{NAME}", nginx)
        self.assertEqual(self.events[-1], ("functions", "publish"))
        self.assertFalse(self.rotation.journal.exists())
        commands = [args for kind, args in self.events if kind == "compose"]
        self.assertEqual(commands[1], ("stop", "nginx", "auth"))
        self.assertTrue(
            all(
                "rest" not in args and "meta" not in args and "down" not in args
                for args in commands[1:]
            )
        )

    def test_custom_auth_urls_are_preserved(self):
        path = self.project / ".env"
        path.write_text(
            self.env.replace(
                f"SITE_URL=https://api.example.test/{OLD}/verify-success.html",
                "SITE_URL=https://app.example/custom",
            )
        )
        self.rotation.rotate()
        self.assertIn("SITE_URL=https://app.example/custom\n", path.read_text())

    def test_render_or_restart_failure_restores_exact_files_and_reference(self):
        for method in ("render", "restart"):
            with self.subTest(method=method):
                self.events.clear()
                self.canonical = OLD
                for relative, content in self.before.items():
                    (self.project / relative).write_bytes(content)
                original = getattr(self.rotation, method)
                attempts = 0

                def fail_once(*args):
                    nonlocal attempts
                    attempts += 1
                    if attempts == 1:
                        raise RuntimeError("injected failure")
                    return original(*args)

                with (
                    patch.object(self.rotation, method, side_effect=fail_once),
                    self.assertRaises(RuntimeError),
                ):
                    self.rotation.rotate()
                self.assertEqual(self.canonical, OLD)
                self.assertEqual(
                    {r: (self.project / r).read_bytes() for r in self.rotation.files}, self.before
                )
                self.assertFalse(self.rotation.journal.exists())

    def test_invalid_identity_and_unresolved_journal_fail_before_mutation(self):
        env = self.project / ".env"
        for invalid in (
            self.env.replace(TENANT, INTERNAL),
            self.env.replace(f"PROJECT_PUBLIC_REF={OLD}", f'PROJECT_PUBLIC_REF="{OLD}"'),
            self.env.replace(OLD, "cdefghijklmnopqrstuv"),
        ):
            with self.subTest(env=invalid):
                env.write_text(invalid)
                self.events.clear()
                with self.assertRaises(RuntimeError):
                    self.rotation.rotate()
                self.assertFalse(any(kind == "compose" for kind, _ in self.events))
        env.write_text(self.env)
        self.rotation.journal.mkdir()
        with self.assertRaises(RuntimeError):
            self.rotation.rotate()

    def test_missing_reservation_is_rejected(self):
        original = self.rotation.sql.side_effect
        with patch.object(
            self.rotation,
            "sql",
            side_effect=lambda query: "0" if "count(*)" in query else original(query),
        ):
            with self.assertRaises(RuntimeError):
                self.rotation.rotate()
        self.assertFalse(self.rotation.journal.exists())

    def test_unconfirmed_rollback_keeps_gateway_stopped_and_journal(self):
        with patch.object(
            self.rotation, "restart", side_effect=RuntimeError("service unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "rollback unconfirmed"):
                self.rotation.rotate()
        self.assertTrue(self.rotation.journal.is_dir())
        self.assertEqual(self.events[-1], ("compose", ("stop", "nginx", "auth")))
        self.rotation.recover_rollback()
        self.assertFalse(self.rotation.journal.exists())
        self.assertEqual(self.canonical, OLD)
        self.assertEqual(
            {r: (self.project / r).read_bytes() for r in self.rotation.files}, self.before
        )

    def test_explicit_recovery_rejects_corrupted_backup_before_mutation(self):
        with patch.object(
            self.rotation, "restart", side_effect=RuntimeError("service unavailable")
        ):
            with self.assertRaises(RuntimeError):
                self.rotation.rotate()
        (self.rotation.journal / ".env").write_text("corrupted backup")
        self.events.clear()
        with self.assertRaisesRegex(RuntimeError, "integrity"):
            self.rotation.recover_rollback()
        self.assertEqual(self.events, [])

    def test_cleanup_failure_never_rolls_back_a_completed_rotation(self):
        with patch.object(module.shutil, "rmtree", side_effect=OSError("cleanup failed")):
            with self.assertRaises(OSError):
                self.rotation.rotate()
        self.assertEqual(self.canonical, NEW)
        self.assertEqual(self.events[-1], ("functions", "publish"))
        manifest = module.json.loads((self.rotation.journal / "manifest.json").read_text())
        self.assertEqual(manifest["state"], "completed")
        self.assertFalse(any("ROLLBACK" in str(event) for event in self.events))

    def test_noncanonical_build_context_and_parent_symlinks_fail_closed(self):
        (self.project / ".dockerignore").write_text("")
        with self.assertRaisesRegex(RuntimeError, "exclusions"):
            self.rotation.rotate()
        self.assertEqual(self.events, [])
        alias = self.root / "project-alias"
        alias.symlink_to(self.project.parent, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symbolic links"):
            module.ReferenceRotation(alias, NAME, INTERNAL, TENANT, OLD, NEW, 3, 4)

    def test_shell_wrapper_rejects_missing_arguments_explicitly(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS / "lib/rename_project_impl.sh")], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Canonical rotation arguments required", result.stderr)
        self.assertNotIn("unbound variable", result.stderr)

    def test_shell_locks_are_inherited_by_real_functions_projection(self):
        script = """
set -Eeuo pipefail
PROJECT_ROOT="$1"
SCRIPT_DIR="$PROJECT_ROOT/generateProject"
source "$SCRIPT_DIR/lib/functions_config.sh"
functions_config_lock "$2"
python3 - "$PROJECT_ROOT" "$2" "$FUNCTIONS_GLOBAL_LOCK_FD" "${FUNCTIONS_TENANT_LOCK_FDS[$2]}" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / 'generateProject'))
from rotate_project_reference import ReferenceRotation
rotation = ReferenceRotation(Path(sys.argv[1]), sys.argv[2],
    '11111111-1111-4111-8111-111111111111', '22222222-2222-4222-8222-222222222222',
    'abcdefghijklmnopqrst', 'bcdefghijklmnopqrstu', int(sys.argv[3]), int(sys.argv[4]))
rotation.functions('withdraw')
assert not (rotation.root / '.functions-tenants' / (rotation.project + '.json')).exists()
rotation.functions('publish')
PY
"""
        result = subprocess.run(
            ["bash", "-c", script, "rotation-lock-test", str(self.root), NAME],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        projection = module.json.loads(
            (self.root / ".functions-tenants" / (NAME + ".json")).read_text()
        )
        self.assertEqual(projection["project_uuid"], TENANT)
        self.assertEqual(projection["technical_name"], NAME)
        self.assertEqual(projection["project_ref"], OLD)
        self.assertFalse((self.root / ".functions-locks" / (NAME + ".withdrawn")).exists())

    def test_atomic_write_does_not_reuse_crash_leftover_name(self):
        path = self.project / ".env"
        leftover = path.with_name(path.name + ".rotation-tmp")
        leftover.write_bytes(b"interrupted write")
        self.rotation.atomic_write(path, b"replacement", 0o600)
        self.assertEqual(path.read_bytes(), b"replacement")
        self.assertEqual(leftover.read_bytes(), b"interrupted write")
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
