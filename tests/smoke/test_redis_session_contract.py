import importlib.util
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class RedisSessionContractTest(unittest.TestCase):
    def test_private_mandatory_backend(self):
        compose = yaml.safe_load((ROOT / 'studio/docker-compose.yml').read_text(encoding='utf-8'))
        services = compose['services']
        redis = services['redis-sessions']
        self.assertEqual(redis['networks'], ['auth-sessions'])
        self.assertTrue(compose['networks']['auth-sessions']['internal'])
        self.assertNotIn('ports', redis)
        self.assertEqual(redis['secrets'], ['REDIS_SESSION_PASSWORD'])
        self.assertIn('redis-sessions:/data', redis['volumes'])
        self.assertEqual(services['authelia']['depends_on']['redis-sessions']['condition'], 'service_healthy')
        self.assertIn('AUTHELIA_SESSION_REDIS_HOST=redis-sessions', services['authelia']['environment'])
        self.assertIn('AUTHELIA_SESSION_REDIS_PASSWORD_FILE=/run/secrets/REDIS_SESSION_PASSWORD', services['authelia']['environment'])
        for service in ('nginx', 'studio'):
            self.assertNotIn('REDIS_SESSION_PASSWORD', services[service].get('secrets', []))
            self.assertNotIn('auth-sessions', services[service]['networks'])
        session = yaml.safe_load((ROOT / 'studio/authelia/configuration.yml.template').read_text(encoding='utf-8'))['session']
        self.assertEqual(session['redis']['host'], 'redis-sessions')
        self.assertEqual(session['redis']['max_retries'], 0)

    def test_generated_private_secret_is_stable(self):
        spec = importlib.util.spec_from_file_location('redis_runtime', ROOT / 'tools/configure_studio_runtime.py')
        runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runtime)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            runtime.ensure_secret_files(path, rotate=False)
            secret = (path / 'REDIS_SESSION_PASSWORD').read_text().strip()
            self.assertRegex(secret, r'^[A-Za-z0-9_-]{64}$')
            runtime.ensure_secret_files(path, rotate=False)
            self.assertEqual((path / 'REDIS_SESSION_PASSWORD').read_text().strip(), secret)

    def test_persistent_noeviction_and_no_secret_argv(self):
        script = (ROOT / 'studio/redis/start-sessions.sh').read_text(encoding='utf-8')
        self.assertIn('set -eu', script)
        self.assertIn('appendonly yes', script)
        self.assertIn('maxmemory-policy noeviction', script)
        self.assertNotIn('--requirepass', script)
        self.assertIn('umask 077', script)
        source = (ROOT / 'tests/integration/fixtures/p1_end_to_end.py').read_text(encoding='utf-8')
        self.assertIn("denial['status'] == 401", source)
        self.assertIn("json.loads(denial['body'])['error'] == 'authentication required'", source)
        self.assertIn("'redis-session-persistence'", source)
