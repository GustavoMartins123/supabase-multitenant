"""CI permanente nao pode sumir silenciosamente (P0 #1 do backlog)."""

from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class CiWorkflowContract(unittest.TestCase):
    def test_workflow_exists_and_runs_the_smoke_suite(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python -m pytest tests/smoke -q", source)
        self.assertIn("bash -n", source)
        self.assertIn("luac -p", source)
        self.assertIn("shellcheck", source)
        self.assertIn("python tools/check-env-contract.py --compose", source)
        self.assertIn("flutter analyze", source)
        self.assertIn("flutter test", source)

    def test_workflow_scans_secrets_dependencies_and_types(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("gitleaks", source)
        self.assertIn(".gitleaks.toml", source)
        self.assertIn("pip_audit", source)
        self.assertIn("python -m mypy", source)

    def test_workflow_runs_migrations_against_real_postgres(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("migrations-live", source)
        self.assertIn("postgres:15", source)
        self.assertIn("RUN_MIGRATIONS_INTEGRATION", source)
        self.assertIn(
            "tests/integration/test_control_plane_migrations_postgres.py",
            source,
        )

    def test_workflow_catches_undefined_names(self) -> None:
        """compileall nao pega NameError: o sweep F821 e obrigatorio.

        Dois bugs reais desta classe passaram pelo compileall — `body`
        fora de escopo no worker de criacao e `ensure_inside` sem import
        no host-agent — e so apareceram em runtime, ja no meio do job.
        """
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--select F821", source)
        for target in (
            "servidor/api-internal/app",
            "servidor/host-agent/hostagent",
            "tools",
        ):
            with self.subTest(target=target):
                self.assertIn(target, source)

    def test_e2e_suite_stays_opt_in(self) -> None:
        e2e = (
            ROOT / "tests" / "smoke" / "test_platform_e2e_integration.py"
        ).read_text(encoding="utf-8")
        self.assertIn('env_flag("RUN_PLATFORM_E2E")', e2e)
        # CI nao pode ligar a flag: E2E roda so em instalacao descartavel.
        self.assertNotIn("RUN_PLATFORM_E2E=1", WORKFLOW.read_text(encoding="utf-8"))

    def test_load_suite_stays_opt_in(self) -> None:
        probe = (
            ROOT / "tests" / "smoke" / "test_platform_load_probe_contract.py"
        ).read_text(encoding="utf-8")
        self.assertIn('env_flag("RUN_PLATFORM_LOAD")', probe)
        self.assertNotIn("RUN_PLATFORM_LOAD=1", WORKFLOW.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
