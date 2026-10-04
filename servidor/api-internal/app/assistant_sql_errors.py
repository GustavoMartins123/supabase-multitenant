from fastapi import HTTPException


SQL_FAILURES = {
    "42883": (422, "sql_operand_types", "PostgreSQL cannot resolve an operator or function for these operand types. Inspect column types and the ownership relationship; do not cast unrelated identifiers to bypass this error."),
    "42804": (422, "sql_type_mismatch", "The SQL expression has incompatible data types. Inspect column types before proposing a corrected statement."),
    "42703": (422, "sql_column_missing", "The SQL references a column that does not exist. Inspect the schema before proposing a corrected statement."),
    "42P01": (422, "sql_relation_missing", "The SQL references a relation that does not exist. Inspect the schema before proposing a corrected statement."),
    "42710": (409, "sql_object_exists", "The database object already exists. Inspect its current definition; replacing or changing a policy requires explicit confirmation."),
    "23502": (422, "sql_not_null", "The operation violates a NOT NULL constraint."),
    "23503": (422, "sql_foreign_key", "The operation violates a foreign-key constraint."),
    "23505": (409, "sql_unique", "The operation violates a unique constraint."),
    "23514": (422, "sql_check", "The operation violates a CHECK constraint."),
    "42501": (403, "sql_privilege_denied", "PostgreSQL denied permission for this operation. Do not elevate privileges or bypass the restriction."),
    "57014": (504, "sql_deadline", "The SQL statement was cancelled or exceeded its deadline."),
    "55P03": (409, "sql_lock_unavailable", "The SQL statement could not acquire the required database lock."),
}


def assistant_sql_failure(error) -> HTTPException:
    sqlstate = getattr(error, "sqlstate", None)
    if sqlstate not in SQL_FAILURES:
        return HTTPException(502, "Assistant SQL outcome could not be confirmed. Inspect database state before continuing. No retry was attempted.")
    status, code, message = SQL_FAILURES[sqlstate]
    return HTTPException(status, {"code": code, "sqlstate": sqlstate,
                                  "message": message + " The transaction was rolled back. No retry was attempted."})
