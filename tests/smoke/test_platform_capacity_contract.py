from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "servidor" / "generateProject" / "lib" / "platform_capacity.sh"
ENV_EXAMPLE = ROOT / "servidor" / ".env.example"
START = ROOT / "start.sh"

BASE_ENV = (
    "PLATFORM_RESERVE_PERCENT=20\n"
    "PLATFORM_HOST_MEMORY=32g\n"
    "PLATFORM_HOST_CPUS=32\n"
    "PLATFORM_POSTGRES_SHARE_PERCENT=50\n"
    "PLATFORM_WORK_MEM_NODES=2\n"
    "PLATFORM_HOST_DISK=500g\n"
    "PLATFORM_CPU_OVERSUBSCRIBE_MAX=300\n"
    "PROJECT_RESOURCE_PROFILE=medium\n"
    "PROJECT_RES_MEDIUM_MEMORY=1g\n"
    "PROJECT_RES_MEDIUM_CPUS=2.00\n"
    "PROJECT_RES_MEDIUM_PIDS=384\n"
)


def compute(env_text: str) -> dict[str, str]:
    bash = shutil.which("bash") or "bash"
    with tempfile.TemporaryDirectory() as tmp:
        root_env = pathlib.Path(tmp) / ".env"
        root_env.write_text(env_text, encoding="utf-8")
        result = subprocess.run(
            [
                bash,
                "-c",
                f'source "{HELPER}"; PLATFORM_SERVICE_CONTAINER=(); '
                f'platform_compute_capacity "{root_env}" '
                "&& set | grep '^PLATFORM_CAP_'",
            ],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "calculador falhou")
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value.strip().strip("'")
    return values


class ReserveContract(unittest.TestCase):
    def test_reserve_is_never_allocated(self) -> None:
        values = compute(BASE_ENV)
        host = int(values["PLATFORM_CAP_HOST_MIB"])
        reserved = int(values["PLATFORM_CAP_RESERVED_MIB"])
        allocatable = int(values["PLATFORM_CAP_ALLOCATABLE_MIB"])
        self.assertEqual(host, 32 * 1024)
        self.assertEqual(reserved, host * 20 // 100)
        self.assertEqual(allocatable, host - reserved)

    def test_allocation_never_exceeds_the_allocatable(self) -> None:
        for reserve in (10, 20, 35, 50):
            env = BASE_ENV.replace(
                "PLATFORM_RESERVE_PERCENT=20",
                f"PLATFORM_RESERVE_PERCENT={reserve}",
            ).replace("PLATFORM_HOST_CPUS=32", "PLATFORM_HOST_CPUS=64")
            values = compute(env)
            with self.subTest(reserve=reserve):
                total = (
                    int(values["PLATFORM_CAP_SHARED_TOTAL_MIB"])
                    + int(values["PLATFORM_CAP_POSTGRES_MIB"])
                    + int(values["PLATFORM_CAP_PROJECTS"])
                    * int(values["PLATFORM_CAP_PROJECT_MIB"])
                )
                self.assertLessEqual(total, int(values["PLATFORM_CAP_ALLOCATABLE_MIB"]))

    def test_invalid_reserve_falls_back_to_default(self) -> None:
        for reserve in ("0", "5", "80", "abc"):
            env = BASE_ENV.replace(
                "PLATFORM_RESERVE_PERCENT=20",
                f"PLATFORM_RESERVE_PERCENT={reserve}",
            )
            with self.subTest(reserve=reserve):
                values = compute(env)
                self.assertEqual(25, int(values["PLATFORM_CAP_RESERVE_PERCENT"]))

    def test_reserve_tolerates_carriage_returns_and_spaces(self) -> None:
        env = BASE_ENV.replace(
            "PLATFORM_RESERVE_PERCENT=20", "PLATFORM_RESERVE_PERCENT=10\r"
        )
        values = compute(env)
        self.assertEqual(10, int(values["PLATFORM_CAP_RESERVE_PERCENT"]))
        env = BASE_ENV.replace(
            "PLATFORM_RESERVE_PERCENT=20", "PLATFORM_RESERVE_PERCENT= 30 "
        )
        self.assertEqual(30, int(compute(env)["PLATFORM_CAP_RESERVE_PERCENT"]))


class DerivationContract(unittest.TestCase):
    def test_work_mem_is_output_not_input(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("PLATFORM_WORK_MEM=", source)
        self.assertIn("work_mem_mib=$(( available_for_sorts", source)

        small = compute(
            BASE_ENV.replace("PLATFORM_HOST_MEMORY=32g", "PLATFORM_HOST_MEMORY=16g")
        )
        large = compute(
            BASE_ENV.replace("PLATFORM_HOST_MEMORY=32g", "PLATFORM_HOST_MEMORY=128g")
        )
        self.assertGreater(
            int(large["PLATFORM_CAP_PROJECTS"]),
            int(small["PLATFORM_CAP_PROJECTS"]),
            "host maior tem de comportar mais projetos",
        )

    def test_postgres_budget_covers_its_own_terms(self) -> None:
        values = compute(BASE_ENV)
        postgres = int(values["PLATFORM_CAP_POSTGRES_MIB"])
        used = (
            int(values["PLATFORM_CAP_SHARED_BUFFERS_MIB"])
            + int(values["PLATFORM_CAP_MAINTENANCE_MIB"])
            * int(values["PLATFORM_CAP_AUTOVACUUM_WORKERS"])
            + int(values["PLATFORM_CAP_WORK_MEM_MIB"])
            * int(values["PLATFORM_CAP_ACTIVE_CONNECTIONS"])
            * int(values["PLATFORM_CAP_ALLOCATIONS_PER_CONNECTION"])
        )
        self.assertLessEqual(used, postgres)

    def test_allocation_factor_includes_parallelism_and_hash(self) -> None:
        values = compute(BASE_ENV)
        nodes = int(values["PLATFORM_CAP_WORK_MEM_NODES"])
        parallel = int(values["PLATFORM_CAP_PARALLEL_PER_GATHER"])
        hash_multiplier = int(values["PLATFORM_CAP_HASH_MEM_MULTIPLIER"])
        self.assertEqual(
            nodes * (1 + parallel) * hash_multiplier,
            int(values["PLATFORM_CAP_ALLOCATIONS_PER_CONNECTION"]),
        )
        self.assertGreaterEqual(hash_multiplier, 2)

    def test_parallelism_is_reduced_on_crowded_hosts(self) -> None:
        crowded = compute(
            BASE_ENV.replace("PLATFORM_HOST_MEMORY=32g", "PLATFORM_HOST_MEMORY=128g")
        )
        self.assertLessEqual(int(crowded["PLATFORM_CAP_PARALLEL_PER_GATHER"]), 1)

    def test_concurrency_factor_is_explicit_and_bounded(self) -> None:
        values = compute(BASE_ENV)
        active = int(values["PLATFORM_CAP_ACTIVE_CONNECTIONS"])
        total = int(values["PLATFORM_CAP_MAX_CONNECTIONS"])
        self.assertLess(active, total)
        self.assertEqual(
            active, total * int(values["PLATFORM_CAP_ACTIVE_PERCENT"]) // 100
        )

        for bad in ("0", "3", "150", "abc", "25\r"):
            env = BASE_ENV + f"PLATFORM_ACTIVE_CONNECTION_PERCENT={bad}\n"
            with self.subTest(percent=bad):
                values = compute(env)
                self.assertEqual(25, int(values["PLATFORM_CAP_ACTIVE_PERCENT"]))

        strict = compute(BASE_ENV + "PLATFORM_ACTIVE_CONNECTION_PERCENT=100\n")
        self.assertLess(
            int(strict["PLATFORM_CAP_PROJECTS"]), int(values["PLATFORM_CAP_PROJECTS"])
        )

    def test_connections_cover_the_control_plane_plus_every_project(self) -> None:
        bash = shutil.which("bash") or "bash"
        values = compute(BASE_ENV)
        projects = int(values["PLATFORM_CAP_PROJECTS"])
        control = subprocess.run(
            [
                bash,
                "-c",
                f'source "{HELPER}"; platform_control_connections {projects}',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_MAX_CONNECTIONS"]),
            int(control.stdout.strip()) + 20 + projects * 40,
        )

    def test_control_plane_connections_scale_with_projects(self) -> None:
        bash = shutil.which("bash") or "bash"

        def control(projects: int) -> int:
            result = subprocess.run(
                [
                    bash,
                    "-c",
                    f'source "{HELPER}"; platform_control_connections {projects}',
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return int(result.stdout.strip())

        self.assertLess(control(0), control(10))
        self.assertLess(control(10), control(50))

        self.assertLess(control(0), 100)

    def _small_host_env(self, memory: str) -> str:
        return (
            "PLATFORM_RESERVE_PERCENT=20\n"
            f"PLATFORM_HOST_MEMORY={memory}\n"
            "PLATFORM_HOST_CPUS=32\n"
            "PLATFORM_HOST_DISK=500g\n"
            "PLATFORM_CPU_OVERSUBSCRIBE_MAX=300\n"
            "PROJECT_RESOURCE_PROFILE=small\n"
            "PROJECT_RES_SMALL_MEMORY=256m\n"
            "PROJECT_RES_SMALL_CPUS=1.85\n"
            "PROJECT_RES_SMALL_PIDS=128\n"
        )

    def test_modest_host_fits_at_least_one_project(self) -> None:
        values = compute(self._small_host_env("12g"))
        self.assertGreaterEqual(int(values["PLATFORM_CAP_PROJECTS"]), 1)

    def test_host_below_the_minimum_starts_degraded(self) -> None:
        values = compute(self._small_host_env("4g"))
        self.assertGreaterEqual(int(values["PLATFORM_CAP_PROJECTS"]), 1)
        self.assertTrue(values.get("PLATFORM_CAP_DEGRADED"))

    def test_ceiling_grows_with_the_host(self) -> None:
        sizes = ["12g", "16g", "32g", "64g"]
        ceilings = [
            int(compute(self._small_host_env(size))["PLATFORM_CAP_PROJECTS"])
            for size in sizes
        ]
        self.assertEqual(ceilings, sorted(ceilings))
        self.assertLess(ceilings[0], ceilings[-1])

    def test_zero_capacity_starts_degraded(self) -> None:
        env = (
            "PLATFORM_RESERVE_PERCENT=20\n"
            "PLATFORM_HOST_MEMORY=3g\n"
            "PLATFORM_HOST_CPUS=2\n"
            "PROJECT_RESOURCE_PROFILE=large\n"
            "PROJECT_RES_LARGE_MEMORY=4g\n"
            "PROJECT_RES_LARGE_CPUS=3.00\n"
            "PROJECT_RES_LARGE_PIDS=768\n"
        )
        values = compute(env)
        self.assertGreaterEqual(int(values["PLATFORM_CAP_PROJECTS"]), 1)
        self.assertTrue(values.get("PLATFORM_CAP_DEGRADED"))
        self.assertGreater(int(values["PLATFORM_CAP_POSTGRES_MIB"]), 0)
        self.assertGreater(int(values["PLATFORM_CAP_WORK_MEM_MIB"]), 0)

    def test_replication_slots_cover_every_project_with_slack(self) -> None:
        values = compute(BASE_ENV)
        self.assertGreater(
            int(values["PLATFORM_CAP_REPLICATION_SLOTS"]),
            int(values["PLATFORM_CAP_PROJECTS"]),
        )
        self.assertGreater(
            int(values["PLATFORM_CAP_WAL_SENDERS"]),
            int(values["PLATFORM_CAP_REPLICATION_SLOTS"]),
        )

    def test_capacity_scales_with_the_project_profile(self) -> None:
        capable_env = BASE_ENV.replace(
            "PLATFORM_HOST_MEMORY=32g", "PLATFORM_HOST_MEMORY=64g"
        ).replace("PLATFORM_HOST_CPUS=16", "PLATFORM_HOST_CPUS=32")
        medium = compute(capable_env)
        large_env = (
            capable_env.replace(
                "PROJECT_RESOURCE_PROFILE=medium", "PROJECT_RESOURCE_PROFILE=large"
            )
            + "PROJECT_RES_LARGE_MEMORY=4g\nPROJECT_RES_LARGE_CPUS=3.00\nPROJECT_RES_LARGE_PIDS=768\n"
        )
        large = compute(large_env)
        self.assertLess(
            int(large["PLATFORM_CAP_PROJECTS"]),
            int(medium["PLATFORM_CAP_PROJECTS"]),
        )


def run_helper(script: str, *, measure: bool = False) -> str:
    bash = shutil.which("bash") or "bash"
    prelude = "" if measure else "PLATFORM_SERVICE_CONTAINER=(); "
    result = subprocess.run(
        [bash, "-c", f'source "{HELPER}"; {prelude}{script}'],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip() or "helper falhou")
    return result.stdout.strip()


class PostgresConfigSourceContract(unittest.TestCase):
    DERIVED = (
        "max_connections",
        "shared_buffers",
        "effective_cache_size",
        "maintenance_work_mem",
        "work_mem",
        "max_wal_size",
        "min_wal_size",
        "max_worker_processes",
        "max_parallel_workers",
        "max_parallel_workers_per_gather",
        "max_parallel_maintenance_workers",
        "autovacuum_max_workers",
        "max_replication_slots",
        "max_wal_senders",
    )

    def test_derived_parameters_left_the_command_line(self) -> None:
        compose = (ROOT / "servidor" / "docker-compose.yml").read_text()
        block = compose.split("  db:", 1)[1].split("\n  realtime:", 1)[0]
        for parameter in self.DERIVED:
            with self.subTest(parameter=parameter):
                self.assertNotRegex(block, rf"(?m)^\s+- {parameter}=")

    def test_generated_config_is_mounted_into_conf_d(self) -> None:
        compose = (ROOT / "servidor" / "docker-compose.yml").read_text()
        self.assertIn("platform-capacity.conf:/etc/postgresql-custom/conf.d/", compose)

    def test_renderer_emits_every_derived_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(BASE_ENV, encoding="utf-8")
            output = pathlib.Path(tmp) / "pg.conf"
            run_helper(f'platform_render_postgres_conf "{root_env}" "{output}"')
            rendered = output.read_text(encoding="utf-8")
        for parameter in self.DERIVED + ("temp_file_limit",):
            with self.subTest(parameter=parameter):
                self.assertRegex(rendered, rf"(?m)^{parameter} = ")

    def test_rendered_config_separates_restart_from_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(BASE_ENV, encoding="utf-8")
            output = pathlib.Path(tmp) / "pg.conf"
            run_helper(f'platform_render_postgres_conf "{root_env}" "{output}"')
            rendered = output.read_text(encoding="utf-8")
        self.assertIn("exigem RESTART", rendered)
        self.assertIn("aceitam reload", rendered)
        restart_at = rendered.index("exigem RESTART")
        reload_at = rendered.index("aceitam reload")

        self.assertLess(restart_at, rendered.index("max_connections = "))
        self.assertLess(rendered.index("max_connections = "), reload_at)
        self.assertLess(reload_at, rendered.index("work_mem = "))

    def test_start_generates_before_the_database_starts(self) -> None:
        start = (ROOT / "start.sh").read_text()
        self.assertIn("platform_render_postgres_conf", start)
        self.assertLess(
            start.index("platform_render_postgres_conf"),
            start.index('docker compose -f docker-compose.yml -f "$CAPACITY_SERVIDOR"'),
        )

    def test_generated_config_is_not_tracked(self) -> None:
        ignored = (ROOT / ".gitignore").read_text()
        self.assertIn("platform-capacity.conf", ignored)


class ComposeLimitsContract(unittest.TestCase):
    TARGETS = {
        "servidor": ROOT / "servidor" / "docker-compose.yml",
        "api": ROOT / "servidor" / "docker-compose-api.yml",
        "studio": ROOT / "studio" / "docker-compose.yml",
        "traefik": ROOT / "servidor" / "traefik" / "docker-compose.yml",
    }

    def _render(self, target: str) -> dict:
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(BASE_ENV, encoding="utf-8")
            output = pathlib.Path(tmp) / "ov.yml"
            run_helper(
                f'platform_render_compose_override "{root_env}" {target} "{output}"'
            )
            return yaml.safe_load(output.read_text(encoding="utf-8")) or {}

    def test_every_service_gets_all_three_limits(self) -> None:
        for target in self.TARGETS:
            rendered = self._render(target).get("services") or {}
            self.assertTrue(rendered, target)
            for name, spec in rendered.items():
                with self.subTest(target=target, service=name):
                    for key in ("mem_limit", "memswap_limit", "cpus", "pids_limit"):
                        self.assertIn(key, spec)

    def test_override_targets_only_services_that_exist(self) -> None:
        import yaml

        for target, compose_path in self.TARGETS.items():
            base = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
            declared = set((base.get("services") or {}).keys())
            rendered = set((self._render(target).get("services") or {}).keys())
            with self.subTest(target=target):
                self.assertEqual(set(), rendered - declared)

    def test_postgres_gets_the_derived_budget_not_a_env_constant(self) -> None:
        rendered = self._render("servidor")["services"]["db"]
        self.assertRegex(str(rendered["mem_limit"]), r"^\d+m$")
        self.assertIn("pids_limit", rendered)

        compose = self.TARGETS["servidor"].read_text(encoding="utf-8")
        self.assertNotIn("POSTGRES_MEM_LIMIT", compose)
        example = (ROOT / "servidor" / ".env.example").read_text(encoding="utf-8")
        self.assertNotRegex(example, r"(?m)^POSTGRES_MEM_LIMIT=")

    def test_start_uses_every_override(self) -> None:
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        for name in (
            "docker-compose.capacity.yml",
            "docker-compose-api.capacity.yml",
            "traefik/docker-compose.capacity.yml",
        ):
            with self.subTest(name=name):
                self.assertIn(name, start)
        self.assertIn("platform_render_compose_override", start)

    def test_overrides_are_not_tracked(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("docker-compose.capacity.yml", ignored)


class HostAdaptiveBaselineContract(unittest.TestCase):
    def test_measurement_can_only_raise_the_baseline(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        body = source.split("platform_service_baseline_mib() {", 1)[1].split("\n}", 1)[
            0
        ]
        self.assertIn('-gt "$floor"', body)

        for service in ("realtime", "supavisor", "analytics"):
            with self.subTest(service=service):
                value = int(
                    run_helper(
                        "PLATFORM_SERVICE_CONTAINER=(); "
                        f"platform_service_baseline_mib {service} 20"
                    )
                )
                self.assertGreater(value, 0)

    def test_reference_scales_with_host_cores(self) -> None:
        small = int(
            run_helper(
                "PLATFORM_SERVICE_CONTAINER=(); "
                "platform_service_baseline_mib supavisor 4"
            )
        )
        large = int(
            run_helper(
                "PLATFORM_SERVICE_CONTAINER=(); "
                "platform_service_baseline_mib supavisor 64"
            )
        )
        self.assertLess(small, large)

        flat_small = int(
            run_helper(
                "PLATFORM_SERVICE_CONTAINER=(); "
                "platform_service_baseline_mib analytics 4"
            )
        )
        flat_large = int(
            run_helper(
                "PLATFORM_SERVICE_CONTAINER=(); "
                "platform_service_baseline_mib analytics 64"
            )
        )
        self.assertEqual(flat_small, flat_large)

    def test_measurement_reads_the_peak_not_the_instant(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertNotIn("platform_container_anon_mib", source)

        memory = source.split("platform_container_peak_mib() {", 1)[1].split("\n}", 1)[
            0
        ]
        self.assertIn("memory.peak", memory)
        pids = source.split("platform_container_peak_pids() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("pids.peak", pids)

        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotIn("docker stats", code)

    def test_measurement_clipped_by_its_own_limit_is_rejected(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        for function in (
            "platform_container_peak_mib",
            "platform_container_peak_pids",
        ):
            with self.subTest(function=function):
                body = source.split(f"{function}() {{", 1)[1].split("\n}", 1)[0]
                self.assertIn("* 95 / 100", body)
                self.assertIn("docker inspect", body)

    def test_worker_per_core_runtimes_scale_with_cores(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        scaled = source.split("PLATFORM_CPU_SCALED_SERVICES=(", 1)[1].split(")", 1)[0]
        for service in ("realtime", "supavisor", "studio-nginx"):
            with self.subTest(service=service):
                self.assertIn(service, scaled)

    def test_limit_headroom_is_separate_from_budget_reserve(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        self.assertIn("PLATFORM_LIMIT_HEADROOM_PERCENT", source)
        headroom = int(
            re.search(r"PLATFORM_LIMIT_HEADROOM_PERCENT=(\d+)", source).group(1)
        )
        self.assertGreaterEqual(headroom, 100, "limite a menos de 2x do pico")

        limit = source.split("platform_service_limit_mib() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("PLATFORM_LIMIT_HEADROOM_PERCENT", limit)
        self.assertIn("PLATFORM_LIMIT_FLOOR_MIB", limit)

    def test_pids_limits_are_orders_of_magnitude_above_normal(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        body = source.split("platform_service_pids() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("pids.peak", source)
        self.assertIn("baseline * 4", body)
        self.assertIn("PLATFORM_LIMIT_FLOOR_PIDS", body)

        for service in ("realtime", "supavisor", "analytics"):
            with self.subTest(service=service):
                value = int(
                    run_helper(
                        "PLATFORM_SERVICE_CONTAINER=(); "
                        f"platform_service_pids {service} 20"
                    )
                )
                self.assertGreaterEqual(value, 128)

    def test_every_service_maps_to_a_container(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        baseline_block = source.split("PLATFORM_SHARED_BASELINE_MIB=(", 1)[1].split(
            ")", 1
        )[0]
        container_block = source.split("PLATFORM_SERVICE_CONTAINER=(", 1)[1].split(
            ")", 1
        )[0]
        services = set(re.findall(r'"([a-z-]+):\d+"', baseline_block))
        mapped = set(re.findall(r'"([a-z-]+):[^"]+"', container_block))
        self.assertEqual(set(), services - mapped)


class BaselineMethodContract(unittest.TestCase):
    def test_baselines_use_the_anon_method(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        body = source.split("platform_container_peak_mib() {", 1)[1].split("\n}", 1)[0]
        self.assertIn("memory.stat", body)
        self.assertIn("/^anon /", body)
        self.assertNotIn("docker stats", body)

    def test_beam_services_are_not_undersized(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        block = source.split("PLATFORM_SHARED_BASELINE_MIB=(", 1)[1].split(")", 1)[0]
        baselines = {
            m.group(1): int(m.group(2))
            for m in re.finditer(r'"([a-z-]+):(\d+)"', block)
        }
        for service in ("realtime", "supavisor"):
            with self.subTest(service=service):
                self.assertGreater(baselines[service], 150)

    def test_per_project_increment_has_explicit_nonzero_values(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        block = source.split("PLATFORM_SHARED_PER_PROJECT_MIB=(", 1)[1].split(")", 1)[0]
        values = {
            match.group(1): int(match.group(2))
            for match in re.finditer(r'"([a-z-]+):(\d+)"', block)
        }
        self.assertEqual({"realtime", "supavisor", "storage"}, set(values))
        self.assertTrue(all(value > 0 for value in values.values()))


class CpuContract(unittest.TestCase):
    def test_default_does_not_oversubscribe_cpu(self) -> None:
        values = compute(BASE_ENV.replace("PLATFORM_CPU_OVERSUBSCRIBE_MAX=300\n", ""))
        self.assertEqual(int(values["PLATFORM_CAP_CPU_OVERSUBSCRIBE_MAX"]), 100)

    def test_oversubscription_is_at_least_neutral(self) -> None:
        values = compute(BASE_ENV)
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_CPU_OVERSUBSCRIBE"]), 100
        )

    def test_cpu_never_lowers_the_ceiling_or_fails_the_host(self) -> None:
        """Tetos de CPU sao contencao, nao reserva: host pequeno inicia.

        Um projeto medium exige ~17 núcleos somando pisos calibrados — qualquer
        laptop consumer falhava antes. Agora a derivacao sempre entrega o teto
        de memoria/work_mem e apenas reporta o sobrecompromisso implicado.
        """
        scarce_env = (
            "PLATFORM_RESERVE_PERCENT=25\n"
            "PLATFORM_HOST_MEMORY=32g\n"
            "PLATFORM_HOST_CPUS=20\n"
            "PLATFORM_POSTGRES_SHARE_PERCENT=50\n"
            "PLATFORM_WORK_MEM_NODES=2\n"
            "PLATFORM_HOST_DISK=500g\n"
            "PROJECT_RESOURCE_PROFILE=medium\n"
            "PROJECT_RES_MEDIUM_MEMORY=1g\n"
            "PROJECT_RES_MEDIUM_CPUS=2.00\n"
            "PROJECT_RES_MEDIUM_PIDS=384\n"
        )
        scarce = compute(scarce_env)
        self.assertGreaterEqual(int(scarce["PLATFORM_CAP_PROJECTS"]), 1)
        self.assertNotEqual("cpu", scarce["PLATFORM_CAP_BINDING"])
        # A escassez aparece como sinal, nao como bloqueio.
        self.assertIn("sobrecomprometido", scarce["PLATFORM_CAP_CPU_FIT"])
        self.assertGreater(int(scarce["PLATFORM_CAP_CPU_OVERSUBSCRIBE"]), 100)

        # Declarar um maximo generoso inverte apenas o SINAL de aptidao;
        # o numero de projetos suportados nunca depende da tolerancia.
        relaxed = compute(
            scarce_env + "PLATFORM_CPU_OVERSUBSCRIBE_MAX=200000\n"
        )
        self.assertEqual(
            scarce["PLATFORM_CAP_PROJECTS"], relaxed["PLATFORM_CAP_PROJECTS"]
        )
        self.assertEqual("dentro do orcamento", relaxed["PLATFORM_CAP_CPU_FIT"])

    def test_declared_maximum_is_kept_as_a_report_reference(self) -> None:
        generous = compute(
            BASE_ENV.replace("PLATFORM_CPU_OVERSUBSCRIBE_MAX=300", "800")
        )
        strict = compute(
            BASE_ENV.replace("PLATFORM_CPU_OVERSUBSCRIBE_MAX=300", "100")
        )
        # O maximo declarado nao altera mais o numero de projetos suportados;
        # ele e so a referencia contra a qual a aptidao (FIT) e comparada.
        self.assertEqual(
            generous["PLATFORM_CAP_PROJECTS"], strict["PLATFORM_CAP_PROJECTS"]
        )

    def test_cpu_is_fully_apportioned(self) -> None:
        values = compute(BASE_ENV)
        allocatable = int(values["PLATFORM_CAP_ALLOCATABLE_CPUS"]) * 100
        self.assertLessEqual(
            int(values["PLATFORM_CAP_SHARED_CPU_CENTI"])
            + int(values["PLATFORM_CAP_POSTGRES_CPU_CENTI"]),
            allocatable,
        )

    def test_shared_cpu_uses_the_sum_after_per_service_floors(self) -> None:
        values = compute(BASE_ENV)
        source = HELPER.read_text(encoding="utf-8")
        block = source.split("PLATFORM_SHARED_CPU_FLOOR_CENTI=(", 1)[1].split(
            ")", 1
        )[0]
        floor_total = sum(
            int(value) for value in re.findall(r'"[a-z-]+:(\d+)"', block)
        )
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_SHARED_CPU_CENTI"]), floor_total
        )
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_SHARED_CPU_CENTI"]),
            int(values["PLATFORM_CAP_SHARED_CPU_BUDGET_CENTI"]),
        )

    def test_calibrated_small_cpu_floor_starts_at_twenty_seven_cores(self) -> None:
        """Pisos calibrados viram SINAL, nunca bloqueio: hosts pequenos sobem.

        Antes: <27 nucleos abortava o start.sh inteiro. Agora a derivacao
        entrega o teto de memoria/work_mem e marca a aptidao de CPU como
        sobrecomprometida (informativo), deixando a decisao ao operador.
        """
        env = (
            "PLATFORM_RESERVE_PERCENT=25\n"
            "PLATFORM_HOST_MEMORY=64g\n"
            "PLATFORM_HOST_CPUS=20\n"
            "PLATFORM_HOST_DISK=500g\n"
            "PLATFORM_CPU_OVERSUBSCRIBE_MAX=100\n"
            "PROJECT_RESOURCE_PROFILE=small\n"
            "PROJECT_RES_SMALL_MEMORY=256m\n"
            "PROJECT_RES_SMALL_CPUS=1.85\n"
            "PROJECT_RES_SMALL_PIDS=128\n"
        )
        for cores in (4, 20):
            with self.subTest(cores=cores):
                accepted = compute(
                    env.replace(
                        "PLATFORM_HOST_CPUS=20",
                        f"PLATFORM_HOST_CPUS={cores}",
                    )
                )
                self.assertGreaterEqual(int(accepted["PLATFORM_CAP_PROJECTS"]), 1)
                self.assertIn(
                    "sobrecomprometido", accepted["PLATFORM_CAP_CPU_FIT"]
                )

    def test_calibrated_shared_cpu_floors_are_applied(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        block = source.split("PLATFORM_SHARED_CPU_FLOOR_CENTI=(", 1)[1].split(")", 1)[0]
        floors = {
            match.group(1): int(match.group(2))
            for match in re.finditer(r'"([a-z-]+):(\d+)"', block)
        }
        baseline = source.split("PLATFORM_SHARED_BASELINE_MIB=(", 1)[1].split(")", 1)[0]
        services = set(re.findall(r'"([a-z-]+):\d+"', baseline))
        self.assertEqual(services, set(floors))
        calibrated = {
            "geoip": 25,
            "imgproxy": 65,
            "key-authorizer": 70,
            "postgres-meta": 60,
            "realtime": 40,
            "storage": 75,
            "studio": 70,
            "studio-nginx": 45,
            "supavisor": 95,
        }
        for service, minimum in calibrated.items():
            with self.subTest(calibrated=service):
                self.assertGreaterEqual(floors[service], minimum)
        for service, floor in floors.items():
            with self.subTest(service=service):
                value = int(run_helper(f"platform_service_cpu_centi {service} 320"))
                self.assertGreaterEqual(value, floor)

    def test_postgres_cpu_floor_follows_the_project_profile(self) -> None:
        profiles = {
            "small": ("256m", "1.85", "128"),
            "medium": ("1g", "2.00", "384"),
            "large": ("4g", "3.00", "768"),
        }
        floors = []
        for profile, (memory, cpus, pids) in profiles.items():
            env = (
                "PLATFORM_RESERVE_PERCENT=20\n"
                "PLATFORM_HOST_MEMORY=64g\n"
                "PLATFORM_HOST_CPUS=32\n"
                "PLATFORM_HOST_DISK=500g\n"
                "PLATFORM_CPU_OVERSUBSCRIBE_MAX=300\n"
                f"PROJECT_RESOURCE_PROFILE={profile}\n"
                f"PROJECT_RES_{profile.upper()}_MEMORY={memory}\n"
                f"PROJECT_RES_{profile.upper()}_CPUS={cpus}\n"
                f"PROJECT_RES_{profile.upper()}_PIDS={pids}\n"
            )
            values = compute(env)
            floor = int(values["PLATFORM_CAP_POSTGRES_CPU_FLOOR_CENTI"])
            floors.append(floor)
            self.assertGreaterEqual(
                int(values["PLATFORM_CAP_POSTGRES_CPU_CENTI"]), floor
            )
        self.assertEqual(floors, [545, 890, 1035])


class DiskContract(unittest.TestCase):
    def test_reserve_applies_to_disk_too(self) -> None:
        values = compute(BASE_ENV)
        total = int(values["PLATFORM_CAP_DISK_MIB"])
        reserved = int(values["PLATFORM_CAP_DISK_RESERVED_MIB"])
        self.assertEqual(reserved, total * 20 // 100)
        self.assertEqual(
            int(values["PLATFORM_CAP_DISK_ALLOCATABLE_MIB"]), total - reserved
        )

    def test_temp_files_are_capped_per_connection(self) -> None:
        values = compute(BASE_ENV)
        limit = int(values["PLATFORM_CAP_TEMP_FILE_LIMIT_MIB"])
        self.assertGreater(limit, 0)
        allocatable = int(values["PLATFORM_CAP_DISK_ALLOCATABLE_MIB"])
        active = int(values["PLATFORM_CAP_ACTIVE_CONNECTIONS"])
        self.assertLessEqual(limit * active, allocatable)

    def test_wal_and_project_quota_fit_the_disk_budget(self) -> None:
        values = compute(BASE_ENV)
        allocatable = int(values["PLATFORM_CAP_DISK_ALLOCATABLE_MIB"])
        used = int(values["PLATFORM_CAP_MAX_WAL_MIB"]) + int(
            values["PLATFORM_CAP_PROJECT_DISK_MIB"]
        ) * int(values["PLATFORM_CAP_PROJECTS"])
        self.assertLessEqual(used, allocatable)
        self.assertGreater(
            int(values["PLATFORM_CAP_MAX_WAL_MIB"]),
            int(values["PLATFORM_CAP_MIN_WAL_MIB"]),
        )


class WorkerContract(unittest.TestCase):
    def test_autovacuum_scales_with_tenant_databases(self) -> None:
        small = compute(BASE_ENV)
        large = compute(
            BASE_ENV.replace(
                "PLATFORM_HOST_MEMORY=32g", "PLATFORM_HOST_MEMORY=128g"
            ).replace("PLATFORM_HOST_CPUS=32", "PLATFORM_HOST_CPUS=64")
        )
        self.assertGreater(
            int(large["PLATFORM_CAP_PROJECTS"]), int(small["PLATFORM_CAP_PROJECTS"])
        )
        self.assertGreaterEqual(int(small["PLATFORM_CAP_AUTOVACUUM_WORKERS"]), 4)
        self.assertGreater(
            int(large["PLATFORM_CAP_AUTOVACUUM_WORKERS"]),
            int(small["PLATFORM_CAP_AUTOVACUUM_WORKERS"]),
        )

    def test_worker_processes_cover_parallel_plus_logical(self) -> None:
        values = compute(BASE_ENV)
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_MAX_WORKER_PROCESSES"]),
            int(values["PLATFORM_CAP_MAX_PARALLEL_WORKERS"])
            + int(values["PLATFORM_CAP_LOGICAL_WORKERS"]),
        )

    def test_logical_workers_cover_every_realtime_tenant(self) -> None:
        values = compute(BASE_ENV)
        self.assertGreaterEqual(
            int(values["PLATFORM_CAP_REPLICATION_SLOTS"]),
            int(values["PLATFORM_CAP_PROJECTS"]),
        )


class SharedTierContract(unittest.TestCase):
    def test_edge_infrastructure_is_budgeted_and_limited(self) -> None:
        source = HELPER.read_text(encoding="utf-8")
        start = START.read_text(encoding="utf-8")
        infrastructure = {
            "traefik",
            "geoip",
            "traefik-config",
            "deny-service",
        }
        for array in (
            "PLATFORM_SERVICE_CONTAINER",
            "PLATFORM_SERVICE_COMPOSE",
            "PLATFORM_SHARED_BASELINE_MIB",
            "PLATFORM_SHARED_CPU_WEIGHT",
            "PLATFORM_SHARED_CPU_FLOOR_CENTI",
            "PLATFORM_SHARED_PIDS_BASELINE",
        ):
            block = source.split(f"{array}=(", 1)[1].split(")", 1)[0]
            with self.subTest(array=array):
                self.assertTrue(
                    all(f'"{service}:' in block for service in infrastructure)
                )
        self.assertIn(
            'platform_render_compose_override "$ROOT_DIR/servidor/.env" traefik',
            start,
        )
        self.assertIn('-f "$CAPACITY_TRAEFIK"', start)

    def test_service_limits_carry_the_reserve(self) -> None:
        bash = shutil.which("bash") or "bash"
        source = HELPER.read_text(encoding="utf-8")

        block = source.split("PLATFORM_SHARED_BASELINE_MIB=(", 1)[1].split(")", 1)[0]
        baselines = dict(
            (m.group(1), int(m.group(2)))
            for m in re.finditer(r'"([a-z-]+):(\d+)"', block)
        )
        self.assertIn("realtime", baselines)
        with tempfile.TemporaryDirectory() as tmp:
            root_env = pathlib.Path(tmp) / ".env"
            root_env.write_text(BASE_ENV, encoding="utf-8")
            for service, baseline in baselines.items():
                result = subprocess.run(
                    [
                        bash,
                        "-c",
                        f'source "{HELPER}"; '
                        f'platform_service_limit_mib "{service}" 0 20',
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    continue
                with self.subTest(service=service):
                    self.assertGreaterEqual(int(result.stdout.strip()), baseline)

    def test_every_shared_service_has_all_three_limits(self) -> None:
        bash = shutil.which("bash") or "bash"
        source = HELPER.read_text(encoding="utf-8")
        block = source.split("PLATFORM_SHARED_BASELINE_MIB=(", 1)[1].split(")", 1)[0]
        services = re.findall(r'"([a-z-]+):\d+"', block)
        self.assertGreaterEqual(len(services), 10)
        for service in services:
            for fn, args in (
                ("platform_service_limit_mib", f'"{service}" 5 20'),
                ("platform_service_cpu_centi", f'"{service}" 320'),
                ("platform_service_pids", f'"{service}" 20'),
            ):
                with self.subTest(service=service, fn=fn):
                    result = subprocess.run(
                        [bash, "-c", f'source "{HELPER}"; {fn} {args}'],
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertGreater(int(result.stdout.strip()), 0)

    def test_env_example_declares_only_the_inputs(self) -> None:
        example = ENV_EXAMPLE.read_text(encoding="utf-8")
        for key in (
            "PLATFORM_RESERVE_PERCENT",
            "PLATFORM_HOST_MEMORY",
            "PLATFORM_POSTGRES_SHARE_PERCENT",
            "PLATFORM_WORK_MEM_NODES",
            "PLATFORM_ACTIVE_CONNECTION_PERCENT",
            "PLATFORM_HOST_DISK",
            "PLATFORM_CPU_OVERSUBSCRIBE_MAX",
        ):
            with self.subTest(key=key):
                self.assertRegex(example, rf"(?m)^{key}=")
        for derived in ("PLATFORM_CAP_PROJECTS", "PLATFORM_MAX_CONNECTIONS"):
            with self.subTest(derived=derived):
                self.assertNotRegex(example, rf"(?m)^{derived}=")


class SharedLimitsReapplicationContract(unittest.TestCase):
    def test_shared_limits_are_reapplied_on_create_and_delete(self) -> None:
        for script in (
            ROOT / "servidor/generateProject/lib/generate_project_impl.sh",
            ROOT / "servidor/generateProject/lib/duplicate_project_impl.sh",
            ROOT / "servidor/generateProject/delete_project.sh",
        ):
            with self.subTest(script=script.name):
                self.assertIn(
                    "platform_apply_shared_limits", script.read_text(encoding="utf-8")
                )


if __name__ == "__main__":
    unittest.main()
