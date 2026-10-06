#!/usr/bin/env python3
"""Migra uma instalacao existente para internal-hmac-v1 estrito.

Execute no checkout da instalacao ANTES de rebuild/restart do Studio nginx e
da Projects API. O script nao imprime nenhum segredo.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER_ENV = ROOT / "servidor" / ".env"
DEFAULT_STUDIO_ENV = ROOT / "studio" / ".env"
SERVICE_KEYS = ("STUDIO_GATEWAY_HMAC_SECRET", "PROJECTS_API_HMAC_SECRET")
REMOVED_KEYS = ("NGINX_SHARED_TOKEN", "INTERNAL_HMAC_ALLOW_LEGACY_SHARED_TOKEN")


class MigrationError(RuntimeError):
    pass


def _assignments(content: str, key: str) -> list[str]:
    pattern = re.compile(rf"(?m)^(?:export[ \t]+)?{re.escape(key)}[ \t]*=(.*)$")
    return [match.group(1).strip() for match in pattern.finditer(content)]


def _value(content: str, key: str) -> str:
    values = _assignments(content, key)
    if len(values) > 1:
        raise MigrationError(f"{key} possui atribuicoes duplicadas")
    return values[0] if values else ""


def _set_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(?:export[ \t]+)?{re.escape(key)}[ \t]*=.*$")
    replacement = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{replacement}\n"


def _remove_key(content: str, key: str) -> str:
    pattern = re.compile(rf"(?m)^(?:export[ \t]+)?{re.escape(key)}[ \t]*=.*\n?")
    return pattern.sub("", content)


def _atomic_write(path: Path, content: str, mode: int) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.hmac-v1.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _backup(path: Path) -> Path:
    backup = path.with_name(path.name + ".pre-internal-hmac-v1")
    if not backup.exists():
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    return backup


def migrate(server_env: Path, studio_env: Path, *, dry_run: bool = False) -> bool:
    for path in (server_env, studio_env):
        if not path.is_file():
            raise MigrationError(f"arquivo ausente: {path}")

    server = server_env.read_text(encoding="utf-8")
    studio = studio_env.read_text(encoding="utf-8")
    resolved: dict[str, str] = {}

    for key in SERVICE_KEYS:
        server_value = _value(server, key)
        studio_value = _value(studio, key)
        if server_value and studio_value and server_value != studio_value:
            raise MigrationError(f"{key} diverge entre servidor/.env e studio/.env")
        resolved[key] = server_value or studio_value or secrets.token_hex(32)

    if resolved[SERVICE_KEYS[0]] == resolved[SERVICE_KEYS[1]]:
        raise MigrationError("os segredos HMAC de servicos distintos nao podem ser iguais")

    for key, value in resolved.items():
        server = _set_value(server, key, value)
        studio = _set_value(studio, key, value)
    for key in REMOVED_KEYS:
        server = _remove_key(server, key)
        studio = _remove_key(studio, key)

    changed = (
        server != server_env.read_text(encoding="utf-8")
        or studio != studio_env.read_text(encoding="utf-8")
    )
    if dry_run or not changed:
        return changed

    _backup(server_env)
    _backup(studio_env)
    _atomic_write(server_env, server, 0o600)
    _atomic_write(studio_env, studio, 0o600)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migra .env existentes para HMAC interno estrito por servico."
    )
    parser.add_argument("--server-env", type=Path, default=DEFAULT_SERVER_ENV)
    parser.add_argument("--studio-env", type=Path, default=DEFAULT_STUDIO_ENV)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        changed = migrate(args.server_env, args.studio_env, dry_run=args.dry_run)
    except (MigrationError, OSError) as exc:
        print(f"erro: {exc}")
        return 1

    if args.dry_run:
        print("migracao necessaria" if changed else "ambiente ja migrado")
    elif changed:
        print("HMAC interno por servico configurado; backups .pre-internal-hmac-v1 criados")
        print("agora faca rebuild/restart do projects-api e do Studio nginx")
    else:
        print("ambiente ja migrado; nenhuma alteracao necessaria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
