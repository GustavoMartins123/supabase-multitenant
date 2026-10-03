'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const patch = fs.readFileSync(
  path.join(__dirname, '../../studio/studio-slug/studio-project-context.patch'), 'utf8'
)
const assignments = [...patch.matchAll(/^\+\s+const (\w+) = (new URL\(.+, baseUrl\))$/gm)]
assert.equal(assignments.length, 7)

for (const [, variable, expression] of assignments) {
  const create = new Function('baseUrl', 'uuid', `return ${expression}`)
  for (const base of ['https://nginx:443/_internal/logflare/api/']) {
    const url = create(base, 'backend-id')
    assert.equal(url.origin, 'https://nginx')
    assert.match(url.pathname, /^\/_internal\/logflare\/api\/(backends|sources|rules)(\/backend-id)?$/)
  }
}

console.log('Studio log-drain URLs preserve the internal gateway prefix')
