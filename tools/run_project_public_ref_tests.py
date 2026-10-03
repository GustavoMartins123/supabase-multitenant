"""Run identity/schema tests in isolated containers without installation credentials."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
LABEL = "multitenant.public-ref-test"


def docker(*args: str) -> str:
    result = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(
            f"Docker {args[0]} failed:\n{result.stdout.strip()}\n{result.stderr.strip()}"
        )
    if args[0] in {"run", "logs"} and result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.stdout.strip()


def owned_remove(kind: str, identifier: str, token: str) -> None:
    record = json.loads(docker(kind, "inspect", identifier))[0]
    labels = record["Config"]["Labels"] if kind == "container" else record["Labels"]
    if labels.get(LABEL) != token:
        raise RuntimeError("Refusing to remove a resource without the test ownership label")
    removals = {"container": ("rm", "-f"), "network": ("network", "rm"), "volume": ("volume", "rm")}
    docker(*removals[kind], identifier)


def remove_owned_resources(resources: list[tuple[str, str]], token: str) -> None:
    errors = []
    for kind, identifier in resources:
        try:
            owned_remove(kind, identifier, token)
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("Could not remove every disposable test resource", errors)


def validate_routing(executor_image: str, nginx_image: str, traefik_image: str) -> None:
    for image in (executor_image, nginx_image, traefik_image):
        if docker("image", "inspect", image, "--format", "{{.Os}}") != "linux":
            raise RuntimeError("Existing Linux routing images required")
    token = uuid.uuid4().hex
    network = volume = None
    containers: list[str] = []
    try:
        network = docker("network", "create", "--internal", "--label", f"{LABEL}={token}",
                         f"ref-routing-{token[:12]}")
        volume = docker("volume", "create", "--label", f"{LABEL}={token}", f"ref-routing-{token[:12]}")
        common = (
            "run", "--rm", "--read-only", "--pull=never", "--network", network,
            "--label", f"{LABEL}={token}", "--tmpfs", "/tmp:rw,exec,size=64m",
            "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
            "-w", "/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTHONPATH=/workspace/servidor/host-agent",
        )
        fixture = "tests/integration/fixtures/project_public_ref_routing.py"
        docker(*common, "-v", volume + ":/test", "--entrypoint", "python", executor_image,
               fixture, "prepare", "/test")
        base = ("run", "--detach", "--read-only", "--pull=never", "--network", network,
                "--label", f"{LABEL}={token}", "--tmpfs", "/tmp:rw,size=64m",
                "--tmpfs", "/var/cache/nginx:rw,size=16m", "-v", volume + ":/test:ro")
        containers.append(docker(
            *base, "--network-alias", "key-authorizer", "--entrypoint", "nginx", nginx_image,
            "-g", "daemon off;", "-c", "/test/deny-authorizer.conf",
        ))
        containers.append(docker(
            *base, "--network-alias", "supabase-nginx-technical_project",
            "-e", "FILE_SIZE_LIMIT=52428800", "-e", "SUPABASE_NETWORK_SUBNET=127.0.0.0/8",
            "-e", "ANON_KEY_PROJETO=header.payload.sig", "-e", "SERVICE_ROLE_KEY_PROJETO=header.payload.sig",
            "-e", "CONFIG_TOKEN_PROJETO=" + "a" * 64, "-e", "API_GATEWAY_TOKEN_PROJETO=" + "b" * 64,
            "--entrypoint", "/bin/sh", nginx_image, "-c",
            "envsubst '$FILE_SIZE_LIMIT $SUPABASE_NETWORK_SUBNET $ANON_KEY_PROJETO $SERVICE_ROLE_KEY_PROJETO "
            "$CONFIG_TOKEN_PROJETO $API_GATEWAY_TOKEN_PROJETO' < /test/projects/technical_project/nginx/"
            "nginx_technical_project.conf > /tmp/nginx.conf && exec nginx -g 'daemon off;' -c /tmp/nginx.conf",
        ))
        containers.append(docker(
            *base, "--network-alias", "router", "--mount",
            f"type=bind,source={ROOT / 'servidor/traefik/plugins-local'},target=/plugins-local,readonly",
            "-w", "/", traefik_image, "--configFile=/test/traefik.yml",
        ))
        try:
            print(docker(*common, "--entrypoint", "python", executor_image, fixture, "verify"))
        except RuntimeError:
            for identifier in containers:
                print(docker("logs", "--tail", "20", identifier))
            raise
    finally:
        resources = [("container", identifier) for identifier in reversed(containers)]
        if network:
            resources.append(("network", network))
        if volume:
            resources.append(("volume", volume))
        remove_owned_resources(resources, token)


def execute(executor_image: str, postgres_image: str) -> None:
    for image in (executor_image, postgres_image):
        if docker("image", "inspect", image, "--format", "{{.Os}}") != "linux":
            raise RuntimeError("Existing Linux images required; no automatic pull/build")
    token = uuid.uuid4().hex
    network_id = database_id = None
    try:
        network_id = docker(
            "network", "create", "--internal", "--label", f"{LABEL}={token}",
            f"public-ref-test-{token[:12]}",
        )
        password = secrets.token_hex(24)
        database_id = docker(
            "run", "--detach", "--pull=never", "--name", f"public-ref-db-{token[:12]}",
            "--label", f"{LABEL}={token}", "--network", network_id, "--network-alias", "db",
            "--tmpfs", "/var/lib/postgresql/data:rw,size=256m",
            "--tmpfs", "/var/run/postgresql:rw,size=16m",
            "-e", f"POSTGRES_PASSWORD={password}", postgres_image,
        )
        deadline = time.monotonic() + 60
        while True:
            ready = subprocess.run(
                ["docker", "exec", database_id, "pg_isready", "-U", "postgres"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Disposable PostgreSQL did not become ready")
            time.sleep(1)
        common = (
            "run", "--rm", "--pull=never", "--read-only", "--label", f"{LABEL}={token}",
            "--network", network_id, "--tmpfs", "/tmp:rw,exec,size=64m",
            "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
            "-w", "/workspace", "-e", "PYTHONDONTWRITEBYTECODE=1",
            "-e", "PYTHONPATH=/workspace/servidor/api-internal",
        )
        print(docker(
            *common, "--entrypoint", "python", executor_image,
            "-m", "unittest", "discover", "-s", "tests/smoke",
            "-p", "test_project_public_ref*.py", "-v",
        ))
        print(docker(
            *common, "--entrypoint", "python", executor_image,
            "-m", "unittest", "discover", "-s", "tests/smoke",
            "-p", "test_control_plane_migrations.py", "-v",
        ))
        print(docker(
            *common, "-e", f"DB_DSN=postgresql://postgres:{password}@db:5432/postgres",
            "--entrypoint", "python", executor_image,
            "tests/integration/fixtures/project_public_ref.py",
        ))
        print(docker(
            *common, "-e", f"CONTROL_PLANE_TEST_DSN=postgresql://postgres:{password}@db:5432/postgres",
            "--entrypoint", "python", executor_image,
            "-m", "unittest", "discover", "-s", "tests/smoke",
            "-p", "test_authorization_behavior.py", "-v",
        ))
    finally:
        resources = []
        if database_id:
            resources.append(("container", database_id))
        if network_id:
            resources.append(("network", network_id))
        remove_owned_resources(resources, token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    parser.add_argument("--routing", action="store_true")
    parser.add_argument("--nginx-image")
    parser.add_argument("--traefik-image")
    args = parser.parse_args()
    execute(args.executor_image, args.postgres_image)
    if args.routing:
        if not args.nginx_image or not args.traefik_image:
            parser.error("--routing requires --nginx-image and --traefik-image")
        validate_routing(args.executor_image, args.nginx_image, args.traefik_image)
