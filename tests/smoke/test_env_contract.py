"""Contrato das variaveis de ambiente: examples vs consumo real.

O `tools/check-env-contract.py` e a fonte da verdade executavel; este
modulo trava os invariantes que ja quebraram antes (placeholders que
sobrevivem ao setup, subnet/gateway inconsistentes, variavel consumida
sem declaracao) e testa a validacao de rede de forma unitaria.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "check-env-contract.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("check_env_contract", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EnvContractToolTest(unittest.TestCase):
    def test_installed_host_agent_dependencies_are_not_platform_sources(self) -> None:
        import tempfile

        tool = load_tool()
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for relative, variable in (
                ("servidor/host-agent/hostagent/config.py", "HOST_AGENT_DB_PASSWORD"),
                ("servidor/host-agent/.venv/lib/python/site-packages/pip/vendor.py", "PIP_VENDOR_ONLY"),
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f'import os\nos.getenv("{variable}")\n', encoding="utf-8")
            with mock.patch.object(tool, "ROOT", root):
                self.assertEqual(tool.scan_python(), {"HOST_AGENT_DB_PASSWORD"})

    def test_tool_passes_on_the_current_tree(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(TOOL)],
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"tools/check-env-contract.py falhou:\n{completed.stdout}\n"
            f"{completed.stderr}",
        )
        self.assertIn("0 error(s)", completed.stdout)

    def test_only_documented_pass_keys_lack_setup_generation(self) -> None:
        import re

        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        setup = (ROOT / "setup.sh").read_text(encoding="utf-8")
        pass_keys = [
            line[:-len("=pass")]
            for line in example.splitlines()
            if line.endswith("=pass")
        ]
        self.assertGreaterEqual(len(pass_keys), 5, pass_keys)
        for key in pass_keys:
            with self.subTest(key=key):
                generated = (
                    re.search(rf"env_secret \S+ {re.escape(key)} ", setup)
                    is not None
                    or f"s|{key}=" in setup
                )
                allowlisted = (
                    key == "TRAEFIK_ACME_EMAIL"
                    and "TRAEFIK_ACME_EMAIL" in setup
                )
                self.assertTrue(
                    generated or allowlisted,
                    f"{key}=pass sem geracao nem allowlist documentada no setup.sh",
                )


class EnvNetworkValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = load_tool()

    def _check(self, values: dict[str, str]) -> list[str]:
        report = self.tool.Report()
        self.tool.check_network(report, values, "test")
        return report.errors

    def test_valid_topology_passes(self) -> None:
        self.assertEqual(
            self._check(
                {
                    "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                    "SUPABASE_NETWORK_GATEWAY": "172.50.0.1",
                    "SUPABASE_NETWORK_IP_RANGE": "172.50.0.0/18",
                    "PROJECTS_API_ALLOWED_IP_RANGES": "10.0.0.5/32,172.50.0.0/16",
                }
            ),
            [],
        )

    def test_gateway_outside_subnet_fails(self) -> None:
        errors = self._check(
            {
                "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                "SUPABASE_NETWORK_GATEWAY": "192.168.1.1",
            }
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("fora da subnet", errors[0])

    def test_malformed_cidr_fails(self) -> None:
        errors = self._check({"SUPABASE_NETWORK_SUBNET": "172.50.0.0/33"})
        self.assertEqual(len(errors), 1)
        errors = self._check(
            {
                "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                "PROJECTS_API_ALLOWED_IP_RANGES": "nao-e-ip",
            }
        )
        self.assertEqual(len(errors), 1)

    def test_example_placeholders_are_accepted_in_examples_only(self) -> None:
        report = self.tool.Report()
        self.tool.check_network(
            report,
            {
                "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                "SUPABASE_NETWORK_GATEWAY": "172.50.0.1",
                "PROJECTS_API_ALLOWED_IP_RANGES": "<SEU_IP>/32,172.50.0.0/16",
            },
            "servidor/.env.example",
        )
        self.assertEqual(report.errors, [])
        errors = self._check(
            {
                "SUPABASE_NETWORK_SUBNET": "172.50.0.0/16",
                "SUPABASE_NETWORK_GATEWAY": "172.50.0.1",
                "PROJECTS_API_ALLOWED_IP_RANGES": "<SEU_IP>/32",
            }
        )
        self.assertEqual(len(errors), 1)


class EnvRealFileHygieneTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tool = load_tool()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tmpdir = pathlib.Path(directory.name)
        self.tool.ROOT = self.tmpdir

    def _write(self, name: str, content: str) -> str:
        (self.tmpdir / name).write_text(content, encoding="utf-8")
        return name

    def _check(self, files: list[str]) -> object:
        report = self.tool.Report()
        self.tool.check_real_files(report, files)
        return report

    def test_leftover_pass_and_placeholders_fail(self) -> None:
        relative = self._write(
            "dirty.env",
            "JWT_SECRET=pass\nSERVER_DOMAIN=https://<SEU_IP>:9091\n"
            "NGINX_HMAC_SECRET=abc \n",
        )
        report = self._check([relative])
        self.assertGreaterEqual(len(report.errors), 3, report.errors)
        joined = "\n".join(report.errors)
        self.assertIn("JWT_SECRET=pass", joined)
        self.assertIn("SERVER_DOMAIN", joined)
        self.assertIn("NGINX_HMAC_SECRET", joined)

    def test_clean_file_passes(self) -> None:
        relative = self._write(
            "clean.env",
            "JWT_SECRET=dummy-value-12345678901234567890\n"
            "NGINX_HMAC_SECRET=dummy-value-12345678901234567890\n"
            "SUPABASE_NETWORK_SUBNET=172.50.0.0/16\n"
            "SUPABASE_NETWORK_GATEWAY=172.50.0.1\n",
        )
        report = self._check([relative])
        self.assertEqual(report.errors, [])


class EnvComposeEnvSynthesisTest(unittest.TestCase):
    def test_compose_uses_only_isolated_example_env_files(self) -> None:
        tool = load_tool()
        seen = []

        def check(command, **kwargs):
            project = pathlib.Path(command[command.index("--project-directory") + 1])
            self.assertFalse(project.is_relative_to(ROOT))
            self.assertTrue((project / ".env").is_file())
            for name in (".analytics.env", ".storage.env") if "servidor" in project.parts else (".analytics.env",):
                self.assertTrue((project / name).is_file())
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        report = tool.Report()
        with mock.patch.object(tool.shutil, "which", return_value="docker"), mock.patch.object(tool.subprocess, "run", side_effect=check):
            tool.check_compose_profiles(report)
        self.assertEqual(report.errors, [])
        self.assertEqual(len(seen), 5)

    def test_requested_compose_validation_fails_without_docker(self) -> None:
        tool = load_tool()
        report = tool.Report()
        with mock.patch.object(tool.shutil, "which", return_value=None):
            tool.check_compose_profiles(report)
        self.assertEqual(len(report.errors), 1)
        self.assertEqual(report.warnings, [])

    def test_empty_example_values_become_dummy(self) -> None:
        import tempfile

        tool = load_tool()
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "studio").mkdir()
            (root / "studio/.env.example").write_text("STUDIO_GATEWAY_HMAC_SECRET=\nSERVICE_KEY_CACHE_TTL_SECONDS=60\n", encoding="utf-8")
            with mock.patch.object(tool, "ROOT", root):
                target = tool._example_env_for_compose("studio/.env.example", root)
            values = tool.parse_env_file(target)
            self.assertEqual(
                values["STUDIO_GATEWAY_HMAC_SECRET"], "dummy"
            )
            self.assertEqual(
                values["SERVICE_KEY_CACHE_TTL_SECONDS"], "60"
            )

    def test_both_topology_overlays_are_covered(self) -> None:
        import inspect

        tool = load_tool()
        source = inspect.getsource(tool.check_compose_profiles)
        self.assertIn("docker-compose.single-node.yml", source)
        self.assertIn("docker-compose.split-node.yml", source)
        self.assertIn("traefik/docker-compose.yml", source)
        self.assertIn("studio/docker-compose.yml", source)


if __name__ == "__main__":
    unittest.main()
