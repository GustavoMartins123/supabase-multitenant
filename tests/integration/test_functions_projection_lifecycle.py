"""Linux filesystem/lock contract; physical database lifecycle is not simulated here."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'servidor/generateProject/functions_config.py'
spec = importlib.util.spec_from_file_location('functions_config_test', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@unittest.skipUnless(sys.platform == 'linux', 'Linux flock and fsync required; run the Docker harness')
class FunctionsProjectionLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scripts = self.root / 'generateProject'
        (self.scripts / 'lib').mkdir(parents=True)
        (self.root / 'projects').mkdir()
        shutil.copy2(SCRIPT, self.scripts / SCRIPT.name)
        shutil.copy2(ROOT / 'servidor/generateProject/lib/functions_config.sh', self.scripts / 'lib')
        self.seed('test_alpha')
        self.seed('test_beta')

    def seed(self, ref, generation='one', identity='11111111-1111-4111-8111-111111111111'):
        directory = self.root / 'projects' / ref
        directory.mkdir(exist_ok=True)
        (directory / '.env').write_text(f'PROJECT_ID={ref}\nPROJECT_UUID={identity}\n'
            f'ANON_KEY_PROJETO={ref}-anon-{generation}\nSERVICE_ROLE_KEY_PROJETO={ref}-service-{generation}\n'
            f'JWT_SECRET_PROJETO={ref}-jwt-{generation}\nPOSTGRES_PASSWORD=cluster-secret-never-project\n'
            'S3_PROTOCOL_ACCESS_KEY_SECRET=storage-secret-never-project\n', encoding='utf-8')

    def shell(self, script, check=True):
        prefix = f'SCRIPT_DIR="{self.scripts}"; PROJECT_ROOT="{self.root}"; source "$SCRIPT_DIR/lib/functions_config.sh"; '
        return subprocess.run(['bash', '-euc', prefix + script], capture_output=True, text=True, check=check)

    def read(self, ref):
        return json.loads((self.root / '.functions-tenants' / f'{ref}.json').read_text())

    def test_exact_projection_and_private_permissions(self):
        module.sync(self.root)
        data = self.read('test_alpha')
        self.assertEqual(set(data), {'project_ref', 'project_uuid', 'anon_key', 'service_role_key', 'jwt_secret'})
        self.assertNotIn('cluster-secret', json.dumps(data))
        self.assertNotIn('storage-secret', json.dumps(data))
        self.assertEqual((self.root / '.functions-tenants/test_alpha.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / '.functions-tenants').stat().st_mode & 0o777, 0o700)

    def test_project_compose_root_cannot_redirect_held_lifecycle_lock(self):
        self.shell('functions_config_lock test_alpha; PROJECT_ROOT=/nonexistent-compose-bind-root; '
                   'functions_config_withdraw test_alpha; functions_config_publish test_alpha')
        self.assertEqual(self.read('test_alpha')['project_ref'], 'test_alpha')
        for name in ('backup_project_impl.sh', 'restore_project_impl.sh'):
            script = (ROOT / 'servidor/generateProject/lib' / name).read_text(encoding='utf-8')
            loaded = script.index('source "$PROJECT_DIR/.env"')
            self.assertIn('PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"', script[loaded:script.index('for variable', loaded)])

    def test_create_duplicate_rotate_restore_rename_delete_projection_transitions(self):
        # These are the real shared projection primitives used by all six scripts.
        self.shell('functions_config_lock test_alpha; functions_config_withdraw test_alpha; functions_config_publish test_alpha')
        self.assertEqual(self.read('test_alpha')['anon_key'], 'test_alpha-anon-one')
        self.shell('functions_config_lock test_alpha test_beta; functions_config_withdraw test_beta; functions_config_publish test_beta')
        self.assertEqual(self.read('test_beta')['project_ref'], 'test_beta')
        self.shell('functions_config_lock test_alpha; functions_config_withdraw test_alpha')
        self.assertFalse((self.root / '.functions-tenants/test_alpha.json').exists())
        self.seed('test_alpha', 'rotated')
        self.shell('functions_config_lock test_alpha; functions_config_publish test_alpha')
        self.assertEqual(self.read('test_alpha')['anon_key'], 'test_alpha-anon-rotated')
        self.shell('functions_config_lock test_alpha; functions_config_withdraw test_alpha; functions_config_publish test_alpha')
        self.assertEqual(self.read('test_alpha')['anon_key'], 'test_alpha-anon-rotated')
        self.shell('functions_config_lock test_alpha test_renamed; functions_config_withdraw test_alpha; functions_config_withdraw test_renamed')
        (self.root / 'projects/test_alpha').rename(self.root / 'projects/test_renamed')
        self.seed('test_renamed', 'renamed')
        self.shell('functions_config_lock test_renamed; functions_config_publish test_renamed')
        self.assertFalse((self.root / '.functions-tenants/test_alpha.json').exists())
        self.shell('functions_config_lock test_renamed; functions_config_withdraw test_renamed')
        shutil.rmtree(self.root / 'projects/test_renamed')
        module.sync(self.root)
        self.assertEqual({p.name for p in (self.root / '.functions-tenants').iterdir()}, {'test_beta.json'})

    def test_restart_refuses_unfinished_lifecycle_and_explicit_rollback_can_republish(self):
        module.sync(self.root)
        self.shell('functions_config_lock test_alpha; functions_config_withdraw test_alpha')
        with self.assertRaisesRegex(ValueError, 'unfinished lifecycle'):
            module.sync(self.root)
        self.assertEqual(list((self.root / '.functions-tenants').iterdir()), [])
        # Caller has verified rollback; publish clears only this tenant's marker.
        self.shell('functions_config_lock test_alpha; functions_config_publish test_alpha')
        module.sync(self.root)
        self.assertEqual(self.read('test_alpha')['anon_key'], 'test_alpha-anon-one')

    def test_invalid_duplicate_missing_identity_and_symlink_fail_closed(self):
        env = self.root / 'projects/test_alpha/.env'
        for corruption in ('PROJECT_ID=other_ref\n', 'JWT_SECRET_PROJETO=duplicate\n'):
            self.seed('test_alpha')
            env.write_text(env.read_text() + corruption)
            with self.assertRaises(ValueError):
                module.sync(self.root)
            self.assertEqual(list((self.root / '.functions-tenants').iterdir()), [])
        self.seed('test_alpha')
        source = env.read_text()
        env.write_text(source.replace('PROJECT_UUID=', 'OMITTED_UUID='))
        with self.assertRaises(ValueError):
            module.projection(self.root, 'test_alpha')
        env.unlink()
        env.symlink_to(self.root / 'projects/test_beta/.env')
        with self.assertRaises(OSError):
            module.projection(self.root, 'test_alpha')

    def test_direct_publish_without_lifecycle_locks_is_refused(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'publish', 'test_alpha'], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'lifecycle lock required', result.stderr)

    def test_tenant_lock_and_startup_sync_wait_for_lifecycle(self):
        signal_file = self.root / 'held'
        script = f'SCRIPT_DIR="{self.scripts}"; PROJECT_ROOT="{self.root}"; source "$SCRIPT_DIR/lib/functions_config.sh"; functions_config_lock test_alpha; touch "{signal_file}"; sleep 1.5'
        process = subprocess.Popen(['bash', '-euc', script])
        self.addCleanup(lambda: process.wait(timeout=5))
        deadline = time.monotonic() + 5
        while not signal_file.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(signal_file.exists())
        start = time.monotonic()
        module.sync(self.root)
        self.assertGreater(time.monotonic() - start, 0.5)


if __name__ == '__main__':
    unittest.main()
