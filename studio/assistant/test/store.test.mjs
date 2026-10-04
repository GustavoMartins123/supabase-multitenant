import test from 'node:test'
import assert from 'node:assert/strict'
import { createHmac, createHash, randomBytes, randomUUID } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { AssistantStore } from '../store.mjs'
import { authenticate } from '../auth.mjs'
import { makeTools } from '../app.mjs'

const scope = () => ({ userId: randomUUID(), projectId: randomUUID(), role: 'admin', ref: 'abcdefghijklmnopqrst' })
const config = { provider: 'openai', model: 'synthetic-model', permission: 'read', apiKey: 'synthetic-test-key-not-real' }
function fixture(t) {
  const root = mkdtempSync(join(tmpdir(), 'assistant-test-'))
  const path = join(root, 'test.sqlite3')
  const master = randomBytes(32).toString('hex')
  const store = new AssistantStore(path, master)
  t.after(() => { try { store.close() } finally { rmSync(root, { recursive: true }) } })
  return { store, path, master }
}

test('credential remains encrypted in database and WAL; status never exposes it', t => {
  const { store, path } = fixture(t); const actor = scope()
  store.save(actor, config)
  assert.equal(store.configuration(actor).apiKey, config.apiKey)
  assert.equal('apiKey' in store.status(actor), false)
  for (const file of [path, path + '-wal']) assert.equal(readFileSync(file).includes(Buffer.from(config.apiKey)), false)
})

test('per-user and per-project isolation; missing settings do not use defaults', t => {
  const { store } = fixture(t); const actor = scope(); store.save(actor, config)
  for (const other of [{ ...actor, userId: randomUUID() }, { ...actor, projectId: randomUUID() }]) {
    assert.equal(store.status(other).hasKey, false)
    assert.throws(() => store.configuration(other))
  }
})

test('ciphertext cannot be transplanted to another user or project', t => {
  const { store } = fixture(t); const actor = scope(); const other = scope(); store.save(actor, config)
  store.db.prepare('UPDATE settings SET user_id=?, project_id=?').run(other.userId, other.projectId)
  assert.throws(() => store.configuration(other))
})

test('credential replacement uses a new envelope and preserves configuration', t => {
  const { store } = fixture(t); const actor = scope(); store.save(actor, config); const before = store.row(actor)
  const replacement = 'replacement-synthetic-key-only'
  store.save(actor, { ...config, apiKey: replacement })
  assert.notEqual(store.row(actor).key_id, before.key_id)
  assert.equal(store.configuration(actor).apiKey, replacement)
  store.save(actor, { provider: 'openai', model: 'different-explicit-model', permission: 'schema' })
  assert.equal(store.configuration(actor).apiKey, replacement)
  assert.throws(() => store.save(actor, { provider: 'openrouter', model: 'model', permission: 'none' }))
})

test('missing or wrong master key refuses startup', t => {
  const { path } = fixture(t)
  assert.throws(() => new AssistantStore(path, ''))
  assert.throws(() => new AssistantStore(path, randomBytes(32).toString('hex')))
})

test('members cannot configure database tools or keep privileges after demotion', t => {
  const { store } = fixture(t); const actor = scope()
  assert.throws(() => store.save({ ...actor, role: 'member' }, config))
  store.save(actor, config)
  assert.throws(() => store.configuration({ ...actor, role: 'member' }))
  store.save({ ...actor, role: 'member' }, { ...config, permission: 'none' })
  assert.equal(store.configuration({ ...actor, role: 'member' }).permission, 'none')
})

test('configuration rejects unrecognized provider, base URL and absent model', t => {
  const { store } = fixture(t); const actor = scope()
  for (const invalid of [{ ...config, provider: 'unknown' }, { ...config, baseURL: 'http://localhost' }, { ...config, model: '' }]) {
    assert.throws(() => store.save(actor, invalid))
  }
})

test('encrypted history follows canonical project UUID rather than URL', t => {
  const { store, path } = fixture(t); const actor = scope(); const privateText = 'synthetic-private-chat-context'
  store.saveState(actor, { chats: { [randomUUID()]: privateText } })
  assert.deepEqual(store.getState({ ...actor, ref: 'zyxwvutsrqponmlkjihg' }), store.getState(actor))
  assert.equal(store.getState({ ...actor, userId: randomUUID() }), null)
  for (const file of [path, path + '-wal']) assert.equal(readFileSync(file).includes(Buffer.from(privateText)), false)
})

test('signature binds body, target, method, identity and nonce; rejects replay and expiry', t => {
  const { store } = fixture(t); const secret = 'c'.repeat(64); const body = Buffer.from('{}')
  const proof = { ...scope(), userToken: 's'.repeat(80), timestamp: Math.floor(Date.now()/1000), nonce: randomBytes(16).toString('hex'), method: 'PUT', target: '/api/ai/settings', bodyHash: createHash('sha256').update(body).digest('hex') }
  const encode = p => { const encoded = Buffer.from(JSON.stringify(p)).toString('base64url'); return encoded + '.' + createHmac('sha256', secret).update(encoded).digest('hex') }
  const request = { method: 'PUT', url: '/api/ai/settings', headers: { 'x-assistant-context': encode(proof) } }
  assert.throws(() => authenticate({ ...request, method: 'POST' }, body, secret, store))
  assert.throws(() => authenticate({ ...request, url: '/api/ai/state' }, body, secret, store))
  assert.throws(() => authenticate(request, Buffer.from('{"changed":true}'), secret, store))
  assert.throws(() => authenticate(request, body, 'd'.repeat(64), store))
  assert.throws(() => authenticate(request, body, secret, store, Date.now()+40_000))
  assert.equal(authenticate(request, body, secret, store).userId, proof.userId)
  assert.throws(() => authenticate(request, body, secret, store))
})

test('approval is scope/chat/input bound, expires and is single-use', t => {
  const { store } = fixture(t); const actor = scope(); const chat = randomUUID()
  const part = { type: 'tool-execute_function', state: 'approval-requested', toolCallId: 'call-one', input: { function_name: 'synthetic', arguments: {} }, approval: { id: 'approval-one' } }
  store.rememberApprovals(actor, chat, { parts: [part] })
  const messages = [{ parts: [{ ...part, state: 'approval-responded', approval: { ...part.approval, approved: true } }] }]
  assert.throws(() => store.claimApproval(actor, randomUUID(), part.toolCallId, part.input, messages))
  assert.throws(() => store.claimApproval({ ...actor, userId: randomUUID() }, chat, part.toolCallId, part.input, messages))
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, { function_name: 'changed', arguments: {} }, messages))
  store.claimApproval(actor, chat, part.toolCallId, part.input, messages)
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, part.input, messages))
})

test('permission levels expose only explicit tools; writes require approval before gateway call', async t => {
  const { store } = fixture(t); const actor = scope(); const calls = []
  const call = (...args) => { calls.push(args); return [] }
  const expected = { none: [], schema: ['inspect_schema'], read: ['inspect_schema','read_rows'], write: ['inspect_schema','read_rows','list_functions','execute_function'] }
  for (const [permission, names] of Object.entries(expected)) {
    const tools = makeTools(actor, { permission }, call, store, randomUUID(), [], new AbortController().signal)
    assert.deepEqual(Object.keys(tools), names)
  }
  const tools = makeTools(actor, { permission:'write' }, call, store, randomUUID(), [], new AbortController().signal)
  assert.equal(tools.execute_function.needsApproval, true)
  await assert.rejects(() => tools.execute_function.execute({ function_name: 'test', arguments:{} }, {toolCallId:'not-approved'}))
  assert.equal(calls.length, 0)
})
