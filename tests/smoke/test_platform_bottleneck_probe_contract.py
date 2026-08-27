from __future__ import annotations

import ast
import hashlib
import hmac
import importlib.util
import os
import pathlib
import struct
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"
PROBE = TOOLS / "platform_bottleneck_probe.py"
sys.path.insert(0, str(TOOLS))
SPEC = importlib.util.spec_from_file_location("platform_bottleneck_probe", PROBE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def env_flag(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


class PlatformBottleneckProbeContract(unittest.TestCase):
    def test_probe_exists_parses_and_has_no_source_comments(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertNotIn('"""', source)
        comments = [
            line
            for index, line in enumerate(source.splitlines())
            if line.lstrip().startswith("#") and index != 0
        ]
        self.assertEqual([], comments)

    def test_profiles_increase_every_real_workload_dimension(self) -> None:
        profiles = MODULE.BOTTLENECK_PROFILES
        self.assertEqual({"small", "medium", "large"}, set(profiles))
        ordered = [profiles[name] for name in ("small", "medium", "large")]
        for field in (
            "http_workers_per_route",
            "postgres_workers",
            "pooler_workers",
            "storage_workers",
            "storage_bytes",
            "realtime_workers",
            "series",
            "rest_rows",
            "image_width",
            "analytics_bytes",
        ):
            values = [profile[field] for profile in ordered]
            with self.subTest(field=field):
                self.assertEqual(values, sorted(values))
                self.assertEqual(len(values), len(set(values)))

    def test_entire_platform_has_explicit_coverage(self) -> None:
        expected = {
            "postgres",
            "supavisor",
            "realtime",
            "storage",
            "imgproxy",
            "analytics",
            "vector",
            "postgres-meta",
            "projects-api",
            "key-authorizer",
            "edge-functions",
            "auth",
            "rest",
            "nginx",
            "studio",
            "studio-nginx",
            "authelia",
            "storage-data-plane",
            "traefik",
            "geoip",
            "deny-service",
            "traefik-config",
        }
        targets = {f"shared/{service}": {"service": service} for service in expected}
        coverage = MODULE.coverage_matrix(targets)
        self.assertEqual(expected, {row["service"] for row in coverage})
        self.assertTrue(all(row["available"] for row in coverage))

    def test_functional_protocols_and_cleanup_are_not_health_only(self) -> None:
        source = PROBE.read_text(encoding="utf-8")
        for signal in (
            "project_api_key_slots",
            "project_api_keys",
            "DELETE FROM project_api_key_slots",
            "/auth/v1/admin/users",
            "/auth/v1/token?grant_type=password",
            "cleanup_auth_user",
            "auth.users",
            "/rest/v1/",
            "/storage/v1/object/",
            "/storage/v1/render/image/authenticated/",
            "/realtime/v1/websocket",
            '"event": "phx_join"',
            '"event": "broadcast"',
            '"self": False',
            "receive_matching",
            "/api/logs?source_name=",
            "/tables",
            "/v1/authorize",
            "pgbouncer.",
            "cleanup_storage",
            "cleanup_database_fixture",
            "cleanup_stale",
            "acquire_probe_lock",
        ):
            with self.subTest(signal=signal):
                self.assertIn(signal, source)

    def test_realtime_gateway_builds_authorized_query_after_auth_request(self) -> None:
        nginx = (ROOT / "servidor" / "generateProject" / "nginxtemplate").read_text(
            encoding="utf-8"
        )
        start = nginx.index("location ^~ /realtime/v1/websocket")
        end = nginx.index("location /storage/v1/", start)
        block = nginx[start:end]
        self.assertIn(
            "proxy_pass http://$realtime_upstream/socket/websocket?$opaque_realtime_upstream_args;",
            block,
        )
        self.assertNotIn("rewrite ^/realtime/v1/websocket$", block)

    def test_internal_hmac_matches_the_published_contract(self) -> None:
        secret = "test-secret"
        target = "/api/projects/internal/content-identity/demo"
        headers = MODULE.internal_hmac_headers(secret, "GET", target)
        canonical = "\n".join(
            (
                "internal-hmac-v1",
                "studio-nginx",
                "GET",
                target,
                headers["X-Internal-Timestamp"],
                headers["X-Internal-Nonce"],
                hashlib.sha256(b"").hexdigest(),
            )
        )
        expected = hmac.new(
            secret.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()
        self.assertEqual(expected, headers["X-Internal-Signature"])

    def test_generated_image_is_a_real_png_with_expected_dimensions(self) -> None:
        image = MODULE.generate_png(32, 24)
        self.assertEqual(b"\x89PNG\r\n\x1a\n", image[:8])
        self.assertEqual((32, 24), struct.unpack(">II", image[16:24]))
        self.assertTrue(image.endswith(b"IEND\xaeB`\x82"))

    def test_ranking_identifies_the_highest_container_pressure(self) -> None:
        def service(name: str, cpu: float, memory: float) -> dict:
            return {
                "scope": "shared",
                "service": name,
                "configured": {"cpu_cores": 1, "memory_mib": 100, "pids": 100},
                "usage_percent": {"cpu": cpu, "memory": memory, "pids": 10},
                "observed": {
                    "cpu_peak_cores": cpu / 100,
                    "memory_peak_mib": memory,
                    "pids_peak": 10,
                    "read_mib": 0,
                    "write_mib": 0,
                },
            }

        host = {
            "cpu_peak_percent": 20,
            "memory_used_peak_percent": 30,
            "load_average_peak": 1,
        }
        ranking = MODULE.bottleneck_ranking(
            [service("slow", 95, 50), service("quiet", 20, 30)], host
        )
        self.assertEqual("host", ranking[0]["service"])
        self.assertEqual("shared/slow", ranking[1]["service"])
        self.assertEqual("cpu", ranking[1]["dominant_resource"])

    def test_host_pressure_is_a_failure_and_sizes_the_machine(self) -> None:
        host = {
            "cpu_logical_cores": 20,
            "cpu_peak_percent": 95.6,
            "memory_used_peak_mib": 26532.4,
            "memory_used_peak_percent": 83.5,
        }
        self.assertEqual(
            [
                "host: CPU em 95.6% (maximo 75%)",
                "host: memoria em 83.5% (maximo 75%)",
            ],
            MODULE.host_failures(host, 75),
        )
        self.assertEqual(
            {
                "cpu_cores": 26,
                "memory_mib": 35392,
                "target_usage_percent": 75,
            },
            MODULE.host_recommendation(host, 75),
        )

    def test_repetitions_keep_totals_worst_latency_and_slo_failure(self) -> None:
        def route(p95: float) -> dict:
            return {
                "operations": 1,
                "success": 1,
                "errors": 0,
                "bytes": 1024,
                "statuses": {"200": 1},
                "last_error": "",
                "mib": 0.01,
                "ops_per_second": 10.0,
                "p50_ms": p95 / 2,
                "p95_ms": p95,
                "p99_ms": p95 + 10,
            }

        def realtime(p95: float) -> dict:
            return {
                "connections": 1,
                "joins": 1,
                "messages": 10,
                "errors": 0,
                "messages_per_second": 10.0,
                "p50_ms": p95 / 2,
                "p95_ms": p95,
                "p99_ms": p95 + 10,
                "last_errors": [],
            }

        def database(p95: float) -> dict:
            return {
                "queries": 1,
                "errors": 0,
                "qps": 10.0,
                "p50_ms": p95 / 2,
                "p95_ms": p95,
                "p99_ms": p95 + 10,
                "series_rows": 100,
                "last_error": "",
            }

        def run(route_p95: float, postgres_p95: float) -> dict:
            http_route = route(route_p95)
            storage_route = route(route_p95)
            return {
                "profile": "small",
                "duration_seconds": 10.0,
                "http": {
                    "operations": 1,
                    "success": 1,
                    "errors": 0,
                    "ops_per_second": 10.0,
                    "mib": 0.01,
                    "mib_per_second": 0.01,
                    "routes": {"route": http_route},
                },
                "storage": {
                    "operations": 1,
                    "success": 1,
                    "errors": 0,
                    "ops_per_second": 10.0,
                    "mib": 0.01,
                    "mib_per_second": 0.01,
                    "routes": {"route": storage_route},
                },
                "realtime": realtime(route_p95),
                "realtime_gateway": realtime(route_p95),
                "postgres": database(postgres_p95),
                "supavisor": database(route_p95),
                "postgres_stats": {
                    "connections": 1,
                    "commits": 2,
                    "rollbacks": 0,
                    "blocks_read": 0,
                    "blocks_hit": 10,
                    "temp_files": 0,
                    "temp_bytes": 0,
                    "deadlocks": 0,
                    "conflicts": 0,
                },
                "host": {
                    "cpu_logical_cores": 20,
                    "cpu_average_percent": 40.0,
                    "cpu_peak_percent": 50.0,
                    "memory_total_mib": 32000.0,
                    "memory_used_peak_mib": 16000.0,
                    "memory_used_peak_percent": 50.0,
                    "load_average_peak": 10.0,
                },
                "host_max_usage_percent": 75,
                "host_recommendation": {},
                "max_p95_ms": 150.0,
                "services": [],
                "project_recommendation": {},
                "shared_recommendation": {},
                "bottlenecks": [],
                "failures": [],
            }

        result = MODULE.aggregate_profiles(
            "small", [run(80.0, 100.0), run(100.0, 200.0)]
        )
        self.assertEqual(2, result["http"]["operations"])
        self.assertEqual(100.0, result["http"]["routes"]["route"]["p95_ms"])
        self.assertEqual(2, result["postgres"]["queries"])
        self.assertEqual(200.0, result["postgres"]["p95_ms"])
        self.assertIn(
            "SLO Postgres direto: p95 200.0 ms (maximo 150.0 ms)",
            result["failures"],
        )

    def test_source_root_is_refused_before_any_fixture(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(PROBE),
                "--root",
                str(ROOT),
                "--project",
                "meu_projeto",
                "--profile",
                "small",
                "--seconds",
                "10",
                "--allow-temporary-fixtures",
                "--host-max-usage",
                os.getenv("PLATFORM_BOTTLENECK_HOST_MAX_USAGE", "75"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(2, result.returncode)
        self.assertIn("recusa o repositorio-fonte", result.stderr)


@unittest.skipUnless(
    env_flag("RUN_PLATFORM_BOTTLENECK"),
    "carga funcional exige RUN_PLATFORM_BOTTLENECK=1",
)
class PlatformBottleneckProbeExecution(unittest.TestCase):
    def test_disposable_platform_survives_functional_load(self) -> None:
        root = os.getenv("PLATFORM_BOTTLENECK_ROOT")
        if not root:
            self.fail(
                "PLATFORM_BOTTLENECK_ROOT precisa apontar para a instalacao descartavel"
            )
        result = subprocess.run(
            [
                sys.executable,
                str(PROBE),
                "--root",
                root,
                "--project",
                os.getenv("PLATFORM_BOTTLENECK_PROJECT", "meu_projeto"),
                "--profile",
                os.getenv("PLATFORM_BOTTLENECK_PROFILE", "small"),
                "--seconds",
                os.getenv("PLATFORM_BOTTLENECK_SECONDS", "30"),
                "--allow-temporary-fixtures",
            ],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        self.assertEqual(0, result.returncode, f"{result.stdout}\n{result.stderr}")


if __name__ == "__main__":
    unittest.main()
