"""Real Edge Runtime harness with two synthetic tenants and no cluster secrets."""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import urllib.error
import urllib.request


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
            headers['X-Project-Ref'] = ref
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
