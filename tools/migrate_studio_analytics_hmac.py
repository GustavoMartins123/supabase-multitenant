#!/usr/bin/env python3
"""Configura o HMAC Studio -> Nginx usado pela rota interna de Analytics."""

from __future__ import annotations

import argparse
import hmac
import os
import re
import secrets
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STUDIO_ENV = ROOT / "studio" / ".env"
KEY = "STUDIO_ANALYTICS_HMAC_SECRET"
DISTINCT_FROM = ("STUDIO_GATEWAY_HMAC_SECRET", "PROJECTS_API_HMAC_SECRET")
HEX_SECRET = re.compile(r"^[0-9a-fA-F]{64}$")


class MigrationError(RuntimeError):
    pass


def _value(content: str, key: str) -> str:
    matches = re.findall(rf"(?m)^(?:export[ \t]+)?{re.escape(key)}[ \t]*=(.*)$", content)
    if len(matches) > 1:
        raise MigrationError(f"{key} possui atribuicoes duplicadas")
    return matches[0].strip() if matches else ""


def _set_value(content: str, key: str, value: str) -> str:
    pattern = re.compile(rf"(?m)^(?:export[ \t]+)?{re.escape(key)}[ \t]*=.*$")
    replacement = f"{key}={value}"
    if pattern.search(content):
        return pattern.sub(replacement, content, count=1)
    separator = "" if not content or content.endswith("\n") else "\n"
    return f"{content}{separator}{replacement}\n"


def _atomic_write(path: Path, content: str) -> None:
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.analytics-hmac.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            if content and not content.endswith("\n"):
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def migrate(studio_env: Path, *, dry_run: bool = False) -> bool:
    if not studio_env.is_file():
        raise MigrationError(f"arquivo ausente: {studio_env}")
    original = studio_env.read_text(encoding="utf-8")
    current = _value(original, KEY)
    if current and not HEX_SECRET.fullmatch(current):
        raise MigrationError(f"{KEY} deve conter 32 bytes em hexadecimal")
    resolved = current or secrets.token_hex(32)
    for other_key in DISTINCT_FROM:
        other = _value(original, other_key)
        if other and hmac.compare_digest(resolved, other):
            raise MigrationError(f"{KEY} deve ser distinto de {other_key}")

    updated = _set_value(original, KEY, resolved)
    changed = updated != original
    if dry_run or not changed:
        return changed

    backup = studio_env.with_name(studio_env.name + ".pre-studio-analytics-hmac")
    if not backup.exists():
        shutil.copy2(studio_env, backup)
        backup.chmod(0o600)
    _atomic_write(studio_env, updated)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migra studio/.env para HMAC interno de Analytics."
    )
    parser.add_argument("--studio-env", type=Path, default=DEFAULT_STUDIO_ENV)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        changed = migrate(args.studio_env, dry_run=args.dry_run)
    except (MigrationError, OSError) as exc:
        print(f"erro: {exc}")
        return 1

    if args.dry_run:
        print("migracao necessaria" if changed else "ambiente ja migrado")
    elif changed:
        print("HMAC interno do Studio Analytics configurado; backup .pre-studio-analytics-hmac criado")
        print("agora faca rebuild/restart do Studio e do nginx")
    else:
        print("ambiente ja migrado; nenhuma alteracao necessaria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
