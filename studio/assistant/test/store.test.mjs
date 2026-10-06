import test from 'node:test'
import assert from 'node:assert/strict'
import { createHmac, createHash, randomBytes, randomUUID } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { AssistantStore, digest } from '../store.mjs'
import { authenticate } from '../auth.mjs'
import { makeTools } from '../app.mjs'
import { assistantPrompt } from '../prompts.mjs'

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
  assert.throws(() => store.claimApproval(actor, randomUUID(), part.toolCallId, part.input, messages, 'execute_function'))
  assert.throws(() => store.claimApproval({ ...actor, userId: randomUUID() }, chat, part.toolCallId, part.input, messages, 'execute_function'))
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, { function_name: 'changed', arguments: {} }, messages, 'execute_function'))
  store.claimApproval(actor, chat, part.toolCallId, part.input, messages, 'execute_function')
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, part.input, messages, 'execute_function'))
})

test('permission levels expose only explicit tools; writes require approval before gateway call', async t => {
  const { store } = fixture(t); const actor = scope(); const calls = []
  const call = (...args) => { calls.push(args); return [] }
  const expected = { none: [], schema: ['inspect_schema','inspect_security'], read: ['inspect_schema','inspect_security','read_rows'], write: ['inspect_schema','inspect_security','read_rows','list_functions','execute_function'], full: ['inspect_schema','inspect_security','read_rows','manage_table_privileges','execute_sql','execute_destructive_sql'] }
  for (const [permission, names] of Object.entries(expected)) {
    const tools = makeTools(actor, { permission }, call, store, randomUUID(), [], new AbortController().signal)
    assert.deepEqual(Object.keys(tools), names)
  }
  const tools = makeTools(actor, { permission:'write' }, call, store, randomUUID(), [], new AbortController().signal)
  assert.equal(tools.execute_function.needsApproval, true)
  await assert.rejects(() => tools.execute_function.execute({ function_name: 'test', arguments:{} }, {toolCallId:'not-approved'}))
  assert.equal(calls.length, 0)
})

test('Destructive approval cannot become ordinary execution, change SQL, expire or cross projects', async t => {
  const { store } = fixture(t); const actor = scope(); const chat = randomUUID()
  const input = { sql: 'UPDATE public.items SET quantity=1 WHERE id=2', label: 'Update quantity' }
  const part = { type: 'tool-execute_destructive_sql', state: 'approval-requested', toolCallId: 'sql-call', input, approval: { id: 'sql-approval' } }
  store.rememberApprovals(actor, chat, { parts: [part] })
  const approved = { ...part, state: 'approval-responded', approval: { id: part.approval.id, approved: true } }
  const messages = [{ parts: [approved] }]
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, input, [{ parts: [{ ...approved, type: 'tool-execute_sql' }] }], 'execute_destructive_sql'))
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, { ...input, sql: 'DELETE FROM public.items' }, messages, 'execute_destructive_sql'))
  assert.throws(() => store.claimApproval({ ...actor, projectId: randomUUID() }, chat, part.toolCallId, input, messages, 'execute_destructive_sql'))
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, input, [{ parts: [{ ...approved, approval: { ...approved.approval, approved: false } }] }], 'execute_destructive_sql'))
  store.db.prepare('UPDATE approvals SET expires_at=?').run(Date.now()-1)
  assert.throws(() => store.claimApproval(actor, chat, part.toolCallId, input, messages, 'execute_destructive_sql'))
})

test('full SQL executes directly; destructive calls require one-use approval and server-issued authority', async t => {
  const { store } = fixture(t); const actor = scope(); const calls = []
  store.save(actor, { ...config, permission: 'full' })
  const call = async (...args) => { calls.push(args); return {} }
  for (const name of ['execute_sql', 'execute_destructive_sql']) {
    const chat = randomUUID(); const input = { sql: name === 'execute_sql' ? 'CREATE TABLE public.items(id integer)' : 'DELETE FROM public.items WHERE id=1', label: 'Synthetic SQL' }
    const part = { type: `tool-${name}`, state: 'approval-requested', toolCallId: name, input, approval: { id: randomUUID() } }
    if (name === 'execute_destructive_sql') store.rememberApprovals(actor, chat, { parts: [part] })
    const messages = name === 'execute_destructive_sql'
      ? [{ parts: [{ ...part, state: 'approval-responded', approval: { ...part.approval, approved: true } }] }] : []
    const tools = makeTools(actor, { permission: 'full' }, call, store, chat, messages, new AbortController().signal)
    assert.equal(tools[name].needsApproval, name === 'execute_destructive_sql')
    store.save(actor, { ...config, permission: 'read' })
    await assert.rejects(() => tools[name].execute(input, { toolCallId: name }), /no longer authorized/)
    store.save(actor, { ...config, permission: 'full' })
    await tools[name].execute(input, { toolCallId: name })
    const [scope, action, payload] = calls.at(-1)
    assert.equal(scope.projectId, actor.projectId)
    assert.equal(action, 'sql')
    assert.equal(payload.permission, 'full')
    assert.equal(payload.execution.tool, name)
    assert.equal(payload.execution.sql_hash, createHash('sha256').update(input.sql).digest('hex'))
    assert.equal(Boolean(payload.execution.approval_id), name === 'execute_destructive_sql')
    await assert.rejects(() => tools[name].execute(input, { toolCallId: name }))
  }
  assert.equal(calls.length, 2)
})

test('direct SQL call IDs cannot be reused, changed or converted into destructive authority', t => {
  const {store} = fixture(t); const actor = scope(); const chat = randomUUID()
  const input = {sql:'CREATE TABLE public.items(id integer)',label:'Create table'}
  store.claimExecution(actor,chat,'one-call',input,'execute_sql')
  assert.throws(()=>store.claimExecution(actor,chat,'one-call',input,'execute_sql'))
  assert.throws(()=>store.claimExecution(actor,chat,'one-call',{...input,sql:'DELETE FROM public.items'},'execute_destructive_sql'))
  assert.throws(()=>store.claimApproval(actor,chat,'one-call',input,[],'execute_destructive_sql'))
})

test('prompts describe actual access without advertising unavailable AI functions', () => {
  for (const permission of ['none', 'schema', 'read', 'full']) assert.equal(assistantPrompt(permission).includes('[AI]'), false)
  assert.match(assistantPrompt('write'), /\[AI\]/)
  assert.match(assistantPrompt('full'), /Full access never authorizes deletion automatically/)
  assert.throws(() => assistantPrompt('unknown'))
})

test('approval digests ignore JSON property order but preserve exact SQL and tool identity', () => {
  const first = { tool: 'tool-execute_sql', input: { sql: 'UPDATE public.items SET id=2', label: 'Update' } }
  const reordered = { input: { label: 'Update', sql: first.input.sql }, tool: first.tool }
  assert.equal(digest(first), digest(reordered))
  assert.notEqual(digest(first), digest({ ...first, input: { ...first.input, sql: first.input.sql + ' ' } }))
  assert.notEqual(digest(first), digest({ ...first, tool: 'tool-execute_destructive_sql' }))
})
