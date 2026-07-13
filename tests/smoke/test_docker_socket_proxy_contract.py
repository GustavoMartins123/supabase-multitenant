from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


def service_block(compose: str, service: str) -> str:
    lines = compose.splitlines()
    marker = f"  {service}:"
    try:
        start = lines.index(marker) + 1
    except ValueError as exc:
        raise AssertionError(f"Service not found: {service}") from exc

    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("  ") and not line.startswith("    ") and line.strip():
            break
        body.append(line)
    return "\n".join(body)


class DockerSocketProxyContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server_compose = (
            ROOT / "servidor" / "docker-compose.yml"
        ).read_text(encoding="utf-8")
        self.traefik_compose = (
            ROOT / "servidor" / "traefik" / "docker-compose.yml"
        ).read_text(encoding="utf-8")
        self.traefik_config = (
            ROOT / "servidor" / "traefik" / "traefik.yml"
        ).read_text(encoding="utf-8")
        self.vector_config = (
            ROOT / "servidor" / "volumes" / "logs" / "vector.yml"
        ).read_text(encoding="utf-8")

    def assert_read_only_permissions(self, proxy: str) -> None:
        for permission in ("CONTAINERS", "EVENTS", "PING", "VERSION"):
            self.assertIn(f'{permission}: "1"', proxy)
        self.assertIn('POST: "0"', proxy)
        for permission in (
            "AUTH",
            "BUILD",
            "EXEC",
            "IMAGES",
            "INFO",
            "NETWORKS",
            "SECRETS",
            "SYSTEM",
            "VOLUMES",
        ):
            self.assertNotIn(f'{permission}: "1"', proxy)

    def test_traefik_uses_its_own_read_only_proxy(self) -> None:
        proxy = service_block(self.traefik_compose, "traefik-docker-proxy")
        traefik = service_block(self.traefik_compose, "traefik")

        self.assertIn("/var/run/docker.sock:ro", proxy)
        self.assertNotIn("/var/run/docker.sock", traefik)
        self.assert_read_only_permissions(proxy)
        self.assertNotIn("ports:", proxy)
        self.assertIn("traefik-docker-api", proxy)
        self.assertIn("traefik-docker-api", traefik)
        self.assertNotIn("rede-supabase", proxy)
        self.assertIn(
            "endpoint: tcp://traefik-docker-proxy:2375",
            self.traefik_config,
        )

    def test_vector_uses_its_own_read_only_proxy(self) -> None:
        proxy = service_block(self.server_compose, "vector-docker-proxy")
        vector = service_block(self.server_compose, "vector")

        self.assertIn("/var/run/docker.sock:ro,z", proxy)
        self.assertNotIn("/var/run/docker.sock", vector)
        self.assert_read_only_permissions(proxy)
        self.assertNotIn("ports:", proxy)
        self.assertIn("vector-docker-api", proxy)
        self.assertIn("vector-docker-api", vector)
        self.assertNotIn("analytics-internal", proxy)
        self.assertIn(
            "docker_host: http://vector-docker-proxy:2375",
            self.vector_config,
        )

    def test_proxy_networks_are_internal_and_not_shared(self) -> None:
        traefik_network = service_block(
            self.traefik_compose,
            "traefik-docker-api",
        )
        vector_network = service_block(self.server_compose, "vector-docker-api")

        self.assertIn("name: supabase-traefik-docker-api", traefik_network)
        self.assertIn("internal: true", traefik_network)
        self.assertIn("name: supabase-vector-docker-api", vector_network)
        self.assertIn("internal: true", vector_network)
        self.assertNotIn("vector-docker-api", self.traefik_compose)
        self.assertNotIn("traefik-docker-api", self.server_compose)


if __name__ == "__main__":
    unittest.main()
