"""Leitura, validacao e escrita atomica das configuracoes de projeto."""

import os
import pathlib
import re
import shutil
import tempfile

from dotenv import dotenv_values
from fastapi import HTTPException


DEFAULT_PROJECTS_ROOT = pathlib.Path("/docker/projects")

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
    "PGRST_DB_SCHEMAS",
    "PGRST_DB_MAX_ROWS",
    "PGRST_DB_POOL",
    "PGRST_DB_POOL_TIMEOUT",
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT",
    "FILE_SIZE_LIMIT",
    "ENABLE_IMAGE_TRANSFORMATION",
    "S3_PROTOCOL_ENABLED",
    "VECTOR_BUCKETS_ENABLED",
    "VECTOR_MAX_BUCKETS",
    "VECTOR_MAX_INDEXES",
    "PROJECT_RESOURCE_PROFILE",
}

CUSTOM_TOTAL_INPUTS = (
    "PROJECT_MEM_LIMIT",
    "PROJECT_CPUS",
    "PROJECT_PIDS_LIMIT",
)

CUSTOM_PROFILE_DISPLAY_KEYS = {
    "PROJECT_RES_CUSTOM_MEMORY",
    "PROJECT_RES_CUSTOM_CPUS",
    "PROJECT_RES_CUSTOM_PIDS",
}

RESOURCE_SERVICES = ("NGINX", "AUTH", "REST")
RESOURCE_WEIGHTS = {
    "MEMORY": (1, 2, 5),
    "CPUS": (1, 4, 1),
}

RESOURCE_CPU_FLOORS_CENTI = (40, 120, 25)
RESOURCE_PIDS_FLOOR = (128, 256, 512)
RESOURCE_MEM_FLOORS_MIB = (16, 64, 32)
RESOURCE_GHC_HEAP_PERCENT = 80

DERIVED_LIMIT_KEYS = {
    "PROJECT_MEM_LIMIT",
    "PROJECT_CPUS",
    "PROJECT_PIDS_LIMIT",
    "PROJECT_REST_GHC_MAX_HEAP",
    *CUSTOM_PROFILE_DISPLAY_KEYS,
    *(
        f"PROJECT_{service}_{suffix}"
        for service in RESOURCE_SERVICES
        for suffix in ("MEM_LIMIT", "CPUS", "PIDS_LIMIT")
    ),
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
    "S3_PROTOCOL_ENABLED",
    "VECTOR_BUCKETS_ENABLED",
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
    "VECTOR_MAX_BUCKETS": (1, 1000000),
    "VECTOR_MAX_INDEXES": (1, 1000000),
}

SCHEMA_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

RESOURCE_PROFILES = ("small", "medium", "large", "custom")
RESOLVED_LIMIT_KEYS = ("PROJECT_MEM_LIMIT", "PROJECT_CPUS", "PROJECT_PIDS_LIMIT")

PROFILE_RESOLVED_FROM_ROOT = {
    "small": {
        "MEMORY": "PROJECT_RES_SMALL_MEMORY",
        "CPUS": "PROJECT_RES_SMALL_CPUS",
        "PIDS": "PROJECT_RES_SMALL_PIDS",
    },
    "medium": {
        "MEMORY": "PROJECT_RES_MEDIUM_MEMORY",
        "CPUS": "PROJECT_RES_MEDIUM_CPUS",
        "PIDS": "PROJECT_RES_MEDIUM_PIDS",
    },
    "large": {
        "MEMORY": "PROJECT_RES_LARGE_MEMORY",
        "CPUS": "PROJECT_RES_LARGE_CPUS",
        "PIDS": "PROJECT_RES_LARGE_PIDS",
    },
    "custom": {
        "MEMORY": "PROJECT_RES_CUSTOM_MEMORY",
        "CPUS": "PROJECT_RES_CUSTOM_CPUS",
        "PIDS": "PROJECT_RES_CUSTOM_PIDS",
    },
}

SETTING_TO_SERVICES: dict[str, list[str]] = {
    "DISABLE_SIGNUP": ["auth"],
    "ENABLE_EMAIL_SIGNUP": ["auth"],
    "ENABLE_EMAIL_AUTOCONFIRM": ["auth"],
    "ENABLE_ANONYMOUS_USERS": ["auth"],
    "ENABLE_PHONE_SIGNUP": ["auth"],
    "ENABLE_PHONE_AUTOCONFIRM": ["auth"],
    "JWT_EXPIRY": ["auth", "rest"],
    "GOTRUE_MAILER_OTP_EXP": ["auth"],
    "GOTRUE_PASSWORD_MIN_LENGTH": ["auth"],
    "GOTRUE_EXTERNAL_IMPLICIT_FLOW_ENABLED": ["auth"],
    "PGRST_DB_SCHEMAS": ["rest"],
    "PGRST_DB_MAX_ROWS": ["rest"],
    "PGRST_DB_POOL": ["rest"],
    "PGRST_DB_POOL_TIMEOUT": ["rest"],
    "PGRST_DB_POOL_ACQUISITION_TIMEOUT": ["rest"],
    "FILE_SIZE_LIMIT": ["storage", "nginx"],
    "ENABLE_IMAGE_TRANSFORMATION": ["storage"],
    "S3_PROTOCOL_ENABLED": ["storage"],
    "VECTOR_BUCKETS_ENABLED": ["storage"],
    "VECTOR_MAX_BUCKETS": ["storage"],
    "VECTOR_MAX_INDEXES": ["storage"],
    "PROJECT_RESOURCE_PROFILE": ["auth", "rest", "nginx"],
}

DEFAULT_SERVER_ENV = pathlib.Path(os.getenv("SERVER_ENV_PATH", "/docker/.env"))


def resolve_resource_limits(
    profile: str,
    *,
    server_env: pathlib.Path = DEFAULT_SERVER_ENV,
) -> dict[str, str]:
    """Resolve o trio do .env raiz para o perfil informado."""

    if profile not in RESOURCE_PROFILES:
        raise HTTPException(
            400, "PROJECT_RESOURCE_PROFILE: use small, medium, large ou custom"
        )
    try:
        content = server_env.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(409, ".env do servidor indisponivel") from exc
    totals: dict[str, str] = {}
    for suffix, key in PROFILE_RESOLVED_FROM_ROOT[profile].items():
        match = re.search(rf"(?m)^{key}=(.*)$", content)
        raw = match.group(1).strip().strip('"').strip("'") if match else ""
        if not raw or raw == "pass":
            raise HTTPException(409, f"{key} ausente no .env do servidor")
        totals[suffix] = raw

    values = {
        RESOLVED_LIMIT_KEYS[index]: totals[suffix]
        for index, suffix in enumerate(("MEMORY", "CPUS", "PIDS"))
    }
    values.update(_split_across_services(totals))
    return values


def resolve_custom_project_limits(totals: dict[str, str]) -> dict[str, str]:
    """Deriva a capacidade personalizada a partir dos totais enviados.

    `totals` usa as chaves MEMORY/CPUS/PIDS. Retorna o perfil `custom`
    persistido junto dos valores proprios e do rateio por servico.
    """

    missing = [key for key in ("MEMORY", "CPUS", "PIDS") if not totals.get(key)]
    if missing:
        raise HTTPException(
            400,
            "capacidade personalizada incompleta: informe "
            + ", ".join(
                {
                    "MEMORY": "PROJECT_MEM_LIMIT",
                    "CPUS": "PROJECT_CPUS",
                    "PIDS": "PROJECT_PIDS_LIMIT",
                }[item]
                for item in missing
            ),
        )
    mem = totals["MEMORY"].strip().lower()
    cpus = totals["CPUS"].strip()
    pids = totals["PIDS"].strip()
    canonical_totals = {
        "MEMORY": mem,
        "CPUS": f"{_cpus_to_centi(cpus) // 100}.{_cpus_to_centi(cpus) % 100:02d}",
        "PIDS": str(int(pids)),
    }
    resolved: dict[str, str] = {"PROJECT_RESOURCE_PROFILE": "custom"}
    resolved.update(
        {
            "PROJECT_MEM_LIMIT": canonical_totals["MEMORY"],
            "PROJECT_CPUS": canonical_totals["CPUS"],
            "PROJECT_PIDS_LIMIT": canonical_totals["PIDS"],
            "PROJECT_RES_CUSTOM_MEMORY": canonical_totals["MEMORY"],
            "PROJECT_RES_CUSTOM_CPUS": canonical_totals["CPUS"],
            "PROJECT_RES_CUSTOM_PIDS": canonical_totals["PIDS"],
        }
    )
    resolved.update(_split_across_services(canonical_totals))
    return resolved


def split_resource_directives(
    settings: dict[str, str],
    *,
    current_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    """Divida updates de settings em (diretos, limites derivados a gravar).

    Perfil nomeado resolve do .env raiz; capacidade personalizada completa
    totais ausentes com `current_env` e deriva o rateio por servico local.
    """

    direct_totals = {
        key
        for key in ("PROJECT_MEM_LIMIT", "PROJECT_CPUS", "PROJECT_PIDS_LIMIT")
        if key in settings
    }
    updates = dict(settings)
    if not direct_totals:
        return updates, {}

    totals: dict[str, str] = {}
    env_now = current_env or {}
    for input_key, suffix in (
        ("PROJECT_MEM_LIMIT", "MEMORY"),
        ("PROJECT_CPUS", "CPUS"),
        ("PROJECT_PIDS_LIMIT", "PIDS"),
    ):
        value = updates.get(input_key) or str(env_now.get(input_key) or "").strip()
        if not value or value == "pass":
            raise HTTPException(
                400,
                "Capacidade personalizada precisa de Memoria, CPUs e PIDs "
                f"completos ({input_key} ausente no projeto)",
            )
        totals[suffix] = value

    resolved = resolve_custom_project_limits(totals)
    updates["PROJECT_RESOURCE_PROFILE"] = "custom"
    return updates, resolved


def _mem_to_mib(raw: str) -> int:
    match = re.fullmatch(r"(\d+)([mMgG])", raw.strip())
    if not match:
        raise HTTPException(409, f"memoria invalida no .env do servidor: {raw}")
    size = int(match.group(1))
    return size * 1024 if match.group(2) in "gG" else size


def _cpus_to_centi(raw: str) -> int:
    match = re.fullmatch(r"(\d+)(?:\.(\d{1,2}))?", raw.strip())
    if not match:
        raise HTTPException(409, f"cpus invalido no .env do servidor: {raw}")
    return int(match.group(1)) * 100 + int((match.group(2) or "0").ljust(2, "0"))


def _split(total: int, weights: tuple[int, ...]) -> list[int]:
    """Rateia por peso; o ultimo servico absorve a sobra da divisao inteira.

    Assim a soma dos servicos fecha exatamente com o teto do perfil.
    """
    denominator = sum(weights)
    shares: list[int] = []
    used = 0
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            share = total - used
        else:
            share = total * weight // denominator
            used += share
        if share < 1:
            raise HTTPException(
                409, f"perfil pequeno demais para ratear entre os servicos: {total}"
            )
        shares.append(share)
    return shares


def _split_with_floors(
    total: int, weights: tuple[int, ...], floors: tuple[int, ...]
) -> list[int]:
    floor_total = sum(floors)
    if total < floor_total:
        raise HTTPException(
            409,
            f"perfil de CPU precisa de pelo menos {floor_total} centi-CPU",
        )
    remaining = total - floor_total
    extras: list[int] = []
    used = 0
    for index, weight in enumerate(weights):
        if index == len(weights) - 1:
            extra = remaining - used
        else:
            extra = remaining * weight // sum(weights)
            used += extra
        extras.append(extra)
    return [floor + extras[index] for index, floor in enumerate(floors)]


def _split_across_services(totals: dict[str, str]) -> dict[str, str]:
    memory = _split(_mem_to_mib(totals["MEMORY"]), RESOURCE_WEIGHTS["MEMORY"])
    cpus = _split_with_floors(
        _cpus_to_centi(totals["CPUS"]),
        RESOURCE_WEIGHTS["CPUS"],
        RESOURCE_CPU_FLOORS_CENTI,
    )
    try:
        pids_total = int(totals["PIDS"])
    except ValueError as exc:
        raise HTTPException(
            409, f"pids invalido no .env do servidor: {totals['PIDS']}"
        ) from exc
    pids = [max(pids_total, floor) for floor in RESOURCE_PIDS_FLOOR]

    resolved: dict[str, str] = {}
    for index, service in enumerate(RESOURCE_SERVICES):
        floor = RESOURCE_MEM_FLOORS_MIB[index]
        if memory[index] < floor:
            raise HTTPException(
                409,
                f"o perfil da apenas {memory[index]}m ao {service.lower()}; "
                f"o minimo seguro e {floor}m",
            )
        resolved[f"PROJECT_{service}_MEM_LIMIT"] = f"{memory[index]}m"
        resolved[f"PROJECT_{service}_CPUS"] = (
            f"{cpus[index] // 100}.{cpus[index] % 100:02d}"
        )
        resolved[f"PROJECT_{service}_PIDS_LIMIT"] = str(pids[index])
    rest_share = memory[RESOURCE_SERVICES.index("REST")]
    resolved["PROJECT_REST_GHC_MAX_HEAP"] = (
        f"{rest_share * RESOURCE_GHC_HEAP_PERCENT // 100}m"
    )
    return resolved


def _read_env_whitelisted(env_path: pathlib.Path) -> dict[str, str]:
    all_values = {
        key: str(value)
        for key, value in dotenv_values(env_path).items()
        if value is not None
    }
    readable = SETTINGS_WHITELIST | CUSTOM_PROFILE_DISPLAY_KEYS | set(CUSTOM_TOTAL_INPUTS)
    return {k: value for k, value in all_values.items() if k in readable}


def get_project_file_size_limit(
    project_name: str,
    *,
    projects_root: pathlib.Path = DEFAULT_PROJECTS_ROOT,
) -> str:
    """Return the tenant upload limit without exposing the tenant env file."""
    try:
        values = dotenv_values(projects_root / project_name / ".env")
    except (OSError, ValueError) as exc:
        raise HTTPException(
            409, "Configuração de Storage do projeto indisponível"
        ) from exc

    value = str(values.get("FILE_SIZE_LIMIT") or "").strip()
    if re.fullmatch(r"\d+", value) and int(value) > 0:
        return value
    raise HTTPException(409, "FILE_SIZE_LIMIT ausente ou inválido no projeto")


def _normalize_setting_value(key: str, raw_value: str) -> str:
    value = str(raw_value).strip()
    if "\n" in value or "\r" in value or "\x00" in value:
        raise HTTPException(
            400, f"{key}: valor não pode conter quebra de linha ou byte nulo"
        )
    if not value:
        raise HTTPException(400, f"{key}: valor obrigatório")

    if key == "PROJECT_RESOURCE_PROFILE":
        if value not in RESOURCE_PROFILES:
            raise HTTPException(
                400, f"{key}: use small, medium, large ou custom"
            )
        return value

    if key == "PROJECT_MEM_LIMIT":
        if not re.fullmatch(r"\d+[mMgG]", value):
            raise HTTPException(400, f"{key}: use o formato 256m ou 1g")
        return value.lower()

    if key == "PROJECT_CPUS":
        if not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
            raise HTTPException(400, f"{key}: use o formato 1.50")
        return value

    if key == "PROJECT_PIDS_LIMIT":
        if not re.fullmatch(r"\d+", value) or int(value) < 1:
            raise HTTPException(400, f"{key}: use um número inteiro maior que zero")
        return value

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
    acceptable = SETTINGS_WHITELIST | set(CUSTOM_TOTAL_INPUTS)
    invalid_keys = set(settings.keys()) - acceptable
    if invalid_keys:
        raise HTTPException(
            400,
            f"Variáveis não permitidas: {', '.join(sorted(invalid_keys))}",
        )

    direct_totals = set(settings.keys()) & set(CUSTOM_TOTAL_INPUTS)
    if direct_totals and "PROJECT_RESOURCE_PROFILE" in settings:
        raise HTTPException(
            400,
            "Informe perfil pronto OU capacidade personalizada na mesma "
            "requisicao, nunca ambos",
        )

    derived_rejected = (
        set(settings.keys()) & DERIVED_LIMIT_KEYS
    ) - direct_totals
    if derived_rejected:
        raise HTTPException(
            400,
            "Limites resolvidos nao sao configuraveis diretamente: "
            f"use PROJECT_RESOURCE_PROFILE ({', '.join(sorted(derived_rejected))})",
        )

    if not settings:
        raise HTTPException(400, "Nenhuma configuração enviada")

    return {
        key: _normalize_setting_value(key, value) for key, value in settings.items()
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
            if key in updates and (
                key in SETTINGS_WHITELIST or key in DERIVED_LIMIT_KEYS
            ):
                value = updates[key]
                new_lines.append(f"{key}={value}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    for key, value in updates.items():
        if key not in updated_keys and (
            key in SETTINGS_WHITELIST or key in DERIVED_LIMIT_KEYS
        ):
            new_lines.append(f"{key}={value}\n")

    original = os.stat(env_path)
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
        temp_stat = os.stat(temp_path)
        if (temp_stat.st_uid, temp_stat.st_gid) != (
            original.st_uid,
            original.st_gid,
        ):
            os.chown(temp_path, original.st_uid, original.st_gid)
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
