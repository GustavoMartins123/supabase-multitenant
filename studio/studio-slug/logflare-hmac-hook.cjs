'use strict'

const crypto = require('node:crypto')

const VERSION = 'internal-hmac-v1'
const SERVICE = 'studio-server'
const originalFetch = globalThis.fetch.bind(globalThis)

function parseTarget(input) {
  if (input instanceof URL) return new URL(input.toString())
  if (typeof Request !== 'undefined' && input instanceof Request) return new URL(input.url)
  return new URL(String(input))
}

function logflareBase() {
  const raw = process.env.LOGFLARE_URL
  if (!raw) return null
  const base = new URL(raw)
  base.pathname = base.pathname.replace(/\/+$/, '') || '/'
  return base
}

function isLogflareTarget(url) {
  const base = logflareBase()
  if (!base || url.origin !== base.origin) return false
  if (base.pathname === '/') return true
  return url.pathname === base.pathname || url.pathname.startsWith(`${base.pathname}/`)
}

function bodyBuffer(body) {
  if (body === undefined || body === null) return Buffer.alloc(0)
  if (typeof body === 'string') return Buffer.from(body)
  if (Buffer.isBuffer(body)) return body
  if (body instanceof Uint8Array) return Buffer.from(body)
  if (body instanceof ArrayBuffer) return Buffer.from(new Uint8Array(body))
  if (body instanceof URLSearchParams) return Buffer.from(body.toString())
  throw new Error('Unsupported LOGFLARE request body for internal HMAC signing')
}

function secret() {
  const value = process.env.STUDIO_ANALYTICS_HMAC_SECRET || ''
  if (!/^[0-9a-f]{64}$/i.test(value)) {
    throw new Error('STUDIO_ANALYTICS_HMAC_SECRET must be a 32-byte hex secret')
  }
  return value
}

globalThis.fetch = async function signedStudioFetch(input, init = {}) {
  const url = parseTarget(input)
  if (!isLogflareTarget(url)) return originalFetch(input, init)

  if (typeof Request !== 'undefined' && input instanceof Request && init.body == null) {
    throw new Error('Request objects are not supported for LOGFLARE internal HMAC signing')
  }

  const method = String(init.method || 'GET').toUpperCase()
  const body = bodyBuffer(init.body)
  const headers = new Headers(init.headers || {})

  for (const name of [
    'authorization',
    'x-api-key',
    'cookie',
    'proxy-authorization',
    'x-user-token',
    'x-user-groups',
    'x-user-username',
    'x-user-display-name',
    'remote-groups',
  ]) {
    headers.delete(name)
  }

  const timestamp = Math.floor(Date.now() / 1000).toString()
  const nonce = crypto.randomBytes(16).toString('hex')
  const bodyHash = crypto.createHash('sha256').update(body).digest('hex')
  const target = `${url.pathname}${url.search}`
  const canonical = [VERSION, SERVICE, method, target, timestamp, nonce, bodyHash].join('\n')
  const signature = crypto.createHmac('sha256', secret()).update(canonical).digest('hex')

  headers.set('X-Internal-Version', VERSION)
  headers.set('X-Internal-Service', SERVICE)
  headers.set('X-Internal-Timestamp', timestamp)
  headers.set('X-Internal-Nonce', nonce)
  headers.set('X-Internal-Signature', signature)

  return originalFetch(input, { ...init, headers })
}
