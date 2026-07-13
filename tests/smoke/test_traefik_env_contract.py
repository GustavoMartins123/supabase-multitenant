from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TraefikEnvContractTests(unittest.TestCase):
    def test_server_example_contains_every_traefik_compose_variable(self) -> None:
        compose = (
            ROOT / "servidor/traefik/docker-compose.yml"
        ).read_text(encoding="utf-8")
        example = (ROOT / "servidor/.env.example").read_text(encoding="utf-8")

        compose_variables = set(
            re.findall(r"\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}", compose)
        )
        example_variables = {
            line.split("=", 1)[0]
            for line in example.splitlines()
            if line and not line.startswith("#") and "=" in line
        }

        self.assertEqual(set(), compose_variables - example_variables)

    def test_start_and_stop_load_server_env_for_traefik(self) -> None:
        expected = "docker compose -f traefik/docker-compose.yml --env-file .env"
        for script_name in ("start.sh", "stop_containers.sh"):
            source = (ROOT / script_name).read_text(encoding="utf-8")
            self.assertIn(expected, source)


if __name__ == "__main__":
    unittest.main()
