import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { createHash, createHmac, randomBytes, randomUUID } from 'node:crypto'
import { MockLanguageModelV3, simulateReadableStream } from 'ai/test'
import { createHandler } from '../app.mjs'
import { AssistantStore } from '../store.mjs'

const secret = 'b'.repeat(64)
const actor = { userId: randomUUID(), projectId: randomUUID(), ref: 'abcdefghijklmnopqrst', role: 'admin', userToken: 'signed-synthetic-token'.repeat(4) }
const usage = { inputTokens: { total: 1 }, outputTokens: { total: 1 } }
const finish = { type: 'finish', finishReason: { unified:'stop', raw:'stop' }, usage }
const textChunks = () => [{ type:'stream-start', warnings:[] }, { type:'text-start', id:'text-one' }, { type:'text-delta', id:'text-one', delta:'Synthetic ' }, { type:'text-delta', id:'text-one', delta:'answer' }, { type:'text-end', id:'text-one' }, finish]

async function harness(t, model) {
  const store = new AssistantStore(':memory:', 'a'.repeat(64))
  const calls = []
  const call = async (scope, action) => { calls.push(action); if (action === 'context') return { project_id:scope.projectId, user_id:scope.userId, role:scope.role }; return [] }
  const server = createServer(createHandler({ store, secret, call, modelFactory: () => model }))
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  t.after(async () => { server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); store.close() })
  const request = async (path, method = 'GET', payload, scope = actor, signed = true) => {
    const body = payload === undefined ? undefined : JSON.stringify(payload)
    const proof = { ...scope, method, target:path, timestamp:Math.floor(Date.now()/1000), nonce:randomBytes(16).toString('hex'), bodyHash:createHash('sha256').update(body ?? '').digest('hex') }
    const encoded = Buffer.from(JSON.stringify(proof)).toString('base64url')
    return fetch(`http://127.0.0.1:${server.address().port}${path}`, { method, body, headers: {
      'Content-Type':'application/json', ...(signed ? {'X-Assistant-Context':encoded + '.' + createHmac('sha256', secret).update(encoded).digest('hex')} : {}),
    } })
  }
  return { store, request, calls }
}

test('real HTTP settings never return the provider key; unsigned and cross-user requests fail closed', async t => {
  const { request } = await harness(t, {})
  assert.equal((await request('/api/ai/settings','GET',undefined,actor,false)).status,401)
  const providerKey = 'synthetic-provider-key-only'
  const response = await request('/api/ai/settings','PUT',{provider:'openai',model:'explicit-model',permission:'none',apiKey:providerKey})
  assert.equal(response.status,200)
  assert.equal((await response.text()).includes(providerKey),false)
  assert.equal((await (await request('/api/ai/settings')).json()).hasKey,true)
  assert.equal((await (await request('/api/ai/settings','GET',undefined,{...actor,userId:randomUUID()})).json()).hasKey,false)
  const refused = await request('/api/ai/settings','PUT',{provider:'openai',model:'explicit-model',permission:'write',apiKey:providerKey},{...actor,role:'member'})
  assert.equal(refused.status,403)
  assert.equal((await refused.text()).includes(providerKey),false)
})

test('AI SDK delivers native UI SSE and finishes without prematurely cancelling a completed POST body', async t => {
  const model = new MockLanguageModelV3({ doStream: { stream:simulateReadableStream({chunks:textChunks(),chunkDelayInMs:20}) } })
  const { store, request } = await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'none',apiKey:'synthetic-provider-key-only'})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Synthetic prompt'}]}]})
  assert.equal(response.status,200)
  assert.equal(response.headers.get('x-vercel-ai-ui-message-stream'),'v1')
  const output = await response.text()
  assert.match(output, /"type":"text-delta"/)
  assert.match(output, /Synthetic /)
  assert.match(output, /\[DONE\]/)
  assert.equal(model.doStreamCalls.length,1)
})

test('provider failure is sanitized and is not retried', async t => {
  const privateMessage = 'synthetic-provider-key-only'
  const model = new MockLanguageModelV3({ doStream:async () => { throw new Error(privateMessage) } })
  const { store, request } = await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'none',apiKey:privateMessage})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Synthetic prompt'}]}]})
  const output = await response.text()
  assert.equal(output.includes(privateMessage),false)
  assert.match(output,/No retry/)
  assert.equal(model.doStreamCalls.length,1)
})

test('native approval round trip is recorded, exact and single-use before executing a write tool', async t => {
  const input = { function_name:'synthetic_function', arguments:{} }
  let turn = 0
  const model = new MockLanguageModelV3({ doStream:async () => ({ stream:simulateReadableStream({chunks:++turn === 1
    ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:'call-write',toolName:'execute_function',input:JSON.stringify(input)},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
    : textChunks() }) }) })
  const { store, request, calls } = await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'write',apiKey:'synthetic-provider-key-only'})
  const chatId = randomUUID(); const user = {id:randomUUID(),role:'user',parts:[{type:'text',text:'Request the synthetic function.'}]}
  const first = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId,messages:[user]})
  const firstOutput = await first.text()
  const events = firstOutput.split('\n').filter(line=>line.startsWith('data: {')).map(line=>JSON.parse(line.slice(6)))
  const approval = events.find(event=>event.type==='tool-approval-request')
  assert.ok(approval,firstOutput)
  assert.equal(calls.includes('execute'),false)
  const assistant = {id:randomUUID(),role:'assistant',parts:[{type:'tool-execute_function',state:'approval-responded',toolCallId:'call-write',input,approval:{id:approval.approvalId,approved:true}}]}
  const next = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId,messages:[user,assistant]})
  const nextOutput = await next.text()
  assert.equal(calls.filter(action=>action==='execute').length,1,nextOutput)
  assert.throws(()=>store.claimApproval(actor,chatId,'call-write',input,[assistant],'execute_function'))
})

for (const name of ['execute_sql', 'execute_destructive_sql']) {
  test(`${name} streams an approval before executing and cannot run after permission downgrade`, async t => {
    const input = { sql: name === 'execute_sql' ? 'CREATE TABLE public.synthetic(id integer)' : 'DELETE FROM public.synthetic WHERE id=1', label: 'Synthetic operation' }
    let turn = 0
    const model = new MockLanguageModelV3({ doStream: async () => ({ stream: simulateReadableStream({ chunks: ++turn === 1
      ? [{ type: 'stream-start', warnings: [] }, { type: 'tool-call', toolCallId: 'call-sql', toolName: name, input: JSON.stringify(input) }, { ...finish, finishReason: { unified: 'tool-calls', raw: 'tool_calls' } }]
      : textChunks() }) }) })
    const { store, request, calls } = await harness(t, model)
    const configuration = { provider: 'openai', model: 'explicit-model', permission: 'full', apiKey: 'synthetic-provider-key-only' }
    store.save(actor, configuration)
    const chatId = randomUUID(); const user = { id: randomUUID(), role: 'user', parts: [{ type: 'text', text: 'Synthetic database request' }] }
    const first = await request('/api/ai/sql/generate-v4', 'POST', { projectRef: actor.ref, chatId, messages: [user] })
    const events = (await first.text()).split('\n').filter(line => line.startsWith('data: {')).map(line => JSON.parse(line.slice(6)))
    const approval = events.find(event => event.type === 'tool-approval-request')
    assert.ok(approval)
    assert.equal(calls.includes('sql'), false)
    assert.equal((await (await request('/api/ai/settings')).json()).maxPermission, 'full')
    const approved = { id: randomUUID(), role: 'assistant', parts: [{ type: `tool-${name}`, state: 'approval-responded', toolCallId: 'call-sql', input, approval: { id: approval.approvalId, approved: true } }] }
    store.save(actor, { ...configuration, permission: 'read' })
    const downgraded = await request('/api/ai/sql/generate-v4', 'POST', { projectRef: actor.ref, chatId, messages: [user, approved] })
    await downgraded.text()
    assert.equal(calls.includes('sql'), false)
    store.save(actor, configuration)
    const next = await request('/api/ai/sql/generate-v4', 'POST', { projectRef: actor.ref, chatId, messages: [user, approved] })
    await next.text()
    assert.equal(calls.filter(action => action === 'sql').length, 1)
    const replay = await request('/api/ai/sql/generate-v4', 'POST', { projectRef: actor.ref, chatId, messages: [user, approved] })
    await replay.text()
    assert.equal(calls.filter(action => action === 'sql').length, 1)
  })
}
