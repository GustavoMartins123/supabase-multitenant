"""Validate Studio SQL against role/password mutations and delegate Storage/Auth DDL."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
from uuid import UUID

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
    "meta_guard",
    "extensions",
    "graphql",
    "graphql_public",
}
INTERNAL_GUARD_SCHEMAS = {"studio_storage_guard", "studio_trigger_guard"}
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


def delegation_key(tenant_uuid):
    from urllib.parse import urlsplit
    from app.tenant_meta_identity import tenant_storage_policy_key
    master = urlsplit(os.getenv("META_ADMIN_DSN", "")).password or ""
    return tenant_storage_policy_key(tenant_uuid, master)


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


def _check_forbidden_statement(tree: dict) -> None:
    for kind, node in _nodes(tree):
        if kind in FORBIDDEN_ROLE_NODES:
            raise StoragePolicyError(
                "Alteração de roles e senhas do PostgreSQL pela interface não é permitida"
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
            if role_name in PROTECTED_OWNER_ROLES or role_name.startswith(PROTECTED_OWNER_PREFIXES):
                raise StoragePolicyError(
                    "Alteração de dono para role privilegiada ou interna não é permitida"
                )
        if kind == "CreateSchemaStmt" and (node.get("schemaname") or "").lower() in INTERNAL_GUARD_SCHEMAS:
            raise StoragePolicyError(
                "Alteração nos schemas internos de guarda do Studio não é permitida"
            )
        if kind == "RangeVar" and (node.get("schemaname") or "").lower() in INTERNAL_GUARD_SCHEMAS:
            raise StoragePolicyError(
                "Alteração nos schemas internos de guarda do Studio não é permitida"
            )
        if kind == "DropStmt":
            for obj in node.get("objects") or ():
                if isinstance(obj, dict) and (obj.get("sval") or "").lower() in INTERNAL_GUARD_SCHEMAS:
                    raise StoragePolicyError(
                        "Alteração nos schemas internos de guarda do Studio não é permitida"
                    )
                if isinstance(obj, list):
                    names = [item["sval"].lower() for item in obj if isinstance(item, dict) and isinstance(item.get("sval"), str)]
                    if names and names[0] in INTERNAL_GUARD_SCHEMAS:
                        raise StoragePolicyError(
                            "Alteração nos schemas internos de guarda do Studio não é permitida"
                        )
    for body, is_do in _extract_do_or_func_bodies(tree):
        _check_body_for_role_mutations(body, allow_do_role_hint=is_do)


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


def prepare_policy_statements(sql):
    """Validate SQL and return parsed statements when Storage/Auth delegation applies."""
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


def rewrite_policy_statements(prepared, tenant_uuid, *, key=None, role=None, now=None):
    role = role or "tenant_meta_" + UUID(str(tenant_uuid)).hex
    key = delegation_key(tenant_uuid) if key is None else key
    expires = int(time.time() if now is None else now) + 60
    result = []
    for node, delegated in prepared:
        statement = RawStream()(node)
        if delegated:
            message = f"{role}\n{expires}\n{statement}".encode()
            proof = hmac.new(key, message, hashlib.sha256).hexdigest()
            literal = statement.encode().hex()
            statement = f"SELECT studio_storage_guard.execute_policy(pg_catalog.convert_from(pg_catalog.decode('{literal}','hex'),'UTF8'),{expires},'{proof}')"
        result.append(statement)
    return ";\n".join(result) + ";"
