from __future__ import annotations
import pathlib
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]
class ContentStableProjectIdentityTests(unittest.TestCase):
    def test_runtime_content_scope_is_authorized_in_python(self):
        source=(ROOT/'servidor/api-internal/app/routers/studio_content.py').read_text()
        self.assertIn('resolve_authenticated_user(request, pool)',source)
        self.assertIn('get_public_project_row(conn, ref)',source)
        self.assertIn('ensure_project_member_access',source)
        self.assertIn('user["db_user_id"]',source)
        self.assertNotIn('project_name_history',source)
    def test_identity_is_a_persisted_uuid_not_a_name_hash(self):
        source=(ROOT/'servidor/api-internal/app/studio_content.py').read_text()
        self.assertIn('self.content.content_id != self.id',source)
        self.assertIn('body.id, project_id, user_id',source)
        self.assertNotIn('deterministic_uuid',source)
        lua=ROOT/'studio/nginx/lua/studio_compat'
        for name in ('content_namespace.lua','content_virtualization.lua','content_user_proxy.lua','content_studio_client.lua'):
            self.assertFalse((lua/name).exists())
    def test_internal_identity_is_ref_only_without_history(self):
        source=(ROOT/'servidor/api-internal/app/routers/internal.py').read_text()
        start=source.index('"/api/projects/internal/content-identity/{project_ref}"')
        end=source.index('"/api/projects/internal/studio-context/{ref}"',start)
        route=source[start:end]
        self.assertIn('_require_studio_nginx(request)',route)
        self.assertIn('get_public_project_row(conn, project_ref)',route)
        self.assertNotIn('project_name_history',route)
    def test_gateway_signature_uses_the_original_public_reference(self):
        source=(ROOT/'studio/nginx/lua/security/projects_api_signer.lua').read_text()
        self.assertIn('content_ref ~= ngx.ctx.studio_request_project_ref',source)
        self.assertIn('append_query("/api/projects/" .. content_ref .. "/content" .. resource)',source)
if __name__ == '__main__': unittest.main()
