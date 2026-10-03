"""Mandatory browser CSRF acceptance with real Authelia and verified TLS.

Invoked inside the disposable browser image, never against an existing install.
The mutation probe echoes the verified actor, not a production domain mutation.
"""
import json
from pathlib import Path
import subprocess
import unittest

from playwright.sync_api import sync_playwright


class RealSessionTest(unittest.TestCase):
    def test_real_cookie_authenticated_mutation_and_same_site_attack(self):
        # Chromium trusts the test CA via its normal Linux NSS trust database.
        # No ignore_https_errors or command-line certificate bypass is allowed.
        database = Path.home() / '.pki/nssdb'
        database.mkdir(parents=True)
        subprocess.run(['certutil', '-N', '-d', 'sql:' + str(database), '--empty-password'], check=True)
        subprocess.run(['certutil', '-A', '-d', 'sql:' + str(database), '-n', 'disposable-test-ca',
                        '-t', 'C,,', '-i', '/fixture/studio/authelia/ssl/ca.pem'], check=True)
        credentials = json.loads(Path('/fixture/browser-credentials.json').read_text())
        origin = 'https://studio.p1.test'
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.goto(origin + '/session-test')
                status = page.evaluate('''async (credentials) => {
                    const response = await fetch('/auth/api/firstfactor', {
                        method:'POST', headers:{'Content-Type':'application/json'},
                        body:JSON.stringify({...credentials, keepMeLoggedIn:false,
                            targetURL:location.origin + '/session-test'})});
                    return response.status;
                }''', credentials)
                self.assertEqual(status, 200, 'real Authelia first factor failed')
                cookies = context.cookies(origin)
                self.assertTrue(any(c['name'] == 'authelia_session' and c['httpOnly'] and c['secure']
                                    for c in cookies), 'Authelia did not issue its real cookie')
                result = page.evaluate('''async () => {
                    const response = await fetch('/api/csrf-probe', {method:'POST',
                        headers:{'Content-Type':'application/json'}, body:'{}'});
                    return {status:response.status, body:await response.text()};
                }''')
                self.assertEqual(result['status'], 200, result['body'])
                self.assertEqual(json.loads(result['body'])['actor'], credentials['username'])
                reauth = page.evaluate('''async credentials => (await fetch('/api/security/step-up', {
                    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
                        password:credentials.password,action:'delete_project',project:'probe_project',resource:'probe_project'})})).status''', credentials)
                self.assertEqual(reauth, 200)
                # A valid session must survive a short idle period without relogin.
                page.wait_for_timeout(10000)
                self.assertEqual(page.evaluate('''async () => (await fetch('/api/csrf-probe', {
                    method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status'''), 200)

                # Independent simultaneous sessions must remain authenticated.
                other_context = browser.new_context()
                other_page = other_context.new_page()
                other_page.goto(origin + '/session-test')
                self.assertEqual(other_page.evaluate('''async credentials => (await fetch('/auth/api/firstfactor', {
                    method:'POST',headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({...credentials,keepMeLoggedIn:false,
                        targetURL:location.origin+'/session-test'})})).status''', credentials), 200)
                for _ in range(12):
                    page.wait_for_timeout(1100)
                    for active_page in (page, other_page):
                        self.assertEqual(active_page.evaluate('''async () => (await fetch('/api/csrf-probe', {
                            method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status'''), 200)
                other_context.close()

                # Same hostname, distinct port: cookies are shared but origins are not.
                page.goto(origin + ':444')
                with page.expect_response(origin + '/api/csrf-probe') as pending:
                    page.locator('form').evaluate('(form) => form.submit()')
                response = pending.value
                self.assertEqual(response.status, 403)
                headers = response.request.all_headers()
                self.assertIn('authelia_session=', headers['cookie'])
                self.assertEqual(headers['origin'], origin + ':444')
                self.assertEqual(headers['sec-fetch-site'], 'same-site')
                self.assertEqual(json.loads(response.text())['error'], 'csrf_origin_denied')

                # Legitimate origin still works after the attack.
                page.goto(origin + '/session-test')
                self.assertEqual(page.evaluate('''async () => (await fetch('/api/csrf-probe', {
                    method:'POST', headers:{'Content-Type':'application/json'},body:'{}'})).status'''), 200)
                anonymous = browser.new_context()
                anonymous_page = anonymous.new_page()
                anonymous_page.goto(origin + '/session-test')
                self.assertEqual(anonymous_page.evaluate('''async () => (await fetch('/api/csrf-probe', {
                    method:'POST', headers:{'Content-Type':'application/json'},body:'{}'})).status'''), 401)
                anonymous.close()
            finally:
                browser.close()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RealSessionTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun and not result.skipped else 1)
