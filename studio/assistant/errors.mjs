import { APICallError } from 'ai'

const sqlFailures = {
  sql_operand_types: [422, '42883', 'PostgreSQL cannot resolve an operator/function for these operand types. Inspect column types and the ownership relationship. auth.uid() returns uuid; a bigint foreign key is not a user identity. Do not cast unrelated identifiers to bypass this error.'],
  sql_type_mismatch: [422, '42804', 'The SQL expression has incompatible data types. Inspect column types.'],
  sql_column_missing: [422, '42703', 'The SQL references a column that does not exist. Inspect the schema.'],
  sql_relation_missing: [422, '42P01', 'The SQL references a relation that does not exist. Inspect the schema.'],
  sql_object_exists: [409, '42710', 'The database object already exists. Inspect its definition; policy changes require explicit confirmation.'],
  sql_not_null: [422, '23502', 'The operation violates a NOT NULL constraint.'],
  sql_foreign_key: [422, '23503', 'The operation violates a foreign-key constraint.'],
  sql_unique: [409, '23505', 'The operation violates a unique constraint.'],
  sql_check: [422, '23514', 'The operation violates a CHECK constraint.'],
  sql_privilege_denied: [403, '42501', 'PostgreSQL denied permission. Do not elevate privileges or bypass the restriction.'],
  sql_deadline: [504, '57014', 'The SQL statement was cancelled or exceeded its deadline.'],
  sql_lock_unavailable: [409, '55P03', 'The SQL statement could not acquire the required database lock.'],
}

export class AssistantToolError extends Error {
  constructor(status, detail) {
    if (status === 409 && detail?.code === 'sql_approval_required' && detail.sqlstate === undefined) {
      super('SQL requires explicit destructive approval or security-change confirmation. No operation was executed.')
      return
    }
    const failure = detail && Object.hasOwn(sqlFailures, detail.code) ? sqlFailures[detail.code] : undefined
    if (failure && failure[0] === status && failure[1] === detail.sqlstate) {
      super(`${failure[2]} (HTTP ${status}; SQLSTATE ${failure[1]}). The transaction was rolled back. No retry was attempted.`)
      return
    }
    const message = {
      400: 'Assistant SQL or tool request is unsupported (HTTP 400). No retry was attempted.',
      403: 'Assistant database access was denied (HTTP 403). No retry was attempted.',
      404: 'Assistant database object or tool was not found (HTTP 404). No retry was attempted.',
      409: 'Assistant tool request conflicts with the current state (HTTP 409). No retry was attempted.',
      422: 'Assistant SQL could not be validated (HTTP 422). No retry was attempted.',
      502: 'Assistant database operation failed (HTTP 502); its outcome could not be confirmed. Inspect database state before continuing. No retry was attempted.',
      503: 'Assistant project database is unavailable or its pool is saturated (HTTP 503). No retry was attempted.',
      504: 'Assistant database operation timed out (HTTP 504). No retry was attempted.',
    }[status] ?? 'Assistant database tool request failed. No retry was attempted.'
    super(message)
  }
}

export function assistantErrorMessage(error) {
  if (error instanceof AssistantToolError) return error.message
  if (error?.cause instanceof AssistantToolError) return error.cause.message
  if (APICallError.isInstance(error)) {
    const messages = {
      400: 'Assistant provider rejected the request (HTTP 400). Check the configured model and its tool support.',
      401: 'Assistant provider rejected authentication (HTTP 401). Check or replace your key in Assistant settings.',
      402: 'Assistant provider requires credits (HTTP 402). Check your provider balance.',
      403: 'Assistant provider denied access (HTTP 403). Check the key permissions and model access.',
      404: 'Assistant provider could not find the configured model or endpoint (HTTP 404). Check Assistant settings.',
      429: 'Assistant provider rate limit reached (HTTP 429).',
    }
    return (messages[error.statusCode] ?? 'Assistant provider request failed.') + ' No retry was attempted.'
  }
  return 'Assistant provider or tool failed. No retry was attempted.'
}
