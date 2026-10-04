import { DatabaseSync } from 'node:sqlite'
import { createCipheriv, createDecipheriv, createHash, randomBytes, randomUUID } from 'node:crypto'
import { z } from 'zod'

export const levels = ['none', 'schema', 'read', 'write', 'full']
export const settingsSchema = z.object({
  provider: z.enum(['openai', 'openrouter']),
  model: z.string().trim().min(1).max(200).regex(/^[a-zA-Z0-9][a-zA-Z0-9._:/-]*$/),
  permission: z.enum(levels),
  apiKey: z.string().min(16).max(1024).regex(/^[\x21-\x7e]+$/).optional(),
}).strict()
const uuid = z.string().uuid()
const aad = (scope, purpose) => Buffer.from(JSON.stringify(['assistant-v1', scope.userId, scope.projectId, purpose]))
const canonical = value => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value
export const digest = value => createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex')

function seal(key, text, context) {
  const nonce = randomBytes(12)
  const cipher = createCipheriv('aes-256-gcm', key, nonce)
  cipher.setAAD(context)
  const encrypted = Buffer.concat([cipher.update(text, 'utf8'), cipher.final()])
  return Buffer.concat([nonce, cipher.getAuthTag(), encrypted])
}

function open(key, encrypted, context) {
  if (!Buffer.isBuffer(encrypted)) encrypted = Buffer.from(encrypted)
  if (encrypted.length < 29) throw new Error('Stored credential is invalid')
  const cipher = createDecipheriv('aes-256-gcm', key, encrypted.subarray(0, 12))
  cipher.setAuthTag(encrypted.subarray(12, 28))
  cipher.setAAD(context)
  return Buffer.concat([cipher.update(encrypted.subarray(28)), cipher.final()]).toString('utf8')
}

export class AssistantStore {
  constructor(path, master) {
    if (!/^[0-9a-f]{64}$/.test(master)) throw new Error('Assistant master key is invalid')
    this.master = Buffer.from(master, 'hex')
    this.db = new DatabaseSync(path)
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=3000;
      PRAGMA secure_delete=ON; PRAGMA foreign_keys=ON;
      CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK (id=1), version INTEGER NOT NULL, master_id TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS settings (
        user_id TEXT NOT NULL, project_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
        permission TEXT NOT NULL, key_id TEXT NOT NULL, wrapped_key BLOB NOT NULL, credential BLOB NOT NULL,
        updated_at TEXT NOT NULL, PRIMARY KEY(user_id, project_id));
      CREATE TABLE IF NOT EXISTS state (user_id TEXT NOT NULL, project_id TEXT NOT NULL, payload BLOB NOT NULL,
        PRIMARY KEY(user_id, project_id));
      CREATE TABLE IF NOT EXISTS approvals (user_id TEXT NOT NULL, project_id TEXT NOT NULL, chat_id TEXT NOT NULL,
        call_id TEXT NOT NULL, approval_id TEXT NOT NULL, input_hash TEXT NOT NULL, used INTEGER NOT NULL DEFAULT 0,
        expires_at INTEGER NOT NULL, PRIMARY KEY(user_id, project_id, chat_id, call_id));
      CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, expires_at INTEGER NOT NULL);`)
    this.db.exec(`CREATE TABLE IF NOT EXISTS executions (
      user_id TEXT NOT NULL, project_id TEXT NOT NULL, chat_id TEXT NOT NULL,
      call_id TEXT NOT NULL, input_hash TEXT NOT NULL, PRIMARY KEY(user_id,project_id,chat_id,call_id));`)
    const id = createHash('sha256').update(this.master).digest('hex')
    this.db.prepare('INSERT OR IGNORE INTO metadata VALUES (1, 1, ?)').run(id)
    const meta = this.db.prepare('SELECT version, master_id FROM metadata WHERE id=1').get()
    if (meta.version !== 1 || meta.master_id !== id) { this.db.close(); throw new Error('Assistant database/key mismatch') }
  }

  scope(scope) { uuid.parse(scope.userId); uuid.parse(scope.projectId); return [scope.userId, scope.projectId] }
  row(scope) { return this.db.prepare('SELECT * FROM settings WHERE user_id=? AND project_id=?').get(...this.scope(scope)) }

  status(scope) {
    const row = this.row(scope)
    if (!row) return { hasKey: false }
    return { hasKey: true, provider: row.provider, model: row.model, permission: row.permission, updatedAt: row.updated_at }
  }

  save(scope, input) {
    const value = settingsSchema.parse(input)
    const current = this.row(scope)
    if (!current && !value.apiKey) throw new Error('A provider key is required')
    if (current && value.provider !== current.provider && !value.apiKey) throw new Error('Changing provider requires a new key')
    if (value.permission !== 'none' && scope.role !== 'admin') throw new Error('Database access requires project administration')
    let keyId, wrappedKey, credential
    if (value.apiKey) {
      const dek = randomBytes(32)
      keyId = randomUUID()
      try {
        wrappedKey = seal(this.master, dek.toString('hex'), aad(scope, `dek:${keyId}`))
        credential = seal(dek, value.apiKey, aad(scope, `provider:${value.provider}:${keyId}`))
      } finally { dek.fill(0) }
    } else { keyId = current.key_id; wrappedKey = current.wrapped_key; credential = current.credential }
    this.db.prepare(`INSERT INTO settings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(user_id,project_id) DO UPDATE SET provider=excluded.provider, model=excluded.model,
      permission=excluded.permission, key_id=excluded.key_id, wrapped_key=excluded.wrapped_key,
      credential=excluded.credential, updated_at=excluded.updated_at`).run(
      ...this.scope(scope), value.provider, value.model, value.permission, keyId, wrappedKey, credential, new Date().toISOString())
    return this.status(scope)
  }

  configuration(scope) {
    const row = this.row(scope)
    if (!row) throw new Error('Assistant is not configured for this user/project')
    if (row.permission !== 'none' && scope.role !== 'admin') throw new Error('Assistant database permission is no longer authorized')
    const hex = open(this.master, row.wrapped_key, aad(scope, `dek:${row.key_id}`))
    if (!/^[0-9a-f]{64}$/.test(hex)) throw new Error('Stored data key is invalid')
    const dek = Buffer.from(hex, 'hex')
    try { return { ...this.status(scope), apiKey: open(dek, row.credential, aad(scope, `provider:${row.provider}:${row.key_id}`)) } }
    finally { dek.fill(0) }
  }

  getState(scope) {
    const row = this.db.prepare('SELECT payload FROM state WHERE user_id=? AND project_id=?').get(...this.scope(scope))
    return row ? JSON.parse(open(this.master, row.payload, aad(scope, 'chat-state'))) : null
  }

  saveState(scope, state) {
    this.db.prepare('INSERT INTO state VALUES (?, ?, ?) ON CONFLICT(user_id,project_id) DO UPDATE SET payload=excluded.payload')
      .run(...this.scope(scope), seal(this.master, JSON.stringify(state), aad(scope, 'chat-state')))
  }

  rememberApprovals(scope, chatId, message) {
    uuid.parse(chatId)
    this.db.prepare('DELETE FROM approvals WHERE expires_at < ?').run(Date.now())
    const query = this.db.prepare('INSERT OR IGNORE INTO approvals VALUES (?, ?, ?, ?, ?, ?, 0, ?)')
    for (const part of message.parts) {
      if (['tool-execute_function', 'tool-execute_destructive_sql'].includes(part.type) && part.state === 'approval-requested') {
        query.run(...this.scope(scope), chatId, part.toolCallId, part.approval.id, digest({ tool: part.type, input: part.input }), Date.now() + 300_000)
      }
    }
  }

  claimApproval(scope, chatId, callId, input, messages, toolName) {
    if (!['execute_function', 'execute_destructive_sql'].includes(toolName)) throw new Error('Unknown approval tool')
    const parts = messages.flatMap(message => message.parts ?? [])
    const matching = parts.filter(part => part.type === `tool-${toolName}` && part.toolCallId === callId)
    if (matching.length !== 1 || matching[0].approval?.approved !== true) throw new Error('Explicit approval is required')
    const changed = this.db.prepare(`UPDATE approvals SET used=1 WHERE user_id=? AND project_id=? AND chat_id=?
      AND call_id=? AND approval_id=? AND input_hash=? AND used=0 AND expires_at>?`)
      .run(...this.scope(scope), chatId, callId, matching[0].approval.id, digest({ tool: `tool-${toolName}`, input }), Date.now()).changes
    if (changed !== 1) throw new Error('Approval is missing, changed, expired or already consumed')
    return { chat_id: chatId, call_id: callId, approval_id: matching[0].approval.id, tool: toolName }
  }

  claimNonce(nonce, expiry) {
    this.db.prepare('DELETE FROM nonces WHERE expires_at < ?').run(Date.now())
    this.db.prepare('INSERT INTO nonces VALUES (?, ?)').run(nonce, expiry)
  }

  claimExecution(scope, chatId, callId, input, toolName) {
    uuid.parse(chatId)
    z.string().min(1).max(200).parse(callId)
    z.enum(['execute_sql', 'execute_destructive_sql']).parse(toolName)
    const inserted = this.db.prepare('INSERT OR IGNORE INTO executions VALUES (?, ?, ?, ?, ?)')
      .run(...this.scope(scope), chatId, callId, digest({tool: toolName, input})).changes
    if (inserted !== 1) throw new Error('SQL tool call already consumed; no retry is allowed')
    return {chat_id: chatId, call_id: callId, tool: toolName}
  }

  close() { this.db.close(); this.master.fill(0) }
}
