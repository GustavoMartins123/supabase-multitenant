#!/usr/bin/env python3
"""Renderiza um .env canonico sem aceitar configuracao de Storage por projeto."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile


OBSOLETE_STORAGE_KEYS = {
    "STORAGE_IMAGE",
    "STORAGE_DB_USER",
    "STORAGE_POSTGREST_URL",
    "STORAGE_BACKEND",
    "REQUEST_ALLOW_X_FORWARDED_PATH",
    "TUS_URL_PATH",
    "FILE_STORAGE_BACKEND_PATH",
    "STORAGE_TENANT_ID",
    "TENANT_ID",
    "STORAGE_REGION",
    "GLOBAL_S3_BUCKET",
    "VECTOR_ENABLED",
    "VECTOR_BUCKET_PROVIDER",
    "VECTOR_DATABASE_URL",
    "VECTOR_DATABASE_CREATE",
    "VECTOR_STORE_MIGRATIONS_ENABLED",
    "IMGPROXY_URL",
    "IMGPROXY_IMAGE",
    "IMGPROXY_BIND",
    "IMGPROXY_LOCAL_FILESYSTEM_ROOT",
    "IMGPROXY_USE_ETAG",
    "IMGPROXY_ENABLE_WEBP_DETECTION",
}

PROTECTED_KEYS = {
    "PROJECT_ID",
    "PROJECT_UUID",
    "POSTGRES_DATABASE",
    "PROJECT_ROOT",
    "ANON_KEY_PROJETO",
    "SERVICE_ROLE_KEY_PROJETO",
    "CONFIG_TOKEN_PROJETO",
    "JWT_SECRET_PROJETO",
    "API_GATEWAY_TOKEN_PROJETO",
    "S3_PROTOCOL_CREDENTIAL_ID",
    "S3_PROTOCOL_ACCESS_KEY_ID",
    "S3_PROTOCOL_ACCESS_KEY_SECRET",
}

ASSIGNMENT_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
COMMENTED_ASSIGNMENT_RE = re.compile(r"^#\s*([A-Z][A-Z0-9_]*)=(.*)$")
PLACEHOLDER_RE = re.compile(r"\{\{[a-z0-9_]+\}\}")


def read_assignments(path: pathlib.Path) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    order: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ASSIGNMENT_RE.fullmatch(line)
        if not match:
            continue
        key, value = match.groups()
        if key in values:
            raise SystemExit(f"atribuicao duplicada em {path}: {key}")
        if "\r" in value or "\n" in value or "\x00" in value:
            raise SystemExit(f"valor nao canonico em {path}: {key}")
        values[key] = value
        order.append(key)
    return values, order


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("uso: render_project_env.py TEMPLATE CURRENT_ENV OUTPUT")
    template_path, current_path, output_path = map(pathlib.Path, sys.argv[1:])
    replacements = json.load(sys.stdin)
    if not isinstance(replacements, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in replacements.items()
    ):
        raise SystemExit("replacements invalidos")

    current_values, current_order = read_assignments(current_path)
    obsolete = sorted(
        OBSOLETE_STORAGE_KEYS.intersection(current_values)
        | {
            key
            for key in current_values
            if "LEGACY" in key and ("STORAGE" in key or "IMGPROXY" in key)
        }
    )
    if obsolete:
        raise SystemExit(
            "configuracao Storage por projeto nao suportada: " + ", ".join(obsolete)
        )

    rendered: list[str] = []
    template_keys: set[str] = set()
    for raw_line in template_path.read_text(encoding="utf-8").splitlines():
        line = raw_line
        for key, value in replacements.items():
            line = line.replace("{{" + key + "}}", value)

        active = ASSIGNMENT_RE.fullmatch(line)
        commented = COMMENTED_ASSIGNMENT_RE.fullmatch(line)
        if active:
            key, value = active.groups()
            template_keys.add(key)
            if key in current_values and key not in PROTECTED_KEYS:
                value = current_values[key]
            rendered.append(f"{key}={value}")
        elif commented:
            key, _ = commented.groups()
            template_keys.add(key)
            if key in current_values and key not in PROTECTED_KEYS:
                rendered.append(f"{key}={current_values[key]}")
            else:
                rendered.append(line)
        else:
            rendered.append(line)

    unresolved = sorted(set(PLACEHOLDER_RE.findall("\n".join(rendered))))
    if unresolved:
        raise SystemExit("placeholders nao resolvidos: " + ", ".join(unresolved))

    preserved = [
        key
        for key in current_order
        if key not in template_keys and key not in PROTECTED_KEYS
    ]
    if preserved:
        rendered.extend(["", "# Configuracoes adicionais preservadas"])
        rendered.extend(f"{key}={current_values[key]}" for key in preserved)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temp_path = pathlib.Path(handle.name)
        handle.write("\n".join(rendered).rstrip() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
