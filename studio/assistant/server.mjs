import { readFileSync, mkdirSync } from 'node:fs'
import { createServer } from 'node:https'
import { AssistantStore } from './store.mjs'
import { createHandler } from './app.mjs'
import { gateway } from './gateway.mjs'

const readSecret = name => {
  const value = readFileSync(`/run/secrets/${name}`, 'utf8').trim()
  if (!/^[0-9a-f]{64}$/.test(value)) throw new Error(`Invalid assistant secret: ${name}`)
  return value
}
process.umask(0o077)
mkdirSync('/data', { recursive: true, mode: 0o700 })
const store = new AssistantStore('/data/assistant.sqlite3', readSecret('ASSISTANT_MASTER_KEY'))
const secret = readSecret('ASSISTANT_GATEWAY_KEY')
const ca = readFileSync('/tls/ca.pem')
const handler = createHandler({ store, secret, call: gateway(secret, ca) })
const server = createServer({ cert: readFileSync('/tls/server.pem'), key: readFileSync('/run/secrets/ASSISTANT_TLS_KEY'), minVersion: 'TLSv1.2' }, handler)
server.requestTimeout = 125_000
server.headersTimeout = 15_000
server.listen(3443, '0.0.0.0', () => process.stdout.write('Studio assistant ready (TLS)\n'))
for (const signal of ['SIGTERM', 'SIGINT']) process.on(signal, () => server.close(() => { store.close(); process.exit(0) }))
