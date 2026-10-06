import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('api_resources_tool', ROOT / 'tools/configure_api_resource_profiles.py')
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))
from app.project_settings import resolve_resource_limits
from fastapi import HTTPException


class ApiResourceProfilesTest(unittest.TestCase):
    def example(self):
        return (ROOT / 'servidor/.env.example').read_text(encoding='utf-8')

    def test_projection_contains_only_all_twelve_non_secret_keys(self):
        rendered = tool.render(self.example() + '\nPOSTGRES_PASSWORD=synthetic-global-secret\n')
        self.assertEqual(len(rendered.splitlines()), 12)
        self.assertNotIn('synthetic-global-secret', rendered)
        self.assertNotIn('JWT_SECRET', rendered)
        self.assertEqual({line.split('=')[0] for line in rendered.splitlines()}, set(tool.KEYS))

    def test_duplicate_missing_and_invalid_source_fail(self):
        for source in (self.example()+'\nPROJECT_RES_SMALL_PIDS=128', self.example().replace('PROJECT_RES_SMALL_PIDS=128', ''), self.example().replace('PROJECT_RES_SMALL_CPUS=1.85', 'PROJECT_RES_SMALL_CPUS=0')):
            with self.subTest(source=source[-30:]), self.assertRaises(ValueError):
                tool.render(source)

    def test_api_resolves_all_profiles_and_rejects_global_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'resource-profiles.env'
            target.write_text(tool.render(self.example()), encoding='utf-8')
            for profile in ('small','medium','large','custom'):
                limits = resolve_resource_limits(profile, profiles_env=target)
                self.assertTrue(limits['PROJECT_MEM_LIMIT'])
            target.write_text(self.example(), encoding='utf-8')
            with self.assertRaises(HTTPException) as error:
                resolve_resource_limits('small', profiles_env=target)
            self.assertEqual(error.exception.status_code, 503)
            target.unlink()
            with self.assertRaises(HTTPException) as error:
                resolve_resource_limits('small', profiles_env=target)
            self.assertEqual(error.exception.status_code, 503)

    def test_compose_never_mounts_global_env_and_start_generates_scoped_file(self):
        compose = (ROOT / 'servidor/docker-compose-api.yml').read_text(encoding='utf-8')
        self.assertNotIn('./.env:/docker/.env', compose)
        self.assertIn('target: /docker/resource-profiles.env', compose)
        self.assertIn('create_host_path: false', compose)
        settings = (ROOT / 'servidor/api-internal/app/project_settings.py').read_text(encoding='utf-8')
        self.assertNotIn('/docker/.env', settings)
        self.assertNotIn('SERVER_ENV_PATH', settings)
        self.assertIn('configure_api_resource_profiles.py', (ROOT / 'start.sh').read_text(encoding='utf-8'))
