
Deno.serve(async () => {
  const reads: Record<string, boolean> = {}
  for (const path of ['/home/deno/tenant-config/test_beta.json', '/home/deno/projects/test_beta/.env']) {
    try { await Deno.readTextFile(path); reads[path] = true } catch { reads[path] = false }
  }
  return new Response(JSON.stringify({ env: Deno.env.toObject(), reads }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
