from __future__ import annotations
import pathlib
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
class StudioSnippetsPermissionsTests(unittest.TestCase):
    def test_no_shared_writable_snippet_filesystem(self):
        for relative in ('studio/docker-compose.yml', 'studio/docker-compose.desktop-wsl.yml', 'studio/.env.example', 'studio/nginx/docker-entrypoint.sh', 'studio/initialize-usersdb.sh'):
            source = (ROOT/relative).read_text(encoding='utf-8')
            self.assertNotIn('SNIPPETS_MANAGEMENT_FOLDER', source)
            self.assertNotIn('/app/snippets', source)
            self.assertNotIn('desktop-snippets', source)
            self.assertNotIn('/seed-snippets', source)
    def test_content_gateway_only_routes_and_authenticates(self):
        source = (ROOT/'studio/nginx/nginx.conf').read_text(encoding='utf-8')
        self.assertIn('security/studio_content_access.lua', source)
        self.assertIn('proxy_pass $server_domain/api/projects/$content_ref/content$content_resource$is_args$args;', source)
        self.assertNotIn('studio_compat/content_user', source)
        gateway=(ROOT/'studio/nginx/lua/security/studio_content_access.lua').read_text()
        self.assertIn('security.project_access', gateway)
        self.assertIn('security.projects_api_signer', gateway)
        self.assertNotIn('cjson', gateway)
        self.assertNotIn('snippet', gateway)
if __name__ == '__main__': unittest.main()
