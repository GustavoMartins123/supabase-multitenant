#!/usr/bin/env python3
"""Stage current server env files from an extracted legacy server tree.

Only ``.env`` and ``docker-compose.yml`` are read from the legacy directory.
The tool never sources dotenv files, never prints their values and never
inspects archives, PostgreSQL data, backups or project contents.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from migrate_legacy_studio import (
    EnvDocument,
    MigrationError,
    atomic_write,
    clean_value,
    generate_secret,
    is_placeholder,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TEMPLATE = REPO_ROOT / "servidor" / ".env.example"
ANALYTICS_TEMPLATE = REPO_ROOT / "servidor" / ".analytics.env.example"
MAIN_TARGET = REPO_ROOT / "servidor" / ".env"
ANALYTICS_TARGET = REPO_ROOT / "servidor" / ".analytics.env"
LEGACY_SECRET_TARGET = REPO_ROOT / "servidor" / ".legacy-migration.env"
STUDIO_ENV = REPO_ROOT / "studio" / ".env"
STUDIO_ANALYTICS_ENV = REPO_ROOT / "studio" / ".analytics.env"

SHARED_MAIN_KEYS = (
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
    "NGINX_SHARED_TOKEN",
    "NGINX_HMAC_SECRET",
    "INTERNAL_HMAC_SECRET",
)
GENERATED_MAIN_KEYS = {
    "META_GUEST_PASSWORD": "password",
    "HOST_AGENT_HMAC_SECRET": "hmac",
    "PROJECT_SECRETS_MASTER_KEY": "fernet",
    "PG_META_CRYPTO_KEY": "hmac",
}
DEPRECATED_KEYS = {
    "FERNET_SECRET": "movida para .legacy-migration.env",
    "LOGFLARE_API_KEY": "movida para LOGFLARE_PUBLIC_ACCESS_TOKEN",
    "PGRST_DB_SCHEMAS": "configuracao agora pertence ao .env de cada projeto",
    "PUSH_WORKER_TOKEN": "substituida pelo canal interno assinado com HMAC",
}
REQUIRED_MAIN_KEYS = (
    "POSTGRES_HOST",
    "POSTGRES_POOLER",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "META_GUEST_PASSWORD",
    "DB_ENC_KEY",
    "VAULT_ENC_KEY",
    "SECRET_KEY_BASE",
    "JWT_SECRET",
    "SERVER_URL",
    "SERVER_PROTO",
    "HOST_PROJECT_ROOT",
    "HOST_AGENT_HMAC_SECRET",
    "PROJECT_SECRETS_MASTER_KEY",
    "PG_META_CRYPTO_KEY",
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
    "NGINX_SHARED_TOKEN",
    "NGINX_HMAC_SECRET",
    "INTERNAL_HMAC_SECRET",
    "PROJECT_DELETE_PASSWORD",
    "DASHBOARD_USER",
    "DASHBOARD_PASSWORD",
    "SUPABASE_NETWORK_SUBNET",
    "SUPABASE_NETWORK_IP_RANGE",
    "SUPABASE_NETWORK_GATEWAY",
)
REQUIRED_ANALYTICS_KEYS = (
    "LOGFLARE_PUBLIC_ACCESS_TOKEN",
    "LOGFLARE_PRIVATE_ACCESS_TOKEN",
    "LOGFLARE_DB_ENCRYPTION_KEY",
)
NETWORK_FIELDS = {
    "subnet": "SUPABASE_NETWORK_SUBNET",
    "ip_range": "SUPABASE_NETWORK_IP_RANGE",
    "gateway": "SUPABASE_NETWORK_GATEWAY",
}
NETWORK_PATTERN = re.compile(
    r"^\s*-?\s*(subnet|ip_range|gateway):\s*([^\s#]+)", re.MULTILINE
)


@dataclass(frozen=True)
class ServerEnvMigration:
    main_text: str
    analytics_text: str
    legacy_secret_text: str
    preserved: tuple[str, ...]
    generated: tuple[str, ...]
    normalized: tuple[str, ...]
    deprecated: tuple[str, ...]
    unresolved: tuple[str, ...]
    legacy_secret_ready: bool


def read_optional(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    return EnvDocument.read(path).values


def generate_server_secret(kind: str) -> str:
    if kind in {"fernet", "hmac", "token"}:
        return generate_secret(kind)
    if kind == "password":
        return secrets.token_urlsafe(32)
    if kind == "base64-32":
        return base64.b64encode(secrets.token_bytes(32)).decode("ascii")
    raise MigrationError(f"gerador de segredo desconhecido: {kind}")


def is_fernet_key(raw: str | None) -> bool:
    value = clean_value(raw)
    try:
        return len(base64.urlsafe_b64decode(value.encode("ascii"))) == 32
    except (ValueError, UnicodeEncodeError):
        return False


def dotenv_quote(value: str) -> str:
    if "\n" in value or "\r" in value or "\x00" in value:
        raise MigrationError("valor dotenv nao pode conter quebra de linha ou byte nulo")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def generate_service_jwt(jwt_secret: str, role: str) -> str:
    now = int(time.time())
    header = b64url(json.dumps(
        {"alg": "HS256", "typ": "JWT"}, separators=(",", ":")
    ).encode("utf-8"))
    payload = b64url(json.dumps(
        {
            "role": role,
            "iss": "supabase",
            "iat": now,
            "exp": now + 315_360_000,
        },
        separators=(",", ":"),
    ).encode("utf-8"))
    signature = hmac.new(
        jwt_secret.encode("utf-8"),
        f"{header}.{payload}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{header}.{payload}.{b64url(signature)}"


def parse_legacy_network(compose_path: Path) -> dict[str, str]:
    try:
        compose = compose_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MigrationError(f"compose legado ausente: {compose_path}") from exc

    discovered: dict[str, str] = {}
    for field, value in NETWORK_PATTERN.findall(compose):
        discovered[NETWORK_FIELDS[field]] = value
    missing = sorted(set(NETWORK_FIELDS.values()) - set(discovered))
    if missing:
        raise MigrationError(
            "rede legada incompleta no docker-compose.yml: " + ", ".join(missing)
        )
    try:
        subnet = ipaddress.ip_network(discovered["SUPABASE_NETWORK_SUBNET"])
        ip_range = ipaddress.ip_network(discovered["SUPABASE_NETWORK_IP_RANGE"])
        gateway = ipaddress.ip_address(discovered["SUPABASE_NETWORK_GATEWAY"])
    except ValueError as exc:
        raise MigrationError("rede legada invalida") from exc
    if not ip_range.subnet_of(subnet) or gateway not in subnet:
        raise MigrationError("ip_range/gateway nao pertencem a subnet legada")
    return discovered


def normalized_origin(raw: str, key: str, *, https_only: bool = False) -> str:
    value = clean_value(raw).rstrip("/")
    parsed = urlsplit(value)
    allowed = {"https"} if https_only else {"http", "https"}
    if parsed.scheme not in allowed or not parsed.hostname or parsed.path:
        raise MigrationError(f"{key} deve ser uma origem HTTP(S) sem caminho")
    return value


def _host_from_server(main_values: dict[str, str]) -> str:
    host = clean_value(main_values.get("SERVER_URL"))
    if "://" in host:
        parsed = urlsplit(host)
        return parsed.hostname or ""
    return host.split(":", 1)[0]


def _effective(template: EnvDocument, overrides: dict[str, str]) -> dict[str, str]:
    values = dict(template.values)
    values.update(overrides)
    return values


def build_server_migration(
    legacy_root: Path,
    *,
    main_template: Path = MAIN_TEMPLATE,
    analytics_template: Path = ANALYTICS_TEMPLATE,
    studio_env: Path = STUDIO_ENV,
    studio_analytics_env: Path = STUDIO_ANALYTICS_ENV,
    host_project_root: Path = REPO_ROOT,
    current_env: Path | None = None,
    current_analytics_env: Path | None = None,
) -> ServerEnvMigration:
    legacy_root = legacy_root.resolve()
    if not legacy_root.is_dir():
        raise MigrationError("legacy_root deve ser uma pasta descompactada")

    legacy = EnvDocument.read(legacy_root / ".env")
    main = EnvDocument.read(main_template)
    analytics = EnvDocument.read(analytics_template)
    studio = EnvDocument.read(studio_env)
    studio_analytics = EnvDocument.read(studio_analytics_env)
    current = read_optional(current_env)
    current_analytics = read_optional(current_analytics_env)

    main_overrides = {
        key: value for key, value in legacy.values.items() if key in main.values
    }
    preserved = set(main_overrides)
    generated: set[str] = set()
    normalized: set[str] = set()

    network = parse_legacy_network(legacy_root / "docker-compose.yml")
    main_overrides.update(network)
    normalized.update(network)
    for address_key in ("POSTGRES_HOST", "POSTGRES_POOLER"):
        try:
            if ipaddress.ip_address(clean_value(main_overrides[address_key])) not in ipaddress.ip_network(
                network["SUPABASE_NETWORK_SUBNET"]
            ):
                raise MigrationError(f"{address_key} nao pertence a subnet legada")
        except KeyError as exc:
            raise MigrationError(f"{address_key} ausente no .env legado") from exc
        except ValueError as exc:
            raise MigrationError(f"{address_key} invalido no .env legado") from exc

    resolved_root = host_project_root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise MigrationError("--host-project-root deve apontar para uma pasta existente")
    main_overrides["HOST_PROJECT_ROOT"] = dotenv_quote(str(resolved_root))
    normalized.add("HOST_PROJECT_ROOT")
    preserved.discard("HOST_PROJECT_ROOT")

    for key in SHARED_MAIN_KEYS:
        value = studio.values.get(key)
        if is_placeholder(value):
            raise MigrationError(f"{key} ausente ou placeholder no Studio")
        main_overrides[key] = value
        normalized.add(key)
        preserved.discard(key)

    for key, kind in GENERATED_MAIN_KEYS.items():
        existing = current.get(key)
        if not is_placeholder(existing):
            main_overrides[key] = existing
            preserved.add(key)
        else:
            main_overrides[key] = generate_server_secret(kind)
            generated.add(key)

    if not is_fernet_key(main_overrides["PROJECT_SECRETS_MASTER_KEY"]):
        raise MigrationError("PROJECT_SECRETS_MASTER_KEY nao e uma chave Fernet valida")
    if not is_fernet_key(main_overrides["STUDIO_SERVICE_KEY_ENCRYPTION_KEY"]):
        raise MigrationError("STUDIO_SERVICE_KEY_ENCRYPTION_KEY do Studio e invalida")
    if hmac.compare_digest(
        clean_value(main_overrides["PROJECT_SECRETS_MASTER_KEY"]),
        clean_value(main_overrides["STUDIO_SERVICE_KEY_ENCRYPTION_KEY"]),
    ):
        raise MigrationError("as chaves Fernet de dados e transporte devem ser distintas")

    studio_origin = normalized_origin(
        studio.values.get("SUPABASE_PUBLIC_URL", ""),
        "SUPABASE_PUBLIC_URL do Studio",
        https_only=True,
    )
    studio_host = urlsplit(studio_origin).hostname or ""
    main_overrides["PUSH_API_URL"] = f"{studio_origin}/api/internal/push"
    main_overrides["FUNCTIONS_SUPABASE_URL"] = studio_origin
    normalized.update({"PUSH_API_URL", "FUNCTIONS_SUPABASE_URL"})

    effective_before_network = _effective(main, main_overrides)
    server_host = _host_from_server(effective_before_network)
    if not server_host:
        raise MigrationError("SERVER_URL legado invalido")
    try:
        studio_ip = ipaddress.ip_address(studio_host)
    except ValueError:
        studio_ip = None
    if studio_ip is not None:
        main_overrides["PROJECTS_API_ALLOWED_IP_RANGES"] = (
            f"{studio_ip}/32,{network['SUPABASE_NETWORK_SUBNET']}"
        )
        normalized.add("PROJECTS_API_ALLOWED_IP_RANGES")
    main_overrides["VECTOR_FLUENTD_BIND"] = (
        "127.0.0.1" if studio_host == server_host else "0.0.0.0"
    )
    normalized.add("VECTOR_FLUENTD_BIND")

    jwt_secret = clean_value(main_overrides.get("JWT_SECRET"))
    if is_placeholder(jwt_secret):
        raise MigrationError("JWT_SECRET legado ausente")
    for key, role in {
        "FUNCTIONS_SUPABASE_ANON_KEY": "anon",
        "FUNCTIONS_SUPABASE_SERVICE_ROLE_KEY": "service_role",
    }.items():
        existing = current.get(key)
        if existing and existing.count(".") == 2:
            main_overrides[key] = existing
            preserved.add(key)
        else:
            main_overrides[key] = generate_service_jwt(jwt_secret, role)
            generated.add(key)

    analytics_overrides: dict[str, str] = {}
    legacy_public = legacy.values.get("LOGFLARE_API_KEY")
    if not is_placeholder(legacy_public):
        analytics_overrides["LOGFLARE_PUBLIC_ACCESS_TOKEN"] = legacy_public
        preserved.add("LOGFLARE_API_KEY")
        normalized.add("LOGFLARE_PUBLIC_ACCESS_TOKEN")
    elif not is_placeholder(current_analytics.get("LOGFLARE_PUBLIC_ACCESS_TOKEN")):
        analytics_overrides["LOGFLARE_PUBLIC_ACCESS_TOKEN"] = current_analytics[
            "LOGFLARE_PUBLIC_ACCESS_TOKEN"
        ]
        preserved.add("LOGFLARE_PUBLIC_ACCESS_TOKEN")
    else:
        analytics_overrides["LOGFLARE_PUBLIC_ACCESS_TOKEN"] = generate_server_secret(
            "token"
        )
        generated.add("LOGFLARE_PUBLIC_ACCESS_TOKEN")

    private_token = studio_analytics.values.get("LOGFLARE_PRIVATE_ACCESS_TOKEN")
    if is_placeholder(private_token):
        raise MigrationError("LOGFLARE_PRIVATE_ACCESS_TOKEN ausente no Studio")
    analytics_overrides["LOGFLARE_PRIVATE_ACCESS_TOKEN"] = private_token
    normalized.add("LOGFLARE_PRIVATE_ACCESS_TOKEN")

    existing_db_key = current_analytics.get("LOGFLARE_DB_ENCRYPTION_KEY")
    if not is_placeholder(existing_db_key):
        analytics_overrides["LOGFLARE_DB_ENCRYPTION_KEY"] = existing_db_key
        preserved.add("LOGFLARE_DB_ENCRYPTION_KEY")
    else:
        analytics_overrides["LOGFLARE_DB_ENCRYPTION_KEY"] = generate_server_secret(
            "base64-32"
        )
        generated.add("LOGFLARE_DB_ENCRYPTION_KEY")

    if hmac.compare_digest(
        clean_value(analytics_overrides["LOGFLARE_PUBLIC_ACCESS_TOKEN"]),
        clean_value(analytics_overrides["LOGFLARE_PRIVATE_ACCESS_TOKEN"]),
    ):
        raise MigrationError("tokens publico e privado do Logflare devem ser distintos")

    effective_main = _effective(main, main_overrides)
    effective_analytics = _effective(analytics, analytics_overrides)
    unresolved = {
        key for key in REQUIRED_MAIN_KEYS if is_placeholder(effective_main.get(key))
    }
    unresolved.update(
        key
        for key in REQUIRED_ANALYTICS_KEYS
        if is_placeholder(effective_analytics.get(key))
    )
    if studio_ip is None:
        unresolved.add("PROJECTS_API_ALLOWED_IP_RANGES")

    legacy_fernet = legacy.values.get("FERNET_SECRET", "")
    legacy_ready = is_fernet_key(legacy_fernet)
    if not legacy_ready:
        unresolved.add("LEGACY_FERNET_SECRET")
    legacy_secret_text = (
        "# Uso temporario: remova apos migrate_project_secrets --apply.\n"
        f"LEGACY_FERNET_SECRET={legacy_fernet}\n"
    )

    return ServerEnvMigration(
        main_text=main.render(main_overrides),
        analytics_text=analytics.render(analytics_overrides),
        legacy_secret_text=legacy_secret_text,
        preserved=tuple(sorted(preserved)),
        generated=tuple(sorted(generated)),
        normalized=tuple(sorted(normalized)),
        deprecated=tuple(sorted(set(legacy.values) & set(DEPRECATED_KEYS))),
        unresolved=tuple(sorted(unresolved)),
        legacy_secret_ready=legacy_ready,
    )


def print_names(label: str, names: tuple[str, ...]) -> None:
    print(f"{label}: {', '.join(names) if names else 'nenhuma'}")


def print_report(result: ServerEnvMigration, *, wrote: bool) -> None:
    print("Migracao de configuracao do servidor")
    print_names("  preservadas", result.preserved)
    print_names("  geradas", result.generated)
    print_names("  normalizadas/sincronizadas", result.normalized)
    print_names("  legadas retiradas do runtime", result.deprecated)
    print_names("  pendencias", result.unresolved)
    print(
        "  segredo Fernet legado: pronto para migracao unica"
        if result.legacy_secret_ready
        else "  segredo Fernet legado: ausente ou invalido"
    )
    print("  valores: omitidos intencionalmente")
    print("Saida: arquivos gravados" if wrote else "Saida: dry-run, nenhum arquivo gravado")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra envs de uma pasta de servidor legado descompactada."
    )
    parser.add_argument("legacy_root", type=Path, help="pasta legada descompactada")
    parser.add_argument("--host-project-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--studio-env", type=Path, default=STUDIO_ENV)
    parser.add_argument(
        "--studio-analytics-env", type=Path, default=STUDIO_ANALYTICS_ENV
    )
    parser.add_argument("--target-env", type=Path, default=MAIN_TARGET)
    parser.add_argument(
        "--target-analytics-env", type=Path, default=ANALYTICS_TARGET
    )
    parser.add_argument(
        "--target-legacy-secret", type=Path, default=LEGACY_SECRET_TARGET
    )
    parser.add_argument("--write-env", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--strict", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        result = build_server_migration(
            args.legacy_root,
            studio_env=args.studio_env,
            studio_analytics_env=args.studio_analytics_env,
            host_project_root=args.host_project_root,
            current_env=args.target_env,
            current_analytics_env=args.target_analytics_env,
        )
        if args.strict and result.unresolved:
            print_report(result, wrote=False)
            return 2
        targets = (
            (args.target_env, result.main_text),
            (args.target_analytics_env, result.analytics_text),
            (args.target_legacy_secret, result.legacy_secret_text),
        )
        if args.write_env:
            existing = [str(path) for path, _ in targets if path.exists()]
            if existing and not args.force:
                raise MigrationError(
                    "destinos ja existem (use --force): " + ", ".join(existing)
                )
            for path, content in targets:
                atomic_write(path, content, force=args.force)
        print_report(result, wrote=args.write_env)
        return 0
    except MigrationError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
