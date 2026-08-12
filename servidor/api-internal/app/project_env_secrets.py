"""Strict reads for canonical secret entries in generated project environments."""

from __future__ import annotations

import pathlib
import re


PROJECTS_ROOT = pathlib.Path("/docker/projects").resolve()
PROJECT_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
_REQUIRED_PROJECT_SECRET_KEYS = (
    "PROJECT_UUID",
    "ANON_KEY_PROJETO",
    "SERVICE_ROLE_KEY_PROJETO",
    "CONFIG_TOKEN_PROJETO",
    "API_GATEWAY_TOKEN_PROJETO",
)


def read_project_secret_keys(project_name: str) -> dict[str, str]:
    """Read exact, unquoted and unique project secret entries or fail closed."""

    if not isinstance(project_name, str) or not PROJECT_NAME_RE.fullmatch(
        project_name
    ):
        raise RuntimeError("Invalid project name for secret lookup")
    env_path = PROJECTS_ROOT / project_name / ".env"
    env_values: dict[str, str] = {}
    if not env_path.is_file():
        raise RuntimeError(f"Project .env is missing: {project_name}")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        candidate = stripped
        if candidate.startswith("export "):
            candidate = candidate[len("export "):].lstrip()
        key, separator, value = candidate.partition("=")
        normalized_key = key.strip()
        if normalized_key not in _REQUIRED_PROJECT_SECRET_KEYS:
            continue
        if (
            not separator
            or raw_line != candidate
            or key != normalized_key
            or value != value.strip()
            or not value
            or (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {'"', "'"}
            )
        ):
            raise RuntimeError(
                f"Non-canonical project .env entry: {normalized_key}"
            )
        if normalized_key in env_values:
            raise RuntimeError(
                f"Duplicate project .env entry: {normalized_key}"
            )
        env_values[normalized_key] = value
    missing = [
        key for key in _REQUIRED_PROJECT_SECRET_KEYS if key not in env_values
    ]
    if missing:
        raise RuntimeError(
            "Missing required project .env entries: " + ", ".join(missing)
        )
    return {
        "tenant_uuid": env_values["PROJECT_UUID"],
        "anon_key": env_values["ANON_KEY_PROJETO"],
        "service_role": env_values["SERVICE_ROLE_KEY_PROJETO"],
        "config_token": env_values["CONFIG_TOKEN_PROJETO"],
        "gateway_token": env_values["API_GATEWAY_TOKEN_PROJETO"],
    }
