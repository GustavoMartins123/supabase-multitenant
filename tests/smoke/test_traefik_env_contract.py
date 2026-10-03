from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class TraefikEnvContractTests(unittest.TestCase):
    def test_server_example_contains_every_traefik_compose_variable(self) -> None:
        compose = (ROOT / "servidor/traefik/docker-compose.yml").read_text(
            encoding="utf-8"
        )
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
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn(
            'TRAEFIK_COMPOSE=(docker compose -f traefik/docker-compose.yml -f "$CAPACITY_TRAEFIK")',
            start,
        )
        self.assertIn('"${TRAEFIK_COMPOSE[@]}" --env-file .env up -d', start)
        expected = (
            r"docker compose -f traefik/docker-compose\.yml"
            r'(?: -f "\$CAPACITY_TRAEFIK")? --env-file \.env'
        )
        stop = (ROOT / "stop_containers.sh").read_text(encoding="utf-8")
        self.assertRegex(stop, expected)


if __name__ == "__main__":
    unittest.main()
