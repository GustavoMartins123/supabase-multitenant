from __future__ import annotations

import os
import pathlib
import re

from fastapi import HTTPException


DEFAULT_CAPACITY_FILE = pathlib.Path("/docker/platform-capacity.env")

_ASSIGNMENT_RE = re.compile(r"(?m)^([A-Z][A-Z0-9_]*)=(.*)$")


def read_capacity(*, capacity_file: pathlib.Path | None = None) -> dict[str, str]:
    path = capacity_file or pathlib.Path(
        os.getenv("PLATFORM_CAPACITY_FILE") or DEFAULT_CAPACITY_FILE
    )
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {
        match.group(1): match.group(2).strip().strip('"').strip("'")
        for match in _ASSIGNMENT_RE.finditer(content)
    }


def project_capacity(*, capacity_file: pathlib.Path | None = None) -> int | None:
    raw = read_capacity(capacity_file=capacity_file).get("PLATFORM_PROJECT_CAPACITY")
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def assert_capacity_available(
    current_projects: int, *, capacity_file: pathlib.Path | None = None
) -> None:
    capacity = project_capacity(capacity_file=capacity_file)
    if capacity is None or current_projects < capacity:
        return

    published = read_capacity(capacity_file=capacity_file)
    binding = published.get("PLATFORM_CAPACITY_BINDING", "recursos")
    profile = published.get("PLATFORM_PROJECT_PROFILE", "atual")
    raise HTTPException(
        409,
        f"Este host comporta {capacity} projetos no perfil {profile} "
        f"(restricao: {binding}) e ja possui {current_projects}. "
        "Aumente a maquina, use um perfil menor ou exclua um projeto; "
        "depois rode o start.sh para recalcular a capacidade.",
    )
