from __future__ import annotations

import ast
import os
import pathlib
import re
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "tools" / "platform_load_probe.py"
HELPER = ROOT / "servidor" / "generateProject" / "lib" / "platform_capacity.sh"


def env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip() in {"1", "true", "yes", "on"}


class LoadProbeContract(unittest.TestCase):
    def test_probe_exists_and_parses(self) -> None:
        self.assertTrue(PROBE.is_file())
        ast.parse(PROBE.read_text(encoding="utf-8"))

    def test_all_project_profiles_have_distinct_workloads(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "LOAD_PROFILES"
                for target in node.targets
            )
        )
        profiles = ast.literal_eval(assignment.value)
        self.assertEqual({"small", "medium", "large"}, set(profiles))
        workers = [profiles[name]["http_workers_per_route"] for name in profiles]
        series = [profiles[name]["series"] for name in profiles]
        rest_rows = [profiles[name]["rest_rows"] for name in profiles]
        self.assertEqual(workers, sorted(workers))
        self.assertEqual(series, sorted(series))
        self.assertEqual(rest_rows, sorted(rest_rows))
        self.assertEqual(len(workers), len(set(workers)))
        self.assertEqual(len(series), len(set(series)))
        self.assertEqual(len(rest_rows), len(set(rest_rows)))

    def test_project_and_shared_services_are_measured(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("PLATFORM_SERVICE_CONTAINER", source)
        self.assertIn("PROJECT_CONTAINER_NAMES", source)
        for service in ("nginx", "auth", "rest"):
            self.assertIn(f'"{service}"', source)
        helper = HELPER.read_text(encoding="utf-8")
        block = helper.split("PLATFORM_SERVICE_CONTAINER=(", 1)[1].split("\n)", 1)[0]
        mapped = dict(re.findall(r'"([a-z-]+):([^"\n]+)"', block))
        self.assertGreaterEqual(len(mapped), 10)
        self.assertIn('mapped["postgres"]', source)

    def test_workload_exercises_project_gateways_and_database(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        for route in (
            "auth/v1/settings",
            "rest/v1/",
            "storage/v1/bucket",
            "functions/v1/hello",
        ):
            self.assertIn(route, source)
        self.assertIn('"psql"', source)
        self.assertIn("ThreadPoolExecutor(max_workers=2)", source)

    def test_workload_exercises_shared_service_endpoints(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        for service in (
            "realtime",
            "analytics",
            "supavisor",
            "vector",
            "projects-api",
            "key-authorizer",
            "postgres-meta",
            "imgproxy",
        ):
            with self.subTest(service=service):
                self.assertRegex(source, rf'"{service}",\s*"shared/{service}"')

    def test_probe_rejects_containers_from_another_root(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("com.docker.compose.project.working_dir", source)
        self.assertIn("path_belongs_to", source)
        self.assertIn("nao pertence", source)

    def test_probe_measures_and_recommends_hardware(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        for signal in (
            "memory.current",
            "pids.current",
            "cpu.stat",
            "io.stat",
            "oom_kill",
            "restarts",
            "container_changed",
            "cpu_samples_discarded",
            "os.sched_getaffinity",
            "recommended",
            "--headroom",
            "--max-usage",
        ):
            with self.subTest(signal=signal):
                self.assertIn(signal, source)

    def test_probe_has_machine_readable_output_and_nonzero_failure(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("--json", source)
        self.assertIn("--output", source)
        self.assertIn('return 1 if any(profile["failures"]', source)

    def test_each_route_has_independent_workers(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("for endpoint in endpoints", source)
        self.assertIn("for _ in range(workers_per_route)", source)
        self.assertIn('"http_workers_total"', source)

    def test_report_includes_transfer_rate_and_capacity_profiles(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("response_mib_per_second", source)
        self.assertIn("def capacity_profiles(", source)
        self.assertIn('"capacity_profiles": capacity_profiles(results)', source)

    def test_repetitions_use_the_most_conservative_measurement(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn("--repetitions", source)
        self.assertIn("def aggregate_runs(", source)
        self.assertIn('result["http"]["rps"] = min(http_rates)', source)
        self.assertIn('service["recommended"][metric] = max(', source)

    def test_fixture_is_explicit_temporary_and_cleaned_up(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        for signal in (
            "--prepare-fixture",
            "CREATE UNLOGGED TABLE",
            "DROP TABLE IF EXISTS",
            "NOTIFY pgrst",
            'settings["rest_rows"]',
            "response.read()",
        ):
            with self.subTest(signal=signal):
                self.assertIn(signal, source)

    def test_restart_is_explicit(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--restart", action="store_true")', source)

    def test_new_probe_code_has_no_comments_or_docstrings(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        self.assertNotIn('"""', source)
        comments = [
            line
            for index, line in enumerate(source.splitlines())
            if line.lstrip().startswith("#") and index != 0
        ]
        self.assertEqual([], comments)


@unittest.skipUnless(
    env_flag("RUN_PLATFORM_LOAD"),
    "carga real exige RUN_PLATFORM_LOAD=1",
)
class LoadProbeExecutionTest(unittest.TestCase):
    def test_platform_survives_load_within_its_limits(self) -> None:
        root = os.getenv("PLATFORM_LOAD_ROOT") or str(ROOT)
        result = subprocess.run(
            [
                sys.executable,
                str(PROBE),
                "--root",
                root,
                "--project",
                os.getenv("PLATFORM_LOAD_PROJECT", "meu_projeto"),
                "--profile",
                os.getenv("PLATFORM_LOAD_PROFILE", "small"),
                "--seconds",
                os.getenv("PLATFORM_LOAD_SECONDS", "30"),
                "--max-usage",
                os.getenv("PLATFORM_LOAD_MAX_USAGE", "80"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, f"{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
