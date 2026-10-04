from __future__ import annotations

from dataclasses import dataclass

from pglast import parse_sql


class SqlPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class SqlPlan:
    statement: str
    destructive: bool
    writes: bool
    relations: tuple[str, ...]
    creates: tuple[str, ...]
    row_events: tuple[tuple[str, int], ...]
    validates: tuple[str, ...]
    identity_functions: tuple[str, ...]


STATEMENTS = {
    "SelectStmt", "InsertStmt", "UpdateStmt", "DeleteStmt", "CreateStmt",
    "AlterTableStmt", "IndexStmt", "DropStmt", "TruncateStmt", "CreatePolicyStmt", "AlterPolicyStmt",
}
FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "array_agg", "json_agg", "jsonb_agg",
    "json_build_object", "jsonb_build_object", "json_build_array", "jsonb_build_array",
    "json_object_agg", "jsonb_object_agg", "string_agg", "lower", "upper", "length",
    "char_length", "trim", "btrim", "ltrim", "rtrim", "substring", "substr", "replace",
    "concat", "concat_ws", "abs", "round", "ceil", "ceiling", "floor", "now",
    "date_trunc", "date_part", "to_char", "gen_random_uuid",
    "generate_series",
}
TYPES = {
    "bool", "boolean", "int2", "int4", "int8", "smallint", "integer", "bigint",
    "serial", "serial4", "bigserial", "serial8", "smallserial", "serial2",
    "numeric", "decimal", "real", "float4", "float8", "text", "varchar", "bpchar",
    "char", "uuid", "json", "jsonb", "date", "time", "timetz", "timestamp",
    "timestamptz", "interval", "bytea",
}
ALTERATIONS = {
    "AT_AddColumn", "AT_SetNotNull", "AT_DropNotNull", "AT_ColumnDefault",
    "AT_AddConstraint", "AT_ValidateConstraint", "AT_DropColumn", "AT_DropConstraint",
    "AT_AlterColumnType", "AT_EnableRowSecurity", "AT_ForceRowSecurity",
    "AT_DisableRowSecurity", "AT_NoForceRowSecurity",
}
NODES = STATEMENTS | {
    "RangeVar", "RangeSubselect", "RangeFunction", "JoinExpr", "Alias", "WithClause",
    "CommonTableExpr", "ColumnDef", "TypeName", "Constraint", "IndexElem", "InferClause",
    "OnConflictClause", "AlterTableCmd", "A_Const", "Integer", "Float", "Boolean",
    "String", "BitString", "A_Star", "ColumnRef", "ResTarget", "A_Expr", "BoolExpr",
    "NullTest", "BooleanTest", "CaseExpr", "CaseWhen", "CoalesceExpr", "MinMaxExpr",
    "TypeCast", "SQLValueFunction", "FuncCall", "NamedArgExpr", "WindowDef", "SortBy",
    "GroupingSet", "GroupingFunc", "A_ArrayExpr", "A_Indirection", "A_Indices", "SubLink", "RoleSpec",
}


def _nodes(value):
    if isinstance(value, dict):
        if "@" in value:
            yield value["@"], value
        for child in value.values():
            yield from _nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from _nodes(child)


def _names(value):
    return [item["sval"] for item in value]


def _normalize(value):
    if isinstance(value, dict):
        if "#" in value:
            return value["name"]
        return {key: _normalize(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(child) for child in value]
    return value


def _builtin(names, permitted):
    return bool(names) and (len(names) == 1 or len(names) == 2 and names[0] == "pg_catalog") and names[-1] in permitted


def default_has_side_effects(expression: str) -> bool:
    try:
        tree = _normalize(parse_sql(f"SELECT {expression}")[0].stmt())
    except Exception as exc:
        raise SqlPolicyError("Stored column default cannot be inspected") from exc
    for kind, node in _nodes(tree):
        if kind not in NODES:
            return True
        if kind == "FuncCall" and not _builtin(_names(node["funcname"]), FUNCTIONS | {"nextval"}):
            return True
        if kind == "TypeName" and not _builtin(_names(node.get("names") or []), TYPES | {"regclass"}):
            return True
        if kind == "A_Expr" and len(_names(node["name"])) > 1 and _names(node["name"])[:-1] != ["pg_catalog"]:
            return True
    return False


def inspect_sql(sql: str) -> SqlPlan:
    try:
        statements = parse_sql(sql)
    except Exception as exc:
        raise SqlPolicyError("Invalid PostgreSQL statement") from exc
    if len(statements) != 1:
        raise SqlPolicyError("Approve exactly one SQL statement at a time")
    tree = _normalize(statements[0].stmt())
    statement = tree["@"]
    if statement not in STATEMENTS:
        raise SqlPolicyError("This SQL operation is not available to the assistant")
    relations, creates = set(), set()
    row_events, validates = {}, set()
    identity_functions = set()
    destructive = False
    writes = False
    for kind, node in _nodes(tree):
        if kind not in NODES:
            raise SqlPolicyError("This SQL expression or operation is not supported")
        if kind in {"DeleteStmt", "TruncateStmt", "DropStmt", "AlterPolicyStmt"}:
            destructive = True
        if kind == "RoleSpec":
            if statement not in {"CreatePolicyStmt", "AlterPolicyStmt"} or (
                node.get("roletype") != "ROLESPEC_CSTRING" or node.get("rolename") not in {"anon", "authenticated"}
            ):
                raise SqlPolicyError("Policies must explicitly target anon or authenticated, never PUBLIC or privileged roles")
        if kind in {"CreatePolicyStmt", "AlterPolicyStmt"}:
            if kind == "CreatePolicyStmt" and not node.get("roles"):
                raise SqlPolicyError("Specify the intended application roles for the policy")
        if kind in STATEMENTS and kind != statement and kind != "SelectStmt":
            if statement in {"CreatePolicyStmt", "AlterPolicyStmt"}:
                raise SqlPolicyError("Policy expressions cannot modify data")
        if kind in STATEMENTS - {"SelectStmt"}:
            writes = True
        if kind in {"InsertStmt", "UpdateStmt", "DeleteStmt"}:
            name = node["relation"]["relname"]
            event = {"InsertStmt": 4, "UpdateStmt": 16, "DeleteStmt": 8}[kind]
            row_events[name] = row_events.get(name, 0) | event
        if kind == "AlterTableStmt" and any(
            command["subtype"] in {"AT_AddConstraint", "AT_ValidateConstraint"}
            for command in node["cmds"]
        ):
            validates.add(node["relation"]["relname"])
        if kind == "RangeVar":
            relation = node
            if relation.get("schemaname") != "public" or relation.get("catalogname") or relation.get("relpersistence", "p") != "p":
                raise SqlPolicyError("Qualify each table as public.table; other schemas and temporary tables are not permitted")
            relations.add(relation["relname"])
        if kind == "CreateStmt":
            creates.add(node["relation"]["relname"])
        if kind == "FuncCall":
            names = _names(node["funcname"])
            if statement in {"CreatePolicyStmt", "AlterPolicyStmt"} and names in (["auth", "uid"], ["auth", "jwt"]):
                if any(node.get(key) for key in ("args", "agg_order", "agg_filter", "over", "agg_star", "agg_distinct", "func_variadic")):
                    raise SqlPolicyError("Use only the zero-argument auth.uid() and auth.jwt() identity functions")
                identity_functions.add(names[-1])
            elif not _builtin(names, FUNCTIONS):
                raise SqlPolicyError("Only supported built-ins and policy-scoped auth.uid()/auth.jwt() are permitted")
        if kind == "TypeName" and not _builtin(_names(node.get("names") or []), TYPES):
            raise SqlPolicyError("Only built-in PostgreSQL column types are permitted")
        if kind == "A_Expr":
            names = _names(node["name"])
            if len(names) > 1 and names[:-1] != ["pg_catalog"]:
                raise SqlPolicyError("Custom operators are not permitted")
        if kind in {"CollateClause", "RangeTableFunc", "RangeTableFuncCol", "ParamRef", "IntoClause"}:
            raise SqlPolicyError("This SQL expression is not supported")
        if kind == "SelectStmt" and node.get("lockingClause"):
            raise SqlPolicyError("Explicit SQL locking is not permitted")
        if kind == "CreateStmt":
            if any(node.get(key) for key in ("inhRelations", "partspec", "partbound", "ofTypename", "options", "tablespacename", "accessMethod")):
                raise SqlPolicyError("Create only ordinary public tables without custom storage options")
        if kind == "AlterTableStmt" and node.get("objtype") != "OBJECT_TABLE":
            raise SqlPolicyError("Alter only ordinary public tables")
        if kind == "AlterTableCmd":
            if node["subtype"] not in ALTERATIONS:
                raise SqlPolicyError("This table alteration is not permitted")
            if node["subtype"] in {"AT_DropColumn", "AT_DropConstraint", "AT_AlterColumnType", "AT_DisableRowSecurity", "AT_NoForceRowSecurity"}:
                destructive = True
        if kind == "Constraint":
            if node.get("contype") == "CONSTR_EXCLUSION":
                raise SqlPolicyError("Exclusion constraints are not supported")
            if node.get("options") or node.get("indexspace") or node.get("access_method"):
                raise SqlPolicyError("Custom constraint storage is not permitted")
        if kind == "IndexStmt":
            if node.get("accessMethod") != "btree" or any(node.get(key) for key in ("options", "tableSpace", "concurrent")):
                raise SqlPolicyError("Create only ordinary btree indexes")
        if kind == "IndexElem" and (node.get("opclass") or node.get("collation")):
            raise SqlPolicyError("Custom index operator classes and collations are not permitted")
        if kind == "SortBy" and node.get("useOp"):
            names = _names(node["useOp"])
            if len(names) > 1 and names[:-1] != ["pg_catalog"]:
                raise SqlPolicyError("Custom sort operators are not permitted")
        if kind == "DropStmt":
            if node.get("removeType") not in {"OBJECT_TABLE", "OBJECT_POLICY"} or node.get("behavior") != "DROP_RESTRICT":
                raise SqlPolicyError("Drop only public tables or their policies with RESTRICT, never CASCADE")
            for obj in node["objects"]:
                names = _names(obj)
                expected = 3 if node["removeType"] == "OBJECT_POLICY" else 2
                if len(names) != expected or names[0] != "public":
                    raise SqlPolicyError("Drop only explicitly qualified public tables or their policies")
                relations.add(names[1])
        if kind in {"AlterTableCmd", "TruncateStmt"} and node.get("behavior") == "DROP_CASCADE":
            raise SqlPolicyError("CASCADE is not permitted")
    return SqlPlan(statement, destructive, writes, tuple(sorted(relations)), tuple(sorted(creates)),
                   tuple(sorted(row_events.items())), tuple(sorted(validates)), tuple(sorted(identity_functions)))
