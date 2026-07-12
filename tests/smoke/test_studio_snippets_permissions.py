from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StudioSnippetsPermissionsTests(unittest.TestCase):
    def test_entrypoint_prepares_shared_snippets_before_openresty(self) -> None:
        source = (
            ROOT / "studio" / "nginx" / "docker-entrypoint.sh"
        ).read_text(encoding="utf-8")

        snippets_index = source.index(
            'SNIPPETS_DIR="${SNIPPETS_MANAGEMENT_FOLDER:-/app/snippets}"'
        )
        openresty_index = source.index('exec openresty -g "daemon off;"')

        self.assertLess(snippets_index, openresty_index)
        self.assertIn('chown -R 65534:65534 "$SNIPPETS_DIR"', source)
        self.assertIn(
            'find "$SNIPPETS_DIR" -type d -exec chmod 777 {} +',
            source,
        )
        self.assertIn(
            'find "$SNIPPETS_DIR" -type f -exec chmod 666 {} +',
            source,
        )

    def test_nginx_and_studio_share_the_same_snippets_path(self) -> None:
        compose = (ROOT / "studio" / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        nginx_start = compose.index("  nginx:\n")
        studio_start = compose.index("  studio:\n", nginx_start)
        nginx_block = compose[nginx_start:studio_start]
        studio_block = compose[studio_start:]

        self.assertIn("SNIPPETS_MANAGEMENT_FOLDER: /app/snippets", nginx_block)
        self.assertIn("SNIPPETS_MANAGEMENT_FOLDER: /app/snippets", studio_block)
        self.assertIn("- ./snippets:/app/snippets", nginx_block)
        self.assertIn("- ./snippets:/app/snippets", studio_block)


if __name__ == "__main__":
    unittest.main()
