from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class ContentStableProjectIdentityTests(unittest.TestCase):
    def test_internal_identity_route_returns_project_id_and_history(self) -> None:
        source = (
            ROOT / "servidor/api-internal/app/routers/internal.py"
        ).read_text(encoding="utf-8")
        start = source.index(
            '@router.get("/api/projects/internal/content-identity/{project_name}")'
        )
        end = source.index(
            '@router.get("/api/projects/internal/enc-key/{ref}")',
            start,
        )
        route = source[start:end]

        self.assertIn('request.headers.get("X-Internal-Service") != "studio-nginx"', route)
        self.assertIn('"SELECT id, name FROM projects WHERE name = $1"', route)
        self.assertIn("FROM project_name_history", route)
        self.assertIn('"project_id": str(project["id"])', route)
        self.assertIn('headers={"Cache-Control": "no-store"}', route)

    def test_content_proxy_uses_stable_identity_only_for_content(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/studio_compat/content_user_proxy.lua"
        ).read_text(encoding="utf-8")

        self.assertIn('content_project_identity.resolve(selected_ref)', source)
        self.assertIn('return identity.project_id', source)
        self.assertIn('content_namespace_migration.ensure(user_id, identity)', source)
        self.assertIn('id_namespace = namespace_state.root_folder.id', source)
        self.assertIn('local legacy_id = virtual_snippet_id(snippet.name, virtual_folder)', source)

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

    def test_legacy_migration_preserves_conflicting_sql(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/studio_compat/content_namespace_migration.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("cache:add(key, token, exptime_seconds)", source)
        self.assertIn('"__legacy_" .. safe_label(label)', source)
        self.assertIn("files_equal(source_path, target_path)", source)
        self.assertIn("stats.conflicts_preserved", source)
        self.assertIn("identity.aliases", source)

    def test_rename_endpoint_no_longer_moves_slug_directories(self) -> None:
        source = (
            ROOT / "studio/nginx/lua/admin_api/snippets_rename.lua"
        ).read_text(encoding="utf-8")

        self.assertIn("deprecated = true", source)
        self.assertNotIn("os.rename", source)
        self.assertNotIn("lfs.dir", source)


if __name__ == "__main__":
    unittest.main()
