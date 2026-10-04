import unittest
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SetupTopologyProfileContractTests(unittest.TestCase):
    @unittest.skipUnless(os.name != "nt" and shutil.which("bash"), "Linux Bash runtime required")
    def test_studio_startup_stops_when_registry_pull_fails(self) -> None:
        self._check_studio_startup(pull_fails=True)

    @unittest.skipUnless(os.name != "nt" and shutil.which("bash"), "Linux Bash runtime required")
    def test_studio_startup_builds_only_the_gateway_after_pull(self) -> None:
        self._check_studio_startup(pull_fails=False)

    def _check_studio_startup(self, *, pull_fails: bool) -> None:
        source = (ROOT / "start.sh").read_text(encoding="utf-8")
        start = source.index("start_studio() {")
        function = source[start:source.index("\n}", start) + 2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "studio").mkdir()
            (root / "servidor").mkdir()
            (root / "servidor/.env").write_text("")
            binary = root / "bin"
            binary.mkdir()
            docker = binary / "docker"
            docker.write_text(
                '#!/usr/bin/env bash\n'
                'printf "%s\\n" "$*" >> "$TRACE"\n'
                'if [[ " $* " == *" pull "* && "$PULL_FAIL" == 1 ]]; then exit 42; fi\n'
            )
            docker.chmod(0o755)
            trace = root / "trace"
            env = {**os.environ, "ROOT_DIR": str(root), "TRACE": str(trace),
                   "PULL_FAIL": "1" if pull_fails else "0",
                   "PATH": str(binary) + os.pathsep + os.environ["PATH"]}
            script = 'set -euo pipefail\ndie() { echo "$*" >&2; exit 1; }\n' + function + '\nstart_studio\n'
            result = subprocess.run([shutil.which("bash"), "-c", script], env=env,
                                    capture_output=True, text=True)
            self.assertTrue(trace.is_file(), result.stderr)
            calls = trace.read_text().splitlines()
            self.assertIn("pull --ignore-buildable --policy always", calls[0])
            if pull_fails:
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(len(calls), 1)
                self.assertIn("falha ao baixar", result.stderr)
            else:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 3)
                self.assertTrue(calls[1].endswith("build nginx studio-assistant"))
                self.assertTrue(calls[2].endswith("up --no-build --pull never -d"))

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
        self.assertIn('"${STUDIO_COMPOSE[@]}" up --no-build --pull never -d', start)


if __name__ == "__main__":
    unittest.main()
