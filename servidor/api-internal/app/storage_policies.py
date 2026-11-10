"""Delegate only parsed Storage policy DDL, retaining tenant SQL transactions."""

from __future__ import annotations

import hashlib
import hmac
import os
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


def delegation_key(tenant_uuid):
    from urllib.parse import urlsplit
    from app.tenant_meta_identity import tenant_storage_policy_key
    master = urlsplit(os.getenv("META_ADMIN_DSN", "")).password or ""
    return tenant_storage_policy_key(tenant_uuid, master)


def _storage_target(tree):
    if tree["@"] in {"CreatePolicyStmt", "AlterPolicyStmt"}:
        table = tree["table"]
        if table.get("schemaname") != "storage":
            return False
        if table.get("catalogname") or table["relname"] not in {"objects", "buckets"}:
            raise StoragePolicyError(
                "Gerencie políticas somente de storage.objects ou storage.buckets"
            )
        return True
    if tree["@"] == "DropStmt" and tree["removeType"] == "OBJECT_POLICY":
        objects = [_names(parts) for parts in tree["objects"]]
        if not any(parts[0] == "storage" for parts in objects):
            return False
        if tree["behavior"] != "DROP_RESTRICT" or any(
            len(parts) != 3
            or parts[0] != "storage"
            or parts[1] not in {"objects", "buckets"}
            for parts in objects
        ):
            raise StoragePolicyError("Remova uma política de Storage sem CASCADE")
        return True
    return False


def _validate_policy(tree):
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
        if kind == "RangeVar" and (
            node.get("catalogname")
            or node.get("schemaname") not in {"storage", "public", "auth"}
            or node.get("relpersistence", "p") != "p"
        ):
            raise StoragePolicyError(
                "Qualifique as tabelas da política com o schema do projeto"
            )
        if kind == "FuncCall":
            names = _names(node["funcname"])
            allowed_identity = names in (["auth", "uid"], ["auth", "jwt"])
            allowed_storage = names in (
                ["storage", "foldername"],
                ["storage", "filename"],
                ["storage", "extension"],
            )
            if not (
                allowed_identity
                or allowed_storage
                or _builtin(names, FUNCTIONS | {"current_setting"})
            ):
                raise StoragePolicyError("Função não suportada na política de Storage")
            if allowed_identity and node.get("args"):
                raise StoragePolicyError("Use auth.uid() ou auth.jwt() sem argumentos")
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


def prepare_policy_statements(sql):
    """Return parsed statements only when the query contains policy delegation."""
    try:
        statements = parse_sql(sql)
    except Exception:
        return None  # Normal PostgreSQL syntax errors retain their existing path.
    prepared = []
    found = False
    for statement in statements:
        tree = _normalize(statement.stmt())
        delegated = _storage_target(tree)
        if delegated:
            _validate_policy(tree)
            found = True
        prepared.append((statement.stmt, delegated))
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
