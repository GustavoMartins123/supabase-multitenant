from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ContentStableProjectIdentityTests(unittest.TestCase):
    def test_runtime_requires_verified_canonical_identity(self):
        lua = ROOT / "studio/nginx/lua/studio_compat"
        identity = (lua / "content_project_identity.lua").read_text()
        namespace = (lua / "content_namespace.lua").read_text()
        virtualization = (lua / "content_virtualization.lua").read_text()
        self.assertIn("ngx.ctx.studio_project_context", identity)
        self.assertIn("context.ref ~= project_ref", identity)
        self.assertNotIn("request_uri", identity)
        self.assertNotIn("content_namespace_migration", namespace)
        self.assertNotIn("legacy_id", virtualization)
        self.assertFalse((lua / "content_namespace_migration.lua").exists())

    def test_internal_identity_is_ref_only_without_history(self):
        source = (ROOT / "servidor/api-internal/app/routers/internal.py").read_text()
        start = source.index('"/api/projects/internal/content-identity/{project_ref}"')
        end = source.index('"/api/projects/internal/studio-context/{ref}"', start)
        route = source[start:end]
        self.assertIn("_require_studio_nginx(request)", route)
        self.assertIn("get_public_project_row(conn, project_ref)", route)
        self.assertNotIn("project_name_history", route)
        self.assertNotIn("aliases", route)
        self.assertIn('"project_id": str(project["id"])', route)

    def test_read_routes_do_not_create_namespace_directories(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/studio_compat/content_user_proxy.lua"
        ).read_text(encoding="utf-8")

        content = source[
            source.index("function _M.handle_content()"):
            source.index("function _M.handle_folders()")
        ]
        folders = source[
            source.index("function _M.handle_folders()"):
            source.index("function _M.handle_folder_item()")
        ]
        count = source[
            source.index("function _M.handle_count()"):
            source.index("function _M.handle_item()")
        ]

        self.assertIn(
            "resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)",
            content,
        )
        self.assertIn(
            "resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)",
            folders,
        )
        self.assertIn(
            "resolve_namespace_root_folder(api_project_ref, user_id, project_scope, false)",
            count,
        )

    def test_no_runtime_migration_or_legacy_endpoint(self):
        nginx = (ROOT / "studio/nginx/nginx.conf").read_text()
        self.assertNotIn("/internal/snippets/rename", nginx)
        self.assertFalse((ROOT / "servidor/api-internal/app/snippets_migration.py").exists())


if __name__ == "__main__":
    unittest.main()
