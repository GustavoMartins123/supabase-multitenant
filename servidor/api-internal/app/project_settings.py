"""Leitura, validacao e escrita atomica das configuracoes de projeto."""

import os
import pathlib
import re
import shutil
import tempfile

from dotenv import dotenv_values
from fastapi import HTTPException

SETTINGS_WHITELIST = {
    "DISABLE_SIGNUP",
    "ENABLE_EMAIL_SIGNUP",
    "ENABLE_EMAIL_AUTOCONFIRM",
    "ENABLE_ANONYMOUS_USERS",
    "ENABLE_PHONE_SIGNUP",
    "ENABLE_PHONE_AUTOCONFIRM",
    "JWT_EXPIRY",
    "GOTRUE_MAILER_OTP_EXP",
    "GOTRUE_PASSWORD_MIN_LENGTH",
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED",
    "PGRST_DB_SCHEMAS",
    "PGRST_DB_MAX_ROWS",
    "PGRST_DB_POOL",
    "PGRST_DB_POOL_TIMEOUT",
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT",
    "FILE_SIZE_LIMIT",
    "ENABLE_IMAGE_TRANSFORMATION",
}

BOOLEAN_SETTINGS = {
    "DISABLE_SIGNUP",
    "ENABLE_EMAIL_SIGNUP",
    "ENABLE_EMAIL_AUTOCONFIRM",
    "ENABLE_ANONYMOUS_USERS",
    "ENABLE_PHONE_SIGNUP",
    "ENABLE_PHONE_AUTOCONFIRM",
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED",
    "ENABLE_IMAGE_TRANSFORMATION",
}

INTEGER_SETTING_RANGES = {
    "JWT_EXPIRY": (60, 3153600000),
    "GOTRUE_MAILER_OTP_EXP": (60, 3153600000),
    "GOTRUE_PASSWORD_MIN_LENGTH": (6, 128),
    "PGRST_DB_MAX_ROWS": (1, 1000000000),
    "PGRST_DB_POOL": (1, 10000),
    "PGRST_DB_POOL_TIMEOUT": (1, 3153600000),
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT": (1, 3153600000),
    "FILE_SIZE_LIMIT": (1, 9007199254740991),
}

SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

SETTING_TO_SERVICES: dict[str, list[str]] = {
    "DISABLE_SIGNUP":                          ["auth"],
    "ENABLE_EMAIL_SIGNUP":                     ["auth"],
    "ENABLE_EMAIL_AUTOCONFIRM":                ["auth"],
    "ENABLE_ANONYMOUS_USERS":                  ["auth"],
    "ENABLE_PHONE_SIGNUP":                     ["auth"],
    "ENABLE_PHONE_AUTOCONFIRM":                ["auth"],
    "JWT_EXPIRY":                              ["auth", "rest"],
    "GOTRUE_MAILER_OTP_EXP":                   ["auth"],
    "GOTRUE_PASSWORD_MIN_LENGTH":              ["auth"],
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED":   ["auth"],
    "PGRST_DB_SCHEMAS":                        ["rest"],
    "PGRST_DB_MAX_ROWS":                       ["rest"],
    "PGRST_DB_POOL":                           ["rest"],
    "PGRST_DB_POOL_TIMEOUT":                   ["rest"],
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT":       ["rest"],
    "FILE_SIZE_LIMIT":                         ["storage", "nginx"],
    "ENABLE_IMAGE_TRANSFORMATION":             ["storage"],
}

def _read_env_whitelisted(env_path: pathlib.Path) -> dict[str, str]:
    all_values = {
        key: str(value)
        for key, value in dotenv_values(env_path).items()
        if value is not None
    }
    return {k: value for k, value in all_values.items() if k in SETTINGS_WHITELIST}


def _normalize_setting_value(key: str, raw_value: str) -> str:
    value = str(raw_value).strip()
    if "\n" in value or "\r" in value or "\x00" in value:
        raise HTTPException(400, f"{key}: valor não pode conter quebra de linha ou byte nulo")
    if not value:
        raise HTTPException(400, f"{key}: valor obrigatório")

    if key in BOOLEAN_SETTINGS:
        normalized = value.lower()
        if normalized not in {"true", "false"}:
            raise HTTPException(400, f"{key}: use true ou false")
        return normalized

    int_range = INTEGER_SETTING_RANGES.get(key)
    if int_range:
        if not re.fullmatch(r"\d+", value):
            raise HTTPException(400, f"{key}: use apenas números inteiros")
        parsed = int(value)
        min_value, max_value = int_range
        if parsed < min_value or parsed > max_value:
            raise HTTPException(
                400,
                f"{key}: use um valor entre {min_value} e {max_value}",
            )
        return str(parsed)

    if key == "PGRST_DB_SCHEMAS":
        schemas = [part.strip() for part in value.split(",")]
        if not schemas or any(not part for part in schemas):
            raise HTTPException(400, f"{key}: informe schemas separados por vírgula")
        for schema in schemas:
            if not SCHEMA_NAME_RE.fullmatch(schema):
                raise HTTPException(400, f"{key}: schema inválido: {schema}")
        return ",".join(schemas)

    raise HTTPException(400, f"{key}: configuração sem validador")


def _normalize_settings_updates(settings: dict[str, str]) -> dict[str, str]:
    invalid_keys = set(settings.keys()) - SETTINGS_WHITELIST
    if invalid_keys:
        raise HTTPException(
            400,
            f"Variáveis não permitidas: {', '.join(sorted(invalid_keys))}",
        )

    if not settings:
        raise HTTPException(400, "Nenhuma configuração enviada")

    return {
        key: _normalize_setting_value(key, value)
        for key, value in settings.items()
    }


def _write_env_whitelisted(env_path: pathlib.Path, updates: dict[str, str]) -> None:
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates and key in SETTINGS_WHITELIST:
                value = updates[key]
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys and key in SETTINGS_WHITELIST:
            new_lines.append(f"{key}={value}\n")

    temp_path: pathlib.Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=env_path.parent,
            prefix=f".{env_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = pathlib.Path(temp_file.name)
            temp_file.writelines(new_lines)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        shutil.copymode(env_path, temp_path)
        os.replace(temp_path, env_path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _get_affected_services(changed_keys: list[str]) -> list[str]:
    services: set[str] = set()
    for key in changed_keys:
        for svc in SETTING_TO_SERVICES.get(key, []):
            services.add(svc)
    return sorted(services)




