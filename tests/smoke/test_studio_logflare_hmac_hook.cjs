'use strict'

const assert = require('node:assert/strict')
const crypto = require('node:crypto')

process.env.LOGFLARE_URL = 'https://nginx:443/_internal/logflare'
process.env.STUDIO_ANALYTICS_HMAC_SECRET = 'ab'.repeat(32)

let captured
globalThis.fetch = async (input, init) => {
  captured = { url: new URL(input.toString()), init }
  return { ok: true, status: 200 }
}

require('../../studio/studio-slug/logflare-hmac-hook.cjs')

;(async () => {
  const body = JSON.stringify({ config: { url: 'https://example.invalid' } })
  await globalThis.fetch(
    new URL('https://nginx:443/_internal/logflare/api/backends?x=1'),
    {
      method: 'POST',
      body,
      headers: {
        Authorization: 'Bearer must-not-cross',
        'x-api-key': 'must-not-cross',
        Cookie: 'session=must-not-cross',
        'Content-Type': 'application/json',
      },
    }
  )

  assert(captured)
  const headers = new Headers(captured.init.headers)
  assert.equal(headers.has('authorization'), false)
  assert.equal(headers.has('x-api-key'), false)
  assert.equal(headers.has('cookie'), false)
  assert.equal(headers.get('x-internal-service'), 'studio-server')
  assert.equal(headers.get('x-internal-version'), 'internal-hmac-v1')

  const timestamp = headers.get('x-internal-timestamp')
  const nonce = headers.get('x-internal-nonce')
  const target = `${captured.url.pathname}${captured.url.search}`
  const bodyHash = crypto.createHash('sha256').update(Buffer.from(body)).digest('hex')
  const canonical = [
    'internal-hmac-v1',
    'studio-server',
    'POST',
    target,
    timestamp,
    nonce,
    bodyHash,
  ].join('\n')
  const expected = crypto
    .createHmac('sha256', process.env.STUDIO_ANALYTICS_HMAC_SECRET)
    .update(canonical)
    .digest('hex')
  assert.equal(headers.get('x-internal-signature'), expected)

  captured = null
  await globalThis.fetch('https://example.com/test', {
    headers: { Authorization: 'keep' },
  })
  assert(captured)
  assert.equal(new Headers(captured.init.headers).get('authorization'), 'keep')

  console.log('studio logflare hmac hook: ok')
})().catch((error) => {
  console.error(error)
  process.exit(1)
})
