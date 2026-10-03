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
    if args[0] == "run" and result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.stdout.strip()


def owned_remove(kind: str, identifier: str, token: str) -> None:
    record = json.loads(docker(kind, "inspect", identifier))[0]
    labels = record["Config"]["Labels"] if kind == "container" else record["Labels"]
    if labels.get(LABEL) != token:
        raise RuntimeError("Refusing to remove a resource without the test ownership label")
    docker("rm", "-f", identifier) if kind == "container" else docker("network", "rm", identifier)


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
            "-p", "test_project_public_ref.py", "-v",
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
    finally:
        try:
            if database_id:
                owned_remove("container", database_id, token)
        finally:
            if network_id:
                owned_remove("network", network_id, token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-image", required=True)
    parser.add_argument("--postgres-image", required=True)
    args = parser.parse_args()
    execute(args.executor_image, args.postgres_image)
