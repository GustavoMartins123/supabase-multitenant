import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SetupTopologyProfileContractTests(unittest.TestCase):
    def test_single_node_uses_the_detected_local_ip_without_a_prompt(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")

        self.assertIn('local topology_profile="${1:-interactive}"', setup)
        self.assertIn('single-node)', setup)
        self.assertIn('SERVER_IP="$LOCAL_IP"', setup)
        self.assertIn('confirm_network_topology "$LOCAL_IP" "$SERVER_IP" false', setup)
        self.assertIn('main "$@"', setup)

    def test_documentation_uses_explicit_single_node_profile(self) -> None:
        for document in ("README.md", "LEIAME.md"):
            source = (ROOT / document).read_text(encoding="utf-8")
            self.assertIn("bash setup.sh single-node", source)
            self.assertIn("bash start.sh single-node", source)

    def test_published_address_is_explicit_and_tls_is_required(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn('validate_ip "$configured_server"', setup)
        self.assertIn('LOCAL_IP="$configured_server"', setup)
        self.assertNotIn("/etc/resolv.conf", setup)
        self.assertNotIn('PROTO="http"', setup)
        self.assertIn('TRAEFIK_ENABLE_TLS=true', setup)
        self.assertIn('--server-host "$SERVER_IP"', setup)

    def test_setup_resolves_geoip_paths_under_the_server_directory(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        self.assertIn('$SCRIPT_DIR/servidor/traefik/geoip/GeoLite2-Country.mmdb', setup)
        self.assertIn('$SCRIPT_DIR/servidor/traefik/logs_backup/geo', setup)
        self.assertIn('safe_sed "s|^MMDB_PATH=.*', setup)
        self.assertIn('safe_sed "s|^BACKUP_DIR=.*', setup)

    def test_ip_deployments_use_one_dns_identity_for_lua_tls(self) -> None:
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn('BACKEND_HOST="supabase-backend.internal"', setup)
        self.assertIn('RUNTIME_DNS_ARGS=(--server-dns-host "$BACKEND_HOST")', setup)
        self.assertIn('SERVER_DOMAIN=${PROTO}://${SERVER_IP}', setup)
        self.assertIn('STUDIO_BACKEND_TLS_NAME="$BACKEND_HOST"', setup)
        self.assertIn('"${STUDIO_COMPOSE[@]}" up --build -d', start)


if __name__ == "__main__":
    unittest.main()
