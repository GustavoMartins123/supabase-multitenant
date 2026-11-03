// Permissions are enforced by the runtime for fetch, sockets and module loading.
export function externalNetworkHosts(value: unknown = []): string[] {
  if (!Array.isArray(value) || value.length > 32) throw new Error('Invalid function network policy')
  const hosts = value.map((entry) => {
    if (typeof entry !== 'string' || entry !== entry.trim().toLowerCase() || /[\s*%\\/@?#]/.test(entry)) {
      throw new Error('Invalid function network destination')
    }
    const parsed = new URL(`tcp://${entry}`)
    const host = parsed.hostname
    const port = Number(parsed.port)
    if (!host || !parsed.port || port < 1 || port > 65535 || String(port) !== parsed.port ||
        parsed.host !== entry || parsed.pathname || host === 'localhost' ||
        /\.(localhost|local|internal|test|invalid)$/.test(host)) {
      throw new Error('Invalid function network destination')
    }
    if (host.startsWith('[')) {
      if (!/^\[[23][0-9a-f]{3}:/.test(host) || /^\[2001:db8:/.test(host)) {
        throw new Error('Nonpublic function network destination')
      }
    } else if (/^[0-9.]+$/.test(host)) {
      const [a, b, c] = host.split('.').map(Number)
      if (host.split('.').length !== 4 || host.split('.').some(part => Number(part) > 255) ||
          a === 0 || a === 10 || a === 127 || a >= 224 ||
          (a === 100 && b >= 64 && b <= 127) || (a === 169 && b === 254) ||
          (a === 172 && b >= 16 && b <= 31) || (a === 192 && (b === 168 || b === 0)) ||
          (a === 198 && (b === 18 || b === 19 || (b === 51 && c === 100))) ||
          (a === 203 && b === 0 && c === 113)) throw new Error('Nonpublic function network destination')
    } else if (!/^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/.test(host)) {
      throw new Error('Invalid external function API domain')
    }
    return entry
  })
  if (new Set(hosts).size !== hosts.length || [...hosts].sort().join(',') !== hosts.join(',')) {
    throw new Error('Noncanonical function network policy')
  }
  return hosts
}

const pinned = new Map<string, string[]>()
let pinning: Promise<void> = Promise.resolve()

function publicAddress(address: string) {
  if (!/^[0-9.]+$/.test(address) && !address.includes(':')) throw new Error('Invalid DNS address')
  externalNetworkHosts([`${address.includes(':') ? `[${address}]` : address}:443`])
  if (/^200[12]:/i.test(address) &&
      (/^2002:/i.test(address) || parseInt(address.split(':')[1] || '0', 16) < 0x200)) {
    throw new Error('Nonpublic DNS address')
  }
}

async function pinNetworkHosts(approved: string[]) {
  const operation = pinning.then(async () => {
    for (const entry of approved) {
      const host = new URL(`tcp://${entry}`).hostname
      if (/^[0-9.]+$/.test(host) || host.startsWith('[')) continue
      const text = await Deno.readTextFile('/etc/hosts')
      if (text.length > 1_048_576) throw new Error('Functions DNS map exceeds its limit')
      const existing = text.split('\n').map(line => line.split('#')[0].trim().split(/\s+/))
        .filter(parts => parts.slice(1).includes(host)).map(parts => parts[0])
      for (const address of existing) publicAddress(address)
      if (pinned.has(host) && existing.length > 0) continue
      const answers = await Promise.allSettled([Deno.resolveDns(host, 'A'), Deno.resolveDns(host, 'AAAA')])
      const addresses = [...new Set(answers.flatMap(answer => answer.status === 'fulfilled' ? answer.value : []))].sort()
      if (addresses.length === 0) throw new Error('External function API DNS is unavailable')
      for (const address of addresses) publicAddress(address)
      // Pin before module loading or worker creation. Workers cannot access this
      // file through their virtual filesystem or obtain write permission to it.
      const additions = addresses.filter(address => !existing.includes(address))
      if (additions.length > 0) {
        await Deno.writeTextFile('/etc/hosts', '\n' + additions.map(address => `${address} ${host}\n`).join(''), { append: true })
      }
      const persisted = await Deno.readTextFile('/etc/hosts')
      if (addresses.some(address => !persisted.split('\n').some(line => line.trim() === `${address} ${host}`))) {
        throw new Error('Function API DNS pins could not be persisted')
      }
      pinned.set(host, addresses)
    }
  })
  pinning = operation.then(() => {}, () => {})
  await operation
}

export async function workerPermissions(project: string, external: unknown = [], databaseUrl?: string) {
  if (!/^[a-z_][a-z0-9_]{2,39}$/.test(project)) throw new Error('Invalid function project')
  const approved = externalNetworkHosts(external)
  await pinNetworkHosts(approved)
  const gateway = `supabase-nginx-${project}:8080`
  const allowNet = [gateway, ...approved]
  if (databaseUrl) {
    const database = new URL(databaseUrl)
    if (!['postgres:', 'postgresql:'].includes(database.protocol) || !database.hostname ||
        database.pathname !== `/_supabase_${project}`) throw new Error('Invalid function database identity')
    allowNet.push(`${database.hostname}:${database.port || '5432'}`)
  }
  return {
    allow_net: [...new Set(allowNet)],
    allow_import: [gateway, ...approved],
    allow_env: [],
    allow_read: [],
    allow_write: ['/tmp'],
    deny_run: [],
    deny_ffi: [],
    allow_sys: ['hostname'],
  }
}
