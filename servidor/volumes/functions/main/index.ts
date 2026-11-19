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
const MAX_CONCURRENT_GLOBAL = 24
const MAX_ESZIP_CACHE_BYTES = 32 * 1024 * 1024
const MAX_ESZIP_CACHE_ENTRY_BYTES = 16 * 1024 * 1024
const eszipBundles = new Map<string, Uint8Array>()
let eszipCacheBytes = 0
const parsedContextByPath = new Map<string, { sig: string; data: Tenant }>()
const parsedProjectionByPath = new Map<string, { sig: string; data: Projection }>()
const MAX_PARSED_CONTEXTS = 200
const secretNamePattern = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/
const reservedSecretNames = new Set([
  'PATH', 'HOME', 'USER', 'SHELL', 'PWD', 'LANG', 'LC_ALL', 'TZ', 'HOST', 'PORT', 'HOSTNAME', 'VERIFY_JWT',
])
const reservedSecretPrefixes = [
  'SUPABASE_', 'PROJECT_', 'TECHNICAL_', 'JWT_', 'POSTGRES_', 'PG_', 'DENO_',
  'EDGE_RUNTIME_', 'TMP', 'XDG_', 'NODE_', 'LD_', 'HOST_AGENT_', 'KEY_AUTHORIZER_',
  'FERNET_', 'ENCRYPTION_', 'ALLOCATOR_',
]
const textEncoder = new TextEncoder()

type Projection = { project_ref: string; technical_name: string; project_uuid: string;
  anon_key: string; service_role_key: string; jwt_secret: string; network_allowlist?: string[]; edge_gateway_token?: string }
const gatewayTokenPattern = /^[0-9a-f]{64}$/

function fileStatSignature(info: Deno.FileInfo): string {
  return `${info.ino ?? 0}:${info.size}:${info.mtime?.getTime() ?? 0}`
}

function getCachedEszip(key: string): Uint8Array | undefined {
  const hit = eszipBundles.get(key)
  if (!hit) return undefined
  eszipBundles.delete(key)
  eszipBundles.set(key, hit)
  return hit.slice()
}

function putCachedEszip(key: string, bytes: Uint8Array): void {
  if (bytes.byteLength <= 0 || bytes.byteLength > MAX_ESZIP_CACHE_ENTRY_BYTES) return
  const existing = eszipBundles.get(key)
  if (existing) {
    eszipCacheBytes -= existing.byteLength
    eszipBundles.delete(key)
  }
  while (eszipCacheBytes + bytes.byteLength > MAX_ESZIP_CACHE_BYTES && eszipBundles.size > 0) {
    const oldestKey = eszipBundles.keys().next().value
    if (!oldestKey) break
    const oldest = eszipBundles.get(oldestKey)
    if (oldest) eszipCacheBytes -= oldest.byteLength
    eszipBundles.delete(oldestKey)
  }
  eszipBundles.set(key, bytes)
  eszipCacheBytes += bytes.byteLength
}

async function canonicalProjection(name: string, ref: string): Promise<Projection> {
  const path = `/home/deno/tenant-config/${name}.json`
  let info: Deno.FileInfo
  try {
    info = await Deno.lstat(path)
  } catch (error) {
    parsedProjectionByPath.delete(path)
    throw error
  }
  if (!info.isFile || info.isSymlink || info.size > 65536) {
    parsedProjectionByPath.delete(path)
    throw new Error('Invalid lifecycle projection')
  }
  const sig = fileStatSignature(info)
  const cached = parsedProjectionByPath.get(path)
  if (cached && cached.sig === sig && cached.data.technical_name === name && cached.data.project_ref === ref) {
    parsedProjectionByPath.delete(path)
    parsedProjectionByPath.set(path, cached)
    return cached.data
  }
  const value = JSON.parse(await Deno.readTextFile(path))
  const required = ['project_ref', 'technical_name', 'project_uuid', 'anon_key', 'service_role_key', 'jwt_secret']
  const allowed = new Set([...required, 'network_allowlist', 'edge_gateway_token'])
  if (!value || typeof value !== 'object' || Array.isArray(value) ||
    Object.keys(value).some(key => !allowed.has(key)) ||
    required.some(key => typeof value[key] !== 'string' || !value[key] || value[key] !== value[key].trim()) ||
    value.project_ref !== ref || value.technical_name !== name || !uuidPattern.test(value.project_uuid)) {
    throw new Error('Invalid lifecycle projection')
  }
  if (value.edge_gateway_token !== undefined &&
    (typeof value.edge_gateway_token !== 'string' || !gatewayTokenPattern.test(value.edge_gateway_token))) {
    throw new Error('Invalid lifecycle projection')
  }
  externalNetworkHosts(value.network_allowlist ?? [])
  parsedProjectionByPath.delete(path)
  parsedProjectionByPath.set(path, { sig, data: value })
  if (parsedProjectionByPath.size > MAX_PARSED_CONTEXTS) {
    const oldest = parsedProjectionByPath.keys().next().value
    if (oldest && oldest !== path) parsedProjectionByPath.delete(oldest)
  }
  return value
}

const reservedFunctionNames = new Set([
  'main', 'secrets', 'logs', 'gc', 'config', 'health', 'versions',
  'templates', 'quotas', 'alerts', 'schedules',
])
const functionNamePattern = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/

type RuntimeLimits = { memory_limit_mb: number; worker_timeout_ms: number; max_concurrent_project: number }
type Tenant = { project: string; uuid: string; jwt_secret: string; revision: string; env: Record<string, string>; network_allowlist?: string[]; secrets?: Record<string, string>; public_functions?: string[]; limits?: RuntimeLimits }

function validatePublicFunctions(raw: unknown): string[] {
  if (raw === undefined) return []
  if (!Array.isArray(raw) || raw.length === 0 || raw.length > 128) throw new Error('Invalid context')
  const seen = new Set<string>()
  const result: string[] = []
  for (const item of raw) {
    if (typeof item !== 'string' || !functionNamePattern.test(item) || reservedFunctionNames.has(item) || seen.has(item)) {
      throw new Error('Invalid context')
    }
    seen.add(item)
    result.push(item)
  }
  return result
}

function validateSecrets(raw: unknown): Record<string, string> {
  if (raw === undefined) return {}
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Invalid context')
  const entries = Object.entries(raw as Record<string, unknown>)
  if (entries.length === 0 || entries.length > 128) throw new Error('Invalid context')
  let totalBytes = 0
  const result: Record<string, string> = {}
  for (const [key, value] of entries) {
    const upper = key.toUpperCase()
    if (!secretNamePattern.test(key) || reservedSecretNames.has(upper) ||
        reservedSecretPrefixes.some((prefix) => upper.startsWith(prefix))) {
      throw new Error('Invalid context')
    }
    if (typeof value !== 'string' || !value || value.includes('\0')) throw new Error('Invalid context')
    const byteLen = textEncoder.encode(value).length
    if (byteLen > 8192) throw new Error('Invalid context')
    totalBytes += textEncoder.encode(key).length + byteLen
    if (totalBytes > 131072) throw new Error('Invalid context')
    result[key] = value
  }
  return result
}

function validateLimits(raw: unknown): RuntimeLimits {
  const defaults: RuntimeLimits = { memory_limit_mb: 150, worker_timeout_ms: 60000, max_concurrent_project: 2 }
  if (raw === undefined) return defaults
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Invalid context')
  const obj = raw as Record<string, unknown>
  const allowed = new Set(['memory_limit_mb', 'worker_timeout_ms', 'max_concurrent_project'])
  if (Object.keys(obj).some((k) => !allowed.has(k)) || Object.keys(obj).length !== 3) {
    throw new Error('Invalid context')
  }
  const mem = obj.memory_limit_mb
  const timeout = obj.worker_timeout_ms
  const conc = obj.max_concurrent_project
  if (!Number.isInteger(mem) || (mem as number) < 64 || (mem as number) > 512) throw new Error('Invalid context')
  if (!Number.isInteger(timeout) || (timeout as number) < 1000 || (timeout as number) > 120000) throw new Error('Invalid context')
  if (!Number.isInteger(conc) || (conc as number) < 1 || (conc as number) > 8) throw new Error('Invalid context')
  return {
    memory_limit_mb: mem as number,
    worker_timeout_ms: timeout as number,
    max_concurrent_project: conc as number,
  }
}

function response(code: string, status: number): Response {
  return Response.json({ code, ...(code === 'service_disabled' ? { service: 'edge_functions' } : {}) }, { status })
}

async function tenantContext(name: string, uuid: string): Promise<Tenant | null> {
  const path = `/home/deno/runtime/tenants/${name}.json`
  let info: Deno.FileInfo
  try { info = await Deno.lstat(path) }
  catch (error) {
    parsedContextByPath.delete(path)
    if (error instanceof Deno.errors.NotFound) return null
    throw error
  }
  if (!info.isFile || info.isSymlink || info.size > 262144) {
    parsedContextByPath.delete(path)
    throw new Error('Invalid context')
  }
  const sig = fileStatSignature(info)
  const cached = parsedContextByPath.get(path)
  if (cached && cached.sig === sig && cached.data.project === name && cached.data.uuid === uuid) {
    parsedContextByPath.delete(path)
    parsedContextByPath.set(path, cached)
    return cached.data
  }
  const data = JSON.parse(await Deno.readTextFile(path))
  const allowedKeys = new Set([...fields, 'network_allowlist', 'secrets', 'public_functions', 'limits'])
  if (!data || typeof data !== 'object' || Array.isArray(data) ||
    Object.keys(data).some((key) => !allowedKeys.has(key)) || fields.some((key) => !(key in data)) ||
    data.project !== name || data.uuid !== uuid || typeof data.jwt_secret !== 'string' || !data.jwt_secret ||
    typeof data.revision !== 'string' || !/^[0-9a-f]{64}$/.test(data.revision) ||
    !data.env || Object.keys(data.env).length !== envFields.length ||
    envFields.some((key) => typeof data.env[key] !== 'string' || !data.env[key])) throw new Error('Invalid context')
  externalNetworkHosts(data.network_allowlist ?? [])
  validateSecrets(data.secrets)
  validatePublicFunctions(data.public_functions)
  validateLimits(data.limits)
  parsedContextByPath.delete(path)
  parsedContextByPath.set(path, { sig, data })
  if (parsedContextByPath.size > MAX_PARSED_CONTEXTS) {
    const oldest = parsedContextByPath.keys().next().value
    if (oldest && oldest !== path) parsedContextByPath.delete(oldest)
  }
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

const MAX_LOGS_PER_PROJECT = 200
const MAX_LOG_PROJECTS = 200
const MAX_LOG_MESSAGE_LEN = 1024

interface LogEntry {
  id: string
  timestamp: string
  function_name: string
  level: string
  source: string
  message: string
  status?: number
  duration_ms?: number
  request_id?: string
}

const projectLogs = new Map<string, LogEntry[]>()
const projectSensitiveValues = new Map<string, string[]>()
const uuidToProject = new Map<string, string>()

const tokenBytes = crypto.getRandomValues(new Uint8Array(32))
const eventIngestToken = Array.from(tokenBytes, (b) => b.toString(16).padStart(2, '0')).join('')
try {
  Deno.writeTextFileSync('/dev/shm/.edge-event-key', eventIngestToken)
} catch {
  // Event worker token delivery unavailable if /dev/shm is not writable.
}

function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length || a.length === 0) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i)
  return diff === 0
}

async function hmacHex(secret: string, message: string): Promise<string> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw', enc.encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  )
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message))
  return Array.from(new Uint8Array(sig), (b) => b.toString(16).padStart(2, '0')).join('')
}

function registerTenantRedaction(project: string, uuid: string, tenant: Tenant, canonical?: Projection): void {
  uuidToProject.set(uuid, project)
  const values = new Set<string>()
  const collect = (val: unknown) => {
    if (typeof val === 'string' && val.length >= 4 && val !== project && val !== uuid) values.add(val)
  }
  collect(tenant.jwt_secret)
  if (canonical) {
    collect(canonical.jwt_secret)
    collect(canonical.anon_key)
    collect(canonical.service_role_key)
    collect(canonical.edge_gateway_token)
  }
  for (const val of Object.values(tenant.secrets ?? {})) collect(val)
  for (const [key, val] of Object.entries(tenant.env ?? {})) {
    if (/SECRET|KEY|TOKEN|PASS/i.test(key)) collect(val)
    if (typeof val === 'string') {
      const m = val.match(/:\/\/[^:@\s]+:([^@\s]+)@/)
      if (m?.[1]) collect(m[1])
    }
  }
  projectSensitiveValues.set(project, Array.from(values).sort((a, b) => b.length - a.length))
  if (projectSensitiveValues.size > MAX_LOG_PROJECTS) {
    const oldest = projectSensitiveValues.keys().next().value
    if (oldest && oldest !== project) projectSensitiveValues.delete(oldest)
  }
}

function redactMessage(project: string, raw: string): string {
  let out = raw.replace(/[\r\n\t]+/g, ' ').trim()
  for (const secret of projectSensitiveValues.get(project) ?? []) {
    if (secret && out.includes(secret)) out = out.split(secret).join('[REDACTED]')
  }
  out = out
    .replace(/(postgres(?:ql)?:\/\/[^:@\s]+:)([^@\s]+)(@)/gi, '$1[REDACTED]$3')
    .replace(/(?<![A-Za-z0-9_-])Bearer\s+(?!Bearer(?:\s|$))\S+/gi, 'Bearer [REDACTED]')
    .replace(/\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g, '[REDACTED_JWT]')
    .replace(/\bsb_(?:secret|publishable)_[A-Za-z0-9_-]+\b/g, '[REDACTED_KEY]')
  if (out.length > MAX_LOG_MESSAGE_LEN) out = `${out.slice(0, MAX_LOG_MESSAGE_LEN - 3)}...`
  return out
}

function recordLog(
  project: string,
  functionName: string,
  level: string,
  source: string,
  rawMessage: string,
  extra?: { status?: number; duration_ms?: number; request_id?: string },
): void {
  const message = redactMessage(project, rawMessage)
  if (!message) return
  let entries = projectLogs.get(project)
  if (!entries) {
    entries = []
    projectLogs.set(project, entries)
    if (projectLogs.size > MAX_LOG_PROJECTS) {
      const oldest = projectLogs.keys().next().value
      if (oldest && oldest !== project) projectLogs.delete(oldest)
    }
  } else {
    projectLogs.delete(project)
    projectLogs.set(project, entries)
  }
  entries.push({
    id: crypto.randomUUID(),
    timestamp: new Date().toISOString(),
    function_name: functionName,
    level,
    source,
    message,
    ...extra,
  })
  if (entries.length > MAX_LOGS_PER_PROJECT) {
    entries.splice(0, entries.length - MAX_LOGS_PER_PROJECT)
  }
}

function parseEventTarget(rawPath: unknown): { project: string; functionName: string } | null {
  if (typeof rawPath !== 'string' || !rawPath) return null
  const match = rawPath.match(/\/code\/([^/]+)\/[0-9a-f]{64}\/([^/]+)/)
  if (!match) return null
  const key = match[1]
  const functionName = match[2]
  if (!functionNamePattern.test(functionName) || reservedFunctionNames.has(functionName)) return null
  const project = uuidToProject.get(key) ?? (projectPattern.test(key) ? key : '')
  if (!project) return null
  return { project, functionName }
}

async function handleEventIngest(request: Request): Promise<Response> {
  if (request.method !== 'POST') return new Response(null, { status: 405 })
  const forbiddenHeaders = [
    'x-forwarded-for', 'x-real-ip', 'x-project-name', 'x-project-uuid',
    'x-project-ref', 'x-gateway-admission', 'x-shared-token', 'authorization', 'apikey',
  ]
  if (forbiddenHeaders.some((name) => request.headers.has(name))) {
    return response('forbidden', 403)
  }
  if (!constantTimeEqual(request.headers.get('x-event-token') ?? '', eventIngestToken)) {
    return response('forbidden', 403)
  }
  let rawText = ''
  try {
    rawText = await request.text()
  } catch {
    return response('invalid_event_payload', 400)
  }
  if (rawText.length > 32768) return response('payload_too_large', 413)
  let payload: Record<string, unknown>
  try {
    const parsed = JSON.parse(rawText)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return response('invalid_event_payload', 400)
    }
    payload = parsed as Record<string, unknown>
  } catch {
    return response('invalid_event_payload', 400)
  }
  const metadata = (payload.metadata && typeof payload.metadata === 'object' ? payload.metadata : {}) as Record<string, unknown>
  const body = (payload.event && typeof payload.event === 'object' ? payload.event : payload) as Record<string, unknown>
  const eventType = String(payload.event_type ?? payload.type ?? '')
  const target = parseEventTarget(metadata.service_path ?? payload.service_path)
  if (!target) return new Response(null, { status: 204 })

  if (eventType === 'Log') {
    const rawLevel = String(body.level ?? 'info').toLowerCase()
    const level = rawLevel.startsWith('warn') ? 'warn' : rawLevel.startsWith('err') ? 'error' : 'info'
    const msg = typeof body.msg === 'string' ? body.msg : JSON.stringify(body.msg ?? body)
    recordLog(target.project, target.functionName, level, 'worker', msg)
  } else if (eventType === 'Boot') {
    const bootTime = typeof body.boot_time === 'number' ? body.boot_time : '?'
    recordLog(target.project, target.functionName, 'info', 'boot', `Worker booted (${bootTime}ms)`)
  } else if (eventType === 'BootFailure') {
    recordLog(target.project, target.functionName, 'error', 'boot', String(body.msg ?? 'Worker boot failed'))
  } else if (eventType === 'UncaughtException') {
    recordLog(target.project, target.functionName, 'error', 'worker', String(body.exception ?? 'Uncaught exception'))
  } else if (eventType === 'Shutdown') {
    const reason = String(body.reason ?? 'Shutdown')
    if (reason !== 'EventLoopCompleted') {
      recordLog(target.project, target.functionName, 'warn', 'boot', `Worker shutdown: ${reason}`)
    }
  }
  return new Response(null, { status: 204 })
}

async function handleLogsRequest(request: Request, url: URL): Promise<Response> {
  if (request.method !== 'GET') return new Response(null, { status: 405 })
  const rejectedProxyHeaders = ['x-forwarded-for', 'x-real-ip', 'x-gateway-admission', 'authorization', 'apikey']
  if (rejectedProxyHeaders.some((name) => request.headers.has(name))) {
    return response('forbidden', 403)
  }
  const project = request.headers.get('x-project-name') ?? ''
  const ref = request.headers.get('x-project-ref') ?? ''
  if (!projectPattern.test(project) || !/^[a-z]{20}$/.test(ref) || url.searchParams.has('ref') || url.searchParams.has('name')) {
    return response('invalid_project_context', 400)
  }
  const tsHeader = request.headers.get('x-logs-timestamp') ?? ''
  const sigHeader = (request.headers.get('x-logs-signature') ?? '').toLowerCase()
  const ts = Number(tsHeader)
  if (!/^\d+$/.test(tsHeader) || !Number.isInteger(ts) || !/^[0-9a-f]{64}$/.test(sigHeader)) {
    return response('forbidden', 403)
  }
  const nowSec = Math.floor(Date.now() / 1000)
  if (Math.abs(nowSec - ts) > 30) return response('forbidden', 403)
  let canonical: Projection
  try {
    canonical = await canonicalProjection(project, ref)
  } catch {
    return response('tenant_configuration_unavailable', 503)
  }
  const uuid = canonical.project_uuid
  let tenant: Tenant | null
  try {
    tenant = await tenantContext(project, uuid)
  } catch {
    return response('tenant_configuration_unavailable', 503)
  }
  if (!tenant) return response('service_disabled', 404)
  const expectedSig = await hmacHex(canonical.jwt_secret, `edge-logs-v1\n${project}\n${uuid}\n${ref}\n${tsHeader}`)
  if (!constantTimeEqual(sigHeader, expectedSig)) return response('forbidden', 403)

  registerTenantRedaction(project, uuid, tenant, canonical)

  const fnFilter = url.searchParams.get('function') ?? ''
  if (fnFilter && (!functionNamePattern.test(fnFilter) || reservedFunctionNames.has(fnFilter))) {
    return response('invalid_function_name', 400)
  }
  const levelFilter = url.searchParams.get('level') ?? ''
  if (levelFilter && !['info', 'warn', 'error'].includes(levelFilter)) {
    return response('invalid_log_level', 400)
  }
  const limitRaw = url.searchParams.get('limit')
  let limit = 50
  if (limitRaw !== null && limitRaw !== '') {
    const parsed = Number(limitRaw)
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 200) return response('invalid_limit', 400)
    limit = parsed
  }

  const all = projectLogs.get(project) ?? []
  const logs: LogEntry[] = []
  for (let i = all.length - 1; i >= 0 && logs.length < limit; i--) {
    const entry = all[i]
    if (fnFilter && entry.function_name !== fnFilter) continue
    if (levelFilter && entry.level !== levelFilter) continue
    logs.push({ ...entry, message: redactMessage(project, entry.message) })
  }
  return Response.json({ logs }, { headers: { 'cache-control': 'no-store' } })
}

Deno.serve(async (request: Request) => {
  const url = new URL(request.url)
  if (url.pathname === '/__health') return Response.json({ status: 'ok' })
  if (url.pathname === '/__event-ingest') return await handleEventIngest(request)
  if (url.pathname === '/__logs') return await handleLogsRequest(request, url)
  const project = request.headers.get('x-project-name') ?? ''
  const ref = request.headers.get('x-project-ref') ?? ''
  if (!projectPattern.test(project) || !/^[a-z]{20}$/.test(ref) || url.searchParams.has('ref') || url.searchParams.has('name')) {
    return response('invalid_project_context', 400)
  }
  let canonical: Projection
  try { canonical = await canonicalProjection(project, ref) }
  catch { return response('tenant_configuration_unavailable', 503) }
  if (canonical.edge_gateway_token) {
    const providedGatewayToken = request.headers.get('x-edge-gateway-token') ?? ''
    if (!providedGatewayToken || !constantTimeEqual(providedGatewayToken, canonical.edge_gateway_token)) {
      return response('forbidden', 403)
    }
  }
  const uuid = canonical.project_uuid
  let tenant: Tenant | null
  try { tenant = await tenantContext(project, uuid) }
  catch { return response('tenant_configuration_unavailable', 503) }
  if (!tenant) return response('service_disabled', 404)
  let name: string
  try { name = decodeURIComponent(url.pathname.split('/')[1]) }
  catch { return response('invalid_function_name', 400) }
  if (!functionNamePattern.test(name) || reservedFunctionNames.has(name)) return response('invalid_function_name', 400)
  const isPublic = Array.isArray(tenant.public_functions) && tenant.public_functions.includes(name)
  const apiKey = request.headers.get('apikey') ?? ''
  if (isPublic) {
    if (apiKey !== '' && apiKey !== canonical.anon_key && apiKey !== canonical.service_role_key) {
      return response('invalid_api_key', 403)
    }
  } else {
    if (apiKey !== canonical.anon_key && apiKey !== canonical.service_role_key) {
      return response('invalid_api_key', 403)
    }
    if (!await authorized(request, { ...tenant, jwt_secret: canonical.jwt_secret })) return response('invalid_jwt', 401)
  }
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
  let maybeEszip: Uint8Array | undefined
  try {
    const eszipPath = `${servicePath}/bundle.eszip`
    const eszipInfo = await Deno.lstat(eszipPath)
    if (!eszipInfo.isFile || eszipInfo.isSymlink || eszipInfo.size <= 0 || eszipInfo.size > 33554432) {
      return response('tenant_configuration_unavailable', 503)
    }
    const eszipKey = `${eszipPath}:${fileStatSignature(eszipInfo)}`
    maybeEszip = getCachedEszip(eszipKey)
    if (!maybeEszip) {
      const loaded = await Deno.readFile(eszipPath)
      putCachedEszip(eszipKey, loaded)
      maybeEszip = loaded.slice()
    }
  } catch (error) {
    if (!(error instanceof Deno.errors.NotFound)) return response('tenant_configuration_unavailable', 503)
  }
  const limits = validateLimits(tenant.limits)
  const currentProjectRunning = running.get(project) ?? 0
  if (totalRunning >= MAX_CONCURRENT_GLOBAL || currentProjectRunning >= limits.max_concurrent_project) {
    const reqId = (request.headers.get('x-request-id') ?? '').trim().slice(0, 128)
    recordLog(
      project,
      name,
      'warn',
      'worker',
      `Saturation: concurrency limit reached (${currentProjectRunning}/${limits.max_concurrent_project} project, ${totalRunning}/${MAX_CONCURRENT_GLOBAL} global)`,
      { status: 429, ...(reqId ? { request_id: reqId } : {}) },
    )
    return response('function_concurrency_limit', 429)
  }
  totalRunning++
  running.set(project, currentProjectRunning + 1)
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
  const timer = setTimeout(release, limits.worker_timeout_ms + 5000)
  registerTenantRedaction(project, uuid, tenant, canonical)
  const startedAt = Date.now()
  try {
    const permissions = await workerPermissions(project, tenant.network_allowlist ?? [], tenant.env.SUPABASE_DB_URL)
    // DNS resolution may await I/O. Recheck both publication and lifecycle only after it completes.
    if ((await tenantContext(project, uuid))?.revision !== tenant.revision ||
      JSON.stringify(await canonicalProjection(project, ref)) !== JSON.stringify(canonical)) {
      release()
      return response('service_disabled', 404)
    }
    const baseEnv = { ...tenant.env, PROJECT_REF: ref, TECHNICAL_PROJECT_NAME: project,
      SUPABASE_PUBLIC_URL: new URL(tenant.env.SUPABASE_PUBLIC_URL).origin + '/' + ref }
    const workerEnv = { ...tenant.env, ...(tenant.secrets ?? {}), ...baseEnv }
    const worker = await EdgeRuntime.userWorkers.create({
      servicePath, memoryLimitMb: limits.memory_limit_mb, workerTimeoutMs: limits.worker_timeout_ms,
      noModuleCache: false, forceCreate: true, importMapPath: maybeEszip ? null : importMapPath,
      ...(maybeEszip ? { maybeEszip } : {}),
      envVars: Object.entries(workerEnv),
      permissions,
    })
    const result = await worker.fetch(request)
    const durationMs = Date.now() - startedAt
    const level = result.status >= 500 ? 'error' : result.status >= 400 ? 'warn' : 'info'
    recordLog(project, name, level, 'invocation', `${request.method} ${url.pathname} -> ${result.status}`, {
      status: result.status,
      duration_ms: durationMs,
    })
    if (result.status === 101) {
      request.signal?.addEventListener('abort', () => { release() }, { once: true })
      return result
    }
    if (!result.body) { release(); return result }
    const headers = new Headers(result.headers)
    if (headers.get('content-type')?.toLowerCase().includes('text/event-stream') && !headers.has('x-accel-buffering')) {
      headers.set('x-accel-buffering', 'no')
    }
    const reader = result.body.getReader()
    request.signal?.addEventListener('abort', () => {
      release()
      void reader.cancel().catch(() => {})
    }, { once: true })
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const chunk = await reader.read()
          if (chunk.done) { release(); controller.close() }
          else controller.enqueue(chunk.value)
        } catch (error) {
          recordLog(project, name, 'error', 'worker', error instanceof Error ? error.message : 'Stream read error')
          release()
          controller.error(error)
        }
      },
      async cancel(reason) { try { await reader.cancel(reason) } finally { release() } },
    })
    return new Response(body, { status: result.status, statusText: result.statusText, headers })
  } catch (error) {
    release()
    const message = error instanceof Error ? error.message : 'Edge function failed to start or complete'
    recordLog(project, name, 'error', 'boot', message, { status: 500, duration_ms: Date.now() - startedAt })
    console.error('Edge function failed to start or complete')
    return response('function_execution_failed', 500)
  }
})
