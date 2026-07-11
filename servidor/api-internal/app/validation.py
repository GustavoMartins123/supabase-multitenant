"""Validadores compartilhados pela API interna."""

import re
import uuid

from fastapi import HTTPException


RESERVED_WORDS = {
    "default", "select", "from", "where", "insert", "update", "delete",
    "table", "create", "drop", "join", "group", "order", "limit", "into",
    "index", "view", "trigger", "procedure", "function", "database",
    "schema", "primary", "foreign", "key", "constraint", "unique", "null",
    "not", "and", "or", "in", "like", "between", "exists", "having",
    "union", "inner", "left", "right", "outer", "cross", "on", "as",
    "case", "when", "then", "else", "end", "if", "while", "for", "begin",
    "commit", "rollback",
}
PROJECT_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
SERVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9\-]{0,39}$")


def normalize_groups(raw_groups: list[str] | tuple[str, ...] | str | None) -> list[str]:
    values = raw_groups.split(",") if isinstance(raw_groups, str) else raw_groups or []
    normalized: list[str] = []
    seen: set[str] = set()
    for group in values:
        clean = (group or "").strip().lower()
        if clean and clean not in seen:
            normalized.append(clean)
            seen.add(clean)
    return normalized


def parse_uuid_value(raw: str | None) -> uuid.UUID | None:
    candidate = (raw or "").strip()
    if not candidate:
        return None
    try:
        return uuid.UUID(candidate)
    except ValueError:
        return None


def validate_project_id(raw: str) -> str:
    name = raw.strip().lower()
    if not PROJECT_NAME_RE.fullmatch(name):
        raise HTTPException(
            400,
            "Nome invalido: use letras minusculas, numeros ou '_', "
            "(3-40 caracteres, comecando por letra ou '_').",
        )
    if name in RESERVED_WORDS:
        raise HTTPException(400, "Nome invalido: palavra reservada SQL.")
    return name


def validate_service_name(raw: str) -> str:
    name = raw.strip().lower()
    if not SERVICE_NAME_RE.fullmatch(name):
        raise HTTPException(
            400,
            "Nome de servico invalido: use letras minusculas, numeros ou '-'.",
        )
    return name
