import { createHash, createHmac, randomBytes } from 'node:crypto'
import https from 'node:https'

export function gateway(secret, ca) {
  return async (scope, action, payload, signal) => {
    if (!['context', 'schema', 'rows', 'functions', 'execute'].includes(action)) throw new Error('Unknown assistant tool')
    const target = `/_internal/assistant/${scope.ref}/${action}`
    const method = payload === undefined ? 'GET' : 'POST'
    const body = payload === undefined ? '' : JSON.stringify(payload)
    const timestamp = Math.floor(Date.now() / 1000)
    const nonce = randomBytes(16).toString('hex')
    const canonical = ['internal-hmac-v1', 'studio-assistant', method, target, timestamp, nonce, createHash('sha256').update(body).digest('hex')].join('\n')
    const headers = {
      'Content-Type': 'application/json', 'X-Internal-Version': 'internal-hmac-v1', 'X-Internal-Service': 'studio-assistant',
      'X-Internal-Timestamp': String(timestamp), 'X-Internal-Nonce': nonce,
      'X-Internal-Signature': createHmac('sha256', secret).update(canonical).digest('hex'), 'X-Assistant-User-Token': scope.userToken,
    }
    return new Promise((resolve, reject) => {
      const request = https.request({ hostname: 'nginx', port: 443, path: target, method, ca, servername: 'nginx',
        rejectUnauthorized: true, signal, headers, timeout: 35_000 }, response => {
        const chunks = []; let size = 0
        response.on('data', chunk => { size += chunk.length; if (size > 1_000_000) response.destroy(new Error('Assistant tool response exceeds limit')); else chunks.push(chunk) })
        response.on('error', () => reject(new Error('Assistant tool response interrupted')))
        response.on('end', () => {
          if (response.statusCode !== 200) return reject(new Error(`Assistant tool refused (HTTP ${response.statusCode})`))
          try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf8'))) } catch { reject(new Error('Invalid assistant tool response')) }
        })
      })
      request.on('timeout', () => request.destroy(new Error('Assistant tool timed out')))
      request.on('error', () => reject(new Error('Assistant gateway request failed')))
      request.end(body)
    })
  }
}
