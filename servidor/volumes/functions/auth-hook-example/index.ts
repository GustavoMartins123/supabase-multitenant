import { serve } from 'https://deno.land/std@0.177.1/http/server.ts'

serve(async (req: Request) => {
  const payload = await req.json().catch(() => ({}))
  console.log('auth-hook-example payload:', payload)
  return new Response(JSON.stringify({ ok: true }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
