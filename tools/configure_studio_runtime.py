#!/usr/bin/env python3
"""Render local Studio runtime files without placing secrets in tracked YAML."""

from __future__ import annotations

import argparse
import ipaddress
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO_ROOT = REPO_ROOT / "studio"
CONFIG_TEMPLATE = STUDIO_ROOT / "authelia" / "configuration.yml.template"
CONFIG_TARGET = STUDIO_ROOT / "authelia" / "configuration.runtime.yml"
SECRETS_ROOT = STUDIO_ROOT / "secrets" / "authelia"
SSL_ROOT = STUDIO_ROOT / "authelia" / "ssl"

SECRET_FILES = ("JWT_SECRET", "SESSION_SECRET", "STORAGE_ENCRYPTION_KEY")


class RuntimeConfigError(RuntimeError):
    pass


def parse_origin(origin: str) -> tuple[str, str]:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path not in {"", "/"}:
        raise RuntimeConfigError("--studio-origin deve usar https://host[:porta]")
    try:
        parsed.port
    except ValueError as exc:
        raise RuntimeConfigError("porta invalida em --studio-origin") from exc
    return origin.rstrip("/"), parsed.hostname


def render_configuration(template: str, *, origin: str, host: str) -> str:
    if "__STUDIO_ORIGIN__" not in template or "__STUDIO_HOST__" not in template:
        raise RuntimeConfigError("template do Authelia nao contem os marcadores esperados")
    rendered = template.replace("__STUDIO_ORIGIN__", origin)
    rendered = rendered.replace("__STUDIO_HOST__", host)
    if "__STUDIO_" in rendered:
        raise RuntimeConfigError("marcador do Authelia nao foi renderizado")
    return rendered


def atomic_write(path: Path, content: str, *, mode: int, replace: bool) -> None:
    if path.exists() and not replace:
        raise RuntimeConfigError(f"destino ja existe: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            if not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def ensure_secret_files(root: Path, *, rotate: bool) -> tuple[Path, ...]:
    written: list[Path] = []
    for name in SECRET_FILES:
        path = root / name
        if path.exists() and not rotate:
            if not path.is_file() or not path.read_text(encoding="utf-8").strip():
                raise RuntimeConfigError(f"arquivo de segredo invalido: {path}")
            path.chmod(0o600)
            continue
        atomic_write(
            path,
            secrets.token_urlsafe(48),
            mode=0o600,
            replace=rotate,
        )
        written.append(path)
    return tuple(written)


def certificate_sans(host: str) -> str:
    entries = ["DNS:authelia", "DNS:nginx", "DNS:localhost", "IP:127.0.0.1"]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        item = f"DNS:{host}"
    else:
        item = f"IP:{address.compressed}"
    if item not in entries:
        entries.append(item)
    return ",".join(entries)


def generate_certificate(root: Path, *, host: str, replace: bool) -> None:
    certificate = root / "ca.pem"
    private_key = root / "ca.key"
    if (certificate.exists() or private_key.exists()) and not replace:
        raise RuntimeConfigError(
            f"certificado local ja existe em {root}; use --force para troca-lo"
        )
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tls.", dir=root) as temporary_name:
        temporary = Path(temporary_name)
        temporary_certificate = temporary / "ca.pem"
        temporary_key = temporary / "ca.key"
        process = subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-nodes",
                "-newkey",
                "rsa:3072",
                "-sha256",
                "-days",
                "825",
                "-subj",
                f"/CN={host}",
                "-addext",
                f"subjectAltName={certificate_sans(host)}",
                "-addext",
                "basicConstraints=critical,CA:TRUE",
                "-addext",
                "keyUsage=critical,digitalSignature,keyEncipherment,keyCertSign",
                "-keyout",
                str(temporary_key),
                "-out",
                str(temporary_certificate),
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if process.returncode != 0:
            raise RuntimeConfigError("openssl nao conseguiu gerar o certificado local")
        temporary_key.chmod(0o600)
        temporary_certificate.chmod(0o644)
        os.replace(temporary_key, private_key)
        os.replace(temporary_certificate, certificate)


def configure_runtime(
    *,
    studio_origin: str,
    template: Path = CONFIG_TEMPLATE,
    target: Path = CONFIG_TARGET,
    secrets_root: Path = SECRETS_ROOT,
    ssl_root: Path = SSL_ROOT,
    force: bool = False,
    rotate_secrets: bool = False,
) -> None:
    origin, host = parse_origin(studio_origin)
    try:
        template_text = template.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeConfigError(f"template ausente: {template}") from exc
    rendered = render_configuration(template_text, origin=origin, host=host)

    if target.exists() and not force:
        raise RuntimeConfigError(f"configuracao local ja existe: {target}")
    ensure_secret_files(secrets_root, rotate=rotate_secrets)
    generate_certificate(ssl_root, host=host, replace=force)
    # This file contains only non-secret Authelia settings. Both the Authelia
    # process and the OpenResty worker need to read it from the shared bind
    # mount; secrets remain in the dedicated mode-0600 files below.
    atomic_write(target, rendered, mode=0o644, replace=force)

    print(f"Authelia renderizado para {host}; valores de segredo omitidos")
    print(f"Configuracao: {target}")
    print(f"Segredos: {secrets_root} (mode 0600)")
    print(f"TLS: {ssl_root}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera configuracao, secrets e TLS locais do Studio."
    )
    parser.add_argument("--studio-origin", required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="atualiza configuracao e certificado existentes sem rotacionar secrets",
    )
    parser.add_argument(
        "--rotate-secrets",
        action="store_true",
        help="rotaciona explicitamente os secrets do Authelia",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        configure_runtime(
            studio_origin=args.studio_origin,
            force=args.force,
            rotate_secrets=args.rotate_secrets,
        )
        return 0
    except (RuntimeConfigError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
