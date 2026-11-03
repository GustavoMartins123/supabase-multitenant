import { readFileSync, writeFileSync } from 'node:fs'

for (const name of ['app.js', 'admin-app.js']) {
  const file = `/usr/src/app/dist/server/${name}`
  const original = readFileSync(file, 'utf8')
  const anchor = '    Sentry.setupFastifyErrorHandler(app);'
  if (original.split(anchor).length !== 2 || original.includes('authenticateMetadataRequest')) {
    throw new Error(`Unsupported upstream metadata initialization: ${name}`)
  }
  const source = "import { authenticateMetadataRequest } from '../../security/internal-auth.mjs';\n" + original.replace(
    anchor,
    "    app.addHook('onRequest', authenticateMetadataRequest);\n" + anchor
  )
  writeFileSync(file, source)
}
