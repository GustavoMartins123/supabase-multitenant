"""Contrato compartilhado entre a Projects API e o host-agent.

Este arquivo existe em duas copias byte-a-byte identicas:

- ``servidor/api-internal/app/host_agent_protocol.py``
- ``servidor/host-agent/hostagent/host_agent_protocol.py``

O teste ``tests/smoke/test_host_agent_contract.py`` falha se as copias
divergirem. Por isso o modulo nao pode ter imports relativos nem
dependencias externas: apenas stdlib.

O canal de intencao API -> agent e a tabela ``host_agent_commands`` no
Postgres do control plane. Cada linha carrega uma assinatura HMAC gerada
com ``HOST_AGENT_HMAC_SECRET``; o agent so executa comandos cuja
assinatura confere, entao um escritor arbitrario no banco nao consegue
forjar execucao no host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Any

PROTOCOL_VERSION = "v1"
NOTIFY_CHANNEL = "host_agent_commands"
OUTPUT_TAIL_LIMIT = 8_000
CONTAINER_LOGS_LIMIT = 256_000
MAX_INTENT_AGE_SECONDS = 24 * 60 * 60

# Timeout duro (em segundos) aplicado pelo agent a cada comando. O conjunto
# de chaves e o proprio conjunto fechado de comandos aceitos.
COMMAND_TIMEOUTS: dict[str, int] = {
    "start_project": 600,
    "stop_project": 600,
    "restart_project": 600,
    "recreate_services": 1_800,
    "create_project": 1_800,
    "duplicate_project": 3_600,
    "delete_project_containers": 300,
    "delete_project_files": 300,
    "rotate_keys": 900,
    "rename_project": 3_600,
    "backup_project": 1_800,
    "restore_project": 3_600,
    "delete_restore_point": 120,
    "container_logs": 60,
    "terminate_supavisor_tenant": 60,
    "delete_supavisor_tenant": 60,
    "delete_realtime_tenant": 60,
}

HOST_AGENT_COMMANDS = frozenset(COMMAND_TIMEOUTS)

# Tempo extra concedido apos SIGTERM antes do SIGKILL. Os scripts longos abaixo
# tratam TERM executando rollback compensatorio (Compose + banco/tenants).
COMMAND_TERM_GRACE: dict[str, int] = {
    "create_project": 180,
    "duplicate_project": 180,
    "rename_project": 240,
    "restore_project": 240,
}
DEFAULT_TERM_GRACE = 30

# Comandos que exigem admin global. Sao os passos fisicos do delete e a
# limpeza de tenants globais, espelhando a regra do endpoint de delete.
GLOBAL_ADMIN_COMMANDS = frozenset(
    {
        "delete_project_containers",
        "delete_project_files",
        "terminate_supavisor_tenant",
        "delete_supavisor_tenant",
        "delete_realtime_tenant",
    }
)

PROJECT_OWNER_COMMANDS = frozenset(
    {
        "restore_project",
        "delete_restore_point",
    }
)

# Comandos executaveis mesmo sem a linha do projeto no control plane: o
# delete remove a linha de ``projects`` antes da limpeza fisica.
PROJECT_ROW_OPTIONAL_COMMANDS = frozenset(
    {
        "delete_project_files",
        "terminate_supavisor_tenant",
        "delete_supavisor_tenant",
        "delete_realtime_tenant",
    }
)

# Espelho de app/validation.py. O agent revalida tudo localmente e nao
# confia na validacao feita pela API.
PROJECT_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
RESERVED_PROJECT_NAMES = frozenset(
    {
        "default", "select", "from", "where", "insert", "update", "delete",
        "table", "create", "drop", "join", "group", "order", "limit", "into",
        "index", "view", "trigger", "procedure", "function", "database",
        "schema", "primary", "foreign", "key", "constraint", "unique", "null",
        "not", "and", "or", "in", "like", "between", "exists", "having",
        "union", "inner", "left", "right", "outer", "cross", "on", "as",
        "case", "when", "then", "else", "end", "if", "while", "for", "begin",
        "commit", "rollback",
    }
)
RECREATE_SERVICE_NAMES = frozenset(
    {"auth", "rest", "storage", "imgproxy", "nginx", "meta"}
)
COPY_MODES = frozenset({"with-data", "schema-only"})
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
MAX_LOG_LINES = 1_000


def is_valid_project_name(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    return bool(PROJECT_NAME_RE.fullmatch(raw)) and raw not in RESERVED_PROJECT_NAMES


def is_valid_uuid(raw: Any) -> bool:
    return isinstance(raw, str) and bool(UUID_RE.fullmatch(raw.lower()))


def validate_command_args(command: str, project: str, args: dict[str, Any]) -> list[str]:
    """Valida o payload de um comando do conjunto fechado.

    Retorna a lista de erros; vazia significa payload aceito. E usada nos
    dois lados: a API valida antes de gravar a intencao e o agent revalida
    antes de executar.
    """
    errors: list[str] = []
    if command not in HOST_AGENT_COMMANDS:
        return [f"unknown_command:{command}"]
    if not is_valid_project_name(project):
        errors.append("invalid_project_name")
    if not isinstance(args, dict):
        return errors + ["args_must_be_object"]

    def require_project_field(field: str) -> None:
        if not is_valid_project_name(args.get(field)):
            errors.append(f"invalid_{field}")

    def reject_unknown(allowed: set[str]) -> None:
        unknown = set(args) - allowed
        if unknown:
            errors.append("unknown_args:" + ",".join(sorted(unknown)))

    if command in {
        "start_project",
        "stop_project",
        "restart_project",
        "delete_project_containers",
        "rotate_keys",
        "terminate_supavisor_tenant",
        "delete_supavisor_tenant",
        "delete_realtime_tenant",
    }:
        reject_unknown(set())
    elif command == "delete_project_files":
        reject_unknown({"tenant_uuid", "project_uuid"})
        if "tenant_uuid" in args and not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
        if "project_uuid" in args and not is_valid_uuid(args.get("project_uuid")):
            errors.append("invalid_project_uuid")
        if "tenant_uuid" in args and "project_uuid" in args:
            errors.append("duplicate_tenant_identity")
    elif command == "recreate_services":
        reject_unknown({"services"})
        services = args.get("services")
        if (
            not isinstance(services, list)
            or not services
            or not set(map(str, services)) <= RECREATE_SERVICE_NAMES
        ):
            errors.append("invalid_services")
    elif command == "create_project":
        reject_unknown({"tenant_uuid", "recover_stale", "stale_tenant_uuids"})
        if not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
        recover_stale = args.get("recover_stale", False)
        if not isinstance(recover_stale, bool):
            errors.append("invalid_recover_stale")
        stale_tenant_uuids = args.get("stale_tenant_uuids", [])
        if (
            not isinstance(stale_tenant_uuids, list)
            or len(stale_tenant_uuids) > 20
            or any(not is_valid_uuid(item) for item in stale_tenant_uuids)
        ):
            errors.append("invalid_stale_tenant_uuids")
        elif stale_tenant_uuids and recover_stale is not True:
            errors.append("stale_tenants_require_recovery")
    elif command == "duplicate_project":
        reject_unknown({"original_name", "copy_mode", "tenant_uuid"})
        require_project_field("original_name")
        if args.get("copy_mode") not in COPY_MODES:
            errors.append("invalid_copy_mode")
        if not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
    elif command == "rename_project":
        reject_unknown({"new_name"})
        require_project_field("new_name")
        if args.get("new_name") == project:
            errors.append("new_name_equals_project")
    elif command == "backup_project":
        reject_unknown({"backup_id", "tenant_uuid"})
        if not is_valid_uuid(args.get("backup_id")):
            errors.append("invalid_backup_id")
        if "tenant_uuid" in args and not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
    elif command == "restore_project":
        reject_unknown({"backup_id", "safety_backup_id", "tenant_uuid"})
        for field in ("backup_id", "safety_backup_id"):
            if not is_valid_uuid(args.get(field)):
                errors.append(f"invalid_{field}")
        if "tenant_uuid" in args and not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
        if args.get("backup_id") == args.get("safety_backup_id"):
            errors.append("backup_id_equals_safety_backup_id")
    elif command == "delete_restore_point":
        reject_unknown({"backup_id", "tenant_uuid"})
        if not is_valid_uuid(args.get("backup_id")):
            errors.append("invalid_backup_id")
        if "tenant_uuid" in args and not is_valid_uuid(args.get("tenant_uuid")):
            errors.append("invalid_tenant_uuid")
    elif command == "container_logs":
        reject_unknown({"service", "lines"})
        service = args.get("service")
        if not isinstance(service, str) or not re.fullmatch(
            r"[a-z][a-z0-9\-]{0,39}", service
        ):
            errors.append("invalid_service")
        lines = args.get("lines")
        if not isinstance(lines, int) or not 1 <= lines <= MAX_LOG_LINES:
            errors.append("invalid_lines")
    return errors


def canonical_args_hash(args: dict[str, Any] | None) -> str:
    payload = json.dumps(
        args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def intent_is_expired(issued_at: Any, *, now: int | None = None) -> bool:
    """Falha fechada quando a intencao nao e um timestamp recente."""
    try:
        issued_timestamp = int(issued_at)
    except (TypeError, ValueError, OverflowError):
        return True
    current_timestamp = int(time.time()) if now is None else int(now)
    return current_timestamp - issued_timestamp > MAX_INTENT_AGE_SECONDS


def command_signature(
    secret: str,
    *,
    command_id: str,
    command: str,
    project: str,
    project_uuid: str | None,
    requested_by: str | None,
    args: dict[str, Any] | None,
    issued_at: int,
) -> str:
    """Assina os campos imutaveis de uma intencao gravada no banco."""
    message = "\n".join(
        (
            PROTOCOL_VERSION,
            str(command_id),
            command,
            project,
            str(project_uuid or ""),
            str(requested_by or ""),
            canonical_args_hash(args),
            str(int(issued_at)),
        )
    )
    return hmac.new(
        secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_command_signature(
    secret: str,
    provided_signature: str | None,
    *,
    command_id: str,
    command: str,
    project: str,
    project_uuid: str | None,
    requested_by: str | None,
    args: dict[str, Any] | None,
    issued_at: int,
) -> bool:
    expected = command_signature(
        secret,
        command_id=command_id,
        command=command,
        project=project,
        project_uuid=project_uuid,
        requested_by=requested_by,
        args=args,
        issued_at=issued_at,
    )
    return hmac.compare_digest(expected, provided_signature or "")


_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}")
_KV_SECRET_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|APIKEY|API_KEY|"
    r"ACCESS_KEY|PRIVATE_KEY|MASTER_KEY|ANON_KEY|SERVICE_ROLE|_KEY|_DSN)"
    r"[A-Z0-9_]*)\s*[=:]\s*([^\s'\"]+)"
)
_URI_CRED_RE = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^/\s:@]+):([^@\s]+)@")
_BEARER_RE = re.compile(r"(?i)\b(authorization\s*:\s*bearer)\s+\S+")


def sanitize_output(text: str | None, *, tail_limit: int = OUTPUT_TAIL_LIMIT) -> str:
    """Redige segredos de stdout/stderr antes de qualquer persistencia.

    Cobre JWTs, atribuicoes ``CHAVE=valor`` de nomes sensiveis, credenciais
    embutidas em URIs e headers Bearer. Aplicada no agent antes de gravar
    tails no banco; a API reaproveita os tails ja sanitizados.
    """
    if not text:
        return ""
    cleaned = _JWT_RE.sub("[REDACTED_JWT]", text)
    cleaned = _KV_SECRET_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", cleaned)
    cleaned = _URI_CRED_RE.sub(lambda m: f"{m.group(1)}:[REDACTED]@", cleaned)
    cleaned = _BEARER_RE.sub(lambda m: f"{m.group(1)} [REDACTED]", cleaned)
    if tail_limit and len(cleaned) > tail_limit:
        cleaned = cleaned[-tail_limit:]
    return cleaned


def evaluate_authorization(
    command: str,
    *,
    user_exists: bool,
    user_active: bool,
    is_global_admin: bool,
    is_owner: bool,
    member_role: str | None,
    project_row_exists: bool,
    project_uuid_matches: bool,
) -> str | None:
    """Reavalia a autorizacao no agent com dados lidos do banco.

    Funcao pura para permitir teste unitario da matriz. Retorna um codigo
    de erro ou ``None`` quando autorizado. E defesa em profundidade: a API
    ja autorizou, mas o agent nao confia nisso.
    """
    if command not in HOST_AGENT_COMMANDS:
        return "unknown_command"
    if not user_exists:
        return "requester_unknown"
    if not user_active:
        return "requester_inactive"
    if command in GLOBAL_ADMIN_COMMANDS:
        if not is_global_admin:
            return "global_admin_required"
    elif command in PROJECT_OWNER_COMMANDS:
        if not (is_global_admin or is_owner):
            return "project_owner_required"
    else:
        if not (is_global_admin or is_owner or member_role == "admin"):
            return "project_admin_required"
    if command not in PROJECT_ROW_OPTIONAL_COMMANDS:
        if not project_row_exists:
            return "project_not_found"
        if not project_uuid_matches:
            return "project_uuid_mismatch"
    return None
