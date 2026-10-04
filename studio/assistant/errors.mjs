import { APICallError } from 'ai'

export function assistantErrorMessage(error) {
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
