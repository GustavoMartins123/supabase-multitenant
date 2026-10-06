"""Run inside the API image with only the generated non-secret profile mount."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))


@unittest.skipUnless(os.environ.get('API_RESOURCE_MOUNT_TEST') == '1', 'Run the isolated API-image mount harness')
class ApiResourceMountTest(unittest.TestCase):
    def test_global_env_and_root_password_are_absent(self):
        self.assertFalse(Path('/docker/.env').exists())
        self.assertFalse(os.environ.get('POSTGRES_PASSWORD'))

    def test_only_twelve_profile_values_are_readable_and_all_profiles_work(self):
        from app.project_settings import resolve_resource_limits
        source = Path('/docker/resource-profiles.env').read_text()
        self.assertEqual(len(source.splitlines()), 12)
        self.assertNotIn('SECRET', source)
        for profile in ('small','medium','large','custom'):
            self.assertTrue(resolve_resource_limits(profile)['PROJECT_CPUS'])

    def test_projection_mount_is_read_only(self):
        with self.assertRaises(OSError):
            Path('/docker/resource-profiles.env').write_text('tampered')
