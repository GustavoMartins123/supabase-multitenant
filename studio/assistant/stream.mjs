import { randomUUID } from 'node:crypto'

export function boundedAssistantStream(stream, { deadlineExceeded, summaryStepReached }) {
  const openText = new Set(), openReasoning = new Set()
  let notified = false
  function notice(controller, text) {
    if (notified) return
    notified = true
    for (const id of openText) controller.enqueue({ type: 'text-end', id })
    for (const id of openReasoning) controller.enqueue({ type: 'reasoning-end', id })
    openText.clear(); openReasoning.clear()
    const id = randomUUID()
    controller.enqueue({ type: 'text-start', id })
    controller.enqueue({ type: 'text-delta', id, delta: `\n\n${text}` })
    controller.enqueue({ type: 'text-end', id })
  }
  return stream.pipeThrough(new TransformStream({
    transform(chunk, controller) {
      if (chunk.type === 'text-start') openText.add(chunk.id)
      if (chunk.type === 'text-end') openText.delete(chunk.id)
      if (chunk.type === 'reasoning-start') openReasoning.add(chunk.id)
      if (chunk.type === 'reasoning-end') openReasoning.delete(chunk.id)
      if (chunk.type === 'abort' && deadlineExceeded()) {
        notice(controller, 'Assistant request deadline reached. This response is incomplete. Completed operations are not undone; verify database state before continuing. An in-flight operation may have completed. No retry was attempted.')
      }
      if (chunk.type === 'finish' && chunk.finishReason === 'length') {
        notice(controller, 'Provider output token limit reached. This response is incomplete. Completed operations are not undone; verify their results before continuing. No retry was attempted.')
      } else if (chunk.type === 'finish' && summaryStepReached()) {
        notice(controller, 'Assistant operation-step budget reached. The final step was reserved for a summary; no further database operations were authorized. Review completed and pending work before continuing. No retry was attempted.')
      }
      controller.enqueue(chunk)
    },
  }))
}
