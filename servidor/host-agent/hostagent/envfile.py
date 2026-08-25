"""Leitor minimalista de arquivos .env (sem dependencias externas)."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _unquote_canonical(value: str, key: str) -> str:
    r"""Remove uma unica camada de aspas, se o valor inteiro estiver citado.

    Caminhos com espaco (`HOST_PROJECT_ROOT`) precisam de aspas: o `.env` do
    servidor tambem e lido por `source` do bash. O que se recusa aqui e valor
    cujo significado para o bash difira do texto literal — expansao (`$`),
    substituicao (crase), escape (`\`) ou aspas desbalanceadas.
    """

    if len(value) < 2 or value[0] != value[-1] or value[0] not in {'"', "'"}:
        return value
    quote = value[0]
    inner = value[1:-1]
    if quote in inner:
        raise RuntimeError(f"Entrada nao canonica no .env: {key}")
    # Aspas simples sao literais no bash; dentro de aspas duplas, estes tres
    # caracteres mudam o valor que o `source` produziria.
    if quote == '"' and any(char in inner for char in "$\\`"):
        raise RuntimeError(f"Entrada nao canonica no .env: {key}")
    return inner


def read_canonical_env_value(path: Path, key: str) -> str | None:
    """Read one exact ``KEY=value`` entry and reject ambiguous syntax."""

    if not path.is_file():
        raise RuntimeError(f"Arquivo .env ausente: {path}")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise ValueError("invalid environment key")
    values: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        candidate = stripped
        exported = candidate.startswith("export ")
        if exported:
            candidate = candidate[len("export "):].lstrip()
        parsed_key, separator, parsed_value = candidate.partition("=")
        if parsed_key.strip() != key:
            continue
        if (
            exported
            or not separator
            or raw_line != candidate
            or parsed_key != key
            or parsed_value != parsed_value.strip()
        ):
            raise RuntimeError(f"Entrada nao canonica no .env: {key}")
        values.append(_unquote_canonical(parsed_value, key))
    if len(values) > 1:
        raise RuntimeError(f"Chave duplicada no .env: {key}")
    return values[0] if values else None


def upsert_env_value(path: Path, key: str, value: str) -> None:
    """Atomically set one unquoted canonical value without tolerating duplicates."""

    if not path.is_file():
        raise RuntimeError(f"Arquivo .env ausente: {path}")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
        raise ValueError("invalid environment key")
    if not value or any(character in value for character in "\r\n\x00"):
        raise ValueError("invalid environment value")
    if any(character in value for character in " \t\"'$`\\"):
        raise ValueError("environment value requires quoting")

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    existing_value = read_canonical_env_value(path, key)
    matches = [
        index for index, line in enumerate(lines) if line.startswith(f"{key}=")
    ]
    if existing_value is not None and not matches:
        raise RuntimeError(f"Entrada nao canonica no .env: {key}")
    if len(matches) > 1:
        raise RuntimeError(f"Chave duplicada no .env: {key}")
    replacement = f"{key}={value}\n"
    if matches:
        lines[matches[0]] = replacement
    else:
        if original and not original.endswith(("\n", "\r")):
            lines.append("\n")
        lines.append(replacement)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.writelines(lines)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
