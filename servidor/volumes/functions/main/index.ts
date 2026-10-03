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
      forceCreate: boolean
      importMapPath: string | null
      envVars: [string, string][]
    }): Promise<{ fetch(req: Request): Promise<Response> }>
  }
}

const verifyJwtSetting = Deno.env.get('VERIFY_JWT')
if (verifyJwtSetting !== 'true' && verifyJwtSetting !== 'false') throw new Error('VERIFY_JWT must be explicit')
const VERIFY_JWT = verifyJwtSetting === 'true'
const TENANTS_DIR = '/home/deno/tenant-config'
const NAME_PATTERN = /^[a-z_][a-z0-9_]{2,39}$/
const REF_PATTERN = /^[a-z]{20}$/

interface TenantConfig {
  env: Record<string, string>
  jwtSecret: string
}

function parseTenantConfig(text: string, name: string, ref: string): { anon: string; service: string; jwtSecret: string } {
  const parsed = JSON.parse(text)
  const fields = ['project_ref', 'technical_name', 'project_uuid', 'anon_key', 'service_role_key', 'jwt_secret']
  if (!parsed || Array.isArray(parsed) || Object.keys(parsed).length !== fields.length ||
      fields.some(key => typeof parsed[key] !== 'string' || !parsed[key] || parsed[key] !== parsed[key].trim()) ||
      parsed.project_ref !== ref || parsed.technical_name !== name || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(parsed.project_uuid)) {
    throw new Error('noncanonical tenant projection')
  }
  return { anon: parsed.anon_key, service: parsed.service_role_key, jwtSecret: parsed.jwt_secret }
}

async function loadTenant(name: string, ref: string): Promise<TenantConfig | null> {
  if (!REF_PATTERN.test(ref) || !NAME_PATTERN.test(name)) return null
  const path = `${TENANTS_DIR}/${name}.json`
  let anon: string, service: string, jwtSecret: string
  try {
    const info = await Deno.lstat(path)
    if (!info.isFile || info.isSymlink || info.size > 65536) return null
    ;({ anon, service, jwtSecret } = parseTenantConfig(await Deno.readTextFile(path), name, ref))
  } catch {
    return null
  }

  const env: Record<string, string> = {
    SUPABASE_URL: `http://supabase-nginx-${name}:8080`,
    SUPABASE_ANON_KEY: anon,
    SUPABASE_SERVICE_ROLE_KEY: service,
    JWT_SECRET: jwtSecret,
    PROJECT_REF: ref,
    TECHNICAL_PROJECT_NAME: name,
  }

  return { env, jwtSecret }
}

function resolveRef(req: Request, url: URL): string | null {
  // The tenant gateway supplies this fixed identity, never query/body aliases.
  if (url.searchParams.has('ref') || url.searchParams.has('name')) return null
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
  const name = req.headers.get('x-project-name')
  if (!name || !NAME_PATTERN.test(name)) return new Response(JSON.stringify({ msg: 'canonical technical identity required' }), { status: 400 })
  const tenant = await loadTenant(name, ref)
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
      forceCreate: true,
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
