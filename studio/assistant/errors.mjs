import { APICallError } from 'ai'

export class AssistantToolError extends Error {
  constructor(status) {
    const message = {
      400: 'Assistant SQL or tool request is unsupported (HTTP 400). No retry was attempted.',
      403: 'Assistant database access was denied (HTTP 403). No retry was attempted.',
      404: 'Assistant database object or tool was not found (HTTP 404). No retry was attempted.',
      409: 'SQL requires explicit destructive approval. No operation was executed.',
      502: 'Assistant database operation failed (HTTP 502). No retry was attempted.',
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
