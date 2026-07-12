from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class StudioRuntimeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compose = (ROOT / "studio/docker-compose.yml").read_text(encoding="utf-8")
        start = compose.index("  studio:\n")
        end = compose.index("  # postgres:", start)
        cls.studio = compose[start:end]

    def test_studio_listens_on_the_docker_interface(self) -> None:
        self.assertIn('HOSTNAME: "0.0.0.0"', self.studio)

    def test_studio_healthcheck_matches_the_dashboard_listener(self) -> None:
        self.assertIn("http://localhost:3000/api/platform/profile", self.studio)
        self.assertIn("start_period: 20s", self.studio)
        self.assertIn("timeout: 10s", self.studio)


if __name__ == "__main__":
    unittest.main()
