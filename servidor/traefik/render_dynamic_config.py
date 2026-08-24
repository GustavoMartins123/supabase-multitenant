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

TRUE_VALUES = {"1", "true", "yes", "on"}
TLS_MODES = {"file", "acme"}
TLS_CERT_NAME = "tls.crt"
TLS_KEY_NAME = "tls.key"
CONTAINER_CERT_DIR = "/certs/traefik"


def parse_bool(key: str, raw: str) -> bool:
    value = (raw or "").strip().lower()
    if not value:
        return False
    if value in TRUE_VALUES:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{key} deve ser booleano (true/false); recebido: {raw!r}"
    )


def resolve_tls_settings(settings: dict[str, str], cert_dir: pathlib.Path | None) -> dict[str, object]:
    enable = parse_bool("TRAEFIK_ENABLE_TLS", settings.get("TRAEFIK_ENABLE_TLS", "false"))
    proto = (settings.get("SERVER_PROTO", "") or "").strip().lower()
    if proto == "https" and not enable:
        raise ValueError(
            "SERVER_PROTO=https exige TRAEFIK_ENABLE_TLS=true; recusando gerar "
            "configuracao sem routers TLS."
        )
    https_port = (settings.get("TRAEFIK_HTTPS_PORT", "443") or "").strip()
    if not https_port.isdigit():
        raise ValueError("TRAEFIK_HTTPS_PORT deve ser numerica")
    mode = (settings.get("TRAEFIK_TLS_MODE", "file") or "file").strip().lower() or "file"
    if mode not in TLS_MODES:
        raise ValueError(f"TRAEFIK_TLS_MODE deve ser um de {sorted(TLS_MODES)}; recebido: {mode!r}")
    tls_block: list[str] = []
    if enable:
        if mode == "acme":
            email = (settings.get("TRAEFIK_ACME_EMAIL", "") or "").strip()
            if not email or email.lower() == "pass":
                raise ValueError(
                    "TRAEFIK_ACME_EMAIL ausente ou placeholder; obrigatorio no modo acme."
                )
            tls_block = ["      tls:", "        certResolver: letsencrypt"]
        else:
            base = cert_dir if cert_dir is not None else pathlib.Path(CONTAINER_CERT_DIR)
            cert_file = base / TLS_CERT_NAME
            key_file = base / TLS_KEY_NAME
            missing = [str(item) for item in (cert_file, key_file) if not item.is_file()]
            if missing:
                raise ValueError(
                    "TRAEFIK_TLS_MODE=file exige "
                    f"{TLS_CERT_NAME} e {TLS_KEY_NAME} em {base}; ausentes: {missing}"
                )
            container_cert = f"{CONTAINER_CERT_DIR}/{TLS_CERT_NAME}"
            container_key = f"{CONTAINER_CERT_DIR}/{TLS_KEY_NAME}"
            tls_block = [
                "      tls:",
                f"        certFile: {yaml_quote(container_cert)}",
                f"        keyFile: {yaml_quote(container_key)}",
            ]
    return {
        "enable": enable,
        "mode": mode,
        "https_port": https_port,
        "tls_block": tls_block,
    }


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


def render(
    root_env: pathlib.Path,
    projects_dir: pathlib.Path,
    cert_dir: pathlib.Path | None = None,
) -> str:
    settings = read_env(root_env)
    api_port = settings.get("PROJECTS_API_PORT", "18000")
    if not api_port.isdigit():
        raise ValueError("PROJECTS_API_PORT deve ser numerica")
    allowed_ranges = [
        item.strip()
        for item in settings.get(
            "PROJECTS_API_ALLOWED_IP_RANGES", "172.50.0.0/16"
        ).split(",")
        if item.strip()
    ]
    tls = resolve_tls_settings(settings, cert_dir)
    enable_tls: bool = tls["enable"]
    tls_block: list[str] = list(tls["tls_block"])  # type: ignore[arg-type]
    entry_points = ["websecure"] if enable_tls else ["web"]

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
            "PathPrefix(`/api/projects`) || PathPrefix(`/api/jobs`) || "
            "PathPrefix(`/api/admin`) || PathPrefix(`/api/internal/analytics`)"
        ),
        "      entryPoints:",
    ]
    lines.extend(f"        - {item}" for item in entry_points)
    if enable_tls:
        lines.extend(tls_block)
    lines.extend(
        [
            "      priority: 1000",
            "      middlewares:",
            "        - projects-api-allowlist",
            "        - api-security-chain",
            "      service: projects-api",
        ]
    )
    for project_id, _ in projects:
        lines.extend(
            [
                f"    project-{project_id}:",
                f"      rule: \"Path(`/{project_id}`) || PathPrefix(`/{project_id}/`)\"",
                "      entryPoints:",
            ]
        )
        lines.extend(f"        - {item}" for item in entry_points)
        if enable_tls:
            lines.extend(tls_block)
        lines.extend(
            [
                "      priority: 500",
                "      middlewares:",
                "        - rate-limit",
                f"        - project-guard-{project_id}",
                "        - security-headers",
                f"        - project-strip-{project_id}",
                f"      service: project-{project_id}",
            ]
        )

    if enable_tls:
        # Router de redirecionamento: acima do http-catchall (100) para vencer o
        # catch-all, abaixo dos routers de scanner (>=1900) que devem continuar
        # respondendo em HTTP puro antes de qualquer redirecionamento.
        lines.extend(
            [
                "    force-https:",
                "      rule: \"HostRegexp(`{host:.+}`)\"",
                "      entryPoints:",
                "        - web",
                "      priority: 150",
                "      middlewares:",
                "        - force-https-redirect",
                "      service: noop@internal",
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
    if enable_tls:
        lines.extend(
            [
                "    force-https-redirect:",
                "      redirectScheme:",
                "        scheme: https",
                f"        port: \"{tls['https_port']}\"",
                "        permanent: true",
            ]
        )
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
    parser.add_argument("--tls-cert-dir", type=pathlib.Path, default=None)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=2.0)
    args = parser.parse_args()

    while True:
        write_atomic(
            args.output.parent / "00-middlewares.yml",
            args.middlewares_file.read_text(encoding="utf-8"),
        )
        write_atomic(args.output, render(args.root_env, args.projects_dir, args.tls_cert_dir))
        if not args.watch:
            return 0
        time.sleep(max(args.interval, 0.5))


if __name__ == "__main__":
    raise SystemExit(main())
