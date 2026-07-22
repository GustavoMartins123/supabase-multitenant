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


class DockerSocketRemovalContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server_compose = (ROOT / "servidor/docker-compose.yml").read_text(
            encoding="utf-8"
        )
        self.api_compose = (ROOT / "servidor/docker-compose-api.yml").read_text(
            encoding="utf-8"
        )
        self.single_node = (
            ROOT / "servidor/docker-compose.single-node.yml"
        ).read_text(encoding="utf-8")
        self.split_node = (
            ROOT / "servidor/docker-compose.split-node.yml"
        ).read_text(encoding="utf-8")
        self.traefik_compose = (
            ROOT / "servidor/traefik/docker-compose.yml"
        ).read_text(encoding="utf-8")
        self.traefik_config = (
            ROOT / "servidor/traefik/traefik.yml"
        ).read_text(encoding="utf-8")
        self.vector_config = (
            ROOT / "servidor/volumes/logs/vector.yml"
        ).read_text(encoding="utf-8")

    def test_traefik_uses_only_file_provider(self) -> None:
        watcher = service_block(self.traefik_compose, "traefik-config-watcher")
        traefik = service_block(self.traefik_compose, "traefik")
        self.assertNotIn("/var/run/docker.sock", self.traefik_compose)
        self.assertNotIn("traefik-docker-proxy", self.traefik_compose)
        self.assertNotIn("  docker:", self.traefik_config)
        self.assertIn("directory: /etc/traefik/dynamic", self.traefik_config)
        self.assertIn("./dynamic:/etc/traefik/dynamic:ro", traefik)
        self.assertNotIn("./middlewares.yml:/etc/traefik/dynamic", traefik)
        self.assertIn("./middlewares.yml:/config/middlewares.yml:ro", watcher)
        self.assertIn("--middlewares-file", watcher)
        self.assertNotIn("labels:", traefik)

    def test_vector_receives_fluent_logs_without_docker_api(self) -> None:
        vector = service_block(self.server_compose, "vector")
        self.assertNotIn("/var/run/docker.sock", self.server_compose)
        self.assertNotIn("vector-docker-proxy", self.server_compose)
        self.assertNotIn("vector-docker-api", self.server_compose)
        self.assertIn("type: fluent", self.vector_config)
        self.assertIn("address: 0.0.0.0:24224", self.vector_config)
        self.assertNotIn("type: docker_logs", self.vector_config)
        self.assertNotIn("docker_host:", self.vector_config.split("sources:", 1)[1])
        self.assertIn("VECTOR_FLUENTD_PORT", vector)

    def test_projects_api_has_no_docker_access_at_all(self) -> None:
        projects_api = service_block(self.api_compose, "projects-api")
        self.assertNotIn("/var/run/docker.sock", projects_api)
        self.assertNotIn("labels:", projects_api)
        self.assertNotIn("DOCKER_HOST", projects_api)
        self.assertIn("HOST_AGENT_HMAC_SECRET", projects_api)

    def test_topology_overrides_have_no_lifecycle_proxy(self) -> None:
        for compose in (self.single_node, self.split_node):
            self.assertNotIn("lifecycle-docker-proxy", compose)
            self.assertNotIn("lifecycle-docker-api", compose)
            self.assertNotIn("/var/run/docker.sock", compose)
            self.assertNotIn("DOCKER_HOST", compose)

    def test_api_image_has_no_docker_cli_or_scripts(self) -> None:
        dockerfile = (ROOT / "servidor/api-internal/Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("docker-ce-cli", dockerfile)
        self.assertNotIn("generateProject", dockerfile)

    def test_startup_profiles_separate_server_and_studio_nodes(self) -> None:
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        stop = (ROOT / "stop_containers.sh").read_text(encoding="utf-8")
        for profile in ("single-node", "split-node-server", "split-node-studio"):
            self.assertIn(profile, start)
            self.assertIn(profile, stop)
        self.assertIn('API_OVERRIDE="docker-compose.${SERVER_TOPOLOGY}.yml"', start)
        self.assertIn('if [ "$DEPLOYMENT_PROFILE" = "single-node" ]', start)

    def test_server_start_requires_and_reloads_operational_host_agent(self) -> None:
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("require_host_agent_installation", start)
        self.assertIn('HOST_AGENT_PYTHON="$HOST_AGENT_DIR/.venv/bin/python"', start)
        self.assertIn('grep -Fq "$HOST_AGENT_PYTHON" "$HOST_AGENT_UNIT"', start)
        self.assertIn("Aguardando Projects API ficar pronta", start)
        self.assertIn('cd "$HOST_AGENT_DIR"', start)
        self.assertIn("--check-schema", start)
        self.assertIn("run_systemctl restart supabase-host-agent", start)
        self.assertIn("host-agent ainda usa o contrato antigo de root", start)
        self.assertNotIn('exec sudo bash "$ROOT_DIR/start.sh"', start)
        self.assertNotIn("systemctl start supabase-host-agent", start)

    def test_server_stop_stops_host_agent_before_shared_services(self) -> None:
        stop = (ROOT / "stop_containers.sh").read_text(encoding="utf-8")
        agent_stop = stop.index("run_systemctl stop supabase-host-agent")
        shared_stop = stop.index('echo "Parando Projects API e servicos compartilhados..."')
        self.assertLess(agent_stop, shared_stop)
        self.assertNotIn('exec sudo bash "$ROOT_DIR/stop_containers.sh"', stop)


if __name__ == "__main__":
    unittest.main()
