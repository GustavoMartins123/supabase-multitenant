import { createHash, createHmac, timingSafeEqual } from 'node:crypto'
import { z } from 'zod'

const contextSchema = z.object({
  userId: z.string().uuid(), projectId: z.string().uuid(), ref: z.string().regex(/^[a-z]{20}$/),
  role: z.enum(['admin', 'member']), userToken: z.string().min(50).max(4096),
  timestamp: z.number().int(), nonce: z.string().regex(/^[0-9a-f]{32}$/),
  method: z.enum(['GET', 'PUT', 'POST']), target: z.string().max(200), bodyHash: z.string().regex(/^[0-9a-f]{64}$/),
}).strict()

export function authenticate(request, body, secret, store, now = Date.now()) {
  const header = request.headers['x-assistant-context']
  if (typeof header !== 'string' || header.length > 8000) throw new Error('Assistant authentication required')
  const parts = header.split('.')
  if (parts.length !== 2 || !/^[A-Za-z0-9_-]+$/.test(parts[0]) || !/^[0-9a-f]{64}$/.test(parts[1])) throw new Error('Invalid assistant authentication')
  const expected = createHmac('sha256', secret).update(parts[0]).digest()
  if (!timingSafeEqual(expected, Buffer.from(parts[1], 'hex'))) throw new Error('Invalid assistant signature')
  const scope = contextSchema.parse(JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8')))
  if (Math.abs(now - scope.timestamp * 1000) > 30_000 || scope.method !== request.method || scope.target !== request.url ||
    scope.bodyHash !== createHash('sha256').update(body).digest('hex')) throw new Error('Assistant request signature mismatch')
  store.claimNonce(scope.nonce, now + 60_000)
  return scope
}
