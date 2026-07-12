from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StatusAndAvatarRegressionTests(unittest.TestCase):
    def test_status_does_not_hold_a_pool_connection_during_auth_resolution(self) -> None:
        source = (ROOT / "servidor/api-internal/app/main.py").read_text(encoding="utf-8")
        start = source.index('@app.get("/api/projects/{project_name}/status")')
        end = source.index('@app.post("/api/projects/{project_name}/stop")', start)
        block = source[start:end]
        self.assertLess(
            block.index("auth_user = await resolve_authenticated_user(request, pool)"),
            block.index("async with pool.acquire() as conn:"),
        )

    def test_status_and_collaboration_keep_the_server_domain_route(self) -> None:
        source = (ROOT / "studio/nginx/nginx.conf").read_text(encoding="utf-8")
        status_start = source.index('location ~ ^/api/projects/(?<slug>[^/]+)/status$')
        status_end = source.index('location ~ ^/api/projects/(?<slug>[^/]+)/logs/', status_start)
        status_block = source[status_start:status_end]
        self.assertIn('proxy_pass $server_domain/api/projects/$slug/status;', status_block)
        generic_start = source.index('location ~ ^/api/projects(/.*)?$')
        generic_end = source.index('location = /api/platform/profile', generic_start)
        generic_block = source[generic_start:generic_end]
        self.assertIn('proxy_pass $server_domain/api/projects$1;', generic_block)
        self.assertNotIn('projects-api:18000', source)

    def test_flutter_accepts_uint8list_from_file_reader(self) -> None:
        source = (
            ROOT / "studio/seletor_de_projetos/lib/user_profile_dialog.dart"
        ).read_text(encoding="utf-8")
        self.assertIn("if (result is Uint8List)", source)
        self.assertIn("else if (result is ByteBuffer)", source)


if __name__ == "__main__":
    unittest.main()
