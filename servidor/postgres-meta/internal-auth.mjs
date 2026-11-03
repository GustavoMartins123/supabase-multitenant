import { createHmac, timingSafeEqual } from 'node:crypto'
import { CRYPTO_KEY } from '../dist/server/constants.js'

if (typeof CRYPTO_KEY !== 'string' || Buffer.byteLength(CRYPTO_KEY) < 16 || CRYPTO_KEY === 'SAMPLE_KEY') {
  throw new Error('A private CRYPTO_KEY of at least 16 bytes is required for metadata HTTP authentication')
}

const credential = createHmac('sha256', CRYPTO_KEY)
  .update('postgres-meta-http-auth-v1')
  .digest('hex')
const expected = Buffer.from(`Bearer ${credential}`)

export async function authenticateMetadataRequest(request, reply) {
  const supplied = request.headers.authorization
  if (typeof supplied !== 'string') {
    return reply.code(401).header('Cache-Control', 'no-store').send({ error: 'metadata_authentication_required' })
  }
  const actual = Buffer.from(supplied)
  if (actual.length !== expected.length || !timingSafeEqual(actual, expected)) {
    return reply.code(401).header('Cache-Control', 'no-store').send({ error: 'metadata_authentication_required' })
  }
  const path = request.url.split('?', 1)[0]
  const connection = request.headers['x-connection-encrypted']
  if (!['/', '/health', '/metrics'].includes(path) &&
      (typeof connection !== 'string' || !/^U2FsdGVkX1[A-Za-z0-9+/]+={0,2}$/.test(connection))) {
    return reply.code(400).header('Cache-Control', 'no-store').send({ error: 'metadata_project_connection_required' })
  }
}
