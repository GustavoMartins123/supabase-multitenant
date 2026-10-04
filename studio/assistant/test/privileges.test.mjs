import test from 'node:test'
import assert from 'node:assert/strict'
import { randomUUID, createHash } from 'node:crypto'
import { AssistantStore } from '../store.mjs'
import { makeTools } from '../app.mjs'
import { privilegeSchema, privilegeSql } from '../privileges.mjs'

const input={operation:'grant',tables:['clientes','Pedidos'],role:'authenticated',privileges:['SELECT','UPDATE'],label:'Application privileges'}
const scope={userId:randomUUID(),projectId:randomUUID(),role:'admin',ref:'abcdefghijklmnopqrst'}

test('structured privilege SQL matches the backend contract without arbitrary SQL',()=>{
  assert.equal(privilegeSql(input),'GRANT SELECT, UPDATE ON TABLE public."clientes", public."Pedidos" TO "authenticated";')
  assert.equal(privilegeSql({...input,operation:'revoke',role:'anon'}),'REVOKE SELECT, UPDATE ON TABLE public."clientes", public."Pedidos" FROM "anon" RESTRICT;')
  for(const change of [{role:'PUBLIC'},{role:'postgres'},{role:'service_role'},{privileges:['ALL']},{privileges:['TRUNCATE']},{privileges:['TRIGGER']},{privileges:['REFERENCES']},{tables:['auth.users']},{tables:['items"; DROP TABLE public.items;--']},{tables:['x'.repeat(64)]},{tables:[]},{tables:['a','a']},{privileges:['SELECT','SELECT']},{sql:'GRANT ALL TO PUBLIC'},{grant_option:true},{cascade:true}]) {
    assert.equal(privilegeSchema.safeParse({...input,...change}).success,false)
  }
})

function fixture(t) {
  const store=new AssistantStore(':memory:','a'.repeat(64))
  t.after(()=>store.close())
  store.save(scope,{provider:'openai',model:'synthetic',permission:'full',apiKey:'synthetic-test-key-only'})
  const chatId=randomUUID(),callId=randomUUID(),approvalId=randomUUID()
  const requested={id:randomUUID(),role:'assistant',parts:[{type:'tool-manage_table_privileges',toolCallId:callId,state:'approval-requested',input,approval:{id:approvalId}}]}
  store.rememberApprovals(scope,chatId,requested)
  const approved={...requested,parts:[{...requested.parts[0],state:'approval-responded',approval:{id:approvalId,approved:true}}]}
  const calls=[]
  const tools=(actor=scope,messages=[approved])=>makeTools(actor,{permission:'full'},async(...args)=>{calls.push(args);return {status:'GRANT'}},store,chatId,messages,new AbortController().signal)
  return {store,chatId,callId,requested,approved,calls,tools}
}

test('privilege execution consumes exact approval and execution once before dispatch',async t=>{
  const {tools,callId,calls}=fixture(t)
  await tools().manage_table_privileges.execute(input,{toolCallId:callId})
  assert.equal(calls.length,1)
  assert.equal(calls[0][1],'privileges')
  const execution=calls[0][2].execution
  assert.equal(execution.tool,'manage_table_privileges')
  assert.ok(execution.approval_id)
  assert.equal(execution.sql_hash,createHash('sha256').update(privilegeSql(input)).digest('hex'))
  await assert.rejects(()=>tools().manage_table_privileges.execute(input,{toolCallId:callId}))
  assert.equal(calls.length,1)
})

test('privilege approval cannot change role, tables, privilege, operation, user, project or tool',async t=>{
  const {store,chatId,callId,approved,calls,tools}=fixture(t)
  for(const change of [{role:'anon'},{tables:['other']},{privileges:['DELETE']},{operation:'revoke'}]) {
    const altered={...input,...change}
    const messages=[{...approved,parts:[{...approved.parts[0],input:altered}]}]
    await assert.rejects(()=>tools(scope,messages).manage_table_privileges.execute(altered,{toolCallId:callId}))
  }
  for(const actor of [{...scope,userId:randomUUID()},{...scope,projectId:randomUUID()}]) {
    assert.throws(()=>store.claimApproval(actor,chatId,callId,input,[approved],'manage_table_privileges'))
  }
  assert.throws(()=>store.claimApproval(scope,chatId,callId,input,[approved],'execute_destructive_sql'))
  await assert.rejects(()=>tools(scope,[]).manage_table_privileges.execute(input,{toolCallId:callId}))
  assert.equal(calls.length,0)
})

test('denied, expired or downgraded privilege approvals never dispatch',async t=>{
  const {store,callId,approved,calls,tools}=fixture(t)
  const denied={...approved,parts:[{...approved.parts[0],approval:{...approved.parts[0].approval,approved:false}}]}
  await assert.rejects(()=>tools(scope,[denied]).manage_table_privileges.execute(input,{toolCallId:callId}))
  store.db.prepare('UPDATE approvals SET expires_at=0').run()
  await assert.rejects(()=>tools().manage_table_privileges.execute(input,{toolCallId:callId}))
  store.save(scope,{provider:'openai',model:'synthetic',permission:'read'})
  await assert.rejects(()=>tools().manage_table_privileges.execute(input,{toolCallId:callId}))
  assert.equal(calls.length,0)
  for(const permission of ['none','schema','read','write']) {
    assert.equal('manage_table_privileges' in makeTools(scope,{permission},()=>{},store,randomUUID(),[],new AbortController().signal),false)
  }
})
