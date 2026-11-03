import { createHmac } from 'node:crypto'
import { CRYPTO_KEY } from '../dist/server/constants.js'

const credential = createHmac('sha256', CRYPTO_KEY).update('postgres-meta-http-auth-v1').digest('hex')
const port = process.env.PG_META_PORT || '8080'
const response = await fetch(`http://127.0.0.1:${port}/health`, {
  headers: { Authorization: `Bearer ${credential}` },
  signal: AbortSignal.timeout(3000),
})
if (response.status !== 200) process.exit(1)
