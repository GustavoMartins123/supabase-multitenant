"""Run the physical lifecycle suite in a disposable Docker-in-Docker daemon."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import uuid

from run_p1_lifecycle_tests import execute

LABEL = "multitenant.isolated-lifecycle"
IMAGES = (
    "servidor-db:latest", "servidor-realtime:latest",
    "servidor-control-plane-migrations:latest", "servidor-key-authorizer:latest",
    "supabase/edge-runtime:v1.74.2", "supabase/supavisor:2.9.7",
    "supabase/storage-api:v1.61.12", "darthsim/imgproxy:v4.0.11",
    "nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim",
    "supabase/gotrue:v2.193.0-rc.3", "postgrest/postgrest:v14.14",
    "redis:8.2.2-alpine",
)


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executor-image", required=True)
    parser.add_argument("--dind-image", required=True)
    args = parser.parse_args()
    for image in (*IMAGES, args.executor_image, args.dind_image):
        if docker("image", "inspect", image, "--format", "{{.Os}}") != "linux":
            raise RuntimeError("Existing Linux images are required")
    token = uuid.uuid4().hex
    name = "isolated-lifecycle-" + token[:12]
    volume = docker("volume", "create", "--label", f"{LABEL}={token}", name)
    daemon = None
    previous_host = os.environ.get("DOCKER_HOST")
    try:
        daemon = docker("run", "-d", "--pull=never", "--privileged", "--name", name,
                        "--label", f"{LABEL}={token}", "-e", "DOCKER_TLS_CERTDIR=",
                        "-v", volume + ":/var/lib/docker", "-p", "127.0.0.1::2375",
                        args.dind_image, "--host=tcp://0.0.0.0:2375", "--tls=false")
        deadline = time.monotonic() + 90
        while subprocess.run(["docker", "exec", daemon, "docker", "info"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            if time.monotonic() > deadline:
                raise RuntimeError("Disposable daemon readiness timeout")
            time.sleep(1)
        port = json.loads(docker("inspect", daemon))[0]["NetworkSettings"]["Ports"]["2375/tcp"][0]
        if port["HostIp"] != "127.0.0.1":
            raise RuntimeError("Test Docker API must be loopback-only")
        print("Loading existing images into the disposable daemon", flush=True)
        saved = subprocess.Popen(["docker", "save", *IMAGES, args.executor_image], stdout=subprocess.PIPE)
        try:
            loaded = subprocess.run(["docker", "exec", "-i", daemon, "docker", "load"],
                                    stdin=saved.stdout, capture_output=True)
        finally:
            saved.stdout.close()
        if saved.wait() != 0 or loaded.returncode != 0:
            raise RuntimeError("Could not load existing lifecycle images")
        os.environ["DOCKER_HOST"] = "tcp://127.0.0.1:" + port["HostPort"]
        execute(args.executor_image,
                extra_sources=("servidor/api-internal/app/migrations/0014_job_public_reference.sql",
                               "servidor/api-internal/app/migrations/0015_project_display_name.sql"))
    finally:
        if previous_host is None:
            os.environ.pop("DOCKER_HOST", None)
        else:
            os.environ["DOCKER_HOST"] = previous_host
        if daemon:
            labels = json.loads(docker("inspect", daemon))[0]["Config"]["Labels"]
            if labels.get(LABEL) != token:
                raise RuntimeError("Disposable daemon cleanup ownership mismatch")
            docker("rm", "-f", "-v", daemon)
        labels = json.loads(docker("volume", "inspect", volume))[0]["Labels"]
        if labels.get(LABEL) != token:
            raise RuntimeError("Disposable volume cleanup ownership mismatch")
        docker("volume", "rm", volume)


if __name__ == "__main__":
    main()
