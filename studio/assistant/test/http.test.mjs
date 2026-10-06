import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { createHash, createHmac, randomBytes, randomUUID } from 'node:crypto'
import { MockLanguageModelV3, simulateReadableStream } from 'ai/test'
import { APICallError } from 'ai'
import { createHandler } from '../app.mjs'
import { AssistantStore } from '../store.mjs'
import { AssistantToolError, assistantErrorMessage } from '../errors.mjs'

const secret = 'b'.repeat(64)
const actor = { userId: randomUUID(), projectId: randomUUID(), ref: 'abcdefghijklmnopqrst', role: 'admin', userToken: 'signed-synthetic-token'.repeat(4) }
const usage = { inputTokens: { total: 1 }, outputTokens: { total: 1 } }
const finish = { type: 'finish', finishReason: { unified:'stop', raw:'stop' }, usage }
const textChunks = () => [{ type:'stream-start', warnings:[] }, { type:'text-start', id:'text-one' }, { type:'text-delta', id:'text-one', delta:'Synthetic ' }, { type:'text-delta', id:'text-one', delta:'answer' }, { type:'text-end', id:'text-one' }, finish]

test('full SQL tool executes a CREATE INDEX directly without an approval dialog', async t => {
  let turn = 0
  const model = new MockLanguageModelV3({doStream:async () => ({stream:simulateReadableStream({chunks:++turn === 1
    ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:'index-call',toolName:'execute_sql',input:JSON.stringify({sql:'CREATE INDEX items_id_idx ON public.items(id)',label:'Create index'})},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
    : textChunks()})})})
  const {store,request,calls} = await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'full',apiKey:'synthetic-provider-key-only'})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Create an index'}]}]})
  const output = await response.text()
  assert.equal(output.includes('tool-approval-request'),false)
  assert.equal(calls.filter(action=>action==='sql').length,1)
  assert.match(output,/tool-output-available/)
})

test('tool errors do not mislabel an unsupported operation as destructive', () => {
  assert.match(assistantErrorMessage(new AssistantToolError(400)), /unsupported/)
  assert.equal(assistantErrorMessage(new AssistantToolError(400)).includes('destructive'), false)
  assert.match(assistantErrorMessage(new AssistantToolError(409, {code:'sql_approval_required'})), /explicit destructive approval/)
  assert.equal(assistantErrorMessage(new AssistantToolError(409)).includes('destructive'), false)
})

test('security inspection is available to schema access without SQL execution', async t => {
  const input = {tables:['orders']}
  let turn=0
  const model=new MockLanguageModelV3({doStream:async()=>({stream:simulateReadableStream({chunks:++turn===1
    ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:'security-one',toolName:'inspect_security',input:JSON.stringify(input)},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
    : textChunks()})})})
  const {store,request,calls}=await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'schema',apiKey:'synthetic-provider-key-only'})
  const response=await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Inspect RLS and grants on orders'}]}]})
  const output=await response.text()
  assert.equal(calls.filter(action=>action==='security').length,1)
  assert.equal(calls.includes('sql'),false)
  assert.match(output,/tool-output-available/)
})

test('stale ordinary SQL approval is not silently replayed as direct execution', async t => {
  const model = new MockLanguageModelV3({doStream:{stream:simulateReadableStream({chunks:textChunks()})}})
  const {store,request,calls} = await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'full',apiKey:'synthetic-provider-key-only'})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{
    id:randomUUID(),role:'assistant',parts:[{type:'tool-execute_sql',state:'approval-responded',toolCallId:'stale',
      input:{sql:'CREATE TABLE public.items(id integer)',label:'Create'},approval:{id:'stale-approval',approved:true}}]}]})
  assert.equal(response.status,409)
  assert.equal(calls.length,0)
  assert.equal(model.doStreamCalls.length,0)
})

async function harness(t, model, options = {}) {
  const store = new AssistantStore(':memory:', 'a'.repeat(64))
  const calls = []
  const call = async (scope, action) => { calls.push(action); if (action === 'context') return { project_id:scope.projectId, user_id:scope.userId, role:scope.role }; if (options.toolError) throw options.toolError; return [] }
  const server = createServer(createHandler({ store, secret, call, modelFactory: () => model, ...options }))
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

test('SQL type errors are sanitized, delivered to the model and followed by a conclusion', async t => {
  let turn = 0
  const model = new MockLanguageModelV3({doStream:async options => {
    if (++turn === 2) assert.match(JSON.stringify(options.prompt), /SQLSTATE 42883/)
    return {stream:simulateReadableStream({chunks:turn === 1
      ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:'invalid-policy',toolName:'execute_sql',input:JSON.stringify({sql:'CREATE POLICY own ON public.orders TO authenticated USING(cliente_id=auth.uid())',label:'Policy'})},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
      : textChunks()})}
  }})
  const {store,request,calls} = await harness(t,model,{toolError:new AssistantToolError(422,{code:'sql_operand_types',sqlstate:'42883',message:'synthetic-secret-do-not-expose'})})
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'full',apiKey:'synthetic-provider-key-only'})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Create the policy'}]}]})
  const output = await response.text()
  assert.match(output,/tool-output-error/)
  assert.match(output,/SQLSTATE 42883/)
  assert.equal(output.includes('"type":"error"'),false)
  assert.match(output,/Synthetic /)
  assert.match(output,/\[DONE\]/)
  assert.equal(output.includes('synthetic-secret-do-not-expose'),false)
  assert.equal(calls.filter(action=>action==='sql').length,1)
  assert.equal(model.doStreamCalls.length,2)
})

test('multiple tools can exceed five steps and finish with a reserved summary step', async t => {
  let turn = 0
  const model = new MockLanguageModelV3({doStream:async options => {
    ++turn
    if (turn === 7) { assert.deepEqual(options.tools,[]); assert.deepEqual(options.toolChoice,{type:'none'}) }
    return {stream:simulateReadableStream({chunks:turn < 7
      ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:`schema-${turn}`,toolName:'inspect_schema',input:'{}'},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
      : textChunks()})}
  }})
  const {store,request,calls} = await harness(t,model,{maxSteps:7})
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'schema',apiKey:'synthetic-provider-key-only'})
  const output = await (await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Inspect'}]}]})).text()
  assert.equal(calls.filter(action=>action==='schema').length,6)
  assert.match(output,/Synthetic /)
  assert.match(output,/operation-step budget reached/)
  assert.equal(output.includes('"type":"error"'),false)
  assert.match(output,/\[DONE\]/)
  assert.equal(model.doStreamCalls.length,7)
})

test('a provider cannot execute another tool in the summary-only step', async t => {
  let turn=0
  const model=new MockLanguageModelV3({doStream:async()=>({stream:simulateReadableStream({chunks:[
    {type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:`ignored-choice-${++turn}`,toolName:'inspect_schema',input:'{}'},
    {...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}},
  ]})})})
  const {store,request,calls}=await harness(t,model,{maxSteps:2})
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'schema',apiKey:'synthetic-provider-key-only'})
  const output=await (await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Inspect'}]}]})).text()
  assert.equal(calls.filter(action=>action==='schema').length,1)
  assert.match(output,/operation-step budget reached/)
  assert.match(output,/\[DONE\]/)
  assert.equal(model.doStreamCalls.length,2)
})

test('provider length stop is explicit in the native stream', async t => {
  const chunks=textChunks(); chunks[chunks.length-1]={...finish,finishReason:{unified:'length',raw:'length'}}
  const model=new MockLanguageModelV3({doStream:{stream:simulateReadableStream({chunks})}})
  const {store,request}=await harness(t,model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'none',apiKey:'synthetic-provider-key-only'})
  const output=await (await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Explain'}]}]})).text()
  assert.match(output,/Provider output token limit reached/)
  assert.equal(output.includes('"type":"error"'),false)
  assert.match(output,/\[DONE\]/)
  assert.equal(model.doStreamCalls.length,1)
})

test('request deadline produces an explicit incomplete response without retries', async t => {
  const model=new MockLanguageModelV3({doStream:{stream:simulateReadableStream({chunks:textChunks(),chunkDelayInMs:200})}})
  const {store,request}=await harness(t,model,{requestTimeoutMs:50})
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'none',apiKey:'synthetic-provider-key-only'})
  const output=await (await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Explain'}]}]})).text()
  assert.match(output,/request deadline reached/)
  assert.match(output,/in-flight operation may have completed/)
  assert.equal(output.includes('"type":"error"'),false)
  assert.match(output,/\[DONE\]/)
  assert.equal(model.doStreamCalls.length,1)
})

test('SQL diagnostics require matching code, status and SQLSTATE and never forward server text',()=>{
  const detail={code:'sql_operand_types',sqlstate:'42883',message:'synthetic-secret',hint:'synthetic-secret',query:'synthetic-secret'}
  assert.match(new AssistantToolError(422,detail).message,/SQLSTATE 42883/)
  for(const error of [new AssistantToolError(422,detail),new AssistantToolError(409,detail),new AssistantToolError(422,{...detail,sqlstate:'private'}),new AssistantToolError(422,{...detail,code:'private'})]) {
    assert.equal(error.message.includes('synthetic-secret'),false)
    assert.equal(error.message.includes('private'),false)
  }
  assert.equal(new AssistantToolError(409,{code:'sql_object_exists',sqlstate:'42710'}).message.includes('destructive approval'),false)
})

for(const operation of ['grant','revoke']) {
  test(`${operation} table privileges uses native approval before dispatch and cannot replay`,async t=>{
    const input={operation,tables:['orders'],role:'authenticated',privileges:['SELECT'],label:'Table privileges'}
    let turn=0
    const model=new MockLanguageModelV3({doStream:async()=>({stream:simulateReadableStream({chunks:++turn===1
      ? [{type:'stream-start',warnings:[]},{type:'tool-call',toolCallId:'privilege-call',toolName:'manage_table_privileges',input:JSON.stringify(input)},{...finish,finishReason:{unified:'tool-calls',raw:'tool_calls'}}]
      : textChunks()})})})
    const {store,request,calls}=await harness(t,model)
    store.save(actor,{provider:'openai',model:'explicit-model',permission:'full',apiKey:'synthetic-provider-key-only'})
    const chatId=randomUUID(),user={id:randomUUID(),role:'user',parts:[{type:'text',text:'Manage table access'}]}
    const first=await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId,messages:[user]})
    const events=(await first.text()).split('\n').filter(line=>line.startsWith('data: {')).map(line=>JSON.parse(line.slice(6)))
    const approval=events.find(event=>event.type==='tool-approval-request')
    assert.ok(approval)
    assert.equal(calls.includes('privileges'),false)
    const assistant={id:randomUUID(),role:'assistant',parts:[{type:'tool-manage_table_privileges',state:'approval-responded',toolCallId:'privilege-call',input,approval:{id:approval.approvalId,approved:true}}]}
    const next=await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId,messages:[user,assistant]})
    const output=await next.text()
    assert.match(output,/tool-output-available/)
    assert.equal(output.includes('"type":"error"'),false)
    assert.equal(calls.filter(action=>action==='privileges').length,1)
    const replay=await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId,messages:[user,assistant]})
    await replay.text()
    assert.equal(calls.filter(action=>action==='privileges').length,1)
  })
}

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

for (const statusCode of [400, 401, 402, 403, 404, 429]) {
  test(`provider HTTP ${statusCode} is explicit without exposing private errors`, async t => {
    const secretText = 'synthetic-secret-provider-body'
    const model = new MockLanguageModelV3({ doStream: async () => {
      throw new APICallError({ message: secretText, url: 'https://provider.invalid',
        requestBodyValues: { apiKey: secretText }, statusCode, responseBody: secretText })
    } })
    const { store, request } = await harness(t, model)
    store.save(actor, {provider:'openrouter',model:'explicit-model',permission:'none',apiKey:'synthetic-provider-key-only'})
    const response = await request('/api/ai/sql/generate-v4','POST',{
      projectRef:actor.ref,chatId:randomUUID(),messages:[{id:randomUUID(),role:'user',parts:[{type:'text',text:'Hello'}]}]})
    const output = await response.text()
    assert.match(output, new RegExp(`HTTP ${statusCode}`))
    assert.match(output, /No retry/)
    assert.equal(output.includes(secretText), false)
    assert.equal(model.doStreamCalls.length, 1)
  })
}

test('invalid messages are refused before contacting provider', async t => {
  const model = new MockLanguageModelV3({ doStream: {stream:simulateReadableStream({chunks:textChunks()})} })
  const { store, request } = await harness(t, model)
  store.save(actor,{provider:'openai',model:'explicit-model',permission:'none',apiKey:'synthetic-provider-key-only'})
  const response = await request('/api/ai/sql/generate-v4','POST',{projectRef:actor.ref,chatId:randomUUID(),messages:[{role:'system',parts:[]}]})
  assert.equal(response.status, 400)
  assert.equal(model.doStreamCalls.length, 0)
})

for (const name of ['execute_destructive_sql']) {
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
