import concurrent.futures
import json
import os
import unittest
import urllib.error
import urllib.request

@unittest.skipUnless(os.environ.get("STUDIO_BOOTSTRAP_TEST_URL"), "Start the disposable bootstrap harness")
class StudioBootstrapTest(unittest.TestCase):
    def call(self, token=None, username="installer"):
        headers={"Content-Type":"application/json"}
        if token is not None: headers["X-Installation-Token"]=token
        body=json.dumps({"username":username,"display_name":"Installer","email":username+"@example.test","password":"test-password-only"}).encode()
        request=urllib.request.Request(os.environ["STUDIO_BOOTSTRAP_TEST_URL"]+"/api/bootstrap/admin",data=body,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=15) as response: return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try: return error.code, json.load(error)
            finally: error.close()

    def test_01_public_access_without_proof_is_denied(self):
        self.assertEqual(self.call()[0],403)

    def test_02_invalid_proof_is_denied(self):
        self.assertEqual(self.call("wrong")[0],403)

    def test_03_concurrent_bootstrap_is_single_use_and_never_reopens(self):
        proof=os.environ["STUDIO_BOOTSTRAP_TEST_TOKEN"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda name:self.call(proof,name),["installer1","installer2"]))
        self.assertEqual(sorted(result[0] for result in results),[201,403])
        self.assertEqual(self.call(proof)[0],403)
        base=os.environ["STUDIO_BOOTSTRAP_TEST_URL"]
        with urllib.request.urlopen(base+"/test/delete-users") as response: response.read()
        with urllib.request.urlopen(base+"/api/bootstrap/status") as response:
            self.assertFalse(json.load(response)["needs_admin"])
        self.assertEqual(self.call(proof)[0],403)
