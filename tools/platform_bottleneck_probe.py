#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import copy
import concurrent.futures
import datetime
import fcntl
import hashlib
import hmac
import json
import math
import os
import pathlib
import re
import secrets
import socket
import ssl
import struct
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib

import platform_load_probe as probe


SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1]
INFRASTRUCTURE_CONTAINERS = {
    "traefik": "traefik-traefik-1",
    "geoip": "traefik-geoip-api-1",
    "traefik-config": "supabase-traefik-config-watcher",
    "deny-service": "traefik-deny-service",
}
BOTTLENECK_PROFILES = {
    "small": {
        "http_workers_per_route": 1,
        "postgres_workers": 2,
        "pooler_workers": 2,
        "storage_workers": 1,
        "storage_bytes": 65536,
        "realtime_workers": 2,
        "series": 20000,
        "rest_rows": 100,
        "image_width": 256,
        "analytics_bytes": 1024,
    },
    "medium": {
        "http_workers_per_route": 2,
        "postgres_workers": 4,
        "pooler_workers": 4,
        "storage_workers": 2,
        "storage_bytes": 262144,
        "realtime_workers": 8,
        "series": 60000,
        "rest_rows": 1000,
        "image_width": 512,
        "analytics_bytes": 4096,
    },
    "large": {
        "http_workers_per_route": 4,
        "postgres_workers": 8,
        "pooler_workers": 8,
        "storage_workers": 4,
        "storage_bytes": 1048576,
        "realtime_workers": 24,
        "series": 120000,
        "rest_rows": 5000,
        "image_width": 1024,
        "analytics_bytes": 16384,
    },
}


def acquire_probe_lock(root: pathlib.Path, project: str):
    digest = hashlib.sha256(f"{root}|{project}".encode()).hexdigest()[:16]
    path = pathlib.Path("/tmp") / f"platform-bottleneck-{digest}.lock"
    handle = path.open("w", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise probe.ProbeError(
            f"ja existe um probe de gargalo para o projeto {project}"
        ) from exc
    return handle


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * ratio) - 1)
    return round(ordered[index], 1)


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def add_infrastructure_targets(
    root: pathlib.Path, targets: dict[str, dict]
) -> list[str]:
    missing: list[str] = []
    for service, container in INFRASTRUCTURE_CONTAINERS.items():
        name = f"shared/{service}"
        inspected = probe.inspect_container(container)
        if inspected is None or inspected.get("State", {}).get("Running") is not True:
            missing.append(name)
            continue
        labels = inspected.get("Config", {}).get("Labels") or {}
        working_dir = labels.get("com.docker.compose.project.working_dir", "")
        if not probe.path_belongs_to(working_dir, root):
            raise probe.ProbeError(
                f"container {container} nao pertence a {root}; label aponta para {working_dir or 'vazio'}"
            )
        path = probe.cgroup_path(inspected.get("Id", ""))
        if path is None:
            raise probe.ProbeError(f"cgroup nao encontrado para {container}")
        host_config = inspected.get("HostConfig") or {}
        networks = inspected.get("NetworkSettings", {}).get("Networks") or {}
        targets[name] = {
            "scope": "shared",
            "service": service,
            "container": container,
            "container_id": inspected.get("Id", ""),
            "path": path,
            "memory_limit_mib": int(host_config.get("Memory") or 0) / 1048576,
            "cpu_limit": probe.cpu_limit(host_config),
            "pids_limit": max(0, int(host_config.get("PidsLimit") or 0)),
            "ip_addresses": {
                network: values.get("IPAddress", "")
                for network, values in networks.items()
                if values.get("IPAddress")
            },
        }
    return missing


def control_psql(query: str, timeout: int = 120) -> str:
    result = probe.run(
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
            "postgres",
            "-tAc",
            query,
        ],
        timeout=timeout,
    )
    if result.returncode != 0:
        raise probe.ProbeError(result.stderr.strip() or "psql do control plane falhou")
    return result.stdout.strip()


def opaque_checksum(project_id: uuid.UUID, prefix: str, random_text: str) -> str:
    material = f"{project_id}|{prefix}{random_text}".encode("ascii")
    return (
        base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        .decode("ascii")
        .rstrip("=")[:8]
    )


def prepare_opaque_key(project: str, kind: str) -> dict[str, str]:
    if kind not in {"publishable", "secret"}:
        raise probe.ProbeError("tipo de chave opaca invalido")
    row = control_psql(
        "SELECT id::text || '|' || (opaque_keys_activated_at IS NOT NULL)::int "
        f"FROM projects WHERE name = {sql_literal(project)};"
    )
    if not row:
        raise probe.ProbeError("projeto ausente no control plane")
    raw_id, active = row.split("|", 1)
    if active != "1":
        raise probe.ProbeError("projeto ainda nao ativou chaves opacas")
    project_id = uuid.UUID(raw_id)
    prefix = f"sb_{kind}_"
    random_text = (
        base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    )
    checksum = opaque_checksum(project_id, prefix, random_text)
    token = f"{prefix}{random_text}_{checksum}"
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    slot_id = str(uuid.uuid4())
    key_id = str(uuid.uuid4())
    slot_name = f"load-{kind[:3]}-{slot_id[:8]}"
    hint = f"{prefix}{random_text[:6]}...{checksum[-4:]}"
    control_psql(
        "BEGIN; "
        "INSERT INTO project_api_key_slots "
        "(id, project_id, name, kind, allowed_services, automatic_rotation_enabled, "
        "rotation_interval_days, status) VALUES "
        f"({sql_literal(slot_id)}::uuid, {sql_literal(str(project_id))}::uuid, "
        f"{sql_literal(slot_name)}, {sql_literal(kind)}, "
        "ARRAY['auth','rest','graphql','realtime','storage','functions']::text[], "
        "false, NULL, 'active'); "
        "INSERT INTO project_api_keys "
        "(id, slot_id, secret_hash, token_hint, status, activated_at, rotation_trigger) VALUES "
        f"({sql_literal(key_id)}::uuid, {sql_literal(slot_id)}::uuid, "
        f"decode({sql_literal(digest)}, 'hex'), {sql_literal(hint)}, "
        "'active', now(), 'manual'); COMMIT;"
    )
    return {"slot_id": slot_id, "key_id": key_id, "token": token}


def cleanup_opaque_key(slot_id: str) -> None:
    control_psql(
        f"DELETE FROM project_api_key_slots WHERE id = {sql_literal(slot_id)}::uuid;"
    )


def encrypt_pg_meta_uri(uri: str, passphrase: str) -> str:
    try:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise probe.ProbeError("dependencia cryptography ausente") from exc
    salt = os.urandom(8)
    data = passphrase.encode("utf-8") + salt
    key_iv = b""
    previous = b""
    while len(key_iv) < 48:
        previous = hashlib.md5(previous + data).digest()
        key_iv += previous
    pad_length = 16 - len(uri.encode("utf-8")) % 16
    padded = uri.encode("utf-8") + bytes([pad_length] * pad_length)
    encryptor = Cipher(
        algorithms.AES(key_iv[:32]),
        modes.CBC(key_iv[32:48]),
        backend=default_backend(),
    ).encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + encrypted).decode("ascii")


def internal_hmac_headers(secret: str, method: str, target: str) -> dict[str, str]:
    timestamp = int(time.time())
    nonce = secrets.token_hex(16)
    body_hash = hashlib.sha256(b"").hexdigest()
    canonical = "\n".join(
        (
            "internal-hmac-v1",
            "studio-nginx",
            method.upper(),
            target,
            str(timestamp),
            nonce,
            body_hash,
        )
    )
    signature = hmac.new(
        secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return {
        "X-Internal-Version": "internal-hmac-v1",
        "X-Internal-Service": "studio-nginx",
        "X-Internal-Timestamp": str(timestamp),
        "X-Internal-Nonce": nonce,
        "X-Internal-Signature": signature,
    }


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def generate_png(width: int, height: int) -> bytes:
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(
                ((x * 17 + y * 3) % 256, (x * 7 + y * 13) % 256, (x + y * 19) % 256)
            )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + png_chunk(b"IEND", b"")
    )


def safe_error_detail(payload: bytes) -> str:
    value = payload[:500].decode("utf-8", errors="replace").strip()
    value = re.sub(r"sb_(?:publishable|secret)_[A-Za-z0-9_-]+", "[REDACTED]", value)
    value = re.sub(
        r"\beyJ[A-Za-z0-9_-]+[.]eyJ[A-Za-z0-9_-]+[.][A-Za-z0-9_-]+\b",
        "[REDACTED]",
        value,
    )
    return value.replace("\n", " ")[:500]


def http_request(endpoint: dict, context: ssl.SSLContext) -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "platform-capacity-client/1",
    }
    headers.update(endpoint.get("headers") or {})
    factory = endpoint.get("header_factory")
    if factory:
        headers.update(factory())
    body = endpoint.get("body")
    request = urllib.request.Request(
        endpoint["url"],
        data=body,
        headers=headers,
        method=endpoint.get("method", "GET"),
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(
            request,
            timeout=endpoint.get("timeout", 15),
            context=context,
        ) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read(4096)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        result = {
            "ok": False,
            "status": 0,
            "latency_ms": (time.monotonic() - started) * 1000,
            "bytes": 0,
            "error": type(exc).__name__,
        }
        if endpoint.get("capture_payload"):
            result["payload"] = b""
        return result
    accepted = endpoint.get("accepted_statuses")
    ok = status in accepted if accepted is not None else 200 <= status < 300
    detail = safe_error_detail(payload) if not ok else ""
    result = {
        "ok": ok,
        "status": status,
        "latency_ms": (time.monotonic() - started) * 1000,
        "bytes": len(payload),
        "error": "" if ok else f"HTTP {status}: {detail}".rstrip(": "),
    }
    if endpoint.get("capture_payload"):
        result["payload"] = payload
    return result


def http_load(endpoints: list[dict], seconds: int, workers_per_route: int) -> dict:
    deadline = time.monotonic() + seconds
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    def worker(endpoint: dict) -> tuple[str, dict]:
        values = {
            "operations": 0,
            "success": 0,
            "errors": 0,
            "bytes": 0,
            "latencies": [],
            "statuses": {},
            "last_error": "",
        }
        while time.monotonic() < deadline:
            result = http_request(endpoint, context)
            values["operations"] += 1
            values["success"] += int(result["ok"])
            values["errors"] += int(not result["ok"])
            values["bytes"] += result["bytes"]
            values["latencies"].append(result["latency_ms"])
            status = str(result["status"]) if result["status"] else "network"
            values["statuses"][status] = values["statuses"].get(status, 0) + 1
            if result["error"]:
                values["last_error"] = result["error"]
        return endpoint["name"], values

    combined: dict[str, dict] = {}
    assignments = [endpoint for endpoint in endpoints for _ in range(workers_per_route)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(assignments)) as pool:
        for name, values in pool.map(worker, assignments):
            target = combined.setdefault(
                name,
                {
                    "operations": 0,
                    "success": 0,
                    "errors": 0,
                    "bytes": 0,
                    "latencies": [],
                    "statuses": {},
                    "last_error": "",
                },
            )
            for key in ("operations", "success", "errors", "bytes"):
                target[key] += values[key]
            target["latencies"].extend(values["latencies"])
            target["last_error"] = values["last_error"] or target["last_error"]
            for status, count in values["statuses"].items():
                target["statuses"][status] = target["statuses"].get(status, 0) + count
    routes: dict[str, dict] = {}
    for name, values in sorted(combined.items()):
        latencies = values.pop("latencies")
        routes[name] = {
            **values,
            "mib": round(values["bytes"] / 1048576, 2),
            "ops_per_second": round(values["operations"] / seconds, 2),
            "p50_ms": percentile(latencies, 0.5),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
        }
    return summarize_routes(routes, seconds)


def summarize_routes(routes: dict[str, dict], seconds: int) -> dict:
    operations = sum(values["operations"] for values in routes.values())
    success = sum(values["success"] for values in routes.values())
    errors = sum(values["errors"] for values in routes.values())
    total_bytes = sum(values["bytes"] for values in routes.values())
    return {
        "operations": operations,
        "success": success,
        "errors": errors,
        "ops_per_second": round(operations / seconds, 2),
        "mib": round(total_bytes / 1048576, 2),
        "mib_per_second": round(total_bytes / 1048576 / seconds, 2),
        "routes": routes,
    }


def database_load(
    database: str,
    seconds: int,
    workers: int,
    series: int,
    connection: dict[str, str] | None = None,
) -> dict:
    deadline = time.monotonic() + seconds
    query = (
        "SELECT count(*) FROM (SELECT g, md5(g::text) AS h "
        f"FROM generate_series(1,{series}) g ORDER BY md5(g::text)) q;"
    )

    def worker(_: int) -> tuple[int, int, list[float], str]:
        completed = 0
        errors = 0
        latencies: list[float] = []
        last_error = ""
        while time.monotonic() < deadline:
            command = ["docker", "exec"]
            if connection:
                command.extend(["-e", f"PGPASSWORD={connection['password']}"])
            command.extend(["supabase-db", "psql"])
            if connection:
                command.extend(
                    [
                        "-h",
                        connection["host"],
                        "-p",
                        connection["port"],
                        "-U",
                        connection["user"],
                    ]
                )
            else:
                command.extend(["-U", "supabase_admin"])
            command.extend(["-d", database, "-v", "ON_ERROR_STOP=1", "-tAc", query])
            started = time.monotonic()
            result = probe.run(command, timeout=max(30, seconds * 2))
            latencies.append((time.monotonic() - started) * 1000)
            if result.returncode == 0:
                completed += 1
            else:
                errors += 1
                last_error = (result.stderr.strip() or "psql falhou")[-500:]
                break
        return completed, errors, latencies, last_error

    completed = 0
    errors = 0
    latencies: list[float] = []
    last_error = ""
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for count, failures, samples, error in pool.map(worker, range(workers)):
            completed += count
            errors += failures
            latencies.extend(samples)
            last_error = error or last_error
    return {
        "queries": completed,
        "errors": errors,
        "qps": round(completed / seconds, 2),
        "p50_ms": percentile(latencies, 0.5),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "series_rows": series,
        "last_error": last_error,
    }


def storage_load(
    base: str,
    key: str,
    bucket: str,
    seconds: int,
    workers: int,
    payload_size: int,
) -> dict:
    deadline = time.monotonic() + seconds
    context = ssl.create_default_context()
    payload = secrets.token_bytes(payload_size)
    key_headers = {"apikey": key, "Authorization": f"Bearer {key}"}

    def worker(index: int) -> tuple[str, dict]:
        object_name = f"blob-{index}.bin"
        upload = {
            "name": "storage-upload",
            "url": f"{base}/storage/v1/object/{bucket}/{object_name}",
            "method": "POST",
            "headers": {
                **key_headers,
                "Content-Type": "application/octet-stream",
                "x-upsert": "true",
            },
            "body": payload,
            "accepted_statuses": (200, 201),
        }
        download = {
            "name": "storage-download",
            "url": f"{base}/storage/v1/object/authenticated/{bucket}/{object_name}",
            "headers": key_headers,
            "accepted_statuses": (200,),
        }
        values = {
            "operations": 0,
            "success": 0,
            "errors": 0,
            "bytes": 0,
            "latencies": [],
            "statuses": {},
            "last_error": "",
        }
        routes: dict[str, dict] = {}
        index_operation = 0
        while time.monotonic() < deadline:
            endpoint = upload if index_operation % 2 == 0 else download
            index_operation += 1
            result = http_request(endpoint, context)
            route = routes.setdefault(
                endpoint["name"],
                {
                    "operations": 0,
                    "success": 0,
                    "errors": 0,
                    "bytes": 0,
                    "latencies": [],
                    "statuses": {},
                    "last_error": "",
                },
            )
            for target in (values, route):
                target["operations"] += 1
                target["success"] += int(result["ok"])
                target["errors"] += int(not result["ok"])
                target["bytes"] += result["bytes"]
                target["latencies"].append(result["latency_ms"])
                status = str(result["status"]) if result["status"] else "network"
                target["statuses"][status] = target["statuses"].get(status, 0) + 1
                if result["error"]:
                    target["last_error"] = result["error"]
        return object_name, {"total": values, "routes": routes}

    partials: list[tuple[str, dict]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        partials.extend(pool.map(worker, range(workers)))
    routes: dict[str, dict] = {}
    objects: list[str] = []
    for object_name, partial in partials:
        objects.append(object_name)
        for name, values in partial["routes"].items():
            target = routes.setdefault(
                name,
                {
                    "operations": 0,
                    "success": 0,
                    "errors": 0,
                    "bytes": 0,
                    "latencies": [],
                    "statuses": {},
                    "last_error": "",
                },
            )
            for metric in ("operations", "success", "errors", "bytes"):
                target[metric] += values[metric]
            target["latencies"].extend(values["latencies"])
            target["last_error"] = values["last_error"] or target["last_error"]
            for status, count in values["statuses"].items():
                target["statuses"][status] = target["statuses"].get(status, 0) + count
    rendered: dict[str, dict] = {}
    for name, values in routes.items():
        latencies = values.pop("latencies")
        rendered[name] = {
            **values,
            "mib": round(values["bytes"] / 1048576, 2),
            "ops_per_second": round(values["operations"] / seconds, 2),
            "p50_ms": percentile(latencies, 0.5),
            "p95_ms": percentile(latencies, 0.95),
            "p99_ms": percentile(latencies, 0.99),
        }
    result = summarize_routes(rendered, seconds)
    result["object_names"] = objects
    result["payload_bytes"] = payload_size
    return result


def realtime_worker(
    url: str,
    headers: dict[str, str],
    origin: str,
    seconds: int,
    worker_id: int,
    socket_target: tuple[str, int] | None = None,
) -> dict:
    try:
        from websockets.sync.client import connect
    except ImportError as exc:
        return {
            "connections": 0,
            "joins": 0,
            "messages": 0,
            "errors": 1,
            "latencies": [],
            "last_error": f"dependencia websockets ausente: {exc}",
        }
    deadline = time.monotonic() + seconds
    result = {
        "connections": 0,
        "joins": 0,
        "messages": 0,
        "errors": 0,
        "latencies": [],
        "last_error": "",
    }
    topic = f"realtime:load-{worker_id}"
    connected_socket = None
    websocket = None

    def receive_matching(events: set[str], timeout: float) -> dict:
        receive_deadline = time.monotonic() + timeout
        while True:
            remaining = receive_deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Realtime sem resposta {','.join(sorted(events))}")
            received = json.loads(websocket.recv(timeout=remaining))
            if received.get("event") in events:
                return received

    try:
        connected_socket = (
            socket.create_connection(socket_target, timeout=10)
            if socket_target
            else None
        )
        websocket = connect(
            url,
            sock=connected_socket,
            additional_headers=headers,
            origin=origin,
            user_agent_header="platform-capacity-client/1",
            proxy=None,
            open_timeout=10,
            close_timeout=3,
            ping_interval=None,
        )
        result["connections"] = 1
        join = {
            "topic": topic,
            "event": "phx_join",
            "payload": {
                "config": {
                    "broadcast": {"self": False, "ack": True},
                    "presence": {"key": f"load-{worker_id}"},
                    "postgres_changes": [],
                }
            },
            "ref": "1",
            "join_ref": "1",
        }
        websocket.send(json.dumps(join, separators=(",", ":")))
        joined = receive_matching({"phx_reply"}, 10)
        if (
            joined.get("event") != "phx_reply"
            or joined.get("payload", {}).get("status") != "ok"
        ):
            raise RuntimeError(f"join recusado: {joined.get('event', 'desconhecido')}")
        result["joins"] = 1
        reference = 2
        while time.monotonic() < deadline:
            payload = {
                "topic": topic,
                "event": "broadcast",
                "payload": {
                    "type": "load",
                    "event": "load",
                    "payload": {"worker": worker_id, "sequence": reference},
                },
                "ref": str(reference),
                "join_ref": "1",
            }
            started = time.monotonic()
            websocket.send(json.dumps(payload, separators=(",", ":")))
            received = receive_matching({"phx_reply"}, 10)
            result["latencies"].append((time.monotonic() - started) * 1000)
            if received.get("event") not in {"phx_reply", "broadcast"}:
                raise RuntimeError("resposta Realtime inesperada")
            result["messages"] += 1
            reference += 1
    except Exception as exc:
        result["errors"] += 1
        response = getattr(exc, "response", None)
        body = getattr(response, "body", b"") if response is not None else b""
        detail = safe_error_detail(body) if isinstance(body, bytes) else ""
        suffix = f": {detail}" if detail else ""
        result["last_error"] = f"{type(exc).__name__}: {exc}{suffix}"[-500:]
    finally:
        if websocket is not None:
            websocket.close_socket()
        elif connected_socket is not None:
            connected_socket.close()
    return result


def realtime_load(
    url: str,
    headers: dict[str, str],
    origin: str,
    seconds: int,
    workers: int,
    socket_target: tuple[str, int] | None = None,
) -> dict:
    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                realtime_worker,
                url,
                headers,
                origin,
                seconds,
                worker,
                socket_target,
            )
            for worker in range(workers)
        ]
        for future in futures:
            results.append(future.result())
    latencies = [latency for result in results for latency in result["latencies"]]
    return {
        "connections": sum(result["connections"] for result in results),
        "joins": sum(result["joins"] for result in results),
        "messages": sum(result["messages"] for result in results),
        "errors": sum(result["errors"] for result in results),
        "messages_per_second": round(
            sum(result["messages"] for result in results) / seconds, 2
        ),
        "p50_ms": percentile(latencies, 0.5),
        "p95_ms": percentile(latencies, 0.95),
        "p99_ms": percentile(latencies, 0.99),
        "last_errors": [
            result["last_error"] for result in results if result["last_error"]
        ][:5],
    }


def read_host_cpu() -> tuple[int, int]:
    fields = (
        pathlib.Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0].split()
    )
    values = [int(value) for value in fields[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def read_host_memory() -> tuple[float, float]:
    values: dict[str, int] = {}
    for line in pathlib.Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, raw = line.split(":", 1)
        values[name] = int(raw.strip().split()[0])
    total = values.get("MemTotal", 0) / 1024
    available = values.get("MemAvailable", 0) / 1024
    return total, max(0.0, total - available)


class HostMonitor:
    def __init__(self, interval: float):
        self.interval = interval
        self.stop_event = threading.Event()
        self.cpu_percent: list[float] = []
        self.memory_used_mib: list[float] = []
        self.load_average: list[float] = []
        self.thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=max(5.0, self.interval * 3))

    def _loop(self) -> None:
        previous_total, previous_idle = read_host_cpu()
        while not self.stop_event.wait(self.interval):
            total, idle = read_host_cpu()
            total_delta = total - previous_total
            idle_delta = idle - previous_idle
            if total_delta > 0:
                self.cpu_percent.append(
                    max(0.0, min(100.0, (total_delta - idle_delta) * 100 / total_delta))
                )
            _, used = read_host_memory()
            self.memory_used_mib.append(used)
            self.load_average.append(os.getloadavg()[0])
            previous_total, previous_idle = total, idle

    def result(self) -> dict:
        total, used = read_host_memory()
        return {
            "cpu_logical_cores": os.cpu_count() or 1,
            "cpu_average_percent": round(
                sum(self.cpu_percent) / len(self.cpu_percent), 1
            )
            if self.cpu_percent
            else 0.0,
            "cpu_peak_percent": round(max(self.cpu_percent or [0.0]), 1),
            "memory_total_mib": round(total, 1),
            "memory_used_peak_mib": round(max(self.memory_used_mib or [used]), 1),
            "memory_used_peak_percent": round(
                max(self.memory_used_mib or [used]) * 100 / total, 1
            )
            if total
            else 0.0,
            "load_average_peak": round(
                max(self.load_average or [os.getloadavg()[0]]), 2
            ),
        }


def pg_stats(database: str) -> dict[str, int]:
    output = probe.psql(
        "postgres",
        "SELECT numbackends || '|' || xact_commit || '|' || xact_rollback || '|' || "
        "blks_read || '|' || blks_hit || '|' || temp_files || '|' || temp_bytes || '|' || "
        "deadlocks || '|' || conflicts FROM pg_stat_database "
        f"WHERE datname = {sql_literal(database)};",
    )
    names = (
        "connections",
        "commits",
        "rollbacks",
        "blocks_read",
        "blocks_hit",
        "temp_files",
        "temp_bytes",
        "deadlocks",
        "conflicts",
    )
    raw = output.split("|") if output else []
    return {
        name: int(raw[index]) if index < len(raw) else 0
        for index, name in enumerate(names)
    }


def pg_stats_delta(before: dict[str, int], after: dict[str, int]) -> dict[str, int]:
    return {
        name: after[name]
        if name == "connections"
        else max(0, after[name] - before[name])
        for name in before
    }


class FunctionalFixture:
    def __init__(
        self,
        root: pathlib.Path,
        project: str,
        project_dir: pathlib.Path,
        targets: dict[str, dict],
    ):
        self.root = root
        self.project = project
        self.project_dir = project_dir
        self.targets = targets
        self.root_env = probe.parse_env(root / "servidor" / ".env")
        self.project_env = probe.parse_env(project_dir / ".env")
        self.database = self.project_env.get("POSTGRES_DATABASE", "")
        self.table = ""
        self.slot_ids: list[str] = []
        self.opaque_key = ""
        self.publishable_key = ""
        self.auth_user_id = ""
        self.auth_email = f"platform-load-{uuid.uuid4().hex}@example.invalid"
        self.auth_password = secrets.token_urlsafe(24)
        self.bucket = f"load-{uuid.uuid4().hex[:16]}"
        self.storage_objects: set[str] = set()
        self.cleanup_failures: list[str] = []

    def project_base(self) -> str:
        address = probe.target_ip(self.targets, "project/nginx", "rede-supabase")
        return f"http://{address}:8080"

    def key_headers(self) -> dict[str, str]:
        return {
            "apikey": self.opaque_key,
            "Authorization": f"Bearer {self.opaque_key}",
        }

    def cleanup_stale(self) -> None:
        if not self.database:
            raise probe.ProbeError("POSTGRES_DATABASE ausente no projeto")
        tables = probe.psql(
            self.database,
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename LIKE '_platform_load_probe_%' ORDER BY tablename;",
        ).splitlines()
        storage_rows = probe.psql(
            self.database,
            "SELECT b.id || E'\\t' || COALESCE(o.name, '') FROM storage.buckets b "
            "LEFT JOIN storage.objects o ON o.bucket_id = b.id "
            "WHERE b.id LIKE 'load-%' ORDER BY b.id, o.name;",
        ).splitlines()
        auth_user_ids = probe.psql(
            self.database,
            "SELECT id::text FROM auth.users "
            "WHERE email LIKE 'platform-load-%@example.invalid' ORDER BY created_at;",
        ).splitlines()
        buckets: dict[str, set[str]] = {}
        for row in storage_rows:
            bucket, _, object_name = row.partition("\t")
            if not re.fullmatch(r"load-[0-9a-f]{16}", bucket):
                raise probe.ProbeError("bucket temporario fora do formato seguro")
            buckets.setdefault(bucket, set())
            if object_name:
                buckets[bucket].add(object_name)
        if buckets or auth_user_ids:
            cleanup_key = prepare_opaque_key(self.project, "secret")
            self.slot_ids.append(cleanup_key["slot_id"])
            self.opaque_key = cleanup_key["token"]
            for bucket, object_names in buckets.items():
                self.bucket = bucket
                self.storage_objects = object_names
                before = len(self.cleanup_failures)
                self.cleanup_storage()
                if len(self.cleanup_failures) != before:
                    raise probe.ProbeError(self.cleanup_failures[-1])
            for user_id in auth_user_ids:
                if not re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                    user_id,
                ):
                    raise probe.ProbeError("usuario temporario fora do formato seguro")
                self.cleanup_auth_user(user_id)
        for table in tables:
            if not re.fullmatch(r"_platform_load_probe_[0-9]+_[0-9]+", table):
                raise probe.ProbeError("tabela temporaria fora do formato seguro")
            probe.cleanup_database_fixture(self.database, table)
        stale_slots = control_psql(
            "SELECT s.id::text FROM project_api_key_slots s "
            "JOIN projects p ON p.id = s.project_id "
            f"WHERE p.name = {sql_literal(self.project)} AND s.name LIKE 'load-%' "
            "ORDER BY s.created_at;"
        ).splitlines()
        for slot_id in stale_slots:
            if not re.fullmatch(
                r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                slot_id,
            ):
                raise probe.ProbeError("slot temporario fora do formato seguro")
            cleanup_opaque_key(slot_id)
        self.slot_ids.clear()
        self.opaque_key = ""
        self.auth_user_id = ""
        self.bucket = f"load-{uuid.uuid4().hex[:16]}"
        self.storage_objects.clear()
        self.cleanup_failures.clear()

    def prepare(self, rows: int) -> None:
        if not self.database:
            raise probe.ProbeError("POSTGRES_DATABASE ausente no projeto")
        self.table = probe.prepare_database_fixture(self.database, rows)
        secret_key = prepare_opaque_key(self.project, "secret")
        self.slot_ids.append(secret_key["slot_id"])
        self.opaque_key = secret_key["token"]
        publishable_key = prepare_opaque_key(self.project, "publishable")
        self.slot_ids.append(publishable_key["slot_id"])
        self.publishable_key = publishable_key["token"]
        context = ssl.create_default_context()
        create_user = {
            "url": f"{self.project_base()}/auth/v1/admin/users",
            "method": "POST",
            "headers": {**self.key_headers(), "Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "email": self.auth_email,
                    "password": self.auth_password,
                    "email_confirm": True,
                }
            ).encode("utf-8"),
            "accepted_statuses": (200, 201),
            "capture_payload": True,
        }
        result = http_request(create_user, context)
        if not result["ok"]:
            raise probe.ProbeError(
                f"falha ao criar usuario Auth temporario: {result['error']}"
            )
        try:
            self.auth_user_id = json.loads(result["payload"])["id"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise probe.ProbeError("resposta invalida ao criar usuario Auth") from exc
        create = {
            "url": f"{self.project_base()}/storage/v1/bucket",
            "method": "POST",
            "headers": {**self.key_headers(), "Content-Type": "application/json"},
            "body": json.dumps(
                {"id": self.bucket, "name": self.bucket, "public": False}
            ).encode("utf-8"),
            "accepted_statuses": (200, 201),
        }
        result = http_request(create, context)
        if not result["ok"]:
            raise probe.ProbeError(
                f"falha ao criar bucket temporario: {result['error']}"
            )
        image = generate_png(1024, 1024)
        upload = {
            "url": f"{self.project_base()}/storage/v1/object/{self.bucket}/source.png",
            "method": "POST",
            "headers": {
                **self.key_headers(),
                "Content-Type": "image/png",
                "x-upsert": "true",
            },
            "body": image,
            "accepted_statuses": (200, 201),
        }
        result = http_request(upload, context)
        if not result["ok"]:
            raise probe.ProbeError(
                f"falha ao enviar imagem temporaria: {result['error']}"
            )
        self.storage_objects.add("source.png")
        time.sleep(2)

    def meta_header(self) -> str:
        password = self.root_env.get("META_ADMIN_DB_PASSWORD", "")
        crypto_key = self.root_env.get("PG_META_CRYPTO_KEY", "")
        host = self.root_env.get("POSTGRES_HOST", "")
        port = self.root_env.get("POSTGRES_PORT", "")
        if not all((password, crypto_key, host, port)):
            raise probe.ProbeError("configuracao Postgres Meta incompleta")
        encoded_password = urllib.parse.quote(password, safe="")
        uri = (
            f"postgresql://platform_meta_admin:{encoded_password}@{host}:{port}/"
            f"{urllib.parse.quote(self.database, safe='')}"
        )
        return encrypt_pg_meta_uri(uri, crypto_key)

    def cleanup_auth_user(self, user_id: str | None = None) -> None:
        target = user_id or self.auth_user_id
        if not target or not self.opaque_key:
            return
        endpoint = {
            "url": f"{self.project_base()}/auth/v1/admin/users/{target}",
            "method": "DELETE",
            "headers": self.key_headers(),
            "accepted_statuses": (200, 204),
        }
        result = http_request(endpoint, ssl.create_default_context())
        if not result["ok"]:
            raise probe.ProbeError(f"usuario Auth temporario: {result['error']}")

    def cleanup_storage(self) -> None:
        if not self.opaque_key:
            return
        context = ssl.create_default_context()
        objects = sorted(self.storage_objects)
        objects.extend(f"blob-{index}.bin" for index in range(64))
        delete_objects = {
            "url": f"{self.project_base()}/storage/v1/object/{self.bucket}",
            "method": "DELETE",
            "headers": {**self.key_headers(), "Content-Type": "application/json"},
            "body": json.dumps({"prefixes": objects}).encode("utf-8"),
            "accepted_statuses": (200,),
        }
        result = http_request(delete_objects, context)
        if not result["ok"]:
            self.cleanup_failures.append(
                f"objetos Storage temporarios: {result['error']}"
            )
        delete_bucket = {
            "url": f"{self.project_base()}/storage/v1/bucket/{self.bucket}",
            "method": "DELETE",
            "headers": self.key_headers(),
            "accepted_statuses": (200,),
        }
        result = http_request(delete_bucket, context)
        if not result["ok"]:
            self.cleanup_failures.append(
                f"bucket Storage temporario: {result['error']}"
            )

    def cleanup(self) -> None:
        try:
            self.cleanup_auth_user()
        except Exception as exc:
            self.cleanup_failures.append(f"Auth: {type(exc).__name__}: {exc}")
        try:
            self.cleanup_storage()
        except Exception as exc:
            self.cleanup_failures.append(f"Storage: {type(exc).__name__}: {exc}")
        for slot_id in self.slot_ids:
            try:
                cleanup_opaque_key(slot_id)
            except Exception as exc:
                self.cleanup_failures.append(
                    f"chave opaca: {type(exc).__name__}: {exc}"
                )
        if self.table:
            try:
                probe.cleanup_database_fixture(self.database, self.table)
            except Exception as exc:
                self.cleanup_failures.append(
                    f"tabela temporaria: {type(exc).__name__}: {exc}"
                )


def build_functional_endpoints(
    fixture: FunctionalFixture, settings: dict, targets: dict[str, dict]
) -> list[dict]:
    project_base = fixture.project_base()
    key_headers = fixture.key_headers()
    rest_path = f"/rest/v1/{fixture.table}?select=id,payload&order=id.desc&limit={settings['rest_rows']}"
    endpoints = [
        {
            "name": "auth-users",
            "url": f"{project_base}/auth/v1/admin/users?page=1&per_page=100",
            "headers": key_headers,
        },
        {
            "name": "auth-login",
            "url": f"{project_base}/auth/v1/token?grant_type=password",
            "method": "POST",
            "headers": {
                "apikey": fixture.publishable_key,
                "Content-Type": "application/json",
            },
            "body": json.dumps(
                {"email": fixture.auth_email, "password": fixture.auth_password}
            ).encode("utf-8"),
        },
        {
            "name": "rest-read",
            "url": f"{project_base}{rest_path}",
            "headers": key_headers,
        },
        {
            "name": "rest-publishable",
            "url": f"{project_base}/rest/v1/{fixture.table}?select=id&limit=1",
            "headers": {
                "apikey": fixture.publishable_key,
                "Authorization": f"Bearer {fixture.publishable_key}",
            },
        },
        {
            "name": "edge-function",
            "url": f"{project_base}/functions/v1/hello?ref={fixture.project}",
            "headers": key_headers,
        },
        {
            "name": "image-transform",
            "url": (
                f"{project_base}/storage/v1/render/image/authenticated/"
                f"{fixture.bucket}/source.png?width={settings['image_width']}"
                f"&height={settings['image_width']}&resize=cover&quality=80"
            ),
            "headers": key_headers,
        },
    ]
    authorizer_ip = probe.target_ip(targets, "shared/key-authorizer", "rede-supabase")
    gateway_token = fixture.project_env.get("API_GATEWAY_TOKEN_PROJETO", "")
    endpoints.append(
        {
            "name": "key-authorizer-db",
            "url": f"http://{authorizer_ip}:18010/v1/authorize",
            "headers": {
                "X-Project-Ref": fixture.project,
                "X-Project-Gateway-Token": gateway_token,
                "X-Api-Key-Header": fixture.opaque_key,
                "X-Api-Key-Query": "",
                "X-Original-Authorization": f"Bearer {fixture.opaque_key}",
                "X-Original-Args": "",
                "X-Target-Service": "rest",
                "X-Required-Role": "service_role",
                "X-Allow-Missing-Key": "0",
            },
            "accepted_statuses": (204,),
        }
    )
    endpoints.append(
        {
            "name": "key-authorizer-realtime",
            "url": f"http://{authorizer_ip}:18010/v1/authorize",
            "headers": {
                "X-Project-Ref": fixture.project,
                "X-Project-Gateway-Token": gateway_token,
                "X-Api-Key-Header": fixture.publishable_key,
                "X-Api-Key-Query": fixture.publishable_key,
                "X-Original-Authorization": f"Bearer {fixture.publishable_key}",
                "X-Original-Args": f"apikey={fixture.publishable_key}&vsn=1.0.0",
                "X-Target-Service": "realtime",
                "X-Required-Role": "anon",
                "X-Allow-Missing-Key": "0",
            },
            "accepted_statuses": (204,),
        }
    )
    projects_ip = probe.target_ip(targets, "shared/projects-api", "rede-supabase")
    content_path = f"/api/projects/internal/content-identity/{fixture.project}"
    hmac_secret = fixture.root_env.get("STUDIO_GATEWAY_HMAC_SECRET", "")
    endpoints.append(
        {
            "name": "projects-api-db",
            "url": f"http://{projects_ip}:18000{content_path}",
            "header_factory": lambda: internal_hmac_headers(
                hmac_secret, "GET", content_path
            ),
        }
    )
    meta_ip = probe.target_ip(targets, "shared/postgres-meta", "rede-supabase")
    endpoints.append(
        {
            "name": "postgres-meta-tables",
            "url": f"http://{meta_ip}:8080/tables",
            "headers": {"x-connection-encrypted": fixture.meta_header()},
        }
    )
    analytics_ip = probe.target_ip(targets, "shared/analytics", "analytics-internal")
    analytics_token = probe.parse_env(fixture.root / "servidor" / ".analytics.env").get(
        "LOGFLARE_PUBLIC_ACCESS_TOKEN", ""
    )
    analytics_payload = json.dumps(
        {
            "event_message": "platform-bottleneck-" + "x" * settings["analytics_bytes"],
            "metadata": {
                "project": fixture.project,
                "tenant_project": fixture.project,
                "probe": "platform-bottleneck",
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")
    endpoints.append(
        {
            "name": "analytics-ingest",
            "url": f"http://{analytics_ip}:4000/api/logs?source_name=cloudflare.logs.prod",
            "method": "POST",
            "headers": {
                "x-api-key": analytics_token,
                "Content-Type": "application/json",
            },
            "body": analytics_payload,
            "accepted_statuses": (200, 201, 202),
        }
    )
    studio_ip = probe.target_ip(targets, "shared/studio", "rede-supabase")
    endpoints.append(
        {
            "name": "studio-profile",
            "url": f"http://{studio_ip}:3000/api/platform/profile",
            "accepted_statuses": (200,),
        }
    )
    studio_env_path = fixture.root / "studio" / ".env"
    if studio_env_path.is_file():
        studio_port = probe.parse_env(studio_env_path).get("STUDIO_HTTPS_PORT", "")
        if studio_port.isdigit():
            endpoints.append(
                {
                    "name": "studio-auth-chain",
                    "url": f"https://127.0.0.1:{studio_port}/",
                    "accepted_statuses": (200, 302, 401, 403),
                }
            )
    vector_ip = probe.target_ip(targets, "shared/vector", "analytics-internal")
    endpoints.append(
        {
            "name": "vector-pipeline-health",
            "url": f"http://{vector_ip}:9001/health",
            "accepted_statuses": (200,),
        }
    )
    traefik = targets.get("shared/traefik")
    if traefik:
        traefik_ip = next(iter(traefik["ip_addresses"].values()))
        endpoints.append(
            {
                "name": "traefik-rest",
                "url": f"http://{traefik_ip}/{fixture.project}{rest_path}",
                "headers": key_headers,
            }
        )
    geoip = targets.get("shared/geoip")
    if geoip:
        geoip_ip = next(iter(geoip["ip_addresses"].values()))
        endpoints.append(
            {
                "name": "geoip-lookup",
                "url": f"http://{geoip_ip}:8000/v1/ip/country/8.8.8.8",
                "accepted_statuses": (200,),
            }
        )
    deny = targets.get("shared/deny-service")
    if deny:
        deny_ip = next(iter(deny["ip_addresses"].values()))
        endpoints.append(
            {
                "name": "deny-service",
                "url": f"http://{deny_ip}:8080/",
                "accepted_statuses": (403,),
            }
        )
    return endpoints


def bottleneck_ranking(services: list[dict], host: dict) -> list[dict]:
    ranked: list[dict] = []
    for service in services:
        usage = service["usage_percent"]
        configured = service["configured"]
        candidates = [
            value
            for key, value in usage.items()
            if configured[
                "cpu_cores"
                if key == "cpu"
                else "memory_mib"
                if key == "memory"
                else "pids"
            ]
        ]
        saturation = max(candidates or [0.0])
        dominant = max(usage, key=usage.get)
        ranked.append(
            {
                "service": f"{service['scope']}/{service['service']}",
                "saturation_percent": round(saturation, 1),
                "dominant_resource": dominant,
                "cpu_peak_cores": service["observed"]["cpu_peak_cores"],
                "memory_peak_mib": service["observed"]["memory_peak_mib"],
                "pids_peak": service["observed"]["pids_peak"],
                "io_mib": round(
                    service["observed"]["read_mib"] + service["observed"]["write_mib"],
                    2,
                ),
            }
        )
    ranked.sort(
        key=lambda value: (
            value["saturation_percent"],
            value["cpu_peak_cores"],
            value["memory_peak_mib"],
        ),
        reverse=True,
    )
    ranked.insert(
        0,
        {
            "service": "host",
            "saturation_percent": max(
                host["cpu_peak_percent"], host["memory_used_peak_percent"]
            ),
            "dominant_resource": (
                "cpu"
                if host["cpu_peak_percent"] >= host["memory_used_peak_percent"]
                else "memory"
            ),
            "cpu_peak_percent": host["cpu_peak_percent"],
            "memory_peak_percent": host["memory_used_peak_percent"],
            "load_average_peak": host["load_average_peak"],
        },
    )
    return ranked[:11]


def workload_failures(
    http: dict,
    storage: dict,
    realtime: dict,
    realtime_gateway: dict,
    postgres: dict,
    pooler: dict,
) -> list[str]:
    failures: list[str] = []
    for label, values in (("HTTP funcional", http), ("Storage", storage)):
        if values["errors"]:
            failures.append(f"{label}: {values['errors']} erro(s)")
        if values["success"] == 0:
            failures.append(f"{label}: nenhuma operacao bem-sucedida")
    if realtime["errors"]:
        failures.append(f"Realtime: {realtime['errors']} worker(s) com erro")
    if realtime["joins"] == 0 or realtime["messages"] == 0:
        failures.append("Realtime: nenhum canal funcional com mensagens")
    if realtime_gateway["errors"]:
        failures.append(
            f"Realtime gateway: {realtime_gateway['errors']} worker(s) com erro"
        )
    if realtime_gateway["joins"] == 0 or realtime_gateway["messages"] == 0:
        failures.append("Realtime gateway: nenhum canal funcional com mensagens")
    for label, values in (("Postgres direto", postgres), ("Supavisor", pooler)):
        if values["errors"]:
            failures.append(f"{label}: {values['errors']} erro(s)")
        if values["queries"] == 0:
            failures.append(f"{label}: nenhuma consulta concluida")
    return failures


def latency_failures(
    http: dict,
    storage: dict,
    realtime: dict,
    realtime_gateway: dict,
    postgres: dict,
    pooler: dict,
    max_p95_ms: float,
) -> list[str]:
    failures: list[str] = []
    for group_name, values in (("HTTP", http), ("Storage", storage)):
        for route_name, route in values["routes"].items():
            if route["p95_ms"] > max_p95_ms:
                failures.append(
                    f"SLO {group_name}/{route_name}: p95 {route['p95_ms']:.1f} ms "
                    f"(maximo {max_p95_ms:.1f} ms)"
                )
    for group_name, values in (
        ("Realtime", realtime),
        ("Realtime gateway", realtime_gateway),
        ("Postgres direto", postgres),
        ("Supavisor", pooler),
    ):
        if values["p95_ms"] > max_p95_ms:
            failures.append(
                f"SLO {group_name}: p95 {values['p95_ms']:.1f} ms "
                f"(maximo {max_p95_ms:.1f} ms)"
            )
    return failures


def host_failures(host: dict, max_usage: int) -> list[str]:
    failures: list[str] = []
    if host["cpu_peak_percent"] > max_usage:
        failures.append(
            f"host: CPU em {host['cpu_peak_percent']:.1f}% (maximo {max_usage}%)"
        )
    if host["memory_used_peak_percent"] > max_usage:
        failures.append(
            "host: memoria em "
            f"{host['memory_used_peak_percent']:.1f}% (maximo {max_usage}%)"
        )
    return failures


def host_recommendation(host: dict, max_usage: int) -> dict:
    cpu_cores = max(
        1,
        math.ceil(
            host["cpu_logical_cores"] * host["cpu_peak_percent"] / max_usage
        ),
    )
    memory_mib = max(
        16,
        math.ceil(
            host["memory_used_peak_mib"] * 100 / max_usage / 16
        )
        * 16,
    )
    return {
        "cpu_cores": cpu_cores,
        "memory_mib": memory_mib,
        "target_usage_percent": max_usage,
    }


def run_profile(
    profile: str,
    fixture: FunctionalFixture,
    targets: dict[str, dict],
    seconds: int,
    sample_interval: float,
    headroom: int,
    max_usage: int,
    host_max_usage: int,
    max_p95_ms: float,
) -> dict:
    settings = BOTTLENECK_PROFILES[profile]
    endpoints = build_functional_endpoints(fixture, settings, targets)
    root_env = fixture.root_env
    pooler_connection = {
        "host": probe.target_ip(targets, "shared/supavisor", "rede-supabase"),
        "port": root_env.get("POOLER_PROXY_PORT_TRANSACTION", "6543"),
        "user": f"pgbouncer.{fixture.project}",
        "password": root_env.get("POSTGRES_PASSWORD", ""),
    }
    realtime_base = fixture.project_base().replace("http://", "ws://", 1)
    realtime_url = (
        f"{realtime_base}/realtime/v1/websocket?apikey="
        f"{urllib.parse.quote(fixture.publishable_key, safe='')}&vsn=1.0.0"
    )
    realtime_origin = f"http://{fixture.project_env.get('PROJECT_UUID', '')}.localhost"
    realtime_headers = {
        "apikey": fixture.publishable_key,
        "Authorization": f"Bearer {fixture.publishable_key}",
    }
    realtime_ip = probe.target_ip(targets, "shared/realtime", "rede-supabase")
    internal_anon = fixture.project_env.get("ANON_KEY_PROJETO", "")
    direct_realtime_url = (
        f"ws://{fixture.project_env.get('PROJECT_UUID', '')}.localhost:4000/"
        f"socket/websocket?apikey={urllib.parse.quote(internal_anon, safe='')}&vsn=1.0.0"
    )
    direct_realtime_headers = {
        "apikey": internal_anon,
        "Authorization": f"Bearer {internal_anon}",
    }
    before = {name: probe.state(target) for name, target in targets.items()}
    pg_before = pg_stats(fixture.database)
    monitor = probe.Monitor(targets, sample_interval)
    host_monitor = HostMonitor(sample_interval)
    started = time.monotonic()
    monitor.start()
    host_monitor.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            futures = {
                "http": pool.submit(
                    http_load,
                    endpoints,
                    seconds,
                    settings["http_workers_per_route"],
                ),
                "storage": pool.submit(
                    storage_load,
                    fixture.project_base(),
                    fixture.opaque_key,
                    fixture.bucket,
                    seconds,
                    settings["storage_workers"],
                    settings["storage_bytes"],
                ),
                "realtime": pool.submit(
                    realtime_load,
                    direct_realtime_url,
                    direct_realtime_headers,
                    realtime_origin,
                    seconds,
                    settings["realtime_workers"],
                    (realtime_ip, 4000),
                ),
                "realtime_gateway": pool.submit(
                    realtime_load,
                    realtime_url,
                    realtime_headers,
                    realtime_origin,
                    seconds,
                    1,
                ),
                "postgres": pool.submit(
                    database_load,
                    fixture.database,
                    seconds,
                    settings["postgres_workers"],
                    settings["series"],
                ),
                "pooler": pool.submit(
                    database_load,
                    fixture.database,
                    seconds,
                    settings["pooler_workers"],
                    settings["series"],
                    pooler_connection,
                ),
            }
            results = {name: future.result() for name, future in futures.items()}
    finally:
        monitor.stop()
        host_monitor.stop()
    elapsed = max(0.001, time.monotonic() - started)
    after = {name: probe.state(target) for name, target in targets.items()}
    pg_after = pg_stats(fixture.database)
    services: list[dict] = []
    failures = workload_failures(
        results["http"],
        results["storage"],
        results["realtime"],
        results["realtime_gateway"],
        results["postgres"],
        results["pooler"],
    )
    failures.extend(
        latency_failures(
            results["http"],
            results["storage"],
            results["realtime"],
            results["realtime_gateway"],
            results["postgres"],
            results["pooler"],
            max_p95_ms,
        )
    )
    for name, target in sorted(targets.items()):
        row, row_failures = probe.service_result(
            name,
            target,
            before[name],
            after[name],
            monitor.samples[name],
            elapsed,
            headroom,
            max_usage,
        )
        services.append(row)
        failures.extend(row_failures)
    host = host_monitor.result()
    failures.extend(host_failures(host, host_max_usage))
    return {
        "profile": profile,
        "duration_seconds": round(elapsed, 2),
        "workload": settings,
        "http": results["http"],
        "storage": results["storage"],
        "realtime": results["realtime"],
        "realtime_gateway": results["realtime_gateway"],
        "postgres": results["postgres"],
        "supavisor": results["pooler"],
        "postgres_stats": pg_stats_delta(pg_before, pg_after),
        "host": host,
        "host_max_usage_percent": host_max_usage,
        "host_recommendation": host_recommendation(host, host_max_usage),
        "max_p95_ms": max_p95_ms,
        "services": services,
        "project_recommendation": probe.recommendations(services, "project"),
        "shared_recommendation": probe.recommendations(services, "shared"),
        "bottlenecks": bottleneck_ranking(services, host),
        "failures": failures,
    }


def aggregate_profiles(profile: str, runs: list[dict]) -> dict:
    if len(runs) == 1:
        result = copy.deepcopy(runs[0])
        result["repetitions"] = 1
        result["runs"] = copy.deepcopy(runs)
        return result
    result = json.loads(json.dumps(runs[0]))
    result["repetitions"] = len(runs)
    result["duration_seconds"] = round(sum(run["duration_seconds"] for run in runs), 2)
    result["failures"] = list(
        dict.fromkeys(
            failure
            for run in runs
            for failure in run["failures"]
            if not failure.startswith(("host: ", "SLO "))
        )
    )
    services_by_container = {row["container"]: row for row in result["services"]}
    for container, target in services_by_container.items():
        candidates = [
            row
            for run in runs
            for row in run["services"]
            if row["container"] == container
        ]
        for metric in (
            "memory_peak_mib",
            "cpu_peak_cores",
            "cpu_average_cores",
            "pids_peak",
            "read_mib",
            "write_mib",
        ):
            target["observed"][metric] = max(
                row["observed"][metric] for row in candidates
            )
        for metric in ("memory", "cpu", "pids"):
            target["usage_percent"][metric] = max(
                row["usage_percent"][metric] for row in candidates
            )
        for metric in ("memory_mib", "cpu_cores", "pids"):
            target["recommended"][metric] = max(
                row["recommended"][metric] for row in candidates
            )
        target["oom_kill"] = sum(row["oom_kill"] for row in candidates)
        target["restarts"] = sum(row["restarts"] for row in candidates)
        target["container_changed"] = any(
            row["container_changed"] for row in candidates
        )
    result["project_recommendation"] = probe.recommendations(
        result["services"], "project"
    )
    result["shared_recommendation"] = probe.recommendations(
        result["services"], "shared"
    )
    for group, rate in (
        ("http", "ops_per_second"),
        ("storage", "ops_per_second"),
        ("realtime", "messages_per_second"),
        ("realtime_gateway", "messages_per_second"),
        ("postgres", "qps"),
        ("supavisor", "qps"),
    ):
        result[group][rate] = min(run[group][rate] for run in runs)
    for group in ("realtime", "realtime_gateway", "postgres", "supavisor"):
        for metric in ("p50_ms", "p95_ms", "p99_ms"):
            result[group][metric] = max(run[group][metric] for run in runs)
    for group in ("http", "storage"):
        for metric in ("operations", "success", "errors"):
            result[group][metric] = sum(run[group][metric] for run in runs)
        result[group]["mib"] = round(sum(run[group]["mib"] for run in runs), 2)
        result[group]["mib_per_second"] = min(
            run[group]["mib_per_second"] for run in runs
        )
        for route_name, route in result[group]["routes"].items():
            candidates = [run[group]["routes"][route_name] for run in runs]
            for metric in ("operations", "success", "errors", "bytes"):
                route[metric] = sum(row[metric] for row in candidates)
            route["mib"] = round(sum(row["mib"] for row in candidates), 2)
            route["ops_per_second"] = min(
                row["ops_per_second"] for row in candidates
            )
            for metric in ("p50_ms", "p95_ms", "p99_ms"):
                route[metric] = max(row[metric] for row in candidates)
            statuses: dict[str, int] = {}
            for row in candidates:
                for status, count in row["statuses"].items():
                    statuses[status] = statuses.get(status, 0) + count
            route["statuses"] = statuses
            route["last_error"] = next(
                (row["last_error"] for row in reversed(candidates) if row["last_error"]),
                "",
            )
    for group, count_fields in (
        ("realtime", ("connections", "joins", "messages", "errors")),
        ("realtime_gateway", ("connections", "joins", "messages", "errors")),
        ("postgres", ("queries", "errors")),
        ("supavisor", ("queries", "errors")),
    ):
        for metric in count_fields:
            result[group][metric] = sum(run[group][metric] for run in runs)
    for group in ("realtime", "realtime_gateway"):
        result[group]["last_errors"] = list(
            dict.fromkeys(
                error
                for run in runs
                for error in run[group]["last_errors"]
            )
        )[:5]
    for group in ("postgres", "supavisor"):
        result[group]["last_error"] = next(
            (
                run[group]["last_error"]
                for run in reversed(runs)
                if run[group]["last_error"]
            ),
            "",
        )
    result["postgres_stats"] = {
        key: max(run["postgres_stats"][key] for run in runs)
        if key == "connections"
        else sum(run["postgres_stats"][key] for run in runs)
        for key in result["postgres_stats"]
    }
    result["host"] = {
        key: max(run["host"][key] for run in runs) for key in result["host"]
    }
    result["host_recommendation"] = host_recommendation(
        result["host"], result["host_max_usage_percent"]
    )
    result["failures"].extend(
        host_failures(result["host"], result["host_max_usage_percent"])
    )
    result["failures"].extend(
        latency_failures(
            result["http"],
            result["storage"],
            result["realtime"],
            result["realtime_gateway"],
            result["postgres"],
            result["supavisor"],
            result["max_p95_ms"],
        )
    )
    result["bottlenecks"] = bottleneck_ranking(result["services"], result["host"])
    result["runs"] = runs
    return result


def coverage_matrix(targets: dict[str, dict]) -> list[dict]:
    rows = [
        ("postgres", "SQL direto, estatisticas e I/O", "functional"),
        ("supavisor", "conexoes SQL reais pelo pool transacional", "functional"),
        ("realtime", "WebSocket, join e broadcast com chave opaca", "functional"),
        ("storage", "bucket, upload, download e remocao", "functional"),
        ("imgproxy", "transformacao de imagem autenticada", "functional"),
        ("analytics", "ingestao Logflare e logs naturais", "functional"),
        ("vector", "pipeline Docker Fluentd para Logflare", "pipeline"),
        ("postgres-meta", "listagem real de tabelas do tenant", "functional"),
        (
            "projects-api",
            "resolucao de projeto com HMAC e consulta ao banco",
            "functional",
        ),
        (
            "key-authorizer",
            "validacao de chave opaca e consulta ao banco",
            "functional",
        ),
        ("edge-functions", "invocacao da funcao hello", "functional"),
        ("auth", "listagem administrativa de usuarios", "functional"),
        ("rest", "leitura paginada de fixture", "functional"),
        ("nginx", "gateway e autorizacao por projeto", "functional"),
        ("studio", "rota dinamica de perfil", "functional"),
        ("studio-nginx", "acesso HTTPS e logs do gateway", "pipeline"),
        ("authelia", "cadeia de autenticacao do Studio", "pipeline"),
        ("storage-data-plane", "proxy multi-tenant de objetos", "functional"),
        ("traefik", "roteamento publico do projeto", "functional"),
        ("geoip", "consulta de pais", "functional"),
        ("deny-service", "resposta de bloqueio", "functional"),
        ("traefik-config", "watcher observado durante toda a carga", "observed"),
    ]
    available = {target["service"] for target in targets.values()}
    return [
        {
            "service": service,
            "scenario": scenario,
            "level": level,
            "available": service in available or service in {"auth", "rest", "nginx"},
        }
        for service, scenario, level in rows
    ]


def print_report(report: dict) -> None:
    print(f"Ambiente descartavel: {report['root']}")
    print(f"Projeto: {report['project']}")
    for result in report["profiles"]:
        print()
        print(
            f"{result['profile']}: HTTP {result['http']['ops_per_second']} ops/s, "
            f"Storage {result['storage']['ops_per_second']} ops/s, "
            f"Realtime {result['realtime']['messages_per_second']} msg/s, "
            f"Postgres {result['postgres']['qps']} q/s, "
            f"Supavisor {result['supavisor']['qps']} q/s, "
            f"{len(result['failures'])} alerta(s)"
        )
        print("Gargalos por saturacao:")
        for bottleneck in result["bottlenecks"][:6]:
            print(
                f"  {bottleneck['service']}: {bottleneck['saturation_percent']:.1f}% "
                f"({bottleneck['dominant_resource']})"
            )
        for failure in result["failures"]:
            print(f"ALERTA: {failure}")
    for failure in report["cleanup_failures"]:
        print(f"ALERTA DE LIMPEZA: {failure}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encontra gargalos reais de toda a plataforma multi-tenant."
    )
    parser.add_argument("--root", type=pathlib.Path, required=True)
    parser.add_argument("--project")
    parser.add_argument(
        "--profile", choices=("small", "medium", "large", "all"), default="all"
    )
    parser.add_argument("--seconds", type=int, default=30)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--headroom", type=int, default=30)
    parser.add_argument("--max-usage", type=int, default=80)
    parser.add_argument("--host-max-usage", type=int)
    parser.add_argument("--max-p95-ms", type=float, default=500.0)
    parser.add_argument("--cooldown", type=int, default=10)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--allow-temporary-fixtures", action="store_true")
    parser.add_argument("--allow-source-root", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args()
    fixture: FunctionalFixture | None = None
    lock_file = None
    cleanup_failures: list[str] = []
    try:
        root = args.root.resolve(strict=True)
        if root == SOURCE_ROOT and not args.allow_source_root:
            raise probe.ProbeError(
                "o probe funcional recusa o repositorio-fonte; use uma instalacao descartavel"
            )
        if not args.allow_temporary_fixtures:
            raise probe.ProbeError("confirme fixtures com --allow-temporary-fixtures")
        if args.seconds < 10:
            raise probe.ProbeError("--seconds precisa ser >= 10")
        if not 0.1 <= args.sample_interval <= 5:
            raise probe.ProbeError("--sample-interval precisa estar entre 0.1 e 5")
        if not 0 <= args.headroom <= 200:
            raise probe.ProbeError("--headroom precisa estar entre 0 e 200")
        if not 1 <= args.max_usage <= 100:
            raise probe.ProbeError("--max-usage precisa estar entre 1 e 100")
        if args.host_max_usage is not None and not 1 <= args.host_max_usage <= 100:
            raise probe.ProbeError("--host-max-usage precisa estar entre 1 e 100")
        if not 1 <= args.max_p95_ms <= 60000:
            raise probe.ProbeError("--max-p95-ms precisa estar entre 1 e 60000")
        if not 1 <= args.repetitions <= 5:
            raise probe.ProbeError("--repetitions precisa estar entre 1 e 5")
        project, project_dir = probe.discover_project(root, args.project)
        lock_file = acquire_probe_lock(root, project)
        targets, missing = probe.build_targets(root, project)
        missing.extend(add_infrastructure_targets(root, targets))
        fixture = FunctionalFixture(root, project, project_dir, targets)
        if args.host_max_usage is None:
            try:
                reserve = int(fixture.root_env.get("PLATFORM_RESERVE_PERCENT", "25"))
            except ValueError as exc:
                raise probe.ProbeError(
                    "PLATFORM_RESERVE_PERCENT precisa ser inteiro"
                ) from exc
            host_max_usage = 100 - reserve
        else:
            host_max_usage = args.host_max_usage
        if not 1 <= host_max_usage <= 100:
            raise probe.ProbeError(
                "limite do host derivado de PLATFORM_RESERVE_PERCENT fora de 1..100"
            )
        profiles = (
            list(BOTTLENECK_PROFILES) if args.profile == "all" else [args.profile]
        )
        fixture.cleanup_stale()
        fixture.prepare(
            max(BOTTLENECK_PROFILES[name]["rest_rows"] for name in profiles)
        )
        results: list[dict] = []
        completed = 0
        for profile in profiles:
            runs: list[dict] = []
            for _ in range(args.repetitions):
                if completed and args.cooldown:
                    time.sleep(args.cooldown)
                runs.append(
                    run_profile(
                        profile,
                        fixture,
                        targets,
                        args.seconds,
                        args.sample_interval,
                        args.headroom,
                        args.max_usage,
                        host_max_usage,
                        args.max_p95_ms,
                    )
                )
                completed += 1
            results.append(aggregate_profiles(profile, runs))
        report = {
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "root": str(root),
            "project": project,
            "headroom_percent": args.headroom,
            "max_usage_percent": args.max_usage,
            "host_max_usage_percent": host_max_usage,
            "max_p95_ms": args.max_p95_ms,
            "missing_services": sorted(missing),
            "coverage": coverage_matrix(targets),
            "profiles": results,
            "cleanup_failures": cleanup_failures,
        }
    except (OSError, probe.ProbeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    finally:
        if fixture is not None:
            fixture.cleanup()
            cleanup_failures.extend(fixture.cleanup_failures)
        if lock_file is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
    report["cleanup_failures"] = cleanup_failures
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if args.json:
        print(rendered)
    else:
        print_report(report)
    failures = any(result["failures"] for result in report["profiles"])
    return 1 if failures or cleanup_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
