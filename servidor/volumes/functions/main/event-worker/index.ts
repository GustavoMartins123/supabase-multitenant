async function readEventToken(): Promise<string> {
  for (let attempt = 0; attempt < 120; attempt++) {
    try {
      const value = Deno.readTextFileSync('/dev/shm/.edge-event-key').trim()
      if (value) {
        try { Deno.removeSync('/dev/shm/.edge-event-key') } catch {}
        return value
      }
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 25))
  }
  return ''
}

const manager = new (globalThis as any).EventManager()
let cachedToken = ''

for await (const event of manager) {
  try {
    if (!cachedToken) cachedToken = await readEventToken()
    if (!cachedToken) continue
    await fetch('http://127.0.0.1:9000/__event-ingest', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-event-token': cachedToken,
      },
      body: JSON.stringify(event),
    })
  } catch {}
}
