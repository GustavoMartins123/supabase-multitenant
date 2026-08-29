#!/usr/bin/env python3
"""Render local Studio runtime files without placing secrets in tracked YAML."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO_ROOT = REPO_ROOT / "studio"
SERVER_ENV = REPO_ROOT / "servidor" / ".env"
STUDIO_ENV = STUDIO_ROOT / ".env"
CONFIG_TEMPLATE = STUDIO_ROOT / "authelia" / "configuration.yml.template"
CONFIG_TARGET = STUDIO_ROOT / "authelia" / "configuration.runtime.yml"
SECRETS_ROOT = STUDIO_ROOT / "secrets" / "authelia"
SSL_ROOT = STUDIO_ROOT / "authelia" / "ssl"

AUTHELIA_RUNTIME_SEEDS = (
    ("users_database.yml", 0o644),
    ("ids.yml", 0o644),
)
AUTHELIA_RUNTIME_EMPTY = (
    ("notifications.txt", 0o644),
    ("db.sqlite3", 0o644),
)

# A chave da CA fica no diretorio de secrets, que nao e bind-mounted em /config:
# so os arquivos declarados como docker secrets entram nos containers.
CA_KEY_NAME = "ca.key"

SECRET_FILES = ("JWT_SECRET", "SESSION_SECRET", "STORAGE_ENCRYPTION_KEY")
INTERNAL_SERVICE_HMAC_KEYS = (
    "STUDIO_GATEWAY_HMAC_SECRET",
    "PROJECTS_API_HMAC_SECRET",
)
STUDIO_ANALYTICS_HMAC_KEY = "STUDIO_ANALYTICS_HMAC_SECRET"


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


def seed_authelia_runtime_files(config_root: Path) -> tuple[str, ...]:
    """Materializa o runtime do Authelia a partir dos .example versionados.

    Nunca sobrescreve um arquivo existente: o conteudo vivo pertence ao
    Authelia, nao ao repositorio.
    """
    created: list[str] = []
    for name, mode in AUTHELIA_RUNTIME_SEEDS:
        target = config_root / name
        if target.exists():
            continue
        example = config_root / f"{name}.example"
        if not example.is_file():
            raise RuntimeConfigError(f"seed ausente: {example}")
        atomic_write(
            target,
            example.read_text(encoding="utf-8"),
            mode=mode,
            replace=False,
        )
        created.append(name)

    for name, mode in AUTHELIA_RUNTIME_EMPTY:
        target = config_root / name
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        target.chmod(mode)
        created.append(name)

    return tuple(created)


def _read_env_value(content: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}=(.*)$", content)
    if match is None:
        return None
    return match.group(1).strip()


def _set_env_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^{re.escape(key)}=.*$")
    replacement = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{replacement}\n"


def ensure_internal_service_hmac_secrets(
    server_env: Path = SERVER_ENV,
    studio_env: Path = STUDIO_ENV,
) -> bool:
    """Sincroniza chaves HMAC internas e mantém Analytics isolado no Studio.

    Instalacoes novas recebem segredos aleatorios distintos. Instalacoes
    existentes devem executar os scripts de migracao antes de subir uma versao
    que exija os novos valores; segredos explicitos nunca sao rotacionados aqui.
    """

    if not server_env.exists() and not studio_env.exists():
        return False
    if not server_env.is_file() or not studio_env.is_file():
        # O utilitario tambem pode ser usado isoladamente apenas para renderizar
        # Authelia/TLS; nesse caso nao transformamos ausencia de um .env em erro.
        return False

    server_content = server_env.read_text(encoding="utf-8")
    studio_content = studio_env.read_text(encoding="utf-8")
    resolved: dict[str, str] = {}

    for key in INTERNAL_SERVICE_HMAC_KEYS:
        server_value = _read_env_value(server_content, key) or ""
        studio_value = _read_env_value(studio_content, key) or ""
        if server_value and studio_value and server_value != studio_value:
            raise RuntimeConfigError(
                f"{key} diverge entre servidor/.env e studio/.env"
            )
        value = server_value or studio_value or secrets.token_hex(32)
        resolved[key] = value
        server_content = _set_env_value(server_content, key, value)
        studio_content = _set_env_value(studio_content, key, value)

    if resolved[INTERNAL_SERVICE_HMAC_KEYS[0]] == resolved[INTERNAL_SERVICE_HMAC_KEYS[1]]:
        raise RuntimeConfigError("segredos HMAC de servicos distintos nao podem ser iguais")

    analytics_secret = _read_env_value(studio_content, STUDIO_ANALYTICS_HMAC_KEY) or ""
    if not analytics_secret:
        analytics_secret = secrets.token_hex(32)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", analytics_secret):
        raise RuntimeConfigError("STUDIO_ANALYTICS_HMAC_SECRET deve conter 32 bytes em hexadecimal")
    if analytics_secret in resolved.values():
        raise RuntimeConfigError(
            "STUDIO_ANALYTICS_HMAC_SECRET deve ser distinto dos segredos de outros servicos"
        )
    studio_content = _set_env_value(
        studio_content,
        STUDIO_ANALYTICS_HMAC_KEY,
        analytics_secret,
    )

    server_mode = server_env.stat().st_mode & 0o777
    studio_mode = studio_env.stat().st_mode & 0o777
    atomic_write(
        server_env,
        server_content,
        mode=server_mode or 0o600,
        replace=True,
    )
    atomic_write(
        studio_env,
        studio_content,
        mode=studio_mode or 0o600,
        replace=True,
    )
    return True


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


def _run_openssl(arguments: list[str], failure: str) -> None:
    process = subprocess.run(
        ["openssl", *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeConfigError(f"{failure}: {process.stderr.strip()}")


def generate_ca(certificate: Path, private_key: Path, *, host: str) -> None:
    """Emite a ancora de confianca. A chave nunca entra no bind mount /config."""
    certificate.parent.mkdir(parents=True, exist_ok=True)
    private_key.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ca.", dir=certificate.parent) as name:
        temporary = Path(name)
        temporary_certificate = temporary / "ca.pem"
        temporary_key = temporary / "ca.key"
        _run_openssl(
            [
                "req", "-x509", "-nodes",
                "-newkey", "rsa:3072",
                "-sha256",
                "-days", "1825",
                "-subj", f"/CN=Supabase Multitenant Internal CA ({host})",
                "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign",
                "-keyout", str(temporary_key),
                "-out", str(temporary_certificate),
            ],
            "openssl nao conseguiu gerar a CA interna",
        )
        temporary_key.chmod(0o600)
        temporary_certificate.chmod(0o644)
        os.replace(temporary_certificate, certificate)
        os.replace(temporary_key, private_key)


def issue_server_certificate(
    root: Path,
    *,
    host: str,
    ca_certificate: Path,
    ca_key: Path,
) -> None:
    """Emite a folha servida por nginx e Authelia, assinada pela CA.

    A folha nao pode assinar outros certificados (CA:FALSE, sem keyCertSign),
    entao comprometer o processo web nao permite forjar hosts internos.
    """
    certificate = root / "server.pem"
    private_key = root / "server.key"
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".tls.", dir=root) as name:
        temporary = Path(name)
        temporary_key = temporary / "server.key"
        temporary_csr = temporary / "server.csr"
        temporary_certificate = temporary / "server.pem"
        extensions = temporary / "server.ext"
        extensions.write_text(
            "\n".join(
                (
                    "basicConstraints=critical,CA:FALSE",
                    "keyUsage=critical,digitalSignature,keyEncipherment",
                    "extendedKeyUsage=serverAuth",
                    f"subjectAltName={certificate_sans(host)}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        _run_openssl(
            [
                "req", "-nodes", "-new",
                "-newkey", "rsa:3072",
                "-sha256",
                "-subj", f"/CN={host}",
                "-keyout", str(temporary_key),
                "-out", str(temporary_csr),
            ],
            "openssl nao conseguiu gerar a CSR do servidor",
        )
        _run_openssl(
            [
                "x509", "-req",
                "-in", str(temporary_csr),
                "-CA", str(ca_certificate),
                "-CAkey", str(ca_key),
                "-CAcreateserial",
                "-CAserial", str(temporary / "ca.srl"),
                "-days", "825",
                "-sha256",
                "-extfile", str(extensions),
                "-out", str(temporary_certificate),
            ],
            "openssl nao conseguiu assinar o certificado do servidor",
        )
        temporary_key.chmod(0o600)
        temporary_certificate.chmod(0o644)
        os.replace(temporary_certificate, certificate)
        os.replace(temporary_key, private_key)


def generate_certificate(
    root: Path,
    *,
    host: str,
    replace: bool,
    ca_key: Path,
    rotate_ca: bool = False,
) -> bool:
    """Garante CA + folha; devolve True quando a CA foi (re)criada.

    Rotacionar a CA obriga a redistribuir ca.pem para todos os servicos, por
    isso e explicito: o padrao preserva a ancora existente e so reemite a folha.
    """
    ca_certificate = root / "ca.pem"
    legacy_ca_key = root / "ca.key"
    server_certificate = root / "server.pem"

    if not rotate_ca and ca_certificate.exists() and not ca_key.exists():
        # Deploy anterior ao split: a chave da CA ainda vivia dentro de /config.
        if legacy_ca_key.is_file():
            ca_key.parent.mkdir(parents=True, exist_ok=True)
            os.replace(legacy_ca_key, ca_key)
            ca_key.chmod(0o600)

    have_ca = ca_certificate.is_file() and ca_key.is_file()
    if have_ca and not rotate_ca:
        if server_certificate.exists() and not replace:
            raise RuntimeConfigError(
                f"certificado local ja existe em {root}; use --force para troca-lo"
            )
        created_ca = False
    else:
        if have_ca and not replace:
            raise RuntimeConfigError(
                f"CA local ja existe em {root}; use --force para troca-la"
            )
        generate_ca(ca_certificate, ca_key, host=host)
        created_ca = True

    issue_server_certificate(
        root, host=host, ca_certificate=ca_certificate, ca_key=ca_key
    )
    # A chave da CA nao pode permanecer no diretorio montado em /config.
    if legacy_ca_key.exists():
        legacy_ca_key.unlink()
    return created_ca


def configure_runtime(
    *,
    studio_origin: str,
    template: Path = CONFIG_TEMPLATE,
    target: Path = CONFIG_TARGET,
    secrets_root: Path = SECRETS_ROOT,
    ssl_root: Path = SSL_ROOT,
    force: bool = False,
    rotate_secrets: bool = False,
    rotate_ca: bool = False,
) -> None:
    origin, host = parse_origin(studio_origin)
    try:
        template_text = template.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeConfigError(f"template ausente: {template}") from exc
    rendered = render_configuration(template_text, origin=origin, host=host)

    if target.exists() and not force:
        raise RuntimeConfigError(f"configuracao local ja existe: {target}")
    hmac_configured = ensure_internal_service_hmac_secrets()
    seeded = seed_authelia_runtime_files(target.parent)
    ensure_secret_files(secrets_root, rotate=rotate_secrets)
    rotated_ca = generate_certificate(
        ssl_root,
        host=host,
        replace=force,
        ca_key=secrets_root / CA_KEY_NAME,
        rotate_ca=rotate_ca,
    )
    # This file contains only non-secret Authelia settings. Both the Authelia
    # process and the OpenResty worker need to read it from the shared bind
    # mount; secrets remain in the dedicated mode-0600 files below.
    atomic_write(target, rendered, mode=0o644, replace=force)

    print(f"Authelia renderizado para {host}; valores de segredo omitidos")
    print(f"Configuracao: {target}")
    print(f"Segredos: {secrets_root} (mode 0600)")
    print(f"TLS: {ssl_root} (folha server.pem; ancora ca.pem)")
    print(f"Chave da CA: {secrets_root / CA_KEY_NAME} (fora de /config)")
    if rotated_ca:
        print(
            "ATENCAO: a CA foi (re)criada. Redistribua studio/authelia/ssl/ca.pem "
            "para os servicos que a usam como ancora (setup.sh copia para "
            "servidor/certs/ca.pem)."
        )
    if seeded:
        print(f"Runtime do Authelia criado a partir dos seeds: {', '.join(seeded)}")
    if hmac_configured:
        print("HMAC interno por servico e Studio Analytics configurado")


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
    parser.add_argument(
        "--rotate-ca",
        action="store_true",
        help=(
            "recria a CA interna; exige redistribuir ca.pem para todos os "
            "servicos que a usam como ancora de confianca"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        configure_runtime(
            studio_origin=args.studio_origin,
            force=args.force,
            rotate_secrets=args.rotate_secrets,
            rotate_ca=args.rotate_ca,
        )
        return 0
    except (RuntimeConfigError, OSError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
