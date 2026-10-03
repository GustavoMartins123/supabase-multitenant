from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class DesktopWslContractTests(unittest.TestCase):
    def test_database_uses_a_linux_volume_and_an_explicit_private_bind(self):
        source = (ROOT / "servidor/docker-compose.desktop-wsl.yml").read_text(encoding="utf-8")
        self.assertIn("source: desktop-db-data", source)
        self.assertIn("target: /var/lib/postgresql/data", source)
        self.assertIn("${DOCKER_DESKTOP_WSL_HOST:?", source)
        self.assertNotIn("0.0.0.0", source)

    def test_start_selects_the_profile_explicitly_and_rejects_unmigrated_data(self):
        source = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn('if [ -n "$desktop_wsl_host" ]; then', source)
        self.assertIn("HOST_AGENT_DB_DSN configurado pelo setup", source)
        self.assertIn("volumes/db/data/PG_VERSION", source)
        self.assertIn("SERVER_COMPOSE+=(-f docker-compose.desktop-wsl.yml)", source)

    def test_setup_provisions_the_dedicated_agent_dsn(self):
        source = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn("SETUP_DOCKER_DESKTOP_WSL_HOST", source)
        self.assertIn("endereco privado RFC1918", source)
        self.assertIn("postgresql://host_agent_rw:", source)
        self.assertNotIn("postgresql://postgres:", source)

    def test_start_and_agent_use_the_same_explicit_linux_docker_configuration(self):
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        installer = (ROOT / "servidor/host-agent/install.sh").read_text(encoding="utf-8")
        self.assertIn('export DOCKER_CONFIG="$agent_docker_config"', start)
        self.assertIn('DOCKER_CONFIG=$(escape_systemd_value "$HOST_AGENT_DOCKER_CONFIG")', installer)
        self.assertIn('config.json" ] || die', start)

    def test_writable_administrative_and_traefik_state_use_linux_volumes(self):
        traefik = (ROOT / "servidor/traefik/docker-compose.desktop-wsl.yml").read_text(encoding="utf-8")
        studio = (ROOT / "studio/docker-compose.desktop-wsl.yml").read_text(encoding="utf-8")
        self.assertIn("desktop-traefik-dynamic:/dynamic", traefik)
        self.assertIn("desktop-traefik-dynamic:/etc/traefik/dynamic:ro", traefik)
        self.assertEqual(studio.count("usersdb:/config"), 2)
        self.assertIn("condition: service_completed_successfully", studio)
        self.assertIn("desktop-snippets:/app/snippets", studio)

    def test_administrative_initialization_preserves_live_data_and_excludes_ca_key(self):
        source = (ROOT / "studio/initialize-usersdb.sh").read_text(encoding="utf-8")
        self.assertIn("if [ ! -f /config/.desktop-initialized ]; then", source)
        self.assertIn("Existing administrative data requires explicit migration", source)
        self.assertNotIn("ca.key", source)
        self.assertNotIn("|| true", source)


if __name__ == "__main__":
    unittest.main()
