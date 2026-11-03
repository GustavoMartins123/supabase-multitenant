// One trusted supervisor; fresh workers receive only their project's code and env.
// No remote imports are needed to start the runtime or validate project JWTs.
import { externalNetworkHosts, workerPermissions } from './network-policy.ts'
const projectPattern = /^[a-z_][a-z0-9_]{2,39}$/
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const fields = ['project', 'uuid', 'jwt_secret', 'env', 'revision']
const envFields = ['SUPABASE_URL', 'SUPABASE_PUBLIC_URL', 'SUPABASE_ANON_KEY',
  'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_DB_URL']
const running = new Map<string, number>()
let totalRunning = 0

type Projection = { project_ref: string; technical_name: string; project_uuid: string;
  anon_key: string; service_role_key: string; jwt_secret: string; network_allowlist?: string[] }

async function canonicalProjection(name: string, ref: string): Promise<Projection> {
  const path = `/home/deno/tenant-config/${name}.json`
  const info = await Deno.lstat(path)
  if (!info.isFile || info.isSymlink || info.size > 65536) throw new Error('Invalid lifecycle projection')
  const value = JSON.parse(await Deno.readTextFile(path))
  const required = ['project_ref', 'technical_name', 'project_uuid', 'anon_key', 'service_role_key', 'jwt_secret']
  if (!value || ![required.length, required.length + 1].includes(Object.keys(value).length) ||
    Object.keys(value).some(key => ![...required, 'network_allowlist'].includes(key)) ||
    required.some(key => typeof value[key] !== 'string' || !value[key] || value[key] !== value[key].trim()) ||
    value.project_ref !== ref || value.technical_name !== name || !uuidPattern.test(value.project_uuid)) {
    throw new Error('Invalid lifecycle projection')
  }
  externalNetworkHosts(value.network_allowlist ?? [])
  return value
}

type Tenant = { project: string; uuid: string; jwt_secret: string; revision: string; env: Record<string, string>; network_allowlist?: string[] }

function response(code: string, status: number): Response {
  return Response.json({ code, ...(code === 'service_disabled' ? { service: 'edge_functions' } : {}) }, { status })
}

async function tenantContext(name: string, uuid: string): Promise<Tenant | null> {
  const path = `/home/deno/runtime/tenants/${name}.json`
  let info: Deno.FileInfo
  try { info = await Deno.lstat(path) }
  catch (error) {
    if (error instanceof Deno.errors.NotFound) return null
    throw error
  }
  if (!info.isFile || info.isSymlink || info.size > 65536) throw new Error('Invalid context')
  const data = JSON.parse(await Deno.readTextFile(path))
  if (!data || ![fields.length, fields.length + 1].includes(Object.keys(data).length) ||
    Object.keys(data).some((key) => ![...fields, 'network_allowlist'].includes(key)) || fields.some((key) => !(key in data)) ||
    data.project !== name || data.uuid !== uuid || typeof data.jwt_secret !== 'string' || !data.jwt_secret ||
    typeof data.revision !== 'string' || !/^[0-9a-f]{64}$/.test(data.revision) ||
    !data.env || Object.keys(data.env).length !== envFields.length ||
    envFields.some((key) => typeof data.env[key] !== 'string' || !data.env[key])) throw new Error('Invalid context')
  externalNetworkHosts(data.network_allowlist ?? [])
  return data
}

function decode(value: string): Uint8Array {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('Invalid encoding')
  return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), (c) => c.charCodeAt(0))
}

async function authorized(request: Request, tenant: Tenant): Promise<boolean> {
  try {
    const bearer = request.headers.get('authorization')?.match(/^Bearer ([^\s]+)$/i)
    const parts = bearer?.[1].split('.')
    if (!parts || parts.length !== 3) return false
    const header = JSON.parse(new TextDecoder().decode(decode(parts[0])))
    if (header.alg !== 'HS256' || header.crit !== undefined) return false
    const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(tenant.jwt_secret),
      { name: 'HMAC', hash: 'SHA-256' }, false, ['verify'])
    if (!await crypto.subtle.verify('HMAC', key, decode(parts[2]),
      new TextEncoder().encode(parts[0] + '.' + parts[1]))) return false
    const claims = JSON.parse(new TextDecoder().decode(decode(parts[1])))
    const now = Date.now() / 1000
    return Number.isFinite(claims.exp) && claims.exp > now &&
      (claims.nbf === undefined || (Number.isFinite(claims.nbf) && claims.nbf <= now)) &&
      ['anon', 'authenticated', 'service_role'].includes(claims.role)
  } catch { return false }
}

Deno.serve(async (request: Request) => {
  const url = new URL(request.url)
  if (url.pathname === '/__health') return Response.json({ status: 'ok' })
  const project = request.headers.get('x-project-name') ?? ''
  const ref = request.headers.get('x-project-ref') ?? ''
  if (!projectPattern.test(project) || !/^[a-z]{20}$/.test(ref) || url.searchParams.has('ref') || url.searchParams.has('name')) {
    return response('invalid_project_context', 400)
  }
  let canonical: Projection
  try { canonical = await canonicalProjection(project, ref) }
  catch { return response('tenant_configuration_unavailable', 503) }
  const uuid = canonical.project_uuid
  let tenant: Tenant | null
  try { tenant = await tenantContext(project, uuid) }
  catch { return response('tenant_configuration_unavailable', 503) }
  if (!tenant) return response('service_disabled', 404)
  const apiKey = request.headers.get('apikey')
  if (apiKey !== canonical.anon_key && apiKey !== canonical.service_role_key) {
    return response('invalid_api_key', 403)
  }
  if (!await authorized(request, { ...tenant, jwt_secret: canonical.jwt_secret })) return response('invalid_jwt', 401)
  let name: string
  try { name = decodeURIComponent(url.pathname.split('/')[1]) }
  catch { return response('invalid_function_name', 400) }
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(name) || name === 'main') return response('invalid_function_name', 400)
  const servicePath = `/home/deno/runtime/code/${uuid}/${tenant.revision}/${name}`
  try { await Deno.stat(`${servicePath}/index.ts`) }
  catch { return response('function_not_found', 404) }
  let importMapPath: string | null = null
  try {
    const info = await Deno.lstat(`${servicePath}/deno.json`)
    if (!info.isFile || info.isSymlink) return response('tenant_configuration_unavailable', 503)
    importMapPath = `${servicePath}/deno.json`
  } catch (error) {
    if (!(error instanceof Deno.errors.NotFound)) return response('tenant_configuration_unavailable', 503)
  }
  if (totalRunning >= 4 || (running.get(project) ?? 0) >= 2) return response('function_concurrency_limit', 429)
  totalRunning++
  running.set(project, (running.get(project) ?? 0) + 1)
  let released = false
  const release = () => {
    if (released) return
    released = true
    totalRunning--
    const count = (running.get(project) ?? 1) - 1
    if (count) running.set(project, count)
    else running.delete(project)
    clearTimeout(timer)
  }
  const timer = setTimeout(release, 65000)
  try {
    const permissions = await workerPermissions(project, tenant.network_allowlist ?? [], tenant.env.SUPABASE_DB_URL)
    // DNS resolution may await I/O. Recheck both publication and lifecycle only after it completes.
    if ((await tenantContext(project, uuid))?.revision !== tenant.revision ||
      JSON.stringify(await canonicalProjection(project, ref)) !== JSON.stringify(canonical)) {
      release()
      return response('service_disabled', 404)
    }
    const workerEnv = { ...tenant.env, PROJECT_REF: ref, TECHNICAL_PROJECT_NAME: project,
      SUPABASE_PUBLIC_URL: new URL(tenant.env.SUPABASE_PUBLIC_URL).origin + '/' + ref }
    const worker = await EdgeRuntime.userWorkers.create({
      servicePath, memoryLimitMb: 150, workerTimeoutMs: 60000,
      noModuleCache: false, forceCreate: true, importMapPath, envVars: Object.entries(workerEnv),
      permissions,
    })
    const result = await worker.fetch(request)
    if (!result.body) { release(); return result }
    const reader = result.body.getReader()
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const chunk = await reader.read()
          if (chunk.done) { release(); controller.close() }
          else controller.enqueue(chunk.value)
        } catch (error) { release(); controller.error(error) }
      },
      async cancel(reason) { try { await reader.cancel(reason) } finally { release() } },
    })
    return new Response(body, { status: result.status, statusText: result.statusText, headers: result.headers })
  } catch {
    release()
    console.error('Edge function failed to start or complete')
    return response('function_execution_failed', 500)
  }
})
