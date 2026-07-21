#!/usr/bin/env python3
"""Audit a legacy Studio tree and stage its environment for the current layout.

The tool deliberately accepts an extracted directory only.  It never sources a
dotenv file and it does not inspect snippets, PostgreSQL data, Authelia state,
certificates or archives.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import re
import secrets
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_TEMPLATE = REPO_ROOT / "studio" / ".env.example"
ANALYTICS_TEMPLATE = REPO_ROOT / "studio" / ".analytics.env.example"
MAIN_TARGET = REPO_ROOT / "studio" / ".env"
ANALYTICS_TARGET = REPO_ROOT / "studio" / ".analytics.env"

ASSIGNMENT = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
DEPRECATED_KEYS = {
    "AUTHELIA_PASS": "nao e consumida pelo compose atual",
    "COOKIE_SIGN_SECRET": "cookies legados foram substituidos por identidade assinada",
    "FERNET_SECRET": "pertence somente a migracao dos segredos legados no servidor",
    "PUSH_WORKER_TOKEN": "foi substituida por requisicoes internas assinadas com HMAC",
    "STUDIO_DB": "nao e consumida pelo Studio atual",
}
SHARED_MAIN_KEYS = (
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY",
    "NGINX_SHARED_TOKEN",
    "NGINX_HMAC_SECRET",
    "INTERNAL_HMAC_SECRET",
)
GENERATED_MAIN_KEYS = {
    "STUDIO_SERVICE_KEY_ENCRYPTION_KEY": "fernet",
    "NGINX_SHARED_TOKEN": "token",
    "NGINX_HMAC_SECRET": "hmac",
    "INTERNAL_HMAC_SECRET": "hmac",
}
REQUIRED_MAIN_KEYS = (
    *SHARED_MAIN_KEYS,
    "SERVER_DOMAIN",
    "BACKEND_PROTO",
    "SUPABASE_PUBLIC_URL",
    "POSTGRES_NGINX_PASSWORD",
    "DATABASE_URL",
)
REQUIRED_ANALYTICS_KEYS = ("LOGFLARE_PRIVATE_ACCESS_TOKEN",)


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnvDocument:
    lines: tuple[str, ...]
    values: dict[str, str]

    @classmethod
    def read(cls, path: Path) -> "EnvDocument":
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise MigrationError(f"arquivo obrigatorio ausente: {path}") from exc

        values: dict[str, str] = {}
        lines = tuple(text.splitlines(keepends=True))
        for number, line in enumerate(lines, start=1):
            match = ASSIGNMENT.match(line.rstrip("\r\n"))
            if not match:
                continue
            key, value = match.groups()
            if key in values:
                raise MigrationError(f"chave duplicada em {path}:{number}: {key}")
            values[key] = value
        return cls(lines=lines, values=values)

    def render(self, overrides: dict[str, str]) -> str:
        unknown = sorted(set(overrides) - set(self.values))
        if unknown:
            raise MigrationError(
                "chaves ausentes no template: " + ", ".join(unknown)
            )

        rendered: list[str] = []
        for line in self.lines:
            match = ASSIGNMENT.match(line.rstrip("\r\n"))
            if not match or match.group(1) not in overrides:
                rendered.append(line)
                continue
            ending = "\n" if line.endswith(("\n", "\r\n")) else ""
            rendered.append(f"{match.group(1)}={overrides[match.group(1)]}{ending}")
        return "".join(rendered)


@dataclass(frozen=True)
class EnvMigration:
    main_text: str
    analytics_text: str
    preserved: tuple[str, ...]
    generated: tuple[str, ...]
    deprecated: tuple[str, ...]
    normalized: tuple[str, ...]
    unresolved: tuple[str, ...]


@dataclass(frozen=True)
class LuaAudit:
    total: int
    exact_current: tuple[str, ...]
    historical: tuple[str, ...]
    unknown: tuple[str, ...]


def clean_value(raw: str | None) -> str:
    if raw is None:
        return ""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value


def is_placeholder(raw: str | None) -> bool:
    value = clean_value(raw)
    return not value or value.lower() == "pass" or "<SEU_" in value.upper()


def generate_secret(kind: str) -> str:
    if kind == "fernet":
        return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
    if kind == "hmac":
        return secrets.token_hex(32)
    if kind == "token":
        return secrets.token_urlsafe(32)
    raise MigrationError(f"gerador de segredo desconhecido: {kind}")


def validated_url(value: str, option: str, *, https_only: bool = False) -> str:
    parsed = urlsplit(value)
    schemes = {"https"} if https_only else {"http", "https"}
    if parsed.scheme not in schemes or not parsed.netloc or parsed.path not in {"", "/"}:
        expected = "https://host[:porta]" if https_only else "http(s)://host[:porta]"
        raise MigrationError(f"{option} deve usar o formato {expected}")
    return value.rstrip("/")


def read_optional_env(path: Path | None) -> dict[str, str]:
    return {} if path is None else EnvDocument.read(path).values


def build_env_migration(
    legacy_env: Path,
    *,
    main_template: Path = MAIN_TEMPLATE,
    analytics_template: Path = ANALYTICS_TEMPLATE,
    server_env: Path | None = None,
    server_analytics_env: Path | None = None,
    studio_origin: str | None = None,
    server_domain: str | None = None,
) -> EnvMigration:
    legacy = EnvDocument.read(legacy_env)
    main = EnvDocument.read(main_template)
    analytics = EnvDocument.read(analytics_template)
    server_values = read_optional_env(server_env)
    server_analytics_values = read_optional_env(server_analytics_env)

    main_overrides = {
        key: value for key, value in legacy.values.items() if key in main.values
    }
    analytics_overrides = {
        key: value for key, value in legacy.values.items() if key in analytics.values
    }
    preserved = set(main_overrides) | set(analytics_overrides)
    generated: set[str] = set()
    normalized: set[str] = set()

    for key in SHARED_MAIN_KEYS:
        if key in server_values and not is_placeholder(server_values[key]):
            main_overrides[key] = server_values[key]
            preserved.add(key)

    for key, kind in GENERATED_MAIN_KEYS.items():
        if key not in main_overrides or is_placeholder(main_overrides[key]):
            main_overrides[key] = generate_secret(kind)
            generated.add(key)
            preserved.discard(key)

    analytics_key = "LOGFLARE_PRIVATE_ACCESS_TOKEN"
    if analytics_key in server_analytics_values and not is_placeholder(
        server_analytics_values[analytics_key]
    ):
        analytics_overrides[analytics_key] = server_analytics_values[analytics_key]
        preserved.add(analytics_key)
    elif analytics_key not in analytics_overrides or is_placeholder(
        analytics_overrides[analytics_key]
    ):
        analytics_overrides[analytics_key] = generate_secret("token")
        generated.add(analytics_key)
        preserved.discard(analytics_key)

    if server_domain is not None:
        main_overrides["SERVER_DOMAIN"] = validated_url(
            server_domain, "--server-domain"
        )
        main_overrides["BACKEND_PROTO"] = urlsplit(server_domain).scheme
        normalized.update({"SERVER_DOMAIN", "BACKEND_PROTO"})
    else:
        raw_domain = main_overrides.get("SERVER_DOMAIN", main.values["SERVER_DOMAIN"])
        domain = clean_value(raw_domain)
        if domain and "://" not in domain and not is_placeholder(raw_domain):
            proto = clean_value(
                main_overrides.get("BACKEND_PROTO", main.values["BACKEND_PROTO"])
            )
            if proto in {"http", "https"}:
                main_overrides["SERVER_DOMAIN"] = f"{proto}://{domain.rstrip('/')}"
                normalized.add("SERVER_DOMAIN")

    if studio_origin is not None:
        origin = validated_url(studio_origin, "--studio-origin", https_only=True)
        parsed_origin = urlsplit(origin)
        main_overrides["SUPABASE_PUBLIC_URL"] = origin
        main_overrides["STUDIO_HTTPS_PORT"] = str(parsed_origin.port or 443)
        normalized.update({"SUPABASE_PUBLIC_URL", "STUDIO_HTTPS_PORT"})

    effective_main = dict(main.values)
    effective_main.update(main_overrides)
    effective_analytics = dict(analytics.values)
    effective_analytics.update(analytics_overrides)
    unresolved = {
        key for key in REQUIRED_MAIN_KEYS if is_placeholder(effective_main.get(key))
    }
    unresolved.update(
        key
        for key in REQUIRED_ANALYTICS_KEYS
        if is_placeholder(effective_analytics.get(key))
    )

    deprecated = set(legacy.values) & set(DEPRECATED_KEYS)
    return EnvMigration(
        main_text=main.render(main_overrides),
        analytics_text=analytics.render(analytics_overrides),
        preserved=tuple(sorted(preserved)),
        generated=tuple(sorted(generated)),
        deprecated=tuple(sorted(deprecated)),
        normalized=tuple(sorted(normalized)),
        unresolved=tuple(sorted(unresolved)),
    )


def git_blob_sha(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def repository_objects(repo_root: Path) -> set[str]:
    process = subprocess.run(
        ["git", "rev-list", "--objects", "--all"],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if process.returncode != 0:
        raise MigrationError("nao foi possivel consultar o historico Git do destino")
    return {line.split(maxsplit=1)[0] for line in process.stdout.splitlines() if line}


def audit_lua(legacy_root: Path, repo_root: Path = REPO_ROOT) -> LuaAudit:
    lua_root = legacy_root / "nginx" / "lua"
    if not lua_root.is_dir():
        raise MigrationError(f"diretorio Lua legado ausente: {lua_root}")

    known_objects = repository_objects(repo_root)
    exact: list[str] = []
    historical: list[str] = []
    unknown: list[str] = []
    files = sorted(lua_root.rglob("*.lua"))
    for path in files:
        relative = path.relative_to(lua_root)
        content = path.read_bytes()
        current_path = repo_root / "studio" / "nginx" / "lua" / relative
        name = relative.as_posix()
        if current_path.is_file() and current_path.read_bytes() == content:
            exact.append(name)
        elif git_blob_sha(content) in known_objects:
            historical.append(name)
        else:
            unknown.append(name)

    return LuaAudit(
        total=len(files),
        exact_current=tuple(exact),
        historical=tuple(historical),
        unknown=tuple(unknown),
    )


def atomic_write(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise MigrationError(f"destino ja existe (use --force): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def print_names(label: str, names: tuple[str, ...]) -> None:
    rendered = ", ".join(names) if names else "nenhuma"
    print(f"{label}: {rendered}")


def print_report(lua: LuaAudit, env: EnvMigration, *, wrote: bool) -> None:
    print("Auditoria Lua")
    print(f"  arquivos legados: {lua.total}")
    print(f"  identicos no caminho atual: {len(lua.exact_current)}")
    print(f"  reconhecidos no historico/refatorados: {len(lua.historical)}")
    print_names("  desconhecidos", lua.unknown)
    print("Configuracao")
    print_names("  preservadas", env.preserved)
    print_names("  geradas", env.generated)
    print_names("  normalizadas", env.normalized)
    print_names("  obsoletas descartadas", env.deprecated)
    print_names("  pendencias", env.unresolved)
    print("  valores: omitidos intencionalmente")
    print("Saida: arquivos gravados" if wrote else "Saida: dry-run, nenhum arquivo gravado")
    print(
        "Sincronizar depois com servidor/.env: " + ", ".join(SHARED_MAIN_KEYS)
    )
    print(
        "Sincronizar depois com servidor/.analytics.env: "
        "LOGFLARE_PRIVATE_ACCESS_TOKEN"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audita Lua e migra apenas a configuracao de um Studio legado extraido."
    )
    parser.add_argument("legacy_root", type=Path, help="pasta Studio descompactada")
    parser.add_argument("--write-env", action="store_true", help="grava os .env atuais")
    parser.add_argument("--force", action="store_true", help="sobrescreve destinos existentes")
    parser.add_argument("--strict", action="store_true", help="falha se houver pendencias")
    parser.add_argument("--studio-origin", help="origem HTTPS local do Studio atual")
    parser.add_argument("--server-domain", help="origem HTTP(S) da Projects API")
    parser.add_argument("--server-env", type=Path, help=".env atual do servidor, se ja existir")
    parser.add_argument(
        "--server-analytics-env",
        type=Path,
        help=".analytics.env atual do servidor, se ja existir",
    )
    parser.add_argument("--target-env", type=Path, default=MAIN_TARGET)
    parser.add_argument("--target-analytics-env", type=Path, default=ANALYTICS_TARGET)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        legacy_root = args.legacy_root.resolve()
        if not legacy_root.is_dir():
            raise MigrationError("legacy_root deve ser uma pasta descompactada")
        lua = audit_lua(legacy_root)
        env = build_env_migration(
            legacy_root / ".env",
            server_env=args.server_env,
            server_analytics_env=args.server_analytics_env,
            studio_origin=args.studio_origin,
            server_domain=args.server_domain,
        )
        if args.write_env and lua.unknown:
            raise MigrationError(
                "existem scripts Lua desconhecidos; revise-os antes de gravar a configuracao"
            )
        if args.strict and (lua.unknown or env.unresolved):
            print_report(lua, env, wrote=False)
            return 2
        if args.write_env:
            if (args.target_env.exists() or args.target_analytics_env.exists()) and not args.force:
                raise MigrationError("um destino ja existe; use --force para sobrescrever")
            atomic_write(args.target_env, env.main_text, force=args.force)
            atomic_write(args.target_analytics_env, env.analytics_text, force=args.force)
        print_report(lua, env, wrote=args.write_env)
        return 0
    except MigrationError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
