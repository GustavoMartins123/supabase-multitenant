"""Real Edge Runtime harness with two synthetic tenants and no cluster secrets."""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import urllib.error
import urllib.request


PUBLIC_REFS = {'test_alpha': 'a'*20, 'test_beta': 'b'*20, 'test_absent': 'c'*20}

def token(ref):
    def encode(value):
        return base64.urlsafe_b64encode(value).decode().rstrip('=')
    header = encode(b'{"alg":"HS256","typ":"JWT"}')
    body = encode(json.dumps({'role':'anon','iat':int(time.time()),'exp':int(time.time())+60}).encode())
    data = header+'.'+body
    signature = hmac.new((ref+'-synthetic-jwt-secret-for-test-only').encode(), data.encode(), hashlib.sha256).digest()
    return data+'.'+encode(signature)


@unittest.skipUnless(os.environ.get('FUNCTIONS_TENANT_TEST_URL'), 'Start the two-tenant Edge Runtime harness')
class FunctionsTenantBoundaryTest(unittest.TestCase):
    def call(self, ref=None, jwt=None, path='/hello'):
        headers = {}
        if ref is not None:
            headers['X-Project-Ref'] = PUBLIC_REFS[ref] if ref in PUBLIC_REFS else ref
            headers['X-Project-Name'] = ref
        if jwt is not None:
            headers['Authorization'] = 'Bearer '+jwt
        try:
            with urllib.request.urlopen(urllib.request.Request(os.environ['FUNCTIONS_TENANT_TEST_URL']+path,headers=headers),timeout=30) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as error:
            try:
                return error.code, error.read().decode()
            finally:
                error.close()

    def test_missing_query_alias_and_noncanonical_identity_are_denied(self):
        self.assertEqual(self.call(jwt=token('test_alpha'))[0],400)
        self.assertEqual(self.call(jwt=token('test_alpha'),path='/hello?ref=test_alpha')[0],400)
        self.assertEqual(self.call('TEST_ALPHA',token('test_alpha'))[0],400)

    def test_cross_tenant_jwt_and_supervisor_function_are_denied(self):
        self.assertEqual(self.call('test_beta',token('test_alpha'))[0],401)
        self.assertEqual(self.call('test_alpha',token('test_alpha'),path='/main')[0],400)
        self.assertEqual(self.call('test_alpha',token('test_alpha'),path='/%2e%2e')[0],400)

    def test_each_tenant_can_run_its_legitimate_function(self):
        for ref in ('test_alpha','test_beta'):
            status, body = self.call(ref,token(ref))
            self.assertEqual(status,200,body)
            self.assertIn('Hello from Edge Functions',body)

    def test_missing_tenant_configuration_fails_closed(self):
        self.assertEqual(self.call('test_absent',token('test_absent'))[0],503)

    def test_workers_receive_only_their_tenant_and_cannot_read_supervisor_files(self):
        for ref in ('test_alpha', 'test_beta', 'test_alpha'):
            status, body = self.call(ref, token(ref), path='/probe')
            self.assertEqual(status, 200, body)
            data = json.loads(body)
            self.assertEqual(data['env']['PROJECT_REF'], PUBLIC_REFS[ref])
            self.assertEqual(data['env']['SUPABASE_ANON_KEY'], 'synthetic-anon-' + ref)
            self.assertEqual(data['env']['SUPABASE_SERVICE_ROLE_KEY'], 'synthetic-service-' + ref)
            self.assertEqual(data['env']['JWT_SECRET'], ref + '-synthetic-jwt-secret-for-test-only')
            for secret in ('POSTGRES_PASSWORD', 'SUPABASE_DB_URL', 'JWT_SECRET_PROJETO'):
                self.assertNotIn(secret, data['env'])
            self.assertFalse(any(data['reads'].values()), data)

    def test_projection_changes_and_withdrawal_take_effect_on_next_request(self):
        directory = Path(os.environ['FUNCTIONS_PROJECTION_TEST_DIR'])
        path = directory / 'test_alpha.json'
        original = path.read_bytes()
        config = json.loads(original)
        self.assertEqual(config['anon_key'], 'synthetic-anon-test_alpha', 'synthetic fixture required')

        def replace(data):
            fd, name = tempfile.mkstemp(dir=directory)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
            os.replace(name, path)

        try:
            status, body = self.call('test_alpha', token('test_alpha'), path='/probe')
            self.assertEqual(status, 200, body)
            config['anon_key'] = 'synthetic-anon-rotated'
            replace(json.dumps(config).encode())
            status, body = self.call('test_alpha', token('test_alpha'), path='/probe')
            self.assertEqual(status, 200, body)
            self.assertEqual(json.loads(body)['env']['SUPABASE_ANON_KEY'], 'synthetic-anon-rotated')
            path.unlink()
            self.assertEqual(self.call('test_alpha', token('test_alpha'))[0], 503)
            config['project_ref'] = PUBLIC_REFS['test_beta']
            replace(json.dumps(config).encode())
            self.assertEqual(self.call('test_alpha', token('test_alpha'))[0], 503)
            config['project_ref'] = PUBLIC_REFS['test_alpha']
            config['unexpected_secret'] = 'synthetic-unexpected'
            replace(json.dumps(config).encode())
            self.assertEqual(self.call('test_alpha', token('test_alpha'))[0], 503)
        finally:
            replace(original)
