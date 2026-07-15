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


if __name__ == "__main__":
    unittest.main()
