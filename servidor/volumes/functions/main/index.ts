import { serve } from 'https://deno.land/std@0.131.0/http/server.ts'
import * as jose from 'https://deno.land/x/jose@v4.14.4/index.ts'

console.log('main function started')

declare const EdgeRuntime: {
  userWorkers: {
    create(opts: {
      servicePath: string
      memoryLimitMb: number
      workerTimeoutMs: number
      noModuleCache: boolean
      importMapPath: string | null
      envVars: [string, string][]
    }): Promise<{ fetch(req: Request): Promise<Response> }>
  }
}

const VERIFY_JWT = Deno.env.get('VERIFY_JWT') === 'true'
const PROJECTS_DIR = Deno.env.get('PROJECTS_DIR') ?? '/home/deno/projects'
const REF_PATTERN = /^[a-z0-9][a-z0-9_-]{0,62}$/

const globalEnv = Deno.env.toObject()

interface TenantConfig {
  env: Record<string, string>
  jwtSecret: string
}

const tenantCache = new Map<string, { config: TenantConfig; mtime: number }>()

function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    let value = line.slice(eq + 1).trim()
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1)
    }
    out[key] = value
  }
  return out
}

async function loadTenant(ref: string): Promise<TenantConfig | null> {
  if (!REF_PATTERN.test(ref)) return null

  const path = `${PROJECTS_DIR}/${ref}/.env`
  let stat: Deno.FileInfo
  try {
    stat = await Deno.stat(path)
  } catch {
    return null
  }

  const mtime = stat.mtime?.getTime() ?? 0
  const cached = tenantCache.get(ref)
  if (cached && cached.mtime === mtime) return cached.config

  let raw: string
  try {
    raw = await Deno.readTextFile(path)
  } catch {
    return null
  }

  const parsed = parseDotenv(raw)
  const anon = parsed['ANON_KEY_PROJETO'] ?? ''
  const service = parsed['SERVICE_ROLE_KEY_PROJETO'] ?? ''
  const jwtSecret = parsed['JWT_SECRET_PROJETO'] ?? ''
  const dbName = parsed['POSTGRES_DATABASE'] ?? `_supabase_${ref}`
  if (!anon || !service || !jwtSecret) return null

  const dbUser = globalEnv['POSTGRES_USER'] ?? 'supabase_admin'
  const dbHost = globalEnv['POSTGRES_HOST'] ?? ''
  const dbPort = globalEnv['POSTGRES_PORT'] ?? '5432'
  const dbPass = globalEnv['POSTGRES_PASSWORD'] ?? ''

  const env: Record<string, string> = {
    ...globalEnv,
    SUPABASE_URL: `http://supabase-nginx-${ref}:8080`,
    SUPABASE_ANON_KEY: anon,
    SUPABASE_SERVICE_ROLE_KEY: service,
    SUPABASE_DB_URL: `postgresql://${dbUser}:${dbPass}@${dbHost}:${dbPort}/${dbName}`,
    JWT_SECRET: jwtSecret,
    PROJECT_REF: ref,
  }

  const config: TenantConfig = { env, jwtSecret }
  tenantCache.set(ref, { config, mtime })
  return config
}

function resolveRef(req: Request, url: URL): string | null {
  const header = req.headers.get('x-project-ref')
  if (header) return header.trim().toLowerCase()
  const query = url.searchParams.get('ref')
  if (query) return query.trim().toLowerCase()
  return null
}

function getAuthToken(req: Request): string {
  const authHeader = req.headers.get('authorization')
  if (!authHeader) throw new Error('Missing authorization header')
  const [bearer, token] = authHeader.split(' ')
  if (bearer !== 'Bearer') throw new Error("Auth header is not 'Bearer {token}'")
  return token
}

async function verifyJWT(jwt: string, secret: string): Promise<boolean> {
  try {
    await jose.jwtVerify(jwt, new TextEncoder().encode(secret))
    return true
  } catch (err) {
    console.error(err)
    return false
  }
}

serve(async (req: Request) => {
  const url = new URL(req.url)
  const ref = resolveRef(req, url)

  let workerEnv = globalEnv
  let jwtSecret = globalEnv['JWT_SECRET'] ?? ''

  if (ref) {
    const tenant = await loadTenant(ref)
    if (!tenant) {
      return new Response(JSON.stringify({ msg: `unknown project ref: ${ref}` }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    workerEnv = tenant.env
    jwtSecret = tenant.jwtSecret
  }

  if (req.method !== 'OPTIONS' && VERIFY_JWT) {
    try {
      const token = getAuthToken(req)
      if (!(await verifyJWT(token, jwtSecret))) {
        return new Response(JSON.stringify({ msg: 'Invalid JWT' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        })
      }
    } catch (e) {
      return new Response(JSON.stringify({ msg: String(e) }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      })
    }
  }

  const service_name = url.pathname.split('/')[1]
  if (!service_name) {
    return new Response(JSON.stringify({ msg: 'missing function name in request' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const servicePath = `/home/deno/functions/${service_name}`
  const envVars = Object.entries(workerEnv)

  try {
    const worker = await EdgeRuntime.userWorkers.create({
      servicePath,
      memoryLimitMb: 150,
      workerTimeoutMs: 60 * 1000,
      noModuleCache: false,
      importMapPath: null,
      envVars,
    })
    return await worker.fetch(req)
  } catch (e) {
    return new Response(JSON.stringify({ msg: String(e) }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' },
    })
  }
})
