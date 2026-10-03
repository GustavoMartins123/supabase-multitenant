"""Real OpenResty CSRF boundary; cookie authentication is synthetic, not Authelia."""
import os
import ssl
import unittest
import urllib.error
import urllib.request


@unittest.skipUnless(os.environ.get('STUDIO_CSRF_TEST_URL'), 'Start the disposable TLS CSRF harness')
class StudioCsrfTest(unittest.TestCase):
    def call(self, origin=None, media='application/json', fetch_site=None, path='/api/mutate'):
        headers = {'Content-Type': media, 'Cookie': 'session=synthetic-valid-cookie'}
        if origin is not None:
            headers['Origin'] = origin
        if fetch_site is not None:
            headers['Sec-Fetch-Site'] = fetch_site
        request = urllib.request.Request(os.environ['STUDIO_CSRF_TEST_URL'] + path, data=b'{}', headers=headers)
        try:
            with urllib.request.urlopen(request, context=ssl._create_unverified_context(), timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            error.close()
            return error.code

    def test_exact_origin_and_json_succeed(self):
        self.assertEqual(self.call('https://localhost:55443', fetch_site='same-origin'), 200)

    def test_absent_null_other_port_and_other_scheme_are_denied(self):
        for origin in (None, 'null', 'https://localhost:55444', 'http://localhost:55443', 'https://evil.test'):
            with self.subTest(origin=origin):
                self.assertEqual(self.call(origin), 403)

    def test_fetch_metadata_and_simple_post_are_denied(self):
        self.assertEqual(self.call('https://localhost:55443', fetch_site='same-site'), 403)
        for media in ('text/plain', 'application/x-www-form-urlencoded', 'multipart/form-data'):
            with self.subTest(media=media):
                self.assertEqual(self.call('https://localhost:55443', media=media), 415)

    def test_browser_same_site_other_port_sends_cookie_but_cannot_mutate(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='msedge', headless=True)
            try:
                context = browser.new_context(ignore_https_errors=True)
                context.add_cookies([{'name': 'session', 'value': 'synthetic-valid-cookie', 'domain': 'localhost', 'path': '/', 'secure': True, 'sameSite': 'Lax'}])
                page = context.new_page()
                page.goto('https://localhost:55444')
                with page.expect_response('https://localhost:55443/api/mutate') as response_info:
                    page.locator('form').evaluate('(form) => form.submit()')
                response = response_info.value
                self.assertEqual(response.status, 403)
                headers = response.request.all_headers()
                self.assertIn('session=synthetic-valid-cookie', headers['cookie'])
                self.assertEqual(headers['origin'], 'https://localhost:55444')
                page.goto('https://localhost:55443')
                self.assertEqual(page.evaluate("async () => (await fetch('/api/mutate', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'})).status"), 200)
            finally:
                browser.close()
