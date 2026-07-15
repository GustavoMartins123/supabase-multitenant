#!/usr/bin/env python3
"""Renderiza a configuracao dinamica completa do Traefik sem consultar Docker."""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import tempfile
import time
import uuid


PROJECT_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")


def read_env(path: pathlib.Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render(root_env: pathlib.Path, projects_dir: pathlib.Path) -> str:
    settings = read_env(root_env)
    api_port = settings.get("PROJECTS_API_PORT", "18000")
    if not api_port.isdigit():
        raise ValueError("PROJECTS_API_PORT deve ser numerica")
    shared_token = settings.get("NGINX_SHARED_TOKEN", "")
    if not shared_token:
        raise ValueError("NGINX_SHARED_TOKEN ausente")
    if "`" in shared_token or "\n" in shared_token or "\r" in shared_token:
        raise ValueError("NGINX_SHARED_TOKEN contem caractere invalido")
    allowed_ranges = [
        item.strip()
        for item in settings.get(
            "PROJECTS_API_ALLOWED_IP_RANGES", "172.50.0.0/16"
        ).split(",")
        if item.strip()
    ]

    guard = {
        "mode": settings.get("TRAEFIK_GUARD_PROJECT_MODE", "observe"),
        "maxTrackedClients": settings.get("TRAEFIK_GUARD_MAX_TRACKED_CLIENTS", "10000"),
        "cleanupInterval": settings.get("TRAEFIK_GUARD_CLEANUP_INTERVAL", "5m"),
        "authThreshold": settings.get("TRAEFIK_GUARD_AUTH_THRESHOLD", "12"),
        "authWindow": settings.get("TRAEFIK_GUARD_AUTH_WINDOW", "10m"),
        "authBanTime": settings.get("TRAEFIK_GUARD_AUTH_BAN_TIME", "15m"),
        "scannerThreshold": settings.get("TRAEFIK_GUARD_SCANNER_THRESHOLD", "2"),
        "scannerWindow": settings.get("TRAEFIK_GUARD_SCANNER_WINDOW", "2m"),
        "scannerBanTime": settings.get("TRAEFIK_GUARD_SCANNER_BAN_TIME", "1h"),
    }

    projects: list[tuple[str, str]] = []
    if projects_dir.is_dir():
        for project_dir in sorted(projects_dir.iterdir(), key=lambda path: path.name):
            if not project_dir.is_dir() or not PROJECT_RE.fullmatch(project_dir.name):
                continue
            project_env = read_env(project_dir / ".env")
            project_id = project_env.get("PROJECT_ID", project_dir.name)
            project_uuid = project_env.get("PROJECT_UUID", "")
            if project_id != project_dir.name or not PROJECT_RE.fullmatch(project_id):
                continue
            try:
                project_uuid = str(uuid.UUID(project_uuid))
            except ValueError:
                continue
            projects.append((project_id, project_uuid))

    lines = [
        "# Gerado por render_dynamic_config.py. Nao edite manualmente.",
        "http:",
        "  routers:",
        "    projects-api:",
        "      rule: " + yaml_quote(
            "(PathPrefix(`/api/projects`) || PathPrefix(`/api/internal/analytics`)) "
            f"&& Header(`X-Shared-Token`, `{shared_token}`)"
        ),
        "      entryPoints:",
        "        - web",
        "      priority: 1000",
        "      middlewares:",
        "        - projects-api-allowlist",
        "        - api-security-chain",
        "      service: projects-api",
    ]
    for project_id, _ in projects:
        lines.extend(
            [
                f"    project-{project_id}:",
                f"      rule: \"Path(`/{project_id}`) || PathPrefix(`/{project_id}/`)\"",
                "      entryPoints:",
                "        - web",
                "      priority: 500",
                "      middlewares:",
                "        - rate-limit",
                f"        - project-guard-{project_id}",
                "        - security-headers",
                f"        - project-strip-{project_id}",
                f"      service: project-{project_id}",
            ]
        )

    lines.extend(
        [
            "  middlewares:",
            "    projects-api-allowlist:",
            "      ipAllowList:",
            "        sourceRange:",
        ]
    )
    lines.extend(f"          - {yaml_quote(item)}" for item in allowed_ranges)
    for project_id, project_uuid in projects:
        lines.extend(
            [
                f"    project-guard-{project_id}:",
                "      plugin:",
                "        supabaseguard:",
                "          profile: project",
                f"          mode: {yaml_quote(guard['mode'])}",
                f"          scope: {yaml_quote(project_uuid)}",
                f"          maxTrackedClients: {guard['maxTrackedClients']}",
                f"          cleanupInterval: {yaml_quote(guard['cleanupInterval'])}",
                f"          authThreshold: {guard['authThreshold']}",
                f"          authWindow: {yaml_quote(guard['authWindow'])}",
                f"          authBanTime: {yaml_quote(guard['authBanTime'])}",
                f"          scannerThreshold: {guard['scannerThreshold']}",
                f"          scannerWindow: {yaml_quote(guard['scannerWindow'])}",
                f"          scannerBanTime: {yaml_quote(guard['scannerBanTime'])}",
                f"    project-strip-{project_id}:",
                "      stripPrefix:",
                "        prefixes:",
                f"          - \"/{project_id}\"",
            ]
        )

    lines.extend(
        [
            "  services:",
            "    projects-api:",
            "      loadBalancer:",
            "        servers:",
            f"          - url: \"http://projects-api:{api_port}\"",
        ]
    )
    for project_id, _ in projects:
        lines.extend(
            [
                f"    project-{project_id}:",
                "      loadBalancer:",
                "        servers:",
                f"          - url: \"http://supabase-nginx-{project_id}:8080\"",
            ]
        )
    return "\n".join(lines) + "\n"


def write_atomic(output: pathlib.Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    current = output.read_text(encoding="utf-8") if output.exists() else None
    if current == content:
        return
    fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root-env", type=pathlib.Path, required=True)
    parser.add_argument("--projects-dir", type=pathlib.Path, required=True)
    parser.add_argument("--middlewares-file", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    while True:
        write_atomic(
            args.output.parent / "00-middlewares.yml",
            args.middlewares_file.read_text(encoding="utf-8"),
        )
        write_atomic(args.output, render(args.root_env, args.projects_dir))
        if not args.watch:
            return 0
        time.sleep(max(args.interval, 0.5))


if __name__ == "__main__":
    raise SystemExit(main())
