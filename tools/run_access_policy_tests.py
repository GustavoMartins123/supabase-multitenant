"""Run admission tests on a disposable Docker network; never use installed envs."""

import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode("utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {output[-5000:]}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorizer-image", default="access-authorizer:test")
    parser.add_argument("--geoip-image", default="access-geoip:test")
    parser.add_argument("--configuration-image", default="access-configuration:test")
    parser.add_argument("--api-image", default="access-api:test")
    parser.add_argument(
        "--nginx-image", default="nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim"
    )
    args = parser.parse_args()
    suffix = uuid.uuid4().hex[:10]
    network = "access-test-" + suffix
    folder = (ROOT / ".tmp-appdata" / "access-tests" / suffix).resolve()
    if not folder.is_relative_to((ROOT / ".tmp-appdata").resolve()):
        raise RuntimeError("Invalid private fixture directory")
    folder.mkdir(parents=True)
    api = folder / "api" / "app"
    for source in (ROOT / "servidor/api-internal/app").rglob("*"):
        if source.is_file() and source.suffix in {".py", ".sql", ".json"}:
            target = api / source.relative_to(ROOT / "servidor/api-internal/app")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    shutil.copyfile(
        ROOT / "tests/integration/fixtures/access_policy_stack.py", folder / "fixture.py"
    )
    shutil.copyfile(ROOT / "servidor/generateProject/nginxtemplate", folder / "nginxtemplate")
    shutil.copyfile(
        ROOT / "servidor/traefik/render_dynamic_config.py", folder / "render_dynamic_config.py"
    )
    plugins = folder / "plugins-local/src/github.com/GustavoMartins123/gatewayadmission"
    plugins.mkdir(parents=True)
    for source in (
        ROOT / "servidor/traefik/plugins-local/src/github.com/GustavoMartins123/gatewayadmission"
    ).glob("*"):
        if source.suffix in {".go", ".mod", ".yml"}:
            shutil.copyfile(source, plugins / source.name)
    cfg = {
        "password": secrets.token_hex(32),
        "redis_password": secrets.token_hex(32),
        "secret": secrets.token_hex(32),
    }
    (folder / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (folder / "dynamic").mkdir()
    geoip = folder / "geoip"
    geoip.mkdir()
    shutil.copyfile(
        ROOT / "servidor/traefik/geoip/GeoLite2-Country.mmdb", geoip / "GeoLite2-Country.mmdb"
    )
    (folder / "traefik.yml").write_text(
        """entryPoints:
  web:
    address: ":8080"
    forwardedHeaders:
      trustedIPs: ["10.207.0.100/32"]
providers:
  file:
    directory: /work/dynamic
    watch: true
experimental:
  localPlugins:
    gatewayadmission:
      moduleName: "github.com/GustavoMartins123/gatewayadmission"
log:
  level: ERROR
global:
  sendAnonymousUsage: false
  checkNewVersion: false
""",
        encoding="utf-8",
    )
    containers = []

    def container(label, image, *options, command=(), ip=None):
        name = network + "-" + label
        containers.append(name)
        flags = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--network",
            network,
            "--network-alias",
            label,
        ]
        if ip:
            flags.extend(["--ip", ip])
        run(*flags, *options, image, *command)
        return name

    try:
        run("docker", "network", "create", "--subnet", "10.207.0.0/24", network)
        db = container("pg", "postgres:15", "-e", "POSTGRES_PASSWORD=" + cfg["password"])
        for _ in range(60):
            if (
                subprocess.run(
                    ["docker", "exec", db, "pg_isready", "-U", "postgres"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                ).returncode
                == 0
            ):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL not ready")
        redis = container(
            "traffic-redis",
            "redis:8.2.2-alpine",
            command=(
                "redis-server",
                "--requirepass",
                cfg["redis_password"],
                "--appendonly",
                "yes",
                "--appendfsync",
                "always",
                "--maxmemory-policy",
                "noeviction",
            ),
        )
        checker = container(
            "checker",
            args.api_image,
            "-v",
            str(folder) + ":/work",
            command=("sleep", "infinity"),
            ip="10.207.0.100",
        )
        print(run("docker", "exec", checker, "python", "/work/fixture.py", "seed"), flush=True)
        country = container("geoip-api", args.geoip_image, "-v", str(geoip) + ":/data:ro")
        evaluator = container(
            "key-authorizer",
            args.authorizer_image,
            "-e",
            "DB_DSN=postgres://key_authorizer:" + cfg["password"] + "@pg:5432/postgres",
            "-e",
            "ACCESS_RATE_REDIS_PASSWORD=" + cfg["redis_password"],
            "-e",
            "ACCESS_ADMISSION_SECRET=" + cfg["secret"],
            "-e",
            "ACCESS_ADMIN_CIDRS=10.207.0.0/24",
        )
        container(
            "client-configuration",
            args.configuration_image,
            "-e",
            "DB_DSN=postgres://client_configuration_reader:"
            + cfg["password"]
            + "@pg:5432/postgres",
            "-e",
            "SERVER_URL=example.test",
            "-e",
            "SERVER_PROTO=http",
            "-e",
            "ACCESS_ADMISSION_SECRET=" + cfg["secret"],
        )
        mock = container(
            "upstream",
            "python:3.12.13-slim",
            "-v",
            str(folder) + ":/work:ro",
            "--network-alias",
            "supabase-rest-alpha",
            "--network-alias",
            "supabase-auth-alpha",
            "--network-alias",
            "supabase-storage-global",
            "--network-alias",
            "functions",
            "--network-alias",
            "realtime-dev.supabase-realtime",
            command=("python", "/work/fixture.py", "mock"),
        )
        gateway = container(
            "supabase-nginx-alpha",
            args.nginx_image,
            "-v",
            str(folder / "nginx.conf") + ":/etc/nginx/nginx.conf:ro",
        )
        traefik = container(
            "edge",
            "traefik:v3.7.6",
            "-v",
            str(folder) + ":/work:ro",
            "-v",
            str(folder / "plugins-local") + ":/plugins-local:ro",
            command=("--configFile=/work/traefik.yml",),
        )
        print(run("docker", "exec", checker, "python", "/work/fixture.py", "check"), flush=True)
        project = json.loads((folder / "state.json").read_text(encoding="utf-8"))["projects"][0]
        origin = json.loads(run("docker", "inspect", gateway))[0]["NetworkSettings"]["Networks"][
            network
        ]["IPAddress"]
        probe = json.dumps(
            {
                "project_ref": project["name"],
                "gateway_token": project["gateway"],
                "uri": "/" + project["ref"] + "/storage/v1/bucket",
                "method": "GET",
                "client_ip": origin,
                "api_key": "",
                "authorization": "",
            }
        )
        script = """response="$(wget -S -O /dev/null -T 10 --header="X-Admission-Secret: $2" \
  --header="Content-Type: application/json" --post-data="$1" http://key-authorizer:18010/v1/admit 2>&1)" || exit 1
ticket="$(printf "%s" "$response" | sed -n "s/^.*X-Gateway-Admission: //Ip" | tr -d "\\r" | head -n 1)"
printf "%s" "$ticket" | grep -Eq "^[A-Za-z0-9_-]{43}$" || exit 1
wget -qO- -T 10 --header="X-Gateway-Admission: $ticket" --header="X-Admission-URI: $3" \
  --header="X-Admission-Method: GET" http://supabase-nginx-alpha:8080/storage/v1/bucket >/dev/null
"""
        run(
            "docker",
            "exec",
            gateway,
            "sh",
            "-eu",
            "-c",
            script,
            "sh",
            probe,
            cfg["secret"],
            "/" + project["ref"] + "/storage/v1/bucket",
        )
        print(
            "PASS real gateway BusyBox admission probe: canonical origin, HTTP 204 ticket extraction and redemption",
            flush=True,
        )
        run("docker", "restart", evaluator)
        print(
            run("docker", "exec", checker, "python", "/work/fixture.py", "restart-check"),
            flush=True,
        )
        run("docker", "restart", redis)
        print(
            run("docker", "exec", checker, "python", "/work/fixture.py", "restart-check"),
            flush=True,
        )
        for label, target in (("geoip", country), ("redis", redis), ("postgres", db)):
            run("docker", "exec", checker, "python", "/work/fixture.py", "prepare-failure", label)
            run("docker", "stop", target)
            print(
                run(
                    "docker", "exec", checker, "python", "/work/fixture.py", "failure-check", label
                ),
                flush=True,
            )
            run("docker", "start", target)
            time.sleep(1)
        run("docker", "exec", checker, "python", "/work/fixture.py", "prepare-failure", "geoip")
        invalid = geoip / "invalid.mmdb"
        invalid.write_bytes(b"invalid-mmdb")
        invalid.replace(geoip / "GeoLite2-Country.mmdb")
        print(
            run(
                "docker",
                "exec",
                checker,
                "python",
                "/work/fixture.py",
                "failure-check",
                "corrupt GeoIP",
            ),
            flush=True,
        )
        shutil.copyfile(
            ROOT / "servidor/traefik/geoip/GeoLite2-Country.mmdb", geoip / "restored.mmdb"
        )
        (geoip / "restored.mmdb").replace(geoip / "GeoLite2-Country.mmdb")
        print(
            run("docker", "exec", checker, "python", "/work/fixture.py", "geoip-reloaded"),
            flush=True,
        )
        run(
            "docker",
            "exec",
            "-e",
            "REDISCLI_AUTH=" + cfg["redis_password"],
            redis,
            "redis-cli",
            "FLUSHDB",
        )
        print(
            run(
                "docker",
                "exec",
                checker,
                "python",
                "/work/fixture.py",
                "failure-check",
                "lost traffic epoch",
            ),
            flush=True,
        )
        print(
            run("docker", "exec", checker, "python", "/work/fixture.py", "recover-epoch"),
            flush=True,
        )
        run("docker", "restart", evaluator)
        print(
            run("docker", "exec", checker, "python", "/work/fixture.py", "restart-check"),
            flush=True,
        )
        for name in (gateway, traefik, mock):
            status = run("docker", "inspect", name, "--format", "{{.State.Running}}").strip()
            if status != "true":
                raise RuntimeError("Test service stopped")
    except BaseException:
        for name in containers:
            result = subprocess.run(
                ["docker", "logs", "--tail", "12", name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            print(name + ": " + result.stdout.decode("utf-8", errors="replace")[-1600:], flush=True)
        raise
    finally:
        for name in reversed(containers):
            subprocess.run(
                ["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        subprocess.run(
            ["docker", "network", "rm", network],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    main()
