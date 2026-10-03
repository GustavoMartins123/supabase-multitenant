"""Real YAML, lock, sequence, HMAC, Lua actor headers and retry timer in OpenResty."""
import asyncio
import hashlib
import json
import os
import pathlib
import sys
import time
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor/api-internal'))


@unittest.skipUnless(os.environ.get('STUDIO_DIRECTORY_TEST_URL'), 'Start disposable directory harness')
class StudioDirectoryTest(unittest.TestCase):
    def request(self, path, body=None):
        with urllib.request.urlopen(urllib.request.Request(os.environ['STUDIO_DIRECTORY_TEST_URL'] + path, data=json.dumps(body).encode() if body is not None else None), timeout=10) as response:
            return response.read().decode()

    def seed(self, groups=None, disabled=False, removed=False):
        users = {} if removed else {'admin': {'email': 'admin@example.test', 'displayname': 'Admin', 'groups': groups if groups is not None else ['admin', 'active'], 'disabled': disabled, 'password': 'synthetic-password-not-exported'}}
        self.request('/test/seed', {'users': users})

    def read(self):
        from app.directory_transport import read_directory
        return asyncio.run(read_directory(os.environ['STUDIO_DIRECTORY_TEST_URL'], '2' * 64, None))

    def test_01_signed_snapshot_excludes_password_and_sequences_increase(self):
        self.seed()
        first, second = self.read(), self.read()
        self.assertGreater(second['sequence'], first['sequence'])
        self.assertEqual(first['revision'], second['revision'])
        self.assertNotIn('synthetic-password-not-exported', json.dumps(first))

    def test_02_active_group_removal_disability_and_deletion_are_canonical(self):
        self.seed(['active'])
        actor = json.loads(self.request('/test/actor'))
        self.assertEqual(actor['groups'], 'active', 'stale Authelia admin group must be ignored')
        self.seed([], disabled=True)
        snapshot = self.read()
        self.assertEqual(snapshot['users'][0]['groups'], [])
        self.assertFalse(snapshot['users'][0]['is_active'])
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/test/actor')
        self.assertEqual(error.exception.code, 403)
        self.seed(removed=True)
        self.assertEqual(self.read()['users'], [])

    def test_03_api_outage_is_retried_from_yaml_without_new_edit(self):
        self.request('/test/outage?enabled=1')
        self.seed(['active'])
        snapshot = self.read()
        self.request('/test/outage?enabled=0')
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                if self.request('/test/sync-state') == snapshot['revision']:
                    return
            except urllib.error.HTTPError:
                pass
            time.sleep(.5)
        self.fail('Persisted YAML was not retried after API recovery')

    def test_04_untrusted_request_and_response_are_denied(self):
        from app.directory_transport import read_directory, DirectoryUnavailable
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/internal/users/directory')
        self.assertEqual(error.exception.code, 401)
        with self.assertRaises(DirectoryUnavailable):
            asyncio.run(read_directory(os.environ['STUDIO_DIRECTORY_TEST_URL'], 'wrong', None))
