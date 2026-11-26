"""Validate Studio SQL against role/password mutations and delegate Storage/Auth/Vector DDL."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import os
from pathlib import Path
import re
import time
from typing import Callable
from uuid import UUID

from dotenv import dotenv_values
from pglast import parse_sql
from pglast.stream import RawStream

from app.assistant_sql import (
    FUNCTIONS,
    NODES,
    TYPES,
    _builtin,
    _names,
    _nodes,
    _normalize,
)


class StoragePolicyError(ValueError):
    pass


@dataclass(frozen=True)
class _RawSql:
    sql: str


@dataclass(frozen=True)
class _VectorFdwGuardCall:
    fn_name: str
    fdw_name: str


@dataclass(frozen=True)
class _PinnedVectorServerSql:
    builder: Callable[[str, str], str]


DELEGATED_POLICY_TABLES = {
    ("storage", "objects"),
    ("storage", "buckets"),
}
DELEGATED_DDL_TABLES = {
    ("storage", "objects"),
    ("storage", "buckets"),
    ("auth", "users"),
    ("auth", "identities"),
}
DELEGATED_ROLE_SCHEMAS = {
    "supabase_storage_admin": "storage",
    "supabase_auth_admin": "auth",
}
RESERVED_SCHEMAS = {
    "pg_catalog",
    "pg_toast",
    "information_schema",
    "storage",
    "auth",
    "realtime",
    "_realtime",
    "_analytics",
    "net",
    "supabase_functions",
    "vault",
    "pgsodium",
    "cron",
    "studio_storage_guard",
    "studio_trigger_guard",
    "studio_vector_fdw_guard",
    "meta_guard",
    "extensions",
    "graphql",
    "graphql_public",
}
INTERNAL_GUARD_SCHEMAS = {
    "studio_storage_guard",
    "studio_trigger_guard",
    "studio_vector_fdw_guard",
}
INTERNAL_GUARD_EVENT_TRIGGERS = {
    "studio_guard_system_trigger_security",
    "studio_vector_fdw_enforce_server_endpoint",
}
PROTECTED_OWNER_ROLES = {
    "postgres",
    "supabase_admin",
    "supabase_storage_admin",
    "supabase_auth_admin",
    "supabase_functions_admin",
    "authenticator",
    "pgbouncer",
    "dashboard_user",
    "meta_guest",
    "anon",
    "authenticated",
    "service_role",
}
PROTECTED_OWNER_PREFIXES = (
    "idr_",
    "tenant_",
    "platform_",
    "mailer_",
    "client_configuration_",
    "key_authorizer",
    "host_agent_",
)
FORBIDDEN_ROLE_NODES = {
    "AlterRoleStmt",
    "AlterRoleSetStmt",
    "CreateRoleStmt",
    "DropRoleStmt",
    "GrantRoleStmt",
}
SAFE_EXPRESSION_NODES = {
    "A_Expr",
    "BoolExpr",
    "NullTest",
    "BooleanTest",
    "CaseExpr",
    "CaseWhen",
    "CoalesceExpr",
    "MinMaxExpr",
    "TypeCast",
    "ColumnRef",
    "A_Const",
    "Integer",
    "Float",
    "Boolean",
    "String",
    "BitString",
    "A_ArrayExpr",
    "A_Indirection",
    "A_Indices",
    "FuncCall",
    "NamedArgExpr",
    "TypeName",
    "SQLValueFunction",
}
SAFE_BUILTINS = FUNCTIONS | {
    "current_setting",
    "split_part",
    "left",
    "right",
    "strpos",
    "position",
    "regexp_replace",
    "regexp_match",
    "regexp_matches",
    "nullif",
    "array_length",
    "cardinality",
    "unnest",
    "to_json",
    "to_jsonb",
    "string_to_array",
    "array_to_string",
    "md5",
    "sha256",
    "encode",
    "decode",
    "convert_to",
    "convert_from",
    "octet_length",
    "bit_length",
    "lpad",
    "rpad",
    "translate",
    "initcap",
    "to_timestamp",
    "extract",
    "greatest",
    "least",
}
SAFE_INDEX_METHODS = {"btree", "hash", "gin", "gist", "brin"}

_IDENT_OR_FMT = r'(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*|%[IsL])'
_ROLE_OPTION_KW = (
    r"(?:WITH|PASSWORD|ENCRYPTED|UNENCRYPTED|SET|RESET|RENAME|"
    r"NO?(?:LOGIN|SUPERUSER|CREATEDB|CREATEROLE|INHERIT|REPLICATION|BYPASSRLS)|"
    r"CONNECTION|VALID|ADD|DROP|IN\s+ROLE|ROLE|ADMIN|USER|SYSID)\b"
)
_ALTER_ROLE_BODY_RE = re.compile(
    rf"\bALTER\s+(?:ROLE|USER|GROUP)\s+(?:CURRENT_USER|CURRENT_ROLE|SESSION_USER|ALL|{_IDENT_OR_FMT})\s+{_ROLE_OPTION_KW}",
    re.IGNORECASE,
)
_CREATE_ROLE_BODY_RE = re.compile(
    rf"\bCREATE\s+(?:(?:ROLE|GROUP)\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT_OR_FMT}"
    rf"|USER\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT_OR_FMT}\s+{_ROLE_OPTION_KW})",
    re.IGNORECASE,
)
_DROP_ROLE_BODY_RE = re.compile(
    rf"\bDROP\s+(?:ROLE|GROUP)\s+(?:IF\s+EXISTS\s+)?{_IDENT_OR_FMT}"
    rf"|\bDROP\s+USER\s+(?:IF\s+EXISTS\s+)?{_IDENT_OR_FMT}\s*(?:;|'|\"|\)|$)",
    re.IGNORECASE,
)
_SET_SESSION_AUTH_RE = re.compile(
    r"\bSET\s+(?:LOCAL\s+)?SESSION\s+AUTHORIZATION\b",
    re.IGNORECASE,
)
_DO_SET_DELEGATED_ROLE_RE = re.compile(
    r'\bSET\s+(?:LOCAL\s+)?ROLE\s+"?(?:supabase_storage_admin|supabase_auth_admin)"?\b',
    re.IGNORECASE,
)
_PROJECT_ID_RE = re.compile(r"^[a-z_][a-z0-9_]{2,39}$")
_FDW_NAME_RE = re.compile(r"^[a-z0-9_]{1,63}$")
_STORAGE_S3_REGION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_SAFE_UNQUOTED_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_PLPGSQL_VAR_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_DO_FDW_DDL_RE = re.compile(
    r"\b(?:CREATE|ALTER|DROP)\s+FOREIGN\s+DATA\s+WRAPPER\b",
    re.IGNORECASE,
)
_DO_CREATE_SERVER_RE = re.compile(r"\bCREATE\s+SERVER\b", re.IGNORECASE)
_DO_ALTER_SERVER_RE = re.compile(r"\bALTER\s+SERVER\b", re.IGNORECASE)
_DO_ENDPOINT_URL_RE = re.compile(r"\bendpoint_url\b", re.IGNORECASE)
_DO_EXECUTE_RE = re.compile(r"\bEXECUTE\b", re.IGNORECASE)
_DOLLAR_TAG_RE = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*)?\$")
_PG_RESERVED_SIMPLE = frozenset(
    {
        "all", "analyse", "analyze", "and", "any", "array", "as", "asc",
        "asymmetric", "authorization", "binary", "both", "case", "cast",
        "check", "collate", "collation", "column", "concurrently",
        "constraint", "create", "cross", "current_catalog", "current_date",
        "current_role", "current_schema", "current_time", "current_timestamp",
        "current_user", "default", "deferrable", "desc", "distinct", "do",
        "else", "end", "except", "false", "fetch", "for", "foreign", "freeze",
        "from", "full", "grant", "group", "having", "ilike", "in", "initially",
        "inner", "intersect", "into", "is", "isnull", "join", "lateral",
        "leading", "left", "like", "limit", "localtime", "localtimestamp",
        "natural", "not", "notnull", "null", "offset", "on", "only", "or",
        "order", "outer", "overlaps", "placing", "primary", "references",
        "returning", "right", "select", "session_user", "similar", "some",
        "symmetric", "table", "tablesample", "then", "to", "trailing", "true",
        "union", "unique", "user", "using", "variadic", "verbose", "when",
        "where", "window", "with",
    }
)
_WRAPPERS_CHECK_SQL = (
    "DO $wrappers_check$\n"
    "BEGIN\n"
    "    IF NOT EXISTS (\n"
    "        SELECT 1\n"
    "          FROM pg_catalog.pg_extension e\n"
    "          JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace\n"
    "         WHERE e.extname = 'wrappers' AND n.nspname = 'extensions'\n"
    "    ) THEN\n"
    "        RAISE EXCEPTION 'Extension wrappers must be pre-installed in schema extensions' USING ERRCODE = '42501';\n"
    "    END IF;\n"
    "END\n"
    "$wrappers_check$"
)


def _default_root_env_path() -> Path:
    resolved = Path(__file__).resolve()
    if len(resolved.parents) > 2 and (resolved.parents[2] / "api-internal").is_dir():
        return resolved.parents[2] / ".env"
    return resolved.parent.parent / ".env"


ROOT_ENV_PATH = _default_root_env_path()


def delegation_key(tenant_uuid):
    from urllib.parse import urlsplit
    from app.tenant_meta_identity import tenant_storage_policy_key
    master = urlsplit(os.getenv("META_ADMIN_DSN", "")).password or ""
    return tenant_storage_policy_key(tenant_uuid, master)


def vector_fdw_delegation_key(tenant_uuid, *, base_key: bytes | None = None) -> bytes:
    root = delegation_key(tenant_uuid) if base_key is None else base_key
    return hmac.new(root, b"studio-vector-fdw-v1", hashlib.sha256).digest()


def vector_fdw_endpoint_url(project_id: str | None) -> str:
    if not isinstance(project_id, str):
        raise StoragePolicyError("Identificador de projeto inválido para S3 Vectors FDW")
    normalized = project_id.strip()
    if not _PROJECT_ID_RE.fullmatch(normalized):
        raise StoragePolicyError("Identificador de projeto inválido para S3 Vectors FDW")
    return f"http://supabase-nginx-{normalized}:8081/vector"


def resolve_storage_s3_region(*, root_env_path: Path | None = None) -> str:
    env_value = (os.getenv("STORAGE_S3_REGION") or "").strip()
    if env_value:
        return normalize_storage_s3_region(env_value)
    env_path = ROOT_ENV_PATH if root_env_path is None else Path(root_env_path)
    if env_path.is_file() and not env_path.is_symlink():
        values = dotenv_values(env_path)
        file_value = (values.get("STORAGE_S3_REGION") or "").strip()
        if file_value:
            return normalize_storage_s3_region(file_value)
    return "us-east-1"


def normalize_storage_s3_region(storage_s3_region: str | None = None) -> str:
    if storage_s3_region is None:
        return resolve_storage_s3_region()
    raw = str(storage_s3_region).strip().lower()
    if not raw:
        raw = "us-east-1"
    if not _STORAGE_S3_REGION_RE.fullmatch(raw):
        raise StoragePolicyError("Região STORAGE_S3_REGION inválida para S3 Vectors FDW")
    return raw


def _quote_ident(name: str) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise StoragePolicyError("Identificador SQL inválido")
    return '"' + name.replace('"', '""') + '"'


def _format_ident(name: str, *, always_quote: bool = False) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise StoragePolicyError("Identificador SQL inválido")
    if (
        not always_quote
        and _SAFE_UNQUOTED_IDENT_RE.fullmatch(name)
        and name not in _PG_RESERVED_SIMPLE
    ):
        return name
    return _quote_ident(name)


def _quote_literal(value: str) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise StoragePolicyError("Literal SQL inválido")
    return "'" + value.replace("'", "''") + "'"


def _dollar_quote(body: str, tag_base: str = "studio_fdw_do") -> str:
    if "$$" not in body:
        return f"$${body}$$"
    tag = f"${tag_base}$"
    counter = 1
    while tag in body:
        tag = f"${tag_base}_{counter}$"
        counter += 1
    return f"{tag}{body}{tag}"


def _strip_sql_comments(sql: str) -> str:
    result: list[str] = []
    i = 0
    n = len(sql)
    block_depth = 0
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if block_depth > 0:
            if ch == "/" and nxt == "*":
                block_depth += 1
                i += 2
            elif ch == "*" and nxt == "/":
                block_depth -= 1
                result.append(" ")
                i += 2
            else:
                i += 1
            continue
        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] != "\n":
                i += 1
            result.append(" ")
            continue
        if ch == "/" and nxt == "*":
            block_depth = 1
            i += 2
            continue
        result.append(ch)
        i += 1
    return "".join(result)


def _check_body_for_role_mutations(body: str, *, allow_do_role_hint: bool = False) -> None:
    cleaned = _strip_sql_comments(body)
    if (
        _ALTER_ROLE_BODY_RE.search(cleaned)
        or _CREATE_ROLE_BODY_RE.search(cleaned)
        or _DROP_ROLE_BODY_RE.search(cleaned)
        or _SET_SESSION_AUTH_RE.search(cleaned)
    ):
        raise StoragePolicyError(
            "Alteração de roles e senhas do PostgreSQL pela interface não é permitida"
        )
    if allow_do_role_hint and _DO_SET_DELEGATED_ROLE_RE.search(cleaned):
        raise StoragePolicyError(
            "Use SET ROLE supabase_storage_admin/supabase_auth_admin como comando SQL direto (fora de blocos DO $$)"
        )


def _is_user_schema(schema: str | None) -> bool:
    return isinstance(schema, str) and bool(schema) and schema not in RESERVED_SCHEMAS and not schema.startswith("pg_")


def _extract_do_or_func_bodies(tree: dict) -> list[tuple[str, bool]]:
    bodies: list[tuple[str, bool]] = []
    kind = tree.get("@")
    if kind == "DoStmt":
        for arg in tree.get("args") or ():
            if arg.get("defname") == "as":
                val = arg.get("arg") or {}
                if isinstance(val, dict) and isinstance(val.get("sval"), str):
                    bodies.append((val["sval"], True))
    elif kind == "CreateFunctionStmt":
        for opt in tree.get("options") or ():
            if opt.get("defname") == "as":
                arg = opt.get("arg")
                if isinstance(arg, list):
                    for item in arg:
                        if isinstance(item, dict) and isinstance(item.get("sval"), str):
                            bodies.append((item["sval"], False))
                elif isinstance(arg, dict) and isinstance(arg.get("sval"), str):
                    bodies.append((arg["sval"], False))
    return bodies


def _is_protected_owner_role(role_name: str) -> bool:
    lowered = (role_name or "").lower()
    return lowered in PROTECTED_OWNER_ROLES or lowered.startswith(PROTECTED_OWNER_PREFIXES)


def _object_touches_internal_guard(obj) -> bool:
    if isinstance(obj, dict):
        if isinstance(obj.get("sval"), str) and obj["sval"].lower() in INTERNAL_GUARD_SCHEMAS:
            return True
        if obj.get("@") == "ObjectWithArgs":
            names = [
                item["sval"].lower()
                for item in (obj.get("objname") or ())
                if isinstance(item, dict) and isinstance(item.get("sval"), str)
            ]
            if names and names[0] in INTERNAL_GUARD_SCHEMAS:
                return True
        if obj.get("@") == "RangeVar" and (obj.get("schemaname") or "").lower() in INTERNAL_GUARD_SCHEMAS:
            return True
    elif isinstance(obj, list):
        names = [
            item["sval"].lower()
            for item in obj
            if isinstance(item, dict) and isinstance(item.get("sval"), str)
        ]
        if names and names[0] in INTERNAL_GUARD_SCHEMAS:
            return True
    return False


def _is_studio_postgres_schema_create(node: dict) -> bool:
    if node.get("@") != "CreateSchemaStmt":
        return False
    authrole = node.get("authrole")
    if not isinstance(authrole, dict):
        return False
    if authrole.get("roletype") != "ROLESPEC_CSTRING":
        return False
    if (authrole.get("rolename") or "").lower() != "postgres":
        return False
    schemaname = node.get("schemaname")
    if not isinstance(schemaname, str) or not _is_user_schema(schemaname.lower()):
        return False
    if node.get("schemaElts"):
        return False
    return True


def _check_forbidden_statement(tree: dict) -> None:
    for kind, node in _nodes(tree):
        if kind in FORBIDDEN_ROLE_NODES:
            raise StoragePolicyError(
                "Alteração de roles e senhas do PostgreSQL pela interface não é permitida"
            )
        if kind == "AlterFdwStmt":
            raise StoragePolicyError(
                "Alteração direta de foreign data wrappers pela interface não é permitida"
            )
        if kind == "AlterEventTrigStmt" and (node.get("trigname") or "").lower() in INTERNAL_GUARD_EVENT_TRIGGERS:
            raise StoragePolicyError(
                "Alteração nos schemas internos de guarda do Studio não é permitida"
            )
        if kind == "VariableSetStmt" and (node.get("name") or "").lower() == "session_authorization":
            raise StoragePolicyError(
                "Alteração de sessão/identidade do PostgreSQL pela interface não é permitida"
            )
        if kind == "AlterOwnerStmt" or (
            kind == "AlterTableCmd" and node.get("subtype") == "AT_ChangeOwner"
        ):
            newowner = node.get("newowner") or {}
            role_name = (newowner.get("rolename") or "").lower()
            if _is_protected_owner_role(role_name):
                raise StoragePolicyError(
                    "Alteração de dono para role privilegiada ou interna não é permitida"
                )
        if kind == "CreateSchemaStmt":
            schemaname = (node.get("schemaname") or "").lower()
            if schemaname in INTERNAL_GUARD_SCHEMAS:
                raise StoragePolicyError(
                    "Alteração nos schemas internos de guarda do Studio não é permitida"
                )
            authrole = node.get("authrole")
            if isinstance(authrole, dict) and not _is_studio_postgres_schema_create(node):
                role_name = (authrole.get("rolename") or "").lower()
                if _is_protected_owner_role(role_name):
                    raise StoragePolicyError(
                        "Alteração de dono para role privilegiada ou interna não é permitida"
                    )
        if kind == "RangeVar" and (node.get("schemaname") or "").lower() in INTERNAL_GUARD_SCHEMAS:
            raise StoragePolicyError(
                "Alteração nos schemas internos de guarda do Studio não é permitida"
            )
        if kind == "FuncCall":
            names = [n.lower() for n in _names(node.get("funcname") or ())]
            if len(names) >= 2 and names[0] in INTERNAL_GUARD_SCHEMAS:
                raise StoragePolicyError(
                    "Alteração ou chamada direta aos schemas internos de guarda do Studio não é permitida"
                )
        if kind == "DropStmt":
            for obj in node.get("objects") or ():
                if _object_touches_internal_guard(obj):
                    raise StoragePolicyError(
                        "Alteração nos schemas internos de guarda do Studio não é permitida"
                    )
                if (
                    node.get("removeType") == "OBJECT_EVENT_TRIGGER"
                    and isinstance(obj, dict)
                    and (obj.get("sval") or "").lower() in INTERNAL_GUARD_EVENT_TRIGGERS
                ):
                    raise StoragePolicyError(
                        "Alteração nos schemas internos de guarda do Studio não é permitida"
                    )
        if kind == "AlterObjectSchemaStmt":
            if (node.get("newschema") or "").lower() in INTERNAL_GUARD_SCHEMAS or _object_touches_internal_guard(
                node.get("object")
            ):
                raise StoragePolicyError(
                    "Alteração nos schemas internos de guarda do Studio não é permitida"
                )
        if kind == "RenameStmt":
            if (node.get("subname") or "").lower() in INTERNAL_GUARD_SCHEMAS or (
                node.get("newname") or ""
            ).lower() in INTERNAL_GUARD_SCHEMAS or _object_touches_internal_guard(node.get("object")):
                raise StoragePolicyError(
                    "Alteração nos schemas internos de guarda do Studio não é permitida"
                )
        if kind == "GrantStmt":
            for obj in node.get("objects") or ():
                if _object_touches_internal_guard(obj):
                    raise StoragePolicyError(
                        "Alteração nos schemas internos de guarda do Studio não é permitida"
                    )
        if kind == "AlterFunctionStmt" and _object_touches_internal_guard(node.get("func")):
            raise StoragePolicyError(
                "Alteração nos schemas internos de guarda do Studio não é permitida"
            )
    for body, is_do in _extract_do_or_func_bodies(tree):
        _check_body_for_role_mutations(body, allow_do_role_hint=is_do)
        cleaned = _strip_sql_comments(body)
        if is_do:
            if _DO_FDW_DDL_RE.search(cleaned):
                raise StoragePolicyError(
                    "Use CREATE/DROP FOREIGN DATA WRAPPER como comando SQL direto (fora de blocos DO $$)"
                )
            if _DO_ALTER_SERVER_RE.search(cleaned):
                raise StoragePolicyError(
                    "Use ALTER SERVER como comando SQL direto (fora de blocos DO $$)"
                )
        else:
            if (
                _DO_FDW_DDL_RE.search(cleaned)
                or _DO_CREATE_SERVER_RE.search(cleaned)
                or _DO_ALTER_SERVER_RE.search(cleaned)
                or _DO_ENDPOINT_URL_RE.search(cleaned)
            ):
                raise StoragePolicyError(
                    "Alteração dinâmica de servidores ou FDWs S3 Vectors dentro de funções não é permitida"
                )


def _find_execute_format_spans(body: str) -> list[tuple[int, int, str]]:
    """Locate all top-level EXECUTE FORMAT(...) calls outside SQL comments and strings."""
    spans: list[tuple[int, int, str]] = []
    n = len(body)
    i = 0

    def skip_ws_and_comments(pos: int) -> int:
        while pos < n:
            if body[pos].isspace():
                pos += 1
                continue
            if body[pos : pos + 2] == "--":
                pos += 2
                while pos < n and body[pos] != "\n":
                    pos += 1
                continue
            if body[pos : pos + 2] == "/*":
                depth = 1
                pos += 2
                while pos < n and depth > 0:
                    if body[pos : pos + 2] == "/*":
                        depth += 1
                        pos += 2
                    elif body[pos : pos + 2] == "*/":
                        depth -= 1
                        pos += 2
                    else:
                        pos += 1
                continue
            break
        return pos

    def skip_single_quoted(pos: int, escape_backslash: bool) -> int:
        pos += 1  # opening '
        while pos < n:
            ch = body[pos]
            if escape_backslash and ch == "\\" and pos + 1 < n:
                pos += 2
                continue
            if ch == "'":
                if pos + 1 < n and body[pos + 1] == "'":
                    pos += 2
                    continue
                return pos + 1
            pos += 1
        raise StoragePolicyError("String SQL não terminada em bloco DO $$")

    def skip_double_quoted(pos: int) -> int:
        pos += 1
        while pos < n:
            if body[pos] == '"':
                if pos + 1 < n and body[pos + 1] == '"':
                    pos += 2
                    continue
                return pos + 1
            pos += 1
        raise StoragePolicyError("Identificador SQL não terminado em bloco DO $$")

    def skip_dollar_quoted(pos: int) -> int:
        match = _DOLLAR_TAG_RE.match(body, pos)
        if not match:
            return pos + 1
        tag = match.group(0)
        end = body.find(tag, match.end())
        if end == -1:
            raise StoragePolicyError("String dollar-quoted não terminada em bloco DO $$")
        return end + len(tag)

    def read_word(pos: int) -> tuple[str, int]:
        start = pos
        while pos < n and (body[pos].isalnum() or body[pos] == "_"):
            pos += 1
        return body[start:pos], pos

    while i < n:
        ch = body[i]
        nxt = body[i + 1] if i + 1 < n else ""
        if ch == "-" and nxt == "-":
            i = skip_ws_and_comments(i)
            continue
        if ch == "/" and nxt == "*":
            i = skip_ws_and_comments(i)
            continue
        if ch in ("E", "e") and nxt == "'" and (i == 0 or not (body[i - 1].isalnum() or body[i - 1] == "_")):
            i = skip_single_quoted(i + 1, escape_backslash=True)
            continue
        if ch == "'":
            i = skip_single_quoted(i, escape_backslash=False)
            continue
        if ch == '"':
            i = skip_double_quoted(i)
            continue
        if ch == "$":
            i = skip_dollar_quoted(i)
            continue
        if ch.isalpha() or ch == "_":
            word_start = i
            word, word_end = read_word(i)
            if word.lower() == "execute":
                pos = skip_ws_and_comments(word_end)
                if pos < n and (body[pos].isalpha() or body[pos] == "_"):
                    fn_word, fn_end = read_word(pos)
                    if fn_word.lower() == "format":
                        open_pos = skip_ws_and_comments(fn_end)
                        if open_pos < n and body[open_pos] == "(":
                            args_start = open_pos + 1
                            cur = args_start
                            depth = 1
                            while cur < n and depth > 0:
                                c = body[cur]
                                cn = body[cur + 1] if cur + 1 < n else ""
                                if c == "-" and cn == "-":
                                    cur = skip_ws_and_comments(cur)
                                    continue
                                if c == "/" and cn == "*":
                                    cur = skip_ws_and_comments(cur)
                                    continue
                                if c in ("E", "e") and cn == "'" and (
                                    cur == 0 or not (body[cur - 1].isalnum() or body[cur - 1] == "_")
                                ):
                                    cur = skip_single_quoted(cur + 1, escape_backslash=True)
                                    continue
                                if c == "'":
                                    cur = skip_single_quoted(cur, escape_backslash=False)
                                    continue
                                if c == '"':
                                    cur = skip_double_quoted(cur)
                                    continue
                                if c == "$":
                                    cur = skip_dollar_quoted(cur)
                                    continue
                                if c == "(":
                                    depth += 1
                                elif c == ")":
                                    depth -= 1
                                    if depth == 0:
                                        spans.append((word_start, cur + 1, body[args_start:cur]))
                                        i = cur + 1
                                        break
                                cur += 1
                            else:
                                raise StoragePolicyError("Chamada execute format() incompleta em bloco DO $$")
                            continue
            i = word_end
            continue
        i += 1
    return spans


def _substitute_format_placeholders(template: str) -> tuple[str, int]:
    out: list[str] = []
    i = 0
    n = len(template)
    arg_idx = 0
    while i < n:
        if template[i : i + 4] == "'%s'":
            out.append(f"'__STUDIO_FMT_{arg_idx}__'")
            arg_idx += 1
            i += 4
            continue
        if template[i : i + 2] == "%%":
            out.append("%")
            i += 2
            continue
        if template[i : i + 2] == "%L":
            out.append(f"'__STUDIO_FMT_{arg_idx}__'")
            arg_idx += 1
            i += 2
            continue
        if template[i] == "%":
            raise StoragePolicyError(
                "Bloco DO $$ com CREATE SERVER usa especificador format() não suportado"
            )
        out.append(template[i])
        i += 1
    return "".join(out), arg_idx


def _render_safe_format_arg(arg_node: dict) -> str:
    kind = arg_node.get("@")
    if kind == "ColumnRef":
        fields = arg_node.get("fields") or []
        if (
            len(fields) == 1
            and isinstance(fields[0], dict)
            and fields[0].get("@") == "String"
            and isinstance(fields[0].get("sval"), str)
            and _PLPGSQL_VAR_RE.fullmatch(fields[0]["sval"])
        ):
            return fields[0]["sval"]
    elif kind == "A_Const":
        val = arg_node.get("val") or {}
        if isinstance(val, dict) and val.get("@") == "String" and isinstance(val.get("sval"), str):
            return _quote_literal(val["sval"])
    raise StoragePolicyError("Argumento não permitido em execute format() de CREATE SERVER")


def _build_create_server_sql(
    tree: dict,
    endpoint_url: str,
    aws_region: str,
) -> str:
    servername = tree.get("servername")
    fdwname = tree.get("fdwname")
    if not isinstance(servername, str) or not isinstance(fdwname, str):
        raise StoragePolicyError("Definição de CREATE SERVER inválida")
    parts = ["CREATE SERVER"]
    if tree.get("if_not_exists"):
        parts.append("IF NOT EXISTS")
    parts.append(_format_ident(servername))
    if isinstance(tree.get("servertype"), str):
        parts.append(f"TYPE {_quote_literal(tree['servertype'])}")
    if isinstance(tree.get("version"), str):
        parts.append(f"VERSION {_quote_literal(tree['version'])}")
    parts.append(f"FOREIGN DATA WRAPPER {_format_ident(fdwname)}")

    options: list[str] = []
    for opt in tree.get("options") or ():
        defname = (opt.get("defname") or "").strip()
        if not defname:
            raise StoragePolicyError("Opção de CREATE SERVER inválida")
        lowered = defname.lower()
        if lowered in {"endpoint_url", "aws_region"}:
            continue
        arg = opt.get("arg") or {}
        if not isinstance(arg, dict) or arg.get("@") != "String" or not isinstance(arg.get("sval"), str):
            raise StoragePolicyError(f"Valor inválido para opção {defname} em CREATE SERVER")
        options.append(f"{_format_ident(defname)} {_quote_literal(arg['sval'])}")

    options.append(f"aws_region {_quote_literal(aws_region)}")
    options.append(f"endpoint_url {_quote_literal(endpoint_url)}")
    parts.append(f"OPTIONS ({', '.join(options)})")
    return " ".join(parts)


def _rewrite_create_extension(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "CreateExtensionStmt":
        return None
    if (tree.get("extname") or "").lower() != "wrappers":
        return None
    for opt in tree.get("options") or ():
        defname = (opt.get("defname") or "").lower()
        if defname not in {"schema", "new_version", "cascade"}:
            raise StoragePolicyError("Opção não suportada na instalação da extensão wrappers")
        if defname == "schema":
            schema_val = ((opt.get("arg") or {}).get("sval") or "").lower()
            if schema_val != "extensions":
                raise StoragePolicyError("A extensão wrappers só é permitida no schema extensions")
    return (_RawSql(_WRAPPERS_CHECK_SQL), False)


def _rewrite_create_fdw(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "CreateFdwStmt":
        return None
    fdw_name = tree.get("fdwname") or ""
    if not isinstance(fdw_name, str) or not _FDW_NAME_RE.fullmatch(fdw_name):
        raise StoragePolicyError("Nome de foreign data wrapper inválido")
    if tree.get("options"):
        raise StoragePolicyError("Opções diretas em CREATE FOREIGN DATA WRAPPER não são permitidas")
    func_map: dict[str, list[str]] = {}
    for opt in tree.get("func_options") or ():
        defname = (opt.get("defname") or "").lower()
        arg = opt.get("arg")
        if defname not in {"handler", "validator"} or not isinstance(arg, list):
            raise StoragePolicyError(
                "Apenas foreign data wrappers s3_vectors_fdw são permitidos pela interface"
            )
        func_map[defname] = [part.lower() for part in _names(arg)]
    if func_map.get("handler") not in (
        ["s3_vectors_fdw_handler"],
        ["extensions", "s3_vectors_fdw_handler"],
    ) or func_map.get("validator") not in (
        ["s3_vectors_fdw_validator"],
        ["extensions", "s3_vectors_fdw_validator"],
    ):
        raise StoragePolicyError(
            "Apenas foreign data wrappers s3_vectors_fdw são permitidos pela interface"
        )
    return (_VectorFdwGuardCall("ensure_s3_vectors_fdw", fdw_name), True)


def _rewrite_drop_fdw(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "DropStmt" or tree.get("removeType") != "OBJECT_FDW":
        return None
    objects = tree.get("objects") or []
    if len(objects) != 1 or not isinstance(objects[0], dict) or not isinstance(objects[0].get("sval"), str):
        raise StoragePolicyError("Remova um foreign data wrapper S3 Vectors por vez")
    fdw_name = objects[0]["sval"]
    if not _FDW_NAME_RE.fullmatch(fdw_name):
        raise StoragePolicyError("Nome de foreign data wrapper inválido")
    return (_VectorFdwGuardCall("drop_s3_vectors_fdw", fdw_name), True)


def _rewrite_create_server(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "CreateForeignServerStmt":
        return None
    # Validate AST shape eagerly before deferring endpoint/region pinning to rewrite time.
    _build_create_server_sql(tree, "http://supabase-nginx-placeholder:8081/vector", "us-east-1")
    return (
        _PinnedVectorServerSql(
            lambda endpoint_url, aws_region, stmt_tree=tree: _build_create_server_sql(
                stmt_tree, endpoint_url, aws_region
            )
        ),
        False,
    )


def _rewrite_alter_server(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "AlterForeignServerStmt":
        return None
    servername = tree.get("servername")
    if not isinstance(servername, str) or not servername:
        raise StoragePolicyError("Definição de ALTER SERVER inválida")
    options = tree.get("options") or ()
    touches_pinned = False
    parsed_opts: list[tuple[str, str, str | None]] = []
    for opt in options:
        defname = (opt.get("defname") or "").strip()
        if not defname:
            raise StoragePolicyError("Opção inválida em ALTER SERVER")
        action = {
            "DEFELEM_ADD": "ADD",
            "DEFELEM_SET": "SET",
            "DEFELEM_DROP": "DROP",
            "DEFELEM_UNSPEC": "",
        }.get(opt.get("defaction") or "DEFELEM_UNSPEC")
        if action is None:
            raise StoragePolicyError("Ação inválida em ALTER SERVER OPTIONS")
        lowered = defname.lower()
        if lowered in {"endpoint_url", "aws_region"}:
            if action == "DROP":
                raise StoragePolicyError(
                    "Não é permitido remover endpoint_url ou aws_region de servidores S3 Vectors"
                )
            touches_pinned = True
            parsed_opts.append((action, lowered, None))
        else:
            if action == "DROP":
                parsed_opts.append((action, defname, None))
            else:
                arg = opt.get("arg") or {}
                if not isinstance(arg, dict) or arg.get("@") != "String" or not isinstance(arg.get("sval"), str):
                    raise StoragePolicyError(f"Valor inválido para opção {defname} em ALTER SERVER")
                parsed_opts.append((action, defname, arg["sval"]))
    if not touches_pinned:
        return None

    def _build(endpoint_url: str, aws_region: str) -> str:
        parts = ["ALTER SERVER", _format_ident(servername)]
        if tree.get("has_version") and isinstance(tree.get("version"), str):
            parts.append(f"VERSION {_quote_literal(tree['version'])}")
        rendered_opts: list[str] = []
        for action, opt_name, opt_val in parsed_opts:
            prefix = f"{action} " if action else ""
            if opt_name == "endpoint_url":
                rendered_opts.append(f"{prefix}endpoint_url {_quote_literal(endpoint_url)}")
            elif opt_name == "aws_region":
                rendered_opts.append(f"{prefix}aws_region {_quote_literal(aws_region)}")
            elif action == "DROP":
                rendered_opts.append(f"DROP {_format_ident(opt_name)}")
            else:
                rendered_opts.append(f"{prefix}{_format_ident(opt_name)} {_quote_literal(opt_val or '')}")
        parts.append(f"OPTIONS ({', '.join(rendered_opts)})")
        return " ".join(parts)

    return (_PinnedVectorServerSql(_build), False)


def _rewrite_vector_server_do_stmt(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "DoStmt":
        return None
    body: str | None = None
    language: str | None = None
    for arg in tree.get("args") or ():
        defname = (arg.get("defname") or "").lower()
        val = arg.get("arg") or {}
        if defname == "as" and isinstance(val, dict) and isinstance(val.get("sval"), str):
            body = val["sval"]
        elif defname == "language" and isinstance(val, dict) and isinstance(val.get("sval"), str):
            language = val["sval"]
    if body is None:
        return None
    cleaned = _strip_sql_comments(body)
    if not (_DO_CREATE_SERVER_RE.search(cleaned) or _DO_ENDPOINT_URL_RE.search(cleaned)):
        return None
    if language is not None and language.lower() != "plpgsql":
        raise StoragePolicyError("Bloco DO com CREATE SERVER deve usar linguagem plpgsql")

    spans = _find_execute_format_spans(body)
    if len(spans) != 1:
        raise StoragePolicyError(
            "CREATE SERVER dentro de bloco DO $$ só é permitido via execute format() padrão do S3 Vectors"
        )
    span_start, span_end, inner_args_str = spans[0]
    remainder_cleaned = _strip_sql_comments(body[:span_start] + " " + body[span_end:])
    if (
        _DO_CREATE_SERVER_RE.search(remainder_cleaned)
        or _DO_ALTER_SERVER_RE.search(remainder_cleaned)
        or _DO_FDW_DDL_RE.search(remainder_cleaned)
        or _DO_ENDPOINT_URL_RE.search(remainder_cleaned)
        or _DO_EXECUTE_RE.search(remainder_cleaned)
    ):
        raise StoragePolicyError(
            "Bloco DO $$ com CREATE SERVER não pode conter outros comandos dinâmicos EXECUTE ou referências a endpoint_url"
        )

    try:
        fmt_parsed = parse_sql(f"SELECT format({inner_args_str})")
    except Exception as exc:
        raise StoragePolicyError("Chamada execute format() inválida para CREATE SERVER") from exc
    if len(fmt_parsed) != 1:
        raise StoragePolicyError("Chamada execute format() inválida para CREATE SERVER")
    fmt_select = _normalize(fmt_parsed[0].stmt())
    targets = fmt_select.get("targetList") or []
    if len(targets) != 1:
        raise StoragePolicyError("Chamada execute format() inválida para CREATE SERVER")
    fmt_call = (targets[0] or {}).get("val") or {}
    if fmt_call.get("@") != "FuncCall" or [p.lower() for p in _names(fmt_call.get("funcname") or ())] != ["format"]:
        raise StoragePolicyError("Chamada execute format() inválida para CREATE SERVER")
    call_args = fmt_call.get("args") or []
    if not call_args:
        raise StoragePolicyError("Chamada execute format() inválida para CREATE SERVER")
    first_arg = call_args[0]
    if (
        first_arg.get("@") != "A_Const"
        or not isinstance(first_arg.get("val"), dict)
        or first_arg["val"].get("@") != "String"
        or not isinstance(first_arg["val"].get("sval"), str)
    ):
        raise StoragePolicyError("Template de execute format() para CREATE SERVER deve ser literal")

    template_str = first_arg["val"]["sval"]
    rest_args = call_args[1:]
    substituted_sql, placeholder_count = _substitute_format_placeholders(template_str)
    if placeholder_count != len(rest_args):
        raise StoragePolicyError("Quantidade de argumentos em execute format() não corresponde ao template")
    # Validate every caller format argument is a safe variable or literal (no side-effecting expressions).
    rendered_args = [_render_safe_format_arg(arg_node) for arg_node in rest_args]

    try:
        inner_stmts = parse_sql(substituted_sql)
    except Exception as exc:
        raise StoragePolicyError("SQL de CREATE SERVER inválido dentro de execute format()") from exc
    if len(inner_stmts) != 1:
        raise StoragePolicyError("execute format() de CREATE SERVER deve conter exatamente um comando")
    server_tree = _normalize(inner_stmts[0].stmt())
    if server_tree.get("@") != "CreateForeignServerStmt":
        raise StoragePolicyError("execute format() em bloco DO $$ S3 Vectors deve executar apenas CREATE SERVER")

    servername = server_tree.get("servername")
    fdwname = server_tree.get("fdwname")
    if not isinstance(servername, str) or not isinstance(fdwname, str):
        raise StoragePolicyError("Definição de CREATE SERVER inválida em execute format()")

    sentinel_re = re.compile(r"^__STUDIO_FMT_(\d+)__$")
    preserved_opt_specs: list[tuple[str, str]] = []
    for opt in server_tree.get("options") or ():
        defname = (opt.get("defname") or "").strip()
        if not defname:
            raise StoragePolicyError("Opção inválida em CREATE SERVER")
        lowered = defname.lower()
        if lowered in {"endpoint_url", "aws_region"}:
            continue
        arg = opt.get("arg") or {}
        if not isinstance(arg, dict) or arg.get("@") != "String" or not isinstance(arg.get("sval"), str):
            raise StoragePolicyError(f"Valor inválido para opção {defname} em CREATE SERVER")
        raw_val = arg["sval"]
        m = sentinel_re.fullmatch(raw_val)
        if m:
            idx = int(m.group(1))
            preserved_opt_specs.append((_format_ident(defname), rendered_args[idx]))
        else:
            if "__STUDIO_FMT_" in raw_val:
                raise StoragePolicyError("Interpolação parcial de opção em CREATE SERVER não é permitida")
            preserved_opt_specs.append((_format_ident(defname), _quote_literal(raw_val)))

    prefix_parts = ["CREATE SERVER"]
    if server_tree.get("if_not_exists"):
        prefix_parts.append("IF NOT EXISTS")
    prefix_parts.append(_format_ident(servername))
    if isinstance(server_tree.get("servertype"), str):
        prefix_parts.append(f"TYPE {_quote_literal(server_tree['servertype'])}")
    if isinstance(server_tree.get("version"), str):
        prefix_parts.append(f"VERSION {_quote_literal(server_tree['version'])}")
    prefix_parts.append(f"FOREIGN DATA WRAPPER {_format_ident(fdwname)}")
    header_sql = " ".join(prefix_parts)
    prefix_body = body[:span_start]
    suffix_body = body[span_end:]
    lang_clause = f" LANGUAGE {_format_ident(language)}" if language else ""

    def _build(endpoint_url: str, aws_region: str) -> str:
        option_clauses = [f"{name} %L" for name, _ in preserved_opt_specs]
        option_clauses.extend(["aws_region %L", "endpoint_url %L"])
        format_args = [expr for _, expr in preserved_opt_specs]
        format_args.extend([_quote_literal(aws_region), _quote_literal(endpoint_url)])
        rebuilt_template = f"{header_sql} OPTIONS ({', '.join(option_clauses)});"
        rebuilt_exec = f"execute format({_quote_literal(rebuilt_template)}, {', '.join(format_args)})"
        rebuilt_body = f"{prefix_body}{rebuilt_exec}{suffix_body}"
        return f"DO{lang_clause} {_dollar_quote(rebuilt_body)}"

    return (_PinnedVectorServerSql(_build), False)


def _rewrite_create_schema(tree: dict) -> tuple[object, bool] | None:
    if not _is_studio_postgres_schema_create(tree):
        return None
    parts = ["CREATE SCHEMA"]
    if tree.get("if_not_exists"):
        parts.append("IF NOT EXISTS")
    parts.append(_format_ident(tree["schemaname"]))
    return (_RawSql(" ".join(parts)), False)


def _rewrite_import_foreign_schema(tree: dict) -> tuple[object, bool] | None:
    if tree.get("@") != "ImportForeignSchemaStmt":
        return None
    options = tree.get("options") or ()
    bucket_name: str | None = None
    remaining_opts: list[str] = []
    for opt in options:
        defname = (opt.get("defname") or "").strip()
        if not defname:
            raise StoragePolicyError("Opção inválida em IMPORT FOREIGN SCHEMA")
        arg = opt.get("arg") or {}
        if not isinstance(arg, dict) or arg.get("@") != "String" or not isinstance(arg.get("sval"), str):
            raise StoragePolicyError(f"Valor inválido para opção {defname} em IMPORT FOREIGN SCHEMA")
        if defname.lower() == "bucket_name":
            if bucket_name is not None:
                raise StoragePolicyError("Opção bucket_name duplicada em IMPORT FOREIGN SCHEMA")
            bucket_name = arg["sval"]
        else:
            remaining_opts.append(f"{_format_ident(defname)} {_quote_literal(arg['sval'])}")
    if bucket_name is None:
        return None
    if not bucket_name.strip() or "\x00" in bucket_name:
        raise StoragePolicyError("Nome de bucket inválido em IMPORT FOREIGN SCHEMA")
    local_schema = tree.get("local_schema") or ""
    server_name = tree.get("server_name") or ""
    if not isinstance(local_schema, str) or not _is_user_schema(local_schema.lower()):
        raise StoragePolicyError("Schema alvo inválido em IMPORT FOREIGN SCHEMA")
    if not isinstance(server_name, str) or not server_name:
        raise StoragePolicyError("Servidor inválido em IMPORT FOREIGN SCHEMA")

    parts = ["IMPORT FOREIGN SCHEMA", _quote_ident(bucket_name)]
    list_type = tree.get("list_type") or "FDW_IMPORT_SCHEMA_ALL"
    table_list = tree.get("table_list") or ()
    if list_type == "FDW_IMPORT_SCHEMA_LIMIT_TO":
        tables = [_format_ident(rv["relname"]) for rv in table_list if isinstance(rv, dict) and rv.get("relname")]
        parts.append(f"LIMIT TO ({', '.join(tables)})")
    elif list_type == "FDW_IMPORT_SCHEMA_EXCEPT":
        tables = [_format_ident(rv["relname"]) for rv in table_list if isinstance(rv, dict) and rv.get("relname")]
        parts.append(f"EXCEPT ({', '.join(tables)})")
    parts.extend(["FROM SERVER", _format_ident(server_name), "INTO", _format_ident(local_schema)])
    if remaining_opts:
        parts.append(f"OPTIONS ({', '.join(remaining_opts)})")
    return (_RawSql(" ".join(parts)), False)


def _rewrite_vector_fdw_statement(tree: dict) -> tuple[object, bool] | None:
    for handler in (
        _rewrite_create_extension,
        _rewrite_create_fdw,
        _rewrite_drop_fdw,
        _rewrite_create_server,
        _rewrite_alter_server,
        _rewrite_vector_server_do_stmt,
        _rewrite_create_schema,
        _rewrite_import_foreign_schema,
    ):
        rewritten = handler(tree)
        if rewritten is not None:
            return rewritten
    return None


def _delegated_role_stmt(tree: dict) -> tuple[str, str | None, bool] | None:
    """Return ('set', role, is_local), ('reset', None, is_local), or None."""
    if tree.get("@") != "VariableSetStmt" or (tree.get("name") or "").lower() != "role":
        return None
    kind = tree.get("kind")
    is_local = bool(tree.get("is_local"))
    if kind in {"VAR_RESET", "VAR_SET_DEFAULT"}:
        return ("reset", None, is_local)
    if kind == "VAR_SET_VALUE":
        args = tree.get("args") or []
        if len(args) == 1 and isinstance(args[0], dict) and args[0].get("@") == "A_Const":
            val = args[0].get("val") or {}
            role_name = (val.get("sval") or "").lower()
            if role_name == "none":
                return ("reset", None, is_local)
            if role_name in DELEGATED_ROLE_SCHEMAS:
                return ("set", role_name, is_local)
        raise StoragePolicyError(
            "SET ROLE pela interface só é permitido para operações delegadas de supabase_storage_admin ou supabase_auth_admin"
        )
    raise StoragePolicyError(
        "SET ROLE pela interface só é permitido para operações delegadas de supabase_storage_admin ou supabase_auth_admin"
    )


def _delegated_target(tree: dict) -> tuple[str, str] | None:
    """Return (kind, schema) if statement is delegated Storage/Auth DDL, else None."""
    stmt_type = tree["@"]

    if stmt_type in {"CreatePolicyStmt", "AlterPolicyStmt"}:
        table = tree["table"]
        schema = table.get("schemaname")
        if schema != "storage":
            return None
        if table.get("catalogname") or (schema, table["relname"]) not in DELEGATED_POLICY_TABLES:
            raise StoragePolicyError(
                "Gerencie políticas somente de storage.objects ou storage.buckets"
            )
        return ("policy", "storage")

    if stmt_type == "DropStmt" and tree.get("removeType") == "OBJECT_POLICY":
        objects = [_names(parts) for parts in tree["objects"]]
        if not any(parts and parts[0] == "storage" for parts in objects):
            return None
        if tree["behavior"] != "DROP_RESTRICT" or any(
            len(parts) != 3 or (parts[0], parts[1]) not in DELEGATED_POLICY_TABLES
            for parts in objects
        ):
            raise StoragePolicyError("Remova uma política de Storage sem CASCADE")
        return ("policy_drop", "storage")

    if stmt_type == "CreateTrigStmt":
        relation = tree["relation"]
        schema = relation.get("schemaname")
        if schema not in {"storage", "auth"}:
            return None
        if relation.get("catalogname") or (schema, relation["relname"]) not in DELEGATED_DDL_TABLES:
            raise StoragePolicyError(
                "Crie triggers delegados somente em storage.objects, storage.buckets, auth.users ou auth.identities"
            )
        return ("trigger", schema)

    if stmt_type == "DropStmt" and tree.get("removeType") == "OBJECT_TRIGGER":
        objects = [_names(parts) for parts in tree["objects"]]
        if not any(parts and parts[0] in {"storage", "auth"} for parts in objects):
            return None
        if (
            tree["behavior"] != "DROP_RESTRICT"
            or len(objects) != 1
            or len(objects[0]) != 3
            or (objects[0][0], objects[0][1]) not in DELEGATED_DDL_TABLES
        ):
            raise StoragePolicyError(
                "Remova um trigger de Storage/Auth por vez, sem CASCADE"
            )
        return ("trigger_drop", objects[0][0])

    if stmt_type == "AlterTableStmt":
        relation = tree["relation"]
        schema = relation.get("schemaname")
        if schema not in {"storage", "auth"}:
            return None
        cmds = tree.get("cmds") or ()
        trigger_subtypes = {
            "AT_EnableTrig",
            "AT_DisableTrig",
            "AT_EnableTrigAll",
            "AT_DisableTrigAll",
            "AT_EnableTrigUser",
            "AT_DisableTrigUser",
            "AT_EnableAlwaysTrig",
            "AT_EnableReplicaTrig",
        }
        if not cmds or not any(cmd.get("subtype") in trigger_subtypes for cmd in cmds):
            return None
        if relation.get("catalogname") or (schema, relation["relname"]) not in DELEGATED_DDL_TABLES:
            raise StoragePolicyError(
                "Altere triggers somente em storage.objects, storage.buckets, auth.users ou auth.identities"
            )
        if (
            len(cmds) != 1
            or cmds[0].get("subtype") not in {"AT_EnableTrig", "AT_DisableTrig"}
            or not cmds[0].get("name")
        ):
            raise StoragePolicyError(
                "Informe explicitamente o nome de um trigger do projeto para habilitar ou desabilitar"
            )
        return ("trigger_toggle", schema)

    if stmt_type == "IndexStmt":
        relation = tree["relation"]
        schema = relation.get("schemaname")
        if schema not in {"storage", "auth"}:
            return None
        if relation.get("catalogname") or (schema, relation["relname"]) not in DELEGATED_DDL_TABLES:
            raise StoragePolicyError(
                "Crie índices delegados somente em storage.objects, storage.buckets, auth.users ou auth.identities"
            )
        return ("index", schema)

    if stmt_type == "DropStmt" and tree.get("removeType") == "OBJECT_INDEX":
        objects = [_names(parts) for parts in tree["objects"]]
        if not any(parts and parts[0] in {"storage", "auth"} for parts in objects):
            return None
        if (
            tree["behavior"] != "DROP_RESTRICT"
            or tree.get("concurrent")
            or len(objects) != 1
            or len(objects[0]) != 2
            or objects[0][0] not in {"storage", "auth"}
        ):
            raise StoragePolicyError(
                "Remova um índice de Storage/Auth por vez, sem CASCADE nem CONCURRENTLY"
            )
        return ("index_drop", objects[0][0])

    return None


def _validate_policy(tree: dict) -> None:
    for kind, node in _nodes(tree):
        if kind not in NODES:
            raise StoragePolicyError("Expressão não suportada na política de Storage")
        if kind == "RoleSpec" and (
            node["roletype"] != "ROLESPEC_CSTRING"
            or node["rolename"] not in {"anon", "authenticated", "service_role"}
        ):
            raise StoragePolicyError(
                "Informe explicitamente anon, authenticated ou service_role na política"
            )
        if kind == "CreatePolicyStmt" and not node.get("roles"):
            raise StoragePolicyError(
                "Informe explicitamente os papéis da política de Storage"
            )
        if kind == "RangeVar":
            schema = node.get("schemaname")
            if (
                node.get("catalogname")
                or node.get("relpersistence", "p") != "p"
                or not (schema in {"storage", "public", "auth"} or _is_user_schema(schema))
            ):
                raise StoragePolicyError(
                    "Qualifique as tabelas da política com o schema do projeto"
                )
        if kind == "FuncCall":
            names = _names(node["funcname"])
            allowed_identity = names in (
                ["auth", "uid"],
                ["auth", "jwt"],
                ["auth", "role"],
                ["auth", "email"],
            )
            allowed_storage = names in (
                ["storage", "foldername"],
                ["storage", "filename"],
                ["storage", "extension"],
            )
            allowed_project_fn = len(names) == 2 and _is_user_schema(names[0])
            if not (
                allowed_identity
                or allowed_storage
                or allowed_project_fn
                or _builtin(names, SAFE_BUILTINS)
            ):
                raise StoragePolicyError("Função não suportada na política de Storage")
            if allowed_identity and node.get("args"):
                raise StoragePolicyError(
                    "Use auth.uid(), auth.jwt(), auth.role() ou auth.email() sem argumentos"
                )
        if kind == "TypeName" and not _builtin(_names(node.get("names") or []), TYPES):
            raise StoragePolicyError("Use tipos nativos do PostgreSQL na política")
        if (
            kind == "A_Expr"
            and len(_names(node["name"])) > 1
            and _names(node["name"])[:-1] != ["pg_catalog"]
        ):
            raise StoragePolicyError("Use operadores nativos do PostgreSQL na política")
        if kind in {
            "InsertStmt",
            "UpdateStmt",
            "DeleteStmt",
            "CreateStmt",
            "AlterTableStmt",
            "IndexStmt",
            "TruncateStmt",
        }:
            raise StoragePolicyError(
                "A expressão da política não pode executar alterações"
            )


def _validate_safe_invoker_expr(expr: dict, context: str) -> None:
    """Validate expressions that execute as storage/auth owner (WHEN, index expr/WHERE)."""
    for kind, node in _nodes(expr):
        if kind not in SAFE_EXPRESSION_NODES:
            raise StoragePolicyError(f"Expressão não suportada em {context}")
        if kind == "FuncCall":
            names = _names(node["funcname"])
            allowed_storage = names in (
                ["storage", "foldername"],
                ["storage", "filename"],
                ["storage", "extension"],
            )
            if not (allowed_storage or _builtin(names, SAFE_BUILTINS - {"current_setting"})):
                raise StoragePolicyError(
                    f"Use apenas funções nativas do PostgreSQL ou helpers storage.* em {context}"
                )
        if kind == "TypeName" and not _builtin(_names(node.get("names") or []), TYPES):
            raise StoragePolicyError(f"Use tipos nativos do PostgreSQL em {context}")
        if (
            kind == "A_Expr"
            and len(_names(node["name"])) > 1
            and _names(node["name"])[:-1] != ["pg_catalog"]
        ):
            raise StoragePolicyError(f"Use operadores nativos do PostgreSQL em {context}")


def _validate_trigger(tree: dict) -> None:
    if tree.get("isconstraint"):
        raise StoragePolicyError(
            "CONSTRAINT TRIGGER não é permitido em tabelas de Storage/Auth"
        )
    if tree["relation"].get("relpersistence", "p") != "p":
        raise StoragePolicyError("Tabela alvo inválida para trigger delegado")
    funcname = _names(tree.get("funcname") or ())
    if len(funcname) != 2 or not _is_user_schema(funcname[0]):
        raise StoragePolicyError(
            "Qualifique a função de trigger com um schema do projeto (ex.: public.minha_funcao)"
        )
    when_clause = tree.get("whenClause")
    if when_clause is not None:
        _validate_safe_invoker_expr(when_clause, "cláusula WHEN do trigger")


def _validate_index(tree: dict) -> None:
    if not tree.get("idxname"):
        raise StoragePolicyError(
            "Informe explicitamente o nome do índice em tabelas de Storage/Auth"
        )
    if tree.get("concurrent"):
        raise StoragePolicyError(
            "Criação de índice com CONCURRENTLY não é suportada em tabelas de Storage/Auth"
        )
    if tree.get("tableSpace"):
        raise StoragePolicyError(
            "TABLESPACE customizado não é permitido em índices de Storage/Auth"
        )
    access_method = (tree.get("accessMethod") or "btree").lower()
    if access_method not in SAFE_INDEX_METHODS:
        raise StoragePolicyError("Método de índice não suportado em Storage/Auth")
    if tree["relation"].get("relpersistence", "p") != "p":
        raise StoragePolicyError("Tabela alvo inválida para índice delegado")
    for param in list(tree.get("indexParams") or ()) + list(tree.get("indexIncludingParams") or ()):
        if param.get("opclass"):
            opclass = _names(param["opclass"])
            if len(opclass) > 1 and opclass[:-1] != ["pg_catalog"]:
                raise StoragePolicyError(
                    "Use operator classes nativas do PostgreSQL em índices de Storage/Auth"
                )
        if param.get("collation"):
            collation = _names(param["collation"])
            if len(collation) > 1 and collation[:-1] != ["pg_catalog"]:
                raise StoragePolicyError(
                    "Use collations nativas do PostgreSQL em índices de Storage/Auth"
                )
        if param.get("expr") is not None:
            _validate_safe_invoker_expr(param["expr"], "expressão de índice de Storage/Auth")
    where_clause = tree.get("whereClause")
    if where_clause is not None:
        _validate_safe_invoker_expr(where_clause, "cláusula WHERE do índice de Storage/Auth")


def _validate_delegated(kind: str, tree: dict) -> None:
    if kind == "policy":
        _validate_policy(tree)
    elif kind == "trigger":
        _validate_trigger(tree)
    elif kind == "index":
        _validate_index(tree)


def prepare_policy_statements(
    sql: str,
    *,
    project_id: str | None = None,
    storage_s3_region: str | None = None,
):
    """Validate SQL and return parsed statements when Storage/Auth/Vector delegation applies."""
    if project_id is not None:
        vector_fdw_endpoint_url(project_id)
    if storage_s3_region is not None:
        normalize_storage_s3_region(storage_s3_region)
    try:
        statements = parse_sql(sql)
    except Exception:
        _check_body_for_role_mutations(sql)
        return None  # Normal PostgreSQL syntax errors retain their existing path.

    prepared = []
    found = False
    active_role: str | None = None
    active_schema: str | None = None
    active_used = False

    for statement in statements:
        tree = _normalize(statement.stmt())
        _check_forbidden_statement(tree)

        role_stmt = _delegated_role_stmt(tree)
        if role_stmt is not None:
            action, role_name, _is_local = role_stmt
            if action == "set" and role_name is not None:
                if active_role is not None and not active_used:
                    raise StoragePolicyError(
                        f"SET ROLE {active_role} deve envolver DDL delegada permitida em {active_schema}"
                    )
                active_role = role_name
                active_schema = DELEGATED_ROLE_SCHEMAS[role_name]
                active_used = False
                found = True
                continue
            if active_role is not None:
                if not active_used:
                    raise StoragePolicyError(
                        f"SET ROLE {active_role} deve envolver ao menos uma DDL delegada permitida em {active_schema}"
                    )
                active_role = None
                active_schema = None
                active_used = False
                found = True
                continue
            prepared.append((statement.stmt, False))
            continue

        if active_role is not None and tree["@"] == "TransactionStmt":
            if not active_used:
                raise StoragePolicyError(
                    f"SET ROLE {active_role} deve envolver ao menos uma DDL delegada permitida em {active_schema}"
                )
            active_role = None
            active_schema = None
            active_used = False
            prepared.append((statement.stmt, False))
            continue

        target = _delegated_target(tree)
        if target is not None:
            kind, schema = target
            if active_role is not None and schema != active_schema:
                expected_role = (
                    "supabase_storage_admin" if schema == "storage" else "supabase_auth_admin"
                )
                raise StoragePolicyError(
                    f"Use SET ROLE {expected_role} para operações delegadas em {schema}"
                )
            _validate_delegated(kind, tree)
            if active_role is not None:
                active_used = True
            found = True
            prepared.append((statement.stmt, True))
        else:
            vector_rewritten = _rewrite_vector_fdw_statement(tree)
            if vector_rewritten is not None:
                if active_role is not None:
                    raise StoragePolicyError(
                        f"Operação não permitida dentro de SET ROLE {active_role}; feche com RESET ROLE"
                    )
                found = True
                prepared.append(vector_rewritten)
            else:
                if active_role is not None:
                    raise StoragePolicyError(
                        f"Operação não permitida dentro de SET ROLE {active_role}; feche com RESET ROLE"
                    )
                prepared.append((statement.stmt, False))

    if active_role is not None and not active_used:
        raise StoragePolicyError(
            f"SET ROLE {active_role} deve envolver ao menos uma DDL delegada permitida em {active_schema}"
        )

    return prepared if found else None


def rewrite_policy_statements(
    prepared,
    tenant_uuid,
    *,
    project_id: str | None = None,
    key=None,
    role=None,
    now=None,
    storage_s3_region: str | None = None,
):
    role = role or "tenant_meta_" + UUID(str(tenant_uuid)).hex
    expires = int(time.time() if now is None else now) + 60
    storage_key: bytes | None = None
    fdw_key: bytes | None = None
    pinned_endpoint: str | None = None
    pinned_region: str | None = None

    def get_storage_key() -> bytes:
        nonlocal storage_key
        if storage_key is None:
            storage_key = delegation_key(tenant_uuid) if key is None else key
        return storage_key

    def get_fdw_key() -> bytes:
        nonlocal fdw_key
        if fdw_key is None:
            fdw_key = vector_fdw_delegation_key(tenant_uuid, base_key=get_storage_key())
        return fdw_key

    def get_pinned_target() -> tuple[str, str]:
        nonlocal pinned_endpoint, pinned_region
        if pinned_endpoint is None:
            pinned_endpoint = vector_fdw_endpoint_url(project_id)
        if pinned_region is None:
            pinned_region = normalize_storage_s3_region(storage_s3_region)
        return pinned_endpoint, pinned_region

    result = []
    for node, delegated in prepared:
        if isinstance(node, _RawSql):
            result.append(node.sql)
            continue
        if isinstance(node, _PinnedVectorServerSql):
            endpoint_url, aws_region = get_pinned_target()
            result.append(node.builder(endpoint_url, aws_region))
            continue
        if isinstance(node, _VectorFdwGuardCall):
            message = f"{node.fn_name}\n{role}\n{expires}\n{node.fdw_name}".encode()
            proof = hmac.new(get_fdw_key(), message, hashlib.sha256).hexdigest()
            result.append(
                f"SELECT studio_vector_fdw_guard.{node.fn_name}('{node.fdw_name}',{expires},'{proof}')"
            )
            continue
        statement = RawStream()(node)
        if delegated:
            message = f"{role}\n{expires}\n{statement}".encode()
            proof = hmac.new(get_storage_key(), message, hashlib.sha256).hexdigest()
            literal = statement.encode().hex()
            statement = f"SELECT studio_storage_guard.execute_policy(pg_catalog.convert_from(pg_catalog.decode('{literal}','hex'),'UTF8'),{expires},'{proof}')"
        result.append(statement)
    return ";\n".join(result) + ";"
