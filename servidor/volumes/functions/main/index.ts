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

const verifyJwtSetting = Deno.env.get('VERIFY_JWT')
if (verifyJwtSetting !== 'true' && verifyJwtSetting !== 'false') throw new Error('VERIFY_JWT must be explicit')
const VERIFY_JWT = verifyJwtSetting === 'true'
const PROJECTS_DIR = '/home/deno/projects'
const REF_PATTERN = /^[a-z_][a-z0-9_]{2,39}$/

interface TenantConfig {
  env: Record<string, string>
  jwtSecret: string
}

function parseDotenv(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  const required = new Set(['ANON_KEY_PROJETO', 'SERVICE_ROLE_KEY_PROJETO', 'JWT_SECRET_PROJETO'])
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim()
    if (!line || line.startsWith('#')) continue
    const eq = line.indexOf('=')
    if (eq === -1) continue
    const key = line.slice(0, eq).trim()
    if (!required.has(key)) continue
    const value = line.slice(eq + 1)
    if (key in out || rawLine !== line || line.slice(0, eq) !== key || !value || value !== value.trim() || value.startsWith('"') || value.startsWith("'")) throw new Error('noncanonical tenant credential')
    out[key] = value
  }
  if (Object.keys(out).length !== required.size) throw new Error('incomplete tenant credentials')
  return out
}

async function loadTenant(ref: string): Promise<TenantConfig | null> {
  if (!REF_PATTERN.test(ref)) return null

  const path = `${PROJECTS_DIR}/${ref}/.env`
  let raw: string
  try {
    raw = await Deno.readTextFile(path)
  } catch {
    return null
  }

  let parsed: Record<string, string>
  try { parsed = parseDotenv(raw) } catch { return null }
  const anon = parsed['ANON_KEY_PROJETO']
  const service = parsed['SERVICE_ROLE_KEY_PROJETO']
  const jwtSecret = parsed['JWT_SECRET_PROJETO']

  const env: Record<string, string> = {
    SUPABASE_URL: `http://supabase-nginx-${ref}:8080`,
    SUPABASE_ANON_KEY: anon,
    SUPABASE_SERVICE_ROLE_KEY: service,
    JWT_SECRET: jwtSecret,
    PROJECT_REF: ref,
  }

  return { env, jwtSecret }
}

function resolveRef(req: Request, url: URL): string | null {
  // The tenant gateway supplies this fixed identity, never query/body aliases.
  if (url.searchParams.has('ref')) return null
  const header = req.headers.get('x-project-ref')
  return header && REF_PATTERN.test(header) ? header : null
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
    await jose.jwtVerify(jwt, new TextEncoder().encode(secret), { algorithms: ['HS256'] })
    return true
  } catch (err) {
    console.error(err)
    return false
  }
}

serve(async (req: Request) => {
  const url = new URL(req.url)
  const ref = resolveRef(req, url)

  if (!ref) return new Response(JSON.stringify({ msg: 'canonical project identity required' }), {
    status: 400, headers: { 'Content-Type': 'application/json' },
  })
  const tenant = await loadTenant(ref)
  if (!tenant) return new Response(JSON.stringify({ msg: 'tenant configuration unavailable' }), {
    status: 503, headers: { 'Content-Type': 'application/json' },
  })
  const workerEnv = tenant.env
  const jwtSecret = tenant.jwtSecret

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
  if (!service_name || !/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(service_name) || service_name === 'main') {
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
