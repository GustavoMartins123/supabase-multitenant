import test from 'node:test'
import assert from 'node:assert/strict'
import { readUIMessageStream } from 'ai'
import { boundedAssistantStream } from '../stream.mjs'

function source(chunks) {
  return new ReadableStream({ start(controller) { for (const chunk of chunks) controller.enqueue(chunk); controller.close() } })
}

for (const reason of ['length', 'budget', 'deadline']) {
  test(`${reason} notice remains readable as native UI message parts`, async () => {
    const chunks = [{type:'start',messageId:'synthetic-message'}, {type:'text-start',id:'original'}, {type:'text-delta',id:'original',delta:'Partial explanation'}]
    if (reason !== 'deadline') chunks.push({type:'text-end',id:'original'})
    chunks.push(reason === 'deadline' ? {type:'abort'} : {type:'finish',finishReason:reason === 'length' ? 'length' : 'stop'})
    let last
    const stream = boundedAssistantStream(source(chunks), {deadlineExceeded:()=>reason === 'deadline',summaryStepReached:()=>reason === 'budget'})
    for await (const message of readUIMessageStream({stream,terminateOnError:true})) last=message
    const text=last.parts.filter(part=>part.type==='text').map(part=>part.text).join('\n')
    assert.match(text,/Partial explanation/)
    assert.match(text,/No retry was attempted/)
    assert.equal(last.parts.filter(part=>part.type==='text').length,2)
  })
}

test('normal completion and user cancellation do not claim that a request limit was reached', async()=>{
  for(const end of [{type:'finish',finishReason:'stop'},{type:'abort'}]) {
    const stream=boundedAssistantStream(source([{type:'start',messageId:'synthetic'},end]),{deadlineExceeded:()=>false,summaryStepReached:()=>false})
    const chunks=[];for await(const chunk of stream) chunks.push(chunk)
    assert.equal(chunks.some(chunk=>chunk.type==='text-delta'),false)
  }
})
