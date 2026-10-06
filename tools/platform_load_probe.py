#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import concurrent.futures
import datetime
import json
import math
import os
import pathlib
import re
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request


SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOAD_PROFILES = {
    "small": {
        "http_workers_per_route": 1,
        "db_workers": 2,
        "series": 20000,
        "rest_rows": 100,
    },
    "medium": {
        "http_workers_per_route": 2,
        "db_workers": 4,
        "series": 60000,
        "rest_rows": 1000,
    },
    "large": {
        "http_workers_per_route": 4,
        "db_workers": 8,
        "series": 120000,
        "rest_rows": 5000,
    },
}
PROJECT_CONTAINER_NAMES = {
    "nginx": "supabase-nginx-{project}",
    "auth": "supabase-auth-{project}",
    "rest": "supabase-rest-{project}",
}


class ProbeError(RuntimeError):
    pass


def run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ProbeError(f"comando ausente: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"timeout executando: {' '.join(args[:3])}") from exc


def parse_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ProbeError(f"nao foi possivel ler {path}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def services_from_helper(root: pathlib.Path) -> dict[str, str]:
    candidates = (
        root / "servidor" / "generateProject" / "lib" / "platform_capacity.sh",
        SOURCE_ROOT / "servidor" / "generateProject" / "lib" / "platform_capacity.sh",
    )
    helper = next((path for path in candidates if path.is_file()), None)
    if helper is None:
        raise ProbeError("platform_capacity.sh nao encontrado")
    source = helper.read_text(encoding="utf-8")
    try:
        block = source.split("PLATFORM_SERVICE_CONTAINER=(", 1)[1].split("\n)", 1)[0]
    except IndexError as exc:
        raise ProbeError("PLATFORM_SERVICE_CONTAINER ausente no calculador") from exc
    mapped = {
        match.group(1): match.group(2)
        for match in re.finditer(r'"([a-z-]+):([^"\n]+)"', block)
    }
    if not mapped:
        raise ProbeError("nenhum servico compartilhado encontrado no calculador")
    mapped["postgres"] = "supabase-db"
    return mapped


def discover_project(
    root: pathlib.Path, requested: str | None
) -> tuple[str, pathlib.Path]:
    projects_root = root / "servidor" / "projects"
    if requested:
        project_dir = projects_root / requested
        if not (project_dir / ".env").is_file():
            raise ProbeError(f"projeto nao encontrado: {requested}")
        return requested, project_dir
    candidates = sorted(
        path.parent for path in projects_root.glob("*/.env") if path.parent.is_dir()
    )
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates) or "nenhum"
        raise ProbeError(f"use --project; projetos encontrados: {names}")
    return candidates[0].name, candidates[0]


def inspect_container(container: str) -> dict | None:
    result = run(["docker", "inspect", container])
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"docker inspect invalido para {container}") from exc
    return payload[0] if payload else None


def path_belongs_to(path: str, root: pathlib.Path) -> bool:
    if not path:
        return False
    resolved = pathlib.Path(path).resolve()
    try:
        return os.path.commonpath((str(resolved), str(root))) == str(root)
    except ValueError:
        return False


def cgroup_path(identifier: str) -> pathlib.Path | None:
    for candidate in (
        pathlib.Path(f"/sys/fs/cgroup/system.slice/docker-{identifier}.scope"),
        pathlib.Path(f"/sys/fs/cgroup/docker/{identifier}"),
    ):
        if (candidate / "memory.stat").is_file():
            return candidate
    return None


def cpu_limit(host_config: dict) -> float:
    nano = int(host_config.get("NanoCpus") or 0)
    if nano > 0:
        return nano / 1_000_000_000
    quota = int(host_config.get("CpuQuota") or 0)
    period = int(host_config.get("CpuPeriod") or 0)
    return quota / period if quota > 0 and period > 0 else 0.0


def build_targets(
    root: pathlib.Path, project: str
) -> tuple[dict[str, dict], list[str]]:
    expected: dict[str, tuple[str, str]] = {
        f"shared/{service}": ("shared", container)
        for service, container in services_from_helper(root).items()
    }
    expected.update(
        {
            f"project/{service}": ("project", pattern.format(project=project))
            for service, pattern in PROJECT_CONTAINER_NAMES.items()
        }
    )
    targets: dict[str, dict] = {}
    missing: list[str] = []
    for name, (scope, container) in expected.items():
        inspect = inspect_container(container)
        if inspect is None or inspect.get("State", {}).get("Running") is not True:
            missing.append(name)
            continue
        labels = inspect.get("Config", {}).get("Labels") or {}
        working_dir = labels.get("com.docker.compose.project.working_dir", "")
        if not path_belongs_to(working_dir, root):
            raise ProbeError(
                f"container {container} nao pertence a {root}; label aponta para {working_dir or 'vazio'}"
            )
        path = cgroup_path(inspect.get("Id", ""))
        if path is None:
            raise ProbeError(f"cgroup nao encontrado para {container}")
        host_config = inspect.get("HostConfig") or {}
        networks = inspect.get("NetworkSettings", {}).get("Networks") or {}
        targets[name] = {
            "scope": scope,
            "service": name.split("/", 1)[1],
            "container": container,
            "container_id": inspect.get("Id", ""),
            "path": path,
            "memory_limit_mib": int(host_config.get("Memory") or 0) / 1048576,
            "cpu_limit": cpu_limit(host_config),
            "pids_limit": max(0, int(host_config.get("PidsLimit") or 0)),
            "ip_addresses": {
                network: values.get("IPAddress", "")
                for network, values in networks.items()
                if values.get("IPAddress")
            },
        }
    required = {f"project/{name}" for name in PROJECT_CONTAINER_NAMES}
    unavailable = sorted(required.difference(targets))
    if unavailable:
        raise ProbeError(f"containers obrigatorios ausentes: {', '.join(unavailable)}")
    return targets, missing


def read_int(path: pathlib.Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def read_cpu_usage(path: pathlib.Path) -> int:
    try:
        lines = (path / "cpu.stat").read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for line in lines:
        key, _, value = line.partition(" ")
        if key == "usage_usec":
            try:
                return int(value)
            except ValueError:
                return 0
    return 0


def read_memory_events(path: pathlib.Path) -> dict[str, int]:
    values: dict[str, int] = {}
    try:
        lines = (path / "memory.events").read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        key, _, raw = line.partition(" ")
        try:
            values[key] = int(raw)
        except ValueError:
            continue
    return values


def read_io(path: pathlib.Path) -> tuple[int, int]:
    read_bytes = 0
    write_bytes = 0
    try:
        lines = (path / "io.stat").read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0, 0
    for line in lines:
        for item in line.split()[1:]:
            key, _, raw = item.partition("=")
            try:
                value = int(raw)
            except ValueError:
                continue
            if key == "rbytes":
                read_bytes += value
            elif key == "wbytes":
                write_bytes += value
    return read_bytes, write_bytes


def state(target: dict) -> dict:
    path = target["path"]
    read_bytes, write_bytes = read_io(path)
    inspect = inspect_container(target["container"]) or {}
    return {
        "memory_mib": read_int(path / "memory.current") / 1048576,
        "memory_peak_mib": read_int(path / "memory.peak") / 1048576,
        "pids": read_int(path / "pids.current"),
        "pids_peak": read_int(path / "pids.peak"),
        "cpu_usec": read_cpu_usage(path),
        "read_bytes": read_bytes,
        "write_bytes": write_bytes,
        "oom_kill": read_memory_events(path).get("oom_kill", 0),
        "restarts": int(inspect.get("RestartCount") or 0),
        "container_changed": (
            inspect.get("Id", "") != target["container_id"]
            or inspect.get("State", {}).get("Running") is not True
        ),
    }


class Monitor:
    def __init__(self, targets: dict[str, dict], interval: float):
        self.targets = targets
        self.interval = interval
        self.stop_event = threading.Event()
        self.samples = {
            name: {
                "memory_mib": [],
                "pids": [],
                "cpu_cores": [],
                "cpu_samples_discarded": 0,
            }
            for name in targets
        }
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(5.0, self.interval * 3))

    def _loop(self) -> None:
        previous = {}
        for name, target in self.targets.items():
            cpu = read_cpu_usage(target["path"])
            previous[name] = (time.monotonic(), cpu)
        while not self.stop_event.wait(self.interval):
            for name, target in self.targets.items():
                path = target["path"]
                memory = read_int(path / "memory.current") / 1048576
                pids = read_int(path / "pids.current")
                cpu = read_cpu_usage(path)
                sampled_at = time.monotonic()
                prior_at, prior_cpu = previous[name]
                elapsed = sampled_at - prior_at
                cores = (
                    max(0.0, (cpu - prior_cpu) / 1_000_000 / elapsed)
                    if elapsed > 0
                    else 0.0
                )
                self.samples[name]["memory_mib"].append(memory)
                self.samples[name]["pids"].append(pids)
                affinity = len(os.sched_getaffinity(0))
                configured = target["cpu_limit"] or affinity
                ceiling = min(configured, affinity) * 1.5
                if cpu < prior_cpu or cores > ceiling:
                    self.samples[name]["cpu_samples_discarded"] += 1
                else:
                    self.samples[name]["cpu_cores"].append(cores)
                previous[name] = (sampled_at, cpu)


def target_ip(targets: dict[str, dict], name: str, network: str) -> str:
    target = targets.get(name)
    if target is None:
        raise ProbeError(f"servico necessario ausente: {name}")
    addresses = target["ip_addresses"]
    address = addresses.get(network) or next(iter(addresses.values()), "")
    if not address:
        raise ProbeError(f"IP Docker ausente para {name}")
    return address


def build_endpoints(
    root: pathlib.Path,
    project_dir: pathlib.Path,
    targets: dict[str, dict],
    fixture_table: str | None = None,
    rest_rows: int = 0,
) -> tuple[list[dict], str]:
    project_env = parse_env(project_dir / ".env")
    external_anon = os.getenv("PLATFORM_LOAD_ANON_KEY", "").strip()
    external_service = os.getenv("PLATFORM_LOAD_SERVICE_KEY", "").strip()
    if bool(external_anon) != bool(external_service):
        raise ProbeError(
            "PLATFORM_LOAD_ANON_KEY e PLATFORM_LOAD_SERVICE_KEY precisam ser informadas juntas"
        )
    if external_anon:
        api_external = project_env.get("API_EXTERNAL_URL", "")
        suffix = "/auth/v1"
        if not api_external.endswith(suffix):
            raise ProbeError("API_EXTERNAL_URL do projeto nao termina em /auth/v1")
        base = api_external[: -len(suffix)].rstrip("/")
        endpoints = [
            {
                "name": "auth",
                "url": f"{base}/auth/v1/settings",
                "headers": {
                    "apikey": external_anon,
                    "Authorization": f"Bearer {external_anon}",
                },
            },
            {
                "name": "rest",
                "url": f"{base}/rest/v1/",
                "headers": {
                    "apikey": external_service,
                    "Authorization": f"Bearer {external_service}",
                },
            },
            {
                "name": "storage",
                "url": f"{base}/storage/v1/bucket",
                "headers": {
                    "apikey": external_service,
                    "Authorization": f"Bearer {external_service}",
                },
            },
            {
                "name": "functions",
                "url": f"{base}/functions/v1/hello",
                "headers": {
                    "apikey": external_anon,
                    "Authorization": f"Bearer {external_anon}",
                },
            },
        ]
        mode = "public"
    else:
        project = project_dir.name
        internal_anon = project_env.get("ANON_KEY_PROJETO", "")
        internal_service = project_env.get("SERVICE_ROLE_KEY_PROJETO", "")
        project_uuid = project_env.get("PROJECT_UUID", "")
        if not internal_anon or not internal_service or not project_uuid:
            raise ProbeError("credenciais internas ou PROJECT_UUID ausentes no projeto")
        auth_ip = target_ip(targets, "project/auth", "rede-supabase")
        rest_ip = target_ip(targets, "project/rest", "rede-supabase")
        nginx_ip = target_ip(targets, "project/nginx", "rede-supabase")
        functions_ip = target_ip(targets, "shared/edge-functions", "rede-supabase")
        storage_ip = target_ip(
            targets, "shared/storage-data-plane", "supabase-storage-gateways"
        )
        rest_path = "/"
        if fixture_table and rest_rows:
            rest_path = (
                f"/{fixture_table}?select=id,payload&order=id.desc&limit={rest_rows}"
            )
        endpoints = [
            {
                "name": "auth",
                "url": f"http://{auth_ip}:9999/admin/users?page=1&per_page=100",
                "headers": {
                    "Authorization": f"Bearer {internal_service}",
                    "apikey": internal_service,
                },
            },
            {
                "name": "rest",
                "url": f"http://{rest_ip}:3000{rest_path}",
                "headers": {
                    "Authorization": f"Bearer {internal_service}",
                    "apikey": internal_service,
                },
            },
            {
                "name": "storage",
                "url": f"http://{storage_ip}:5000/bucket",
                "headers": {
                    "Authorization": f"Bearer {internal_service}",
                    "apikey": internal_service,
                    "X-Forwarded-Host": f"{project_uuid}.storage.internal",
                    "X-Forwarded-Prefix": f"/{project}/storage/v1",
                },
            },
            {
                "name": "functions",
                "url": f"http://{functions_ip}:9000/hello?ref={project}",
                "headers": {"Authorization": f"Bearer {internal_anon}"},
            },
            {
                "name": "gateway",
                "url": f"http://{nginx_ip}:8080/verify-success.html",
                "headers": {},
            },
        ]
        mode = "internal"
    health_specs = (
        ("realtime", "shared/realtime", "rede-supabase", 4000, "/healthcheck", (200,)),
        (
            "analytics",
            "shared/analytics",
            "analytics-internal",
            4000,
            "/health",
            (200,),
        ),
        ("supavisor", "shared/supavisor", "rede-supabase", 4000, "/", (404,)),
        ("vector", "shared/vector", "analytics-internal", 9001, "/health", (200,)),
        (
            "projects-api",
            "shared/projects-api",
            "rede-supabase",
            18000,
            "/healthz",
            (200,),
        ),
        (
            "key-authorizer",
            "shared/key-authorizer",
            "rede-supabase",
            18010,
            "/healthz",
            (200,),
        ),
        (
            "postgres-meta",
            "shared/postgres-meta",
            "rede-supabase",
            8080,
            "/health",
            (200,),
        ),
        (
            "imgproxy",
            "shared/imgproxy",
            "supabase-storage-control",
            5001,
            "/health",
            (200,),
        ),
    )
    for name, target, network, port, path, accepted in health_specs:
        address = target_ip(targets, target, network)
        endpoints.append(
            {
                "name": name,
                "url": f"http://{address}:{port}{path}",
                "headers": {},
                "accepted_statuses": accepted,
            }
        )
    studio_env_path = root / "studio" / ".env"
    if studio_env_path.is_file():
        port = parse_env(studio_env_path).get("STUDIO_HTTPS_PORT", "")
        if port.isdigit():
            endpoints.append(
                {
                    "name": "studio",
                    "url": f"https://127.0.0.1:{port}/",
                    "headers": {},
                }
            )
    return endpoints, mode


def request_once(
    endpoint: dict, context: ssl.SSLContext
) -> tuple[bool, int, float, int]:
    headers = {"Accept": "application/json", "User-Agent": "platform-load-probe/1"}
    headers.update(endpoint["headers"])
    request = urllib.request.Request(endpoint["url"], headers=headers)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=10, context=context) as response:
            response_bytes = len(response.read())
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        response_bytes = len(exc.read(1024))
    except (urllib.error.URLError, OSError, ValueError):
        return False, 0, (time.monotonic() - started) * 1000, 0
    elapsed = (time.monotonic() - started) * 1000
    accepted_statuses = endpoint.get("accepted_statuses")
    if accepted_statuses is not None:
        accepted = status in accepted_statuses
    else:
        accepted = status < 500 if endpoint["name"] == "studio" else 200 <= status < 400
    return accepted, status, elapsed, response_bytes


def http_load(endpoints: list[dict], seconds: int, workers_per_route: int) -> dict:
    deadline = time.monotonic() + seconds
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    def worker(assigned: list[dict]) -> dict[str, dict]:
        local = {
            endpoint["name"]: {
                "requests": 0,
                "success": 0,
                "errors": 0,
                "response_bytes": 0,
                "latencies": [],
                "statuses": {},
            }
            for endpoint in assigned
        }
        index = 0
        while time.monotonic() < deadline:
            endpoint = assigned[index % len(assigned)]
            index += 1
            accepted, status, latency, response_bytes = request_once(endpoint, context)
            values = local[endpoint["name"]]
            values["requests"] += 1
            values["success"] += int(accepted)
            values["errors"] += int(not accepted)
            values["response_bytes"] += response_bytes
            values["latencies"].append(latency)
            key = str(status) if status else "network"
            values["statuses"][key] = values["statuses"].get(key, 0) + 1
        return local

    combined = {
        endpoint["name"]: {
            "requests": 0,
            "success": 0,
            "errors": 0,
            "response_bytes": 0,
            "latencies": [],
            "statuses": {},
        }
        for endpoint in endpoints
    }
    assignments = [
        [endpoint] for endpoint in endpoints for _ in range(workers_per_route)
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(assignments)) as pool:
        for partial in pool.map(worker, assignments):
            for name, values in partial.items():
                target = combined[name]
                target["requests"] += values["requests"]
                target["success"] += values["success"]
                target["errors"] += values["errors"]
                target["response_bytes"] += values["response_bytes"]
                target["latencies"].extend(values["latencies"])
                for status, count in values["statuses"].items():
                    target["statuses"][status] = (
                        target["statuses"].get(status, 0) + count
                    )
    routes: dict[str, dict] = {}
    for name, values in combined.items():
        latencies = sorted(values.pop("latencies"))
        index = max(0, math.ceil(len(latencies) * 0.95) - 1)
        routes[name] = {
            **values,
            "response_mib": round(values["response_bytes"] / 1048576, 2),
            "p95_ms": round(latencies[index], 1) if latencies else 0.0,
        }
    total = sum(values["requests"] for values in routes.values())
    success = sum(values["success"] for values in routes.values())
    errors = sum(values["errors"] for values in routes.values())
    response_bytes = sum(values["response_bytes"] for values in routes.values())
    return {
        "requests": total,
        "success": success,
        "errors": errors,
        "rps": round(total / seconds, 2),
        "response_bytes": response_bytes,
        "response_mib": round(response_bytes / 1048576, 2),
        "response_mib_per_second": round(response_bytes / 1048576 / seconds, 2),
        "routes": routes,
    }


def database_load(database: str, seconds: int, workers: int, series: int) -> dict:
    deadline = time.monotonic() + seconds
    query = (
        "SELECT count(*) FROM (SELECT g, md5(g::text) AS h "
        f"FROM generate_series(1,{series}) g ORDER BY md5(g::text)) t;"
    )

    def worker(_: int) -> tuple[int, int]:
        completed = 0
        errors = 0
        while time.monotonic() < deadline:
            result = run(
                [
                    "docker",
                    "exec",
                    "supabase-db",
                    "psql",
                    "-U",
                    "supabase_admin",
                    "-d",
                    database,
                    "-tAc",
                    query,
                ],
                timeout=max(30, seconds * 2),
            )
            if result.returncode == 0:
                completed += 1
            else:
                errors += 1
                break
        return completed, errors

    completed = 0
    errors = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for worker_completed, worker_errors in pool.map(worker, range(workers)):
            completed += worker_completed
            errors += worker_errors
    return {
        "queries": completed,
        "errors": errors,
        "qps": round(completed / seconds, 2),
        "series_rows": series,
    }


def psql(database: str, query: str, timeout: int = 120) -> str:
    result = run(
        [
            "docker",
            "exec",
            "supabase-db",
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "supabase_admin",
            "-d",
            database,
            "-tAc",
            query,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise ProbeError(result.stderr.strip() or "psql falhou")
    return result.stdout.strip()


def prepare_database_fixture(database: str, rows: int) -> str:
    table = f"_platform_load_probe_{os.getpid()}_{int(time.time())}"
    query = (
        f"CREATE UNLOGGED TABLE public.{table} (id bigint PRIMARY KEY, payload text NOT NULL); "
        f"INSERT INTO public.{table} "
        f"SELECT g, repeat(md5(g::text), 16) FROM generate_series(1, {rows}) g; "
        f"GRANT SELECT ON public.{table} TO anon, authenticated, service_role; "
        f"ANALYZE public.{table}; NOTIFY pgrst, 'reload schema';"
    )
    try:
        psql(database, query)
    except ProbeError:
        try:
            cleanup_database_fixture(database, table)
        except ProbeError:
            pass
        raise
    time.sleep(2)
    return table


def cleanup_database_fixture(database: str, table: str) -> None:
    psql(
        database,
        f"DROP TABLE IF EXISTS public.{table}; NOTIFY pgrst, 'reload schema';",
    )


def ceil_step(value: float, step: int) -> int:
    return int(math.ceil(value / step) * step) if value > 0 else 0


def service_result(
    name: str,
    target: dict,
    before: dict,
    after: dict,
    samples: dict,
    elapsed: float,
    headroom: int,
    max_usage: int,
) -> tuple[dict, list[str]]:
    memory_peak = max(
        samples["memory_mib"] or [before["memory_mib"], after["memory_mib"]]
    )
    pids_peak = max(samples["pids"] or [before["pids"], after["pids"]])
    cpu_average = max(
        0.0, (after["cpu_usec"] - before["cpu_usec"]) / 1_000_000 / elapsed
    )
    cpu_peak = max(samples["cpu_cores"] or [cpu_average])
    memory_limit = target["memory_limit_mib"]
    cpu_configured = target["cpu_limit"]
    pids_limit = target["pids_limit"]
    memory_usage = memory_peak * 100 / memory_limit if memory_limit else 0.0
    cpu_usage = cpu_peak * 100 / cpu_configured if cpu_configured else 0.0
    pids_usage = pids_peak * 100 / pids_limit if pids_limit else 0.0
    factor = 1 + headroom / 100
    recommended_memory = (
        max(16, ceil_step(memory_peak * factor, 16)) if memory_peak else 0
    )
    recommended_cpu = math.ceil(cpu_peak * factor / 0.05) * 0.05 if cpu_peak else 0.0
    recommended_pids = max(64, ceil_step(pids_peak * factor, 16)) if pids_peak else 0
    oom = after["oom_kill"] - before["oom_kill"]
    restarts = after["restarts"] - before["restarts"]
    failures: list[str] = []
    if oom > 0:
        failures.append(f"{name}: {oom} OOM kill(s)")
    if restarts > 0:
        failures.append(f"{name}: {restarts} reinicio(s)")
    if after["container_changed"]:
        failures.append(f"{name}: container substituido ou parado durante a carga")
    if samples["cpu_samples_discarded"]:
        failures.append(
            f"{name}: {samples['cpu_samples_discarded']} amostra(s) de CPU invalida(s) descartada(s)"
        )
    if memory_limit and memory_usage > max_usage:
        failures.append(f"{name}: memoria em {memory_usage:.0f}% do limite")
    if cpu_configured and cpu_usage > max_usage:
        failures.append(f"{name}: CPU em {cpu_usage:.0f}% do limite")
    if pids_limit and pids_usage > max_usage:
        failures.append(f"{name}: PIDs em {pids_usage:.0f}% do limite")
    result = {
        "scope": target["scope"],
        "service": target["service"],
        "container": target["container"],
        "observed": {
            "memory_peak_mib": round(memory_peak, 1),
            "cpu_peak_cores": round(cpu_peak, 3),
            "cpu_average_cores": round(cpu_average, 3),
            "pids_peak": pids_peak,
            "read_mib": round(
                max(0, after["read_bytes"] - before["read_bytes"]) / 1048576, 2
            ),
            "write_mib": round(
                max(0, after["write_bytes"] - before["write_bytes"]) / 1048576, 2
            ),
        },
        "configured": {
            "memory_mib": round(memory_limit, 1),
            "cpu_cores": round(cpu_configured, 3),
            "pids": pids_limit,
        },
        "usage_percent": {
            "memory": round(memory_usage, 1),
            "cpu": round(cpu_usage, 1),
            "pids": round(pids_usage, 1),
        },
        "recommended": {
            "memory_mib": recommended_memory,
            "cpu_cores": round(recommended_cpu, 2),
            "pids": recommended_pids,
        },
        "oom_kill": oom,
        "restarts": restarts,
        "container_changed": after["container_changed"],
        "cpu_samples_discarded": samples["cpu_samples_discarded"],
    }
    return result, failures


def configured_profile(root_env: dict[str, str], profile: str) -> dict:
    prefix = f"PROJECT_RES_{profile.upper()}_"
    return {
        "memory": root_env.get(f"{prefix}MEMORY", ""),
        "cpu": root_env.get(f"{prefix}CPUS", ""),
        "pids": root_env.get(f"{prefix}PIDS", ""),
    }


def recommendations(services: list[dict], scope: str) -> dict:
    selected = [service for service in services if service["scope"] == scope]
    return {
        "memory_mib": sum(service["recommended"]["memory_mib"] for service in selected),
        "cpu_cores": round(
            sum(service["recommended"]["cpu_cores"] for service in selected), 2
        ),
        "services": {
            service["service"]: service["recommended"] for service in selected
        },
    }


def aggregate_runs(profile: str, runs: list[dict]) -> dict:
    result = copy.deepcopy(runs[0])
    result["profile"] = profile
    result["repetitions"] = len(runs)
    result["duration_seconds"] = round(sum(run["duration_seconds"] for run in runs), 2)
    result["http"]["requests"] = sum(run["http"]["requests"] for run in runs)
    result["http"]["success"] = sum(run["http"]["success"] for run in runs)
    result["http"]["errors"] = sum(run["http"]["errors"] for run in runs)
    result["http"]["response_bytes"] = sum(
        run["http"]["response_bytes"] for run in runs
    )
    result["http"]["response_mib"] = round(
        result["http"]["response_bytes"] / 1048576, 2
    )
    http_rates = [run["http"]["rps"] for run in runs]
    byte_rates = [run["http"]["response_mib_per_second"] for run in runs]
    result["http"]["rps"] = min(http_rates)
    result["http"]["rps_average"] = round(sum(http_rates) / len(http_rates), 2)
    result["http"]["response_mib_per_second"] = min(byte_rates)
    result["http"]["response_mib_per_second_average"] = round(
        sum(byte_rates) / len(byte_rates), 2
    )
    route_names = {name for run in runs for name in run["http"]["routes"]}
    result["http"]["routes"] = {}
    for name in sorted(route_names):
        routes = [run["http"]["routes"][name] for run in runs]
        statuses: dict[str, int] = {}
        for route in routes:
            for status, count in route["statuses"].items():
                statuses[status] = statuses.get(status, 0) + count
        result["http"]["routes"][name] = {
            "requests": sum(route["requests"] for route in routes),
            "success": sum(route["success"] for route in routes),
            "errors": sum(route["errors"] for route in routes),
            "response_bytes": sum(route["response_bytes"] for route in routes),
            "response_mib": round(
                sum(route["response_bytes"] for route in routes) / 1048576, 2
            ),
            "statuses": statuses,
            "p95_ms": max(route["p95_ms"] for route in routes),
        }
    result["database"]["queries"] = sum(run["database"]["queries"] for run in runs)
    result["database"]["errors"] = sum(run["database"]["errors"] for run in runs)
    database_rates = [run["database"]["qps"] for run in runs]
    result["database"]["qps"] = min(database_rates)
    result["database"]["qps_average"] = round(
        sum(database_rates) / len(database_rates), 2
    )
    services_by_name = {service["container"]: service for service in result["services"]}
    for container, service in services_by_name.items():
        candidates = [
            candidate
            for run in runs
            for candidate in run["services"]
            if candidate["container"] == container
        ]
        for metric in (
            "memory_peak_mib",
            "cpu_peak_cores",
            "cpu_average_cores",
            "pids_peak",
            "read_mib",
            "write_mib",
        ):
            service["observed"][metric] = max(
                candidate["observed"][metric] for candidate in candidates
            )
        for metric in ("memory", "cpu", "pids"):
            service["usage_percent"][metric] = max(
                candidate["usage_percent"][metric] for candidate in candidates
            )
        for metric in ("memory_mib", "cpu_cores", "pids"):
            service["recommended"][metric] = max(
                candidate["recommended"][metric] for candidate in candidates
            )
        service["oom_kill"] = sum(candidate["oom_kill"] for candidate in candidates)
        service["restarts"] = sum(candidate["restarts"] for candidate in candidates)
        service["container_changed"] = any(
            candidate["container_changed"] for candidate in candidates
        )
        service["cpu_samples_discarded"] = sum(
            candidate["cpu_samples_discarded"] for candidate in candidates
        )
    result["project_recommendation"] = recommendations(result["services"], "project")
    result["shared_recommendation"] = recommendations(result["services"], "shared")
    result["failures"] = list(
        dict.fromkeys(failure for run in runs for failure in run["failures"])
    )
    result["runs"] = runs
    return result


def run_profile(
    profile: str,
    root: pathlib.Path,
    project_dir: pathlib.Path,
    targets: dict[str, dict],
    seconds: int,
    workers_override: int | None,
    db_workers_override: int | None,
    sample_interval: float,
    headroom: int,
    max_usage: int,
    fixture_table: str | None,
) -> dict:
    settings = LOAD_PROFILES[profile]
    http_workers_per_route = workers_override or settings["http_workers_per_route"]
    db_workers = db_workers_override or settings["db_workers"]
    project_env = parse_env(project_dir / ".env")
    database = project_env.get("POSTGRES_DATABASE", "")
    if not database:
        raise ProbeError("POSTGRES_DATABASE ausente no projeto")
    endpoints, endpoint_mode = build_endpoints(
        root,
        project_dir,
        targets,
        fixture_table,
        settings["rest_rows"],
    )
    before = {name: state(target) for name, target in targets.items()}
    monitor = Monitor(targets, sample_interval)
    started = time.monotonic()
    monitor.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            http_future = pool.submit(
                http_load, endpoints, seconds, http_workers_per_route
            )
            database_future = pool.submit(
                database_load,
                database,
                seconds,
                db_workers,
                settings["series"],
            )
            http_result = http_future.result()
            database_result = database_future.result()
    finally:
        monitor.stop()
    elapsed = max(0.001, time.monotonic() - started)
    after = {name: state(target) for name, target in targets.items()}
    rows: list[dict] = []
    failures: list[str] = []
    for name, target in sorted(targets.items()):
        row, row_failures = service_result(
            name,
            target,
            before[name],
            after[name],
            monitor.samples[name],
            elapsed,
            headroom,
            max_usage,
        )
        rows.append(row)
        failures.extend(row_failures)
    if http_result["errors"]:
        failures.append(f"HTTP: {http_result['errors']} erro(s)")
    if database_result["errors"]:
        failures.append(f"Postgres: {database_result['errors']} erro(s)")
    if http_result["success"] == 0:
        failures.append("HTTP: nenhuma requisicao bem-sucedida")
    if database_result["queries"] == 0:
        failures.append("Postgres: nenhuma consulta concluida")
    return {
        "profile": profile,
        "duration_seconds": round(elapsed, 2),
        "workload": {
            "http_workers_per_route": http_workers_per_route,
            "http_workers_total": http_workers_per_route * len(endpoints),
            "db_workers": db_workers,
            "series_rows": settings["series"],
            "rest_rows": settings["rest_rows"],
        },
        "http": http_result,
        "database": database_result,
        "services": rows,
        "project_recommendation": recommendations(rows, "project"),
        "shared_recommendation": recommendations(rows, "shared"),
        "failures": failures,
        "endpoint_mode": endpoint_mode,
    }


def wait_running(containers: list[str], timeout: int = 90) -> None:
    deadline = time.monotonic() + timeout
    pending = set(containers)
    while pending and time.monotonic() < deadline:
        ready: set[str] = set()
        for container in pending:
            inspect = inspect_container(container) or {}
            state_data = inspect.get("State") or {}
            health = (state_data.get("Health") or {}).get("Status")
            if state_data.get("Running") and health in (None, "healthy"):
                ready.add(container)
        pending.difference_update(ready)
        if pending:
            time.sleep(2)
    if pending:
        raise ProbeError(
            f"containers nao ficaram prontos: {', '.join(sorted(pending))}"
        )


def restart_targets(targets: dict[str, dict]) -> None:
    containers = [target["container"] for target in targets.values()]
    result = run(["docker", "restart", *containers], timeout=180)
    if result.returncode != 0:
        raise ProbeError(result.stderr.strip() or "falha ao reiniciar containers")
    wait_running(containers)


def print_report(report: dict) -> None:
    print(f"Ambiente: {report['root']}")
    print(
        f"Projeto: {report['project']} (configurado como {report['project_configured_profile']})"
    )
    if report["missing_services"]:
        print(f"Servicos ausentes: {', '.join(report['missing_services'])}")
    for profile in report["profiles"]:
        print()
        print(
            f"Perfil {profile['profile']} ({profile['repetitions']} rodada(s)): "
            f"{profile['http']['rps']} req/s, "
            f"{profile['http']['response_mib_per_second']} MiB/s, "
            f"{profile['database']['qps']} query/s, endpoints {profile['endpoint_mode']}, "
            f"{len(profile['failures'])} alerta(s)"
        )
        print(
            f"{'ESCOPO/SERVICO':30} {'RAM pico/limite':>19} {'CPU pico/limite':>19} "
            f"{'PIDs pico/limite':>19} {'RECOMENDADO RAM/CPU/PIDs':>29}"
        )
        print("-" * 122)
        for service in profile["services"]:
            observed = service["observed"]
            configured = service["configured"]
            recommended = service["recommended"]
            label = f"{service['scope']}/{service['service']}"
            print(
                f"{label:30} "
                f"{observed['memory_peak_mib']:7.1f}/{configured['memory_mib']:<7.1f} "
                f"{observed['cpu_peak_cores']:7.2f}/{configured['cpu_cores']:<7.2f} "
                f"{observed['pids_peak']:7}/{configured['pids']:<7} "
                f"{recommended['memory_mib']:7} MiB/{recommended['cpu_cores']:.2f}/{recommended['pids']}"
            )
        project = profile["project_recommendation"]
        shared = profile["shared_recommendation"]
        print(
            f"Projeto recomendado: {project['memory_mib']} MiB, {project['cpu_cores']:.2f} CPU; "
            f"compartilhados: {shared['memory_mib']} MiB, {shared['cpu_cores']:.2f} CPU"
        )
        configured = profile["configured_profile"]
        print(
            f"Perfil atual no .env raiz: RAM={configured['memory'] or '-'}, "
            f"CPU={configured['cpu'] or '-'}, PIDs={configured['pids'] or '-'}"
        )
        for failure in profile["failures"]:
            print(f"ALERTA: {failure}")


def capacity_profiles(results: list[dict]) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for result in results:
        project = result["project_recommendation"]
        shared = result["shared_recommendation"]
        profiles[result["profile"]] = {
            "workload": result["workload"],
            "project": project,
            "shared": shared,
            "combined": {
                "memory_mib": project["memory_mib"] + shared["memory_mib"],
                "cpu_cores": round(project["cpu_cores"] + shared["cpu_cores"], 2),
            },
        }
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mede projetos small, medium e large e os servicos compartilhados."
    )
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--project")
    parser.add_argument(
        "--profile", choices=("small", "medium", "large", "all"), default="all"
    )
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--workers", type=int)
    parser.add_argument("--db-workers", type=int)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--headroom", type=int, default=30)
    parser.add_argument("--max-usage", type=int, default=80)
    parser.add_argument("--cooldown", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--prepare-fixture", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        if args.seconds < 5:
            raise ProbeError("--seconds precisa ser >= 5")
        if args.workers is not None and args.workers < 1:
            raise ProbeError("--workers precisa ser >= 1")
        if args.db_workers is not None and args.db_workers < 1:
            raise ProbeError("--db-workers precisa ser >= 1")
        if not 0.1 <= args.sample_interval <= 5:
            raise ProbeError("--sample-interval precisa estar entre 0.1 e 5")
        if not 0 <= args.headroom <= 200:
            raise ProbeError("--headroom precisa estar entre 0 e 200")
        if not 1 <= args.max_usage <= 100:
            raise ProbeError("--max-usage precisa estar entre 1 e 100")
        if not 1 <= args.repetitions <= 10:
            raise ProbeError("--repetitions precisa estar entre 1 e 10")
        project, project_dir = discover_project(root, args.project)
        targets, missing = build_targets(root, project)
        if args.restart:
            restart_targets(targets)
        root_env = parse_env(root / "servidor" / ".env")
        project_env = parse_env(project_dir / ".env")
        profiles = list(LOAD_PROFILES) if args.profile == "all" else [args.profile]
        database = project_env.get("POSTGRES_DATABASE", "")
        fixture_table = None
        if args.prepare_fixture:
            if not database:
                raise ProbeError("POSTGRES_DATABASE ausente no projeto")
            fixture_table = prepare_database_fixture(
                database,
                max(LOAD_PROFILES[profile]["rest_rows"] for profile in profiles),
            )
        try:
            results = []
            completed_runs = 0
            for profile in profiles:
                runs = []
                for repetition in range(args.repetitions):
                    if completed_runs and args.cooldown:
                        time.sleep(args.cooldown)
                    run_result = run_profile(
                        profile,
                        root,
                        project_dir,
                        targets,
                        args.seconds,
                        args.workers,
                        args.db_workers,
                        args.sample_interval,
                        args.headroom,
                        args.max_usage,
                        fixture_table,
                    )
                    run_result["run_number"] = repetition + 1
                    runs.append(run_result)
                    completed_runs += 1
                result = aggregate_runs(profile, runs)
                result["configured_profile"] = configured_profile(root_env, profile)
                results.append(result)
        finally:
            if fixture_table:
                cleanup_database_fixture(database, fixture_table)
        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "root": str(root),
            "project": project,
            "project_configured_profile": project_env.get(
                "PROJECT_RESOURCE_PROFILE", "unknown"
            ),
            "headroom_percent": args.headroom,
            "max_usage_percent": args.max_usage,
            "missing_services": missing,
            "capacity_profiles": capacity_profiles(results),
            "profiles": results,
        }
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        if args.json:
            print(rendered)
        else:
            print_report(report)
        return 1 if any(profile["failures"] for profile in results) else 0
    except (OSError, ProbeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
