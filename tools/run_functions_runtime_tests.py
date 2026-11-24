"""Exercise Edge Functions runtime streaming, CORS, waitUntil, internal services, deno.json and limits."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

import httpx


CANARY_AND_AUTH = r'''
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AUTH_TOKENS = json.loads(Path('/fixture/auth_tokens.json').read_text())

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle()
    def do_POST(self):
        self._handle()
    def _record_and_ok(self, service):
        entry = {
            'service': service,
            'method': self.command,
            'path': self.path,
            'host': self.headers.get('Host', ''),
            'has_auth': bool(self.headers.get('Authorization', '')),
            'auth_prefix': self.headers.get('Authorization', '')[:16],
        }
        with Path('/fixture/hits.jsonl').open('a') as stream:
            stream.write(json.dumps(entry) + '\n')
        payload = json.dumps({'service': service, 'path': self.path, 'ok': True}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle(self):
        target = self.headers.get('X-Target-Service', '')
        if self.path.startswith('/v1/authorize') or self.path.startswith('/v1/functions-authorize'):
            project = self.headers.get('X-Project-Ref', '')
            api_key = self.headers.get('X-Api-Key-Header', '')
            expected = AUTH_TOKENS.get(project, {})
            valid = expected and api_key in {
                expected.get('anon'), expected.get('service_role'),
                expected.get('fn_anon'), expected.get('fn_service_role'),
            }
            if self.path.startswith('/v1/functions-authorize') and api_key not in {
                expected.get('fn_anon'), expected.get('fn_service_role'),
            }:
                valid = False
            uri = self.headers.get('X-Gateway-Request-URI', '') or self.headers.get('X-Admission-URI', '')
            is_public_webhook = target == 'functions' and (
                uri == '/functions/v1/webhook' or uri.startswith('/functions/v1/webhook/') or '/functions/v1/webhook' in uri
            )
            if not api_key and is_public_webhook and not self.path.startswith('/v1/functions-authorize'):
                self.send_response(204)
                self.send_header('X-Opaque-Key-Present', '0')
                self.send_header('X-Opaque-Preserve-Authorization', '1')
                self.send_header('X-Opaque-Keyset-Version', '1')
                self.end_headers()
                return
            if not valid:
                self.send_response(403)
                self.end_headers()
                return
            role = 'service_role' if api_key in {expected.get('service_role'), expected.get('fn_service_role')} else 'anon'
            orig_auth = self.headers.get('X-Original-Authorization', '')
            preserve = '1' if (target in {'storage', 'functions'} and orig_auth.startswith('Bearer ') and orig_auth.split(' ', 1)[1] != api_key) else '0'
            self.send_response(204)
            self.send_header('X-Opaque-Key-Role', role)
            self.send_header('X-Opaque-Key-Present', '1')
            self.send_header('X-Opaque-Key-Id', '11111111-1111-4111-8111-111111111111')
            self.send_header('X-Opaque-Preserve-Authorization', preserve)
            self.send_header('X-Opaque-Keyset-Version', '1')
            self.end_headers()
            return
        if target or self.headers.get('X-Canary-Role'):
            svc = self.headers.get('X-Canary-Service', 'upstream')
            self._record_and_ok(svc)
            return
        self._record_and_ok(self.headers.get('X-Forwarded-Host', '') or 'upstream')

    def log_message(self, *args):
        pass

ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
'''

FUNCTIONS = {
    'stream/index.ts': '''
Deno.serve(() => {
  const enc = new TextEncoder()
  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(enc.encode('data: first\\n\\n'))
      await new Promise((r) => setTimeout(r, 350))
      controller.enqueue(enc.encode('data: second\\n\\n'))
      controller.close()
    },
  })
  return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
})
''',
    'slow/index.ts': '''
Deno.serve(async (req) => {
  const url = new URL(req.url)
  const delayMs = Number(url.searchParams.get('ms') ?? '900')
  const mode = url.searchParams.get('mode') ?? 'sleep'
  if (mode === 'tick') {
    let intervalId: number | undefined
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('data: open\\n\\n'))
        intervalId = setInterval(() => {
          try { controller.enqueue(new TextEncoder().encode('data: tick\\n\\n')) }
          catch { clearInterval(intervalId) }
        }, 120)
        setTimeout(() => {
          clearInterval(intervalId)
          try { controller.close() } catch {}
        }, delayMs)
      },
      cancel() { clearInterval(intervalId) },
    })
    return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
  }
  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(new TextEncoder().encode('data: open\\n\\n'))
      await new Promise((r) => setTimeout(r, delayMs))
      try { controller.close() } catch {}
    },
  })
  return new Response(stream, { headers: { 'content-type': 'text/event-stream' } })
})
''',
    'wait_until/index.ts': '''
Deno.serve(() => {
  const url = Deno.env.get('SUPABASE_URL')!
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  EdgeRuntime.waitUntil((async () => {
    await new Promise((r) => setTimeout(r, 200))
    const resp = await fetch(`${url}/rest/v1/wait_until_marker`, {
      method: 'POST',
      headers: { apikey: key, Authorization: `Bearer ${key}` },
    })
    await resp.body?.cancel()
  })())
  return Response.json({ scheduled: true })
})
''',
    'hold_bg/index.ts': '''
Deno.serve((req) => {
  const secs = Number(new URL(req.url).searchParams.get('secs') ?? '1.5')
  EdgeRuntime.waitUntil((async () => {
    await new Promise((r) => setTimeout(r, secs * 1000))
  })())
  return Response.json({ scheduled: true })
})
''',
    'internal_calls/index.ts': '''
Deno.serve(async (req) => {
  const url = Deno.env.get('SUPABASE_URL')!
  const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  const ref = Deno.env.get('PROJECT_REF')
  const headers = { apikey: key, Authorization: `Bearer ${key}` }
  const results: Record<string, number> = {}
  for (const [label, path] of [
    ['rest', '/rest/v1/items?select=*'],
    ['auth', '/auth/v1/user'],
    ['storage', '/storage/v1/bucket'],
  ]) {
    const res = await fetch(`${url}${path}`, { headers })
    await res.body?.cancel()
    results[label] = res.status
  }
  let crossTenantAllowed = false
  try {
    const bad = await fetch('http://supabase-nginx-test_beta:8080/rest/v1/items', { headers })
    await bad.body?.cancel()
    crossTenantAllowed = true
  } catch {
    crossTenantAllowed = false
  }
  const parsed = new URL(req.url)
  return Response.json({ ref, path: parsed.pathname, query: parsed.search, results, crossTenantAllowed })
})
''',
    'imported/deno.json': '{"imports":{"@local-helper":"./helper.ts"}}',
    'imported/helper.ts': 'export const marker = "from-local-import-map"',
    'imported/index.ts': '''
import { marker } from '@local-helper'
Deno.serve(() => Response.json({ marker }))
''',
    'remote_import/index.ts': '''
import { serve } from 'https://unapproved.example.com/mod.ts'
serve(() => Response.json({ ok: true }))
''',
    'check_env/index.ts': '''
Deno.serve(() => Response.json({
  webhookSecret: Deno.env.get('WEBHOOK_SECRET') ?? null,
  customToken: Deno.env.get('CUSTOM_API_TOKEN') ?? null,
  projectRef: Deno.env.get('PROJECT_REF') ?? null,
  supabaseUrl: Deno.env.get('SUPABASE_URL') ?? null,
}))
''',
    'webhook/index.ts': '''
Deno.serve(async (req) => {
  const payload = req.method === 'POST' ? await req.text() : ''
  return Response.json({
    ok: true,
    method: req.method,
    sig: req.headers.get('stripe-signature'),
    auth: req.headers.get('authorization'),
    payload,
  })
})
''',
    'log_test/index.ts': '''
Deno.serve(() => {
  console.log('worker-log-entry', Deno.env.get('WEBHOOK_SECRET') ?? '')
  console.warn('worker-warn-bearer Bearer live-bearer-secret-999')
  console.error('worker-error-secret', 'sec_alpha_999', 'token', Deno.env.get('CUSTOM_API_TOKEN') ?? '')
  return Response.json({ logged: true })
})
''',
    'ws_wasm/add.wasm': bytes([
        0x00, 0x61, 0x73, 0x6D, 0x01, 0x00, 0x00, 0x00,
        0x01, 0x07, 0x01, 0x60, 0x02, 0x7F, 0x7F, 0x01, 0x7F,
        0x03, 0x02, 0x01, 0x00,
        0x07, 0x07, 0x01, 0x03, 0x61, 0x64, 0x64, 0x00, 0x00,
        0x0A, 0x09, 0x01, 0x07, 0x00, 0x20, 0x00, 0x20, 0x01, 0x6A, 0x0B,
    ]),
    'ws_wasm/index.ts': '''
import * as mod from './add.wasm'
Deno.serve((req) => {
  if (req.headers.get('upgrade')?.toLowerCase() === 'websocket') {
    const { socket, response } = Deno.upgradeWebSocket(req)
    socket.onmessage = (ev) => socket.send(`ws-wasm:${ev.data}:${mod.add(20, 22)}`)
    return response
  }
  return Response.json({ wasmSum: mod.add(20, 22) })
})
''',
    'npm_jsr/deno.json': '{"imports":{"ms":"npm:ms@2.1.3","@std/fmt/bytes":"jsr:@std/fmt@1/bytes"}}',
    'npm_jsr/index.ts': '''
import ms from 'ms'
import { format } from '@std/fmt/bytes'
Deno.serve(async () => {
  console.log('eszip-worker-log')
  let blockedRead = false
  try { await Deno.readTextFile('/etc/passwd') } catch { blockedRead = true }
  let blockedNet = false
  try { await fetch('https://example.com') } catch { blockedNet = true }
  return Response.json({
    ms: ms('1h'),
    fmt: format(2048),
    blockedRead,
    blockedNet,
  })
})
''',
    'priv_pkg/index.ts': '''
import privHello from 'npm:@priv/hello@1.0.0'
import { privJsr } from 'jsr:@pjsr/tool@1.0.0'
Deno.serve(async () => {
  let blockedNet = false
  try { await fetch('https://npmreg.internal:8443/npm/@priv/hello') } catch { blockedNet = true }
  const npmVal = typeof privHello === 'function' ? privHello() : privHello.default()
  return Response.json({
    npm: npmVal,
    jsr: privJsr(),
    blockedNet,
  })
})
''',
    'fs_scope/index.ts': '''
Deno.serve(async (req) => {
  const url = new URL(req.url)
  const denoCanary = url.searchParams.get('deno_canary') ?? '/var/cache/deno/edge01-canary'
  const otherTenant = url.searchParams.get('other_tenant') ?? ''
  const otherFn = url.searchParams.get('other_fn') ?? ''
  const oversizeMb = Number(url.searchParams.get('oversize_mb') ?? '6')
  const results: Record<string, string> = {}
  const attempt = async (name: string, fn: () => Promise<unknown>) => {
    try { await fn(); results[name] = 'allowed' } catch (error) { results[name] = `blocked:${(error as Error).name}` }
  }
  const canary = '/edge01-canary/canary'
  await attempt('read_etc_hostname', () => Deno.readTextFile('/etc/hostname'))
  await attempt('read_traversal_etc', () => Deno.readTextFile('/tmp/../etc/hostname'))
  await attempt('read_supervisor_deno_dir', () => Deno.readTextFile(denoCanary))
  if (otherTenant) {
    await attempt('read_other_tenant_code', () => Deno.readTextFile(otherTenant))
  }
  if (otherFn) {
    await attempt('read_other_function_code', () => Deno.readTextFile(otherFn))
  }
  await attempt('read_tenant_config', () => Deno.readTextFile('/home/deno/runtime/tenants/test_beta.json'))
  await attempt('read_symlink_etc', async () => {
    await Deno.symlink('/etc/hostname', '/tmp/esc-read')
    return await Deno.readTextFile('/tmp/esc-read')
  })
  await attempt('read_symlink_canary', async () => {
    await Deno.symlink(canary, '/tmp/esc-canary')
    return await Deno.readTextFile('/tmp/esc-canary')
  })
  await attempt('write_traversal_canary', () => Deno.writeTextFile('/tmp/../edge01-canary/canary', 'pwned'))
  await attempt('write_symlink_canary', async () => {
    await Deno.symlink(canary, '/tmp/esc-write')
    await Deno.writeTextFile('/tmp/esc-write', 'pwned')
  })
  await attempt('write_outside_tmp', () => Deno.writeTextFile('/edge01-canary/outside', 'x'))
  await attempt('read_private_tmp_before_write', () => Deno.readTextFile('/tmp/owned'))
  await attempt('write_private_tmp', () => Deno.writeTextFile('/tmp/owned', 'owned'))
  await attempt('read_private_tmp', () => Deno.readTextFile('/tmp/owned'))
  await attempt('temp_dir', () => Deno.makeTempDir())
  await attempt('tmp_within_quota', () => Deno.writeFile('/tmp/within', new Uint8Array(512 * 1024)))
  await attempt('tmp_oversize', () => Deno.writeFile('/tmp/oversize', new Uint8Array(oversizeMb * 1024 * 1024)))
  return Response.json(results)
})
''',
}


PRIVATE_REGISTRY_MOCK = r'''
import base64
import hashlib
import io
import json
import ssl
import tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TAR_BUF = io.BytesIO()
PKG_JSON = json.dumps({'name': '@priv/hello', 'version': '1.0.0', 'main': 'index.js'}).encode()
INDEX_JS = b'module.exports = function () { return "priv-npm:ok"; };\n'
with tarfile.open(fileobj=TAR_BUF, mode='w:gz') as tf:
    for rel, raw in (('package/package.json', PKG_JSON), ('package/index.js', INDEX_JS)):
        ti = tarfile.TarInfo(rel)
        ti.size = len(raw)
        ti.mode = 0o644
        tf.addfile(ti, io.BytesIO(raw))
TGZ_BYTES = TAR_BUF.getvalue()
TGZ_SHA1 = hashlib.sha1(TGZ_BYTES).hexdigest()
TGZ_SHA512 = base64.b64encode(hashlib.sha512(TGZ_BYTES).digest()).decode('ascii')

NPM_META = json.dumps({
    'name': '@priv/hello',
    'dist-tags': {'latest': '1.0.0'},
    'versions': {
        '1.0.0': {
            'name': '@priv/hello',
            'version': '1.0.0',
            'main': 'index.js',
            'dist': {
                'tarball': 'https://npmreg.internal:8443/npm/@priv/hello/-/hello-1.0.0.tgz',
                'shasum': TGZ_SHA1,
                'integrity': f'sha512-{TGZ_SHA512}',
            },
        },
    },
}).encode()

MOD_TS = b'export function privJsr(): string { return "priv-jsr:ok"; }\n'
MOD_SHA = hashlib.sha256(MOD_TS).hexdigest()
JSR_ROOT_META = json.dumps({'scope': 'pjsr', 'name': 'tool', 'latest': '1.0.0', 'versions': {'1.0.0': {}}}).encode()
JSR_VER_META = json.dumps({
    'manifest': {'/mod.ts': {'size': len(MOD_TS), 'checksum': f'sha256-{MOD_SHA}'}},
    'exports': {'.': './mod.ts'},
}).encode()

EXPECTED_BASIC = 'Basic ' + base64.b64encode(b'ci:basic-pass-123').decode('ascii')
EXPECTED_BEARER = 'Bearer jsr-tok-secret-456'

class RegHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        auth = self.headers.get('Authorization', '')
        path = self.path.split('?', 1)[0]
        if path.startswith('/npm/'):
            if auth != EXPECTED_BASIC:
                self._send(401, b'{"error":"unauthorized npm"}', 'application/json')
                return
            if path in ('/npm/@priv/hello', '/npm/@priv%2fhello', '/npm/@priv%2Fhello'):
                self._send(200, NPM_META, 'application/json')
                return
            if path == '/npm/@priv/hello/-/hello-1.0.0.tgz':
                self._send(200, TGZ_BYTES, 'application/octet-stream')
                return
        elif path.startswith('/@pjsr/'):
            if auth != EXPECTED_BEARER:
                self._send(401, b'{"error":"unauthorized jsr"}', 'application/json')
                return
            if path == '/@pjsr/tool/meta.json':
                self._send(200, JSR_ROOT_META, 'application/json')
                return
            if path == '/@pjsr/tool/1.0.0_meta.json':
                self._send(200, JSR_VER_META, 'application/json')
                return
            if path == '/@pjsr/tool/1.0.0/mod.ts':
                self._send(200, MOD_TS, 'application/typescript')
                return
        self._send(404, b'not found', 'text/plain')

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass

httpd = ThreadingHTTPServer(('0.0.0.0', 8443), RegHandler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.load_cert_chain('/fixture/privreg.crt', '/fixture/privreg.key')
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
httpd.serve_forever()
'''


def _generate_privreg_pki(out_dir: Path) -> str:
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'privreg-test-ca')])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'npmreg.internal')])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName('npmreg.internal'),
                x509.DNSName('jsrreg.internal'),
            ]),
            critical=False,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM).decode('ascii')
    (out_dir / 'privreg-ca.pem').write_text(ca_pem, encoding='utf-8')
    (out_dir / 'privreg.crt').write_text(srv_cert.public_bytes(serialization.Encoding.PEM).decode('ascii'), encoding='utf-8')
    (out_dir / 'privreg.key').write_text(
        srv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode('ascii'),
        encoding='utf-8',
    )
    for fname in ('privreg-ca.pem', 'privreg.crt', 'privreg.key'):
        (out_dir / fname).chmod(0o644)
    return ca_pem


def render_nginx_template(template: str, *, contract: str, project: str, identity: str,
                          public_ref: str, anon_key: str, service_role_key: str,
                          gateway_token: str, subnet: str) -> str:
    rendered = (template
        .replace('{{project_id}}', project)
        .replace('{{project_uuid}}', identity)
        .replace('{{public_base_url}}', 'http://localhost:3000')
        .replace('{{project_public_url}}', f'http://localhost:8000/{project}')
        .replace('{{project_public_ref}}', public_ref)
        .replace('{{server_url}}', 'localhost')
        .replace('${EDGE_FUNCTIONS_ENABLED}', 'true')
        .replace('${GRAPHQL_ENABLED}', 'false')
        .replace('${FILE_SIZE_LIMIT}', '50m')
        .replace('${ANON_KEY_PROJETO}', anon_key)
        .replace('${SERVICE_ROLE_KEY_PROJETO}', service_role_key)
        .replace('${API_GATEWAY_TOKEN_PROJETO}', gateway_token)
        .replace('${SUPABASE_NETWORK_SUBNET}', subnet)
        .replace('${PROJECT_INTERNAL_SUBNET}', subnet)
        .replace('${POSTGRES_POOLER}', 'supabase-pooler')
        .replace('${POOLER_PROXY_PORT_SESSION}', '5432')
        .replace('${POOLER_PROXY_PORT_TRANSACTION}', '6543'))
    rendered = rendered.replace(f'supabase-auth-{project}:9999', 'canary:8080')
    rendered = rendered.replace(f'supabase-rest-{project}:3000', 'canary:8080')
    rendered = rendered.replace('supabase-storage-global:5000', 'canary:8080')
    rendered = rendered.replace('key-authorizer:18010', 'canary:8080')
    if contract == 'versioned':
        rendered = rendered.replace('/etc/nginx/conf.d/keys.conf', '/tmp/nginx-conf/keys.conf')
    if '\npid ' not in rendered and not rendered.startswith('pid '):
        rendered = 'pid /tmp/nginx.pid;\n' + rendered
    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supervisor', type=Path, required=True)
    parser.add_argument('--template', type=Path, required=True)
    parser.add_argument('--contract', choices=('versioned', 'projected'), required=True)
    parser.add_argument('--edge-image', required=True)
    parser.add_argument('--nginx-image', default='nginxinc/nginx-unprivileged:1.31.7-alpine3.24-slim')
    parser.add_argument('--python-image', default='servidor-projects-api:latest')
    parser.add_argument('--bundler-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'servidor/edge-bundler')
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()

    prefix = f'functions-rt-test-{uuid.uuid4().hex[:8]}'
    network = prefix
    bundler_img = f'{prefix}-bundler'
    names: list[str] = []
    checks: list[str] = []
    built_bundler_img = False

    def docker(*command: str) -> str:
        return subprocess.check_output(['docker', *command], stderr=subprocess.PIPE, text=True).strip()

    def record(name: str) -> None:
        checks.append(name)
        print(f'{name}: passed', flush=True)

    def jwt_token(project: str, role: str) -> str:
        def enc(data: bytes) -> str:
            return base64.urlsafe_b64encode(data).rstrip(b'=').decode()
        signed = enc(b'{"alg":"HS256","typ":"JWT"}') + '.' + enc(json.dumps({'role': role, 'exp': int(time.time()) + 600}).encode())
        return signed + '.' + enc(hmac.new((project + '-synthetic-secret').encode(), signed.encode(), hashlib.sha256).digest())

    identities = {'test_alpha': '11111111-1111-4111-8111-111111111111',
                  'test_beta': '22222222-2222-4222-8222-222222222222'}
    refs = {'test_alpha': 'a' * 20, 'test_beta': 'b' * 20}
    internal_tokens = {
        p: {'anon': jwt_token(p, 'anon'), 'service_role': jwt_token(p, 'service_role'),
            'fn_anon': f'sb_publishable_fn_{p}_anon', 'fn_service_role': f'sb_secret_fn_{p}_svc',
            'gateway_token': hashlib.sha256(p.encode()).hexdigest()}
        for p in identities
    }

    with tempfile.TemporaryDirectory(prefix=prefix + '-') as temporary:
        fixture = Path(temporary)
        fixture.chmod(0o755)
        code = fixture / 'code'
        shutil.copytree(args.supervisor, code / 'main')
        for rel, content in FUNCTIONS.items():
            target = code / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding='utf-8')

        (fixture / 'canary.py').write_text(CANARY_AND_AUTH, encoding='utf-8')
        (fixture / 'privreg.py').write_text(PRIVATE_REGISTRY_MOCK, encoding='utf-8')
        privreg_ca_pem = _generate_privreg_pki(fixture)
        (fixture / 'auth_tokens.json').write_text(json.dumps(internal_tokens), encoding='utf-8')
        (fixture / 'hits.jsonl').write_text('', encoding='utf-8')
        (fixture / 'hits.jsonl').chmod(0o666)

        hosts = fixture / 'hosts'
        hosts.write_text('127.0.0.1 localhost\n::1 localhost\n', encoding='utf-8')
        hosts.chmod(0o666)

        config = fixture / 'config'
        config.mkdir()
        runtime = fixture / 'runtime'
        (runtime / 'tenants').mkdir(parents=True)

        (code / 'npm_jsr').chmod(0o755)
        docker('run', '--rm', '--user', f'{os.getuid()}:{os.getgid()}',
               '-e', 'HOME=/tmp', '-e', 'DENO_DIR=/tmp/deno',
               '-v', f"{code / 'npm_jsr'}:/work:rw", '-w', '/work',
               args.edge_image, 'bundle', '--entrypoint', '/work/index.ts', '--output', '/work/bundle.eszip')
        (code / 'npm_jsr' / 'bundle.eszip').chmod(0o644)

        for project, identity in identities.items():
            toks = internal_tokens[project]
            if args.contract == 'projected':
                (config / f'{project}.json').write_text(json.dumps({
                    'project_ref': refs[project], 'technical_name': project, 'project_uuid': identity,
                    'anon_key': toks['anon'], 'service_role_key': toks['service_role'],
                    'jwt_secret': f'{project}-synthetic-secret', 'network_allowlist': [],
                }))
                env_anon = toks['fn_anon']
                env_srv = toks['fn_service_role']
                code_root = runtime / 'code' / identity / ('1' * 64)
            else:
                env_anon = toks['anon']
                env_srv = toks['service_role']
                code_root = runtime / 'code' / project / ('1' * 64)
            code_root.mkdir(parents=True, exist_ok=True)
            for fn in ('stream', 'slow', 'wait_until', 'hold_bg', 'internal_calls', 'imported', 'remote_import', 'check_env', 'fs_scope', 'webhook', 'log_test', 'ws_wasm', 'npm_jsr', 'priv_pkg'):
                shutil.copytree(code / fn, code_root / fn)
            if project == 'test_alpha':
                alpha_code_root = code_root
            tenant_doc = {
                'project': project, 'uuid': identity, 'jwt_secret': f'{project}-synthetic-secret',
                'revision': '1' * 64, 'network_allowlist': [],
                'env': {
                    'SUPABASE_URL': f'http://supabase-nginx-{project}:8080',
                    'SUPABASE_PUBLIC_URL': 'http://localhost:8000',
                    'SUPABASE_ANON_KEY': env_anon,
                    'SUPABASE_SERVICE_ROLE_KEY': env_srv,
                    'SUPABASE_DB_URL': f'postgres://synthetic:synthetic@database:5432/_supabase_{project}',
                },
            }
            if project == 'test_alpha':
                tenant_doc['secrets'] = {'WEBHOOK_SECRET': 'sec_alpha_999', 'CUSTOM_API_TOKEN': 'tok_alpha_123'}
                tenant_doc['public_functions'] = ['webhook']
            (runtime / 'tenants' / f'{project}.json').write_text(json.dumps(tenant_doc))

        try:
            docker('network', 'create', '--label', 'functions.runtime-fixture=true', network)
            net_info = json.loads(docker('network', 'inspect', network))[0]
            subnet = net_info['IPAM']['Config'][0]['Subnet']

            docker('build', '-t', bundler_img, str(args.bundler_dir))
            built_bundler_img = True
            # The bundler refuses private addresses inside its own bridge subnets, so the mock shares the
            # bundler's network namespace and is reached over loopback through the bundler's test-only switch.
            bundler_hmac = 'runtime-test-bundler-hmac-secret'
            bundler_c = f'{prefix}-bundler'
            docker('run', '-d', '--name', bundler_c, '--network', network,
                   '--add-host', 'npmreg.internal:127.0.0.1', '--add-host', 'jsrreg.internal:127.0.0.1',
                   '-e', f'EDGE_BUNDLER_HMAC_SECRET={bundler_hmac}',
                   '-e', 'EDGE_BUNDLER_ALLOW_LOOPBACK_FOR_TESTS=1',
                   '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                   '--tmpfs', '/tmp:rw,noexec,nosuid,size=512m',
                   '-p', '127.0.0.1::18030', bundler_img)
            names.append(bundler_c)
            privreg_c = f'{prefix}-privreg'
            docker('run', '-d', '--name', privreg_c, '--network', f'container:{bundler_c}',
                   '-v', f'{fixture}:/fixture:ro', '--entrypoint', 'python',
                   args.python_image, '/fixture/privreg.py')
            names.append(privreg_c)
            for _ in range(50):
                ready = subprocess.run(
                    ['docker', 'exec', privreg_c, 'python', '-c',
                     "import socket; socket.create_connection(('127.0.0.1', 8443), timeout=0.5)"],
                    capture_output=True,
                )
                if ready.returncode == 0:
                    break
                time.sleep(0.1)
            else:
                raise RuntimeError('private registry TLS mock did not become ready')
            b_port = docker('inspect', '-f', '{{(index (index .NetworkSettings.Ports "18030/tcp") 0).HostPort}}', bundler_c)
            b_origin = f'http://127.0.0.1:{b_port}'

            with httpx.Client(trust_env=False, timeout=25) as bclient:
                for _ in range(50):
                    try:
                        if bclient.get(f'{b_origin}/healthz').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.15)
                else:
                    raise RuntimeError('edge-bundler container did not become healthy')

                def call_bundler(payload_obj: dict) -> httpx.Response:
                    raw = json.dumps(payload_obj, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
                    ts = str(int(time.time()))
                    sig = hmac.new(bundler_hmac.encode('utf-8'), f'{ts}.'.encode('ascii') + raw, hashlib.sha256).hexdigest()
                    return bclient.post(
                        f'{b_origin}/bundle',
                        content=raw,
                        headers={
                            'Content-Type': 'application/json',
                            'X-Edge-Bundler-Timestamp': ts,
                            'X-Edge-Bundler-Signature': sig,
                        },
                    )

                priv_files = [{'name': 'index.ts', 'content': FUNCTIONS['priv_pkg/index.ts']}]
                assert bclient.post(f'{b_origin}/bundle', json={'files': priv_files}).status_code == 401
                denied_ssrf = call_bundler({
                    'files': priv_files,
                    'registries': [{
                        'kind': 'npm', 'scope': '@priv', 'registry_url': 'https://npmreg.internal:8443/npm',
                        'auth_type': 'basic', 'token': 'ci:basic-pass-123', 'allow_private_network': False,
                    }],
                })
                assert denied_ssrf.status_code == 422, (denied_ssrf.status_code, denied_ssrf.text)

                missing_ca = call_bundler({
                    'files': priv_files,
                    'registries': [
                        {'kind': 'npm', 'scope': '@priv', 'registry_url': 'https://npmreg.internal:8443/npm',
                         'auth_type': 'basic', 'token': 'ci:basic-pass-123', 'allow_private_network': True},
                        {'kind': 'jsr', 'scope': '', 'registry_url': 'https://jsrreg.internal:8443',
                         'auth_type': 'bearer', 'token': 'jsr-tok-secret-456', 'allow_private_network': True},
                    ],
                })
                assert missing_ca.status_code == 422, (missing_ca.status_code, missing_ca.text)
                basic_b64 = base64.b64encode(b'ci:basic-pass-123').decode('ascii')
                for secret_piece in ('basic-pass-123', basic_b64, 'jsr-tok-secret-456'):
                    assert secret_piece not in missing_ca.text, f'Credential leaked in bundler error: {missing_ca.text}'

                built_ok = call_bundler({
                    'files': priv_files,
                    'registries': [
                        {'kind': 'npm', 'scope': '@priv', 'registry_url': 'https://npmreg.internal:8443/npm',
                         'auth_type': 'basic', 'token': 'ci:basic-pass-123', 'allow_private_network': True,
                         'ca_pem': privreg_ca_pem},
                        {'kind': 'jsr', 'scope': '', 'registry_url': 'https://jsrreg.internal:8443',
                         'auth_type': 'bearer', 'token': 'jsr-tok-secret-456', 'allow_private_network': True,
                         'ca_pem': privreg_ca_pem},
                    ],
                })
                assert built_ok.status_code == 200, (built_ok.status_code, built_ok.text)
                priv_eszip = base64.b64decode(built_ok.json()['eszip_b64'], validate=True)
                assert priv_eszip.startswith(b'ESZIP') and len(priv_eszip) > 100
                (alpha_code_root / 'priv_pkg' / 'bundle.eszip').write_bytes(priv_eszip)
                (alpha_code_root / 'priv_pkg' / 'bundle.eszip').chmod(0o644)

            docker('rm', '-f', '-v', bundler_c)
            docker('rm', '-f', '-v', privreg_c)
            names.remove(bundler_c)
            names.remove(privreg_c)

            nginx_dir = fixture / 'nginx-alpha'
            nginx_dir.mkdir(mode=0o755)
            nginx_dir.chmod(0o755)
            rendered_nginx = render_nginx_template(
                args.template.read_text(encoding='utf-8'),
                contract=args.contract,
                project='test_alpha',
                identity=identities['test_alpha'],
                public_ref=refs['test_alpha'],
                anon_key=internal_tokens['test_alpha']['anon'],
                service_role_key=internal_tokens['test_alpha']['service_role'],
                gateway_token=internal_tokens['test_alpha']['gateway_token'],
                subnet=subnet,
            )
            (nginx_dir / 'nginx.conf').write_text(rendered_nginx, encoding='utf-8')
            (nginx_dir / 'keys.conf').write_text(
                f'map $http_apikey $is_valid_key {{ default 0; "{internal_tokens["test_alpha"]["anon"]}" 1; "{internal_tokens["test_alpha"]["service_role"]}" 1; }}\n'
                f'map $http_apikey $is_admin_key {{ default 0; "{internal_tokens["test_alpha"]["service_role"]}" 1; }}\n'
                f'map $arg_apikey $is_valid_api_key {{ default 0; "{internal_tokens["test_alpha"]["anon"]}" 1; "{internal_tokens["test_alpha"]["service_role"]}" 1; }}\n'
                f'map $http_x_config_token $is_valid_config_token {{ default 0; "cfg" 1; }}\n'
                f'map "" $config_anon_key {{ default "{internal_tokens["test_alpha"]["anon"]}"; }}\n',
                encoding='utf-8',
            )
            (nginx_dir / 'nginx.conf').chmod(0o644)
            (nginx_dir / 'keys.conf').chmod(0o644)

            canary = f'{prefix}-canary'
            docker('run', '-d', '--name', canary, '--network', network,
                   '--network-alias', 'canary',
                   '--network-alias', 'supabase-nginx-test_beta',
                   '--network-alias', 'unapproved.example.com',
                   '-v', f'{fixture}:/fixture:rw', '--entrypoint', 'python',
                   args.python_image, '/fixture/canary.py')
            names.append(canary)

            runtime_c = f'{prefix}-runtime'
            rt_cmd = [
                'run', '-d', '--name', runtime_c, '--network', network,
                '--network-alias', 'functions', '--network-alias', 'supabase-edge-functions-global',
                '-e', 'DENO_DIR=/var/cache/deno', '-e', 'VERIFY_JWT=true',
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--tmpfs', '/tmp:rw,noexec,nosuid,size=128m',
                '--tmpfs', '/var/cache/deno:rw,noexec,nosuid,size=128m',
                '--tmpfs', '/edge01-canary:rw,nosuid,size=1m',
                '-v', f'{hosts}:/etc/hosts:rw',
                '-v', f'{code / "main"}:/home/deno/main:ro',
                '-v', f'{runtime}:/home/deno/runtime:ro',
                '-p', '127.0.0.1::9000',
            ]
            if args.contract == 'projected':
                rt_cmd += ['-v', f'{config}:/home/deno/tenant-config:ro']
            rt_cmd += [args.edge_image, 'start', '--main-service', '/home/deno/main', '--event-worker', '/home/deno/main/event-worker']
            docker(*rt_cmd)
            names.append(runtime_c)

            nginx_c = f'{prefix}-nginx'
            docker('run', '-d', '--name', nginx_c, '--network', network,
                   '--network-alias', 'supabase-nginx-test_alpha',
                   '-v', f'{nginx_dir}:/tmp/nginx-conf:ro',
                   '-v', f'{nginx_dir / "nginx.conf"}:/etc/nginx/nginx.conf:ro',
                   '-p', '127.0.0.1::8080',
                   args.nginx_image)
            names.append(nginx_c)

            nginx_test = subprocess.run(
                ['docker', 'exec', nginx_c, 'nginx', '-t'],
                capture_output=True, text=True,
            )
            if nginx_test.returncode != 0:
                logs = subprocess.run(['docker', 'logs', nginx_c], capture_output=True, text=True).stdout
                raise RuntimeError(f'nginx -t failed ({nginx_test.returncode}): {nginx_test.stderr}\n{logs}')
            record('nginx_template_syntax_ok')

            rt_port = docker('inspect', '-f', '{{(index (index .NetworkSettings.Ports "9000/tcp") 0).HostPort}}', runtime_c)
            nx_port = docker('inspect', '-f', '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostPort}}', nginx_c)
            nginx_origin = f'http://127.0.0.1:{nx_port}'
            rt_origin = f'http://127.0.0.1:{rt_port}'

            with httpx.Client(trust_env=False, timeout=10) as client:
                for _ in range(50):
                    try:
                        if client.get(f'{rt_origin}/__health').status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.15)
                else:
                    raise RuntimeError('edge runtime did not become healthy')

                def gw_headers(path: str, method: str = 'GET', origin: str = 'http://localhost:3000', svc: bool = False) -> dict[str, str]:
                    key = internal_tokens['test_alpha']['service_role' if svc else 'anon']
                    hdr = {'apikey': key, 'Authorization': 'Bearer ' + key}
                    if origin:
                        hdr['Origin'] = origin
                    if args.contract == 'projected':
                        hdr['X-Gateway-Admission'] = 'a' * 43
                        hdr['X-Admission-URI'] = f'/{refs["test_alpha"]}{path}'
                        hdr['X-Admission-Method'] = method
                    return hdr

                # 1. CORS OPTIONS preflight & error headers
                preflight = client.options(
                    f'{nginx_origin}/functions/v1/stream',
                    headers={'Origin': 'http://localhost:3000', 'Access-Control-Request-Headers': 'Authorization, apikey, X-Client-Info'},
                )
                assert preflight.status_code == 204, preflight.text
                assert preflight.headers.get('access-control-allow-origin') == 'http://localhost:3000'
                allow_hdrs = preflight.headers.get('access-control-allow-headers', '').lower()
                assert 'x-client-info' in allow_hdrs and 'x-supabase-auth' in allow_hdrs, allow_hdrs
                assert 'head' in preflight.headers.get('access-control-allow-methods', '').lower()
                record('cors_preflight_headers')

                disallowed = client.get(
                    f'{nginx_origin}/functions/v1/imported',
                    headers=gw_headers('/functions/v1/imported', origin='https://evil.example.com'),
                )
                assert disallowed.status_code == 200, disallowed.text
                assert 'access-control-allow-origin' not in disallowed.headers
                record('cors_disallowed_origin_rejected')

                # 2. SSE unbuffered streaming across real nginx + edge-runtime
                t0 = time.monotonic()
                chunk_times: list[tuple[float, str]] = []
                with client.stream('GET', f'{nginx_origin}/functions/v1/stream', headers=gw_headers('/functions/v1/stream')) as resp:
                    assert resp.status_code == 200, resp.read()
                    assert 'text/event-stream' in resp.headers.get('content-type', '')
                    assert resp.headers.get('access-control-allow-origin') == 'http://localhost:3000'
                    for line in resp.iter_lines():
                        if line:
                            chunk_times.append((time.monotonic() - t0, line))
                assert len(chunk_times) == 2, chunk_times
                assert chunk_times[1][0] - chunk_times[0][0] >= 0.25, chunk_times
                record('sse_streaming_unbuffered_through_nginx')

                # 3. EdgeRuntime.waitUntil finishes asynchronously after 200 response
                (fixture / 'hits.jsonl').write_text('')
                t_start = time.monotonic()
                wu = client.get(f'{nginx_origin}/functions/v1/wait_until', headers=gw_headers('/functions/v1/wait_until'))
                elapsed = time.monotonic() - t_start
                assert wu.status_code == 200 and wu.json()['scheduled'] is True, wu.text
                assert elapsed < 0.25, f'waitUntil blocked HTTP response ({elapsed:.3f}s)'
                for _ in range(25):
                    hits = (fixture / 'hits.jsonl').read_text()
                    if '/wait_until_marker' in hits:
                        break
                    time.sleep(0.05)
                assert '/wait_until_marker' in (fixture / 'hits.jsonl').read_text(), 'waitUntil task never hit backend'
                record('edge_runtime_wait_until_completes')

                # 4. Internal calls to REST + Auth + Storage & cross-tenant isolation
                ic = client.get(
                    f'{nginx_origin}/functions/v1/internal_calls/sub/route?alpha=1',
                    headers=gw_headers('/functions/v1/internal_calls/sub/route?alpha=1'),
                )
                assert ic.status_code == 200, ic.text
                payload = ic.json()
                assert payload['path'] == '/internal_calls/sub/route', payload
                assert payload['query'] == '?alpha=1', payload
                assert payload['results'] == {'rest': 200, 'auth': 200, 'storage': 200}, payload
                assert payload['crossTenantAllowed'] is False, payload
                record('internal_rest_auth_storage_and_isolation')

                # 5. deno.json local import map works; unapproved remote import fails closed cleanly
                imp = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                assert imp.status_code == 200 and imp.json()['marker'] == 'from-local-import-map', imp.text
                (fixture / 'hits.jsonl').write_text('')
                rem = client.get(f'{nginx_origin}/functions/v1/remote_import', headers=gw_headers('/functions/v1/remote_import'))
                assert rem.status_code == 500 and rem.json() == {'code': 'function_execution_failed'}, rem.text
                assert 'unapproved.example.com' not in (fixture / 'hits.jsonl').read_text()
                record('deno_json_import_map_and_offline_boundary')

                # 6. SSE client cancellation releases concurrency slots before stream timeout
                with client.stream('GET', f'{nginx_origin}/functions/v1/slow?ms=4000&mode=tick', headers=gw_headers('/functions/v1/slow?ms=4000&mode=tick')) as s1:
                    next(s1.iter_lines())
                with client.stream('GET', f'{nginx_origin}/functions/v1/slow?ms=4000&mode=tick', headers=gw_headers('/functions/v1/slow?ms=4000&mode=tick')) as s2:
                    next(s2.iter_lines())
                time.sleep(0.35)
                after_cancel = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                assert after_cancel.status_code == 200, after_cancel.text
                record('sse_client_cancel_releases_concurrency')

                # 7. Per-project concurrency (2), bounded admission queue and slot recovery
                codes: list[int] = []

                def slow_alpha():
                    r = client.get(f'{nginx_origin}/functions/v1/slow?ms=700', headers=gw_headers('/functions/v1/slow?ms=700'))
                    codes.append(r.status_code)

                threads = [threading.Thread(target=slow_alpha), threading.Thread(target=slow_alpha)]
                for t in threads:
                    t.start()
                time.sleep(0.18)
                beta_hdrs = {
                    'apikey': internal_tokens['test_beta']['anon'],
                    'Authorization': 'Bearer ' + internal_tokens['test_beta']['anon'],
                    'X-Project-Name': 'test_beta',
                    'X-Project-Ref': refs['test_beta'],
                    'X-Project-UUID': identities['test_beta'],
                }
                # beta still has capacity on supervisor directly
                beta_ok = client.get(f'{rt_origin}/imported', headers=beta_hdrs)
                assert beta_ok.status_code == 200, beta_ok.text
                # The third alpha request waits in the bounded queue and runs as soon as a slot frees.
                queued_t0 = time.monotonic()
                third_alpha = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                queued_for = time.monotonic() - queued_t0
                assert third_alpha.status_code == 200 and queued_for > 0.35, (third_alpha.status_code, queued_for, third_alpha.text)
                assert third_alpha.headers.get('access-control-allow-origin') == 'http://localhost:3000'
                for t in threads:
                    t.join()
                assert codes == [200, 200], codes
                # Slots freed after slow requests end
                recovered = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                assert recovered.status_code == 200, recovered.text
                record('concurrency_queue_waits_then_serves')
                failures: list[BaseException] = []

                def guarded(target):
                    def run(*args):
                        try:
                            target(*args)
                        except BaseException as exc:
                            failures.append(exc)
                    return run

                def settle():
                    time.sleep(0.6)

                # 7b. The queue is bounded: once it is full, one more request is rejected at once
                settle()
                waiting = 16
                burst: list[tuple[int, str]] = []

                def burst_alpha(path: str):
                    with httpx.Client(trust_env=False, timeout=30) as own:
                        r = own.get(f'{nginx_origin}/functions/v1/{path}', headers=gw_headers(f'/functions/v1/{path}'))
                    burst.append((r.status_code, r.headers.get('retry-after')))

                runners = [threading.Thread(target=guarded(burst_alpha), args=('slow?ms=2500',)) for _ in range(2)]
                for t in runners:
                    t.start()
                time.sleep(0.5)
                waiters = [threading.Thread(target=guarded(burst_alpha), args=('imported',)) for _ in range(waiting)]
                for t in waiters:
                    t.start()
                time.sleep(0.7)
                # A request that is queued instead of rejected would be served later; never abandon it here.
                overflow_t0 = time.monotonic()
                overflow = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'), timeout=20.0)
                overflow_for = time.monotonic() - overflow_t0
                assert overflow.status_code == 429 and overflow.json()['code'] == 'function_concurrency_limit', (overflow.status_code, overflow.text)
                assert overflow.headers.get('retry-after') == '1' and overflow_for < 0.4, (overflow.headers, overflow_for)
                assert overflow.headers.get('access-control-allow-origin') == 'http://localhost:3000'
                for t in runners + waiters:
                    t.join()
                assert not failures, failures
                assert sorted(code for code, _ in burst) == [200] * (2 + waiting), burst
                record('concurrency_queue_overflow_rejected')

                # 7c. A background task (waitUntil) keeps its slot until it finishes
                settle()
                for _ in range(2):
                    background = client.get(f'{nginx_origin}/functions/v1/hold_bg?secs=1.5', headers=gw_headers('/functions/v1/hold_bg?secs=1.5'))
                    assert background.status_code == 200 and background.json()['scheduled'] is True, background.text
                held_codes: list[int] = []

                def fast_alpha():
                    with httpx.Client(trust_env=False, timeout=10) as own:
                        held_codes.append(own.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported')).status_code)

                held_t0 = time.monotonic()
                held = [threading.Thread(target=guarded(fast_alpha)) for _ in range(2)]
                for t in held:
                    t.start()
                for t in held:
                    t.join()
                held_for = time.monotonic() - held_t0
                assert not failures, failures
                assert held_codes == [200, 200] and held_for > 1.0, (held_codes, held_for)
                record('background_task_holds_concurrency_slot')

                # 7d. Finished isolates are ended right away instead of piling up until the wall clock
                settle()
                served: list[int] = []

                def fast_burst(count: int):
                    with httpx.Client(trust_env=False, timeout=10) as own:
                        for _ in range(count):
                            served.append(own.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported')).status_code)

                # Two clients saturate the per-project concurrency cap (2) across 90 back-to-back requests.
                fast = [threading.Thread(target=guarded(fast_burst), args=(45,)) for _ in range(2)]
                for t in fast:
                    t.start()
                for t in fast:
                    t.join()
                assert not failures, failures
                assert served == [200] * 90, sorted(set(served))
                time.sleep(1.0)
                usage = docker('stats', '--no-stream', '--format', '{{.MemUsage}}', runtime_c).split('/')[0].strip()
                runtime_mib = float(''.join(ch for ch in usage if ch.isdigit() or ch == '.'))
                if usage.endswith('GiB'):
                    runtime_mib *= 1024
                assert runtime_mib < 350, f'runtime kept {usage} after 90 short requests; isolates are not being ended'
                record('finished_isolates_do_not_accumulate')

                # 8. Project-scoped secrets injection & cross-tenant isolation
                env_alpha = client.get(f'{nginx_origin}/functions/v1/check_env', headers=gw_headers('/functions/v1/check_env'))
                assert env_alpha.status_code == 200, env_alpha.text
                ea = env_alpha.json()
                assert ea['webhookSecret'] == 'sec_alpha_999' and ea['customToken'] == 'tok_alpha_123', ea
                assert ea['supabaseUrl'] == 'http://supabase-nginx-test_alpha:8080', ea
                env_beta = client.get(f'{rt_origin}/check_env', headers=beta_hdrs)
                assert env_beta.status_code == 200, env_beta.text
                eb = env_beta.json()
                assert eb['webhookSecret'] is None and eb['customToken'] is None, eb
                beta_ctx = runtime / 'tenants/test_beta.json'
                saved_beta = beta_ctx.read_text()
                try:
                    tampered = json.loads(saved_beta)
                    tampered['secrets'] = {'SUPABASE_URL': 'http://evil'}
                    beta_ctx.write_text(json.dumps(tampered))
                    bad_env = client.get(f'{rt_origin}/check_env', headers=beta_hdrs)
                    assert bad_env.status_code == 503, bad_env.text
                finally:
                    beta_ctx.write_text(saved_beta)
                record('project_secrets_injection_and_isolation')

                # 8b. Worker filesystem scope: private per-worker tmpfs, isolated DENO_DIR, no cross-tenant read/write escape
                canary_dir = '/edge01-canary'
                deno_canary = '/var/cache/deno/edge01-canary'
                docker('exec', runtime_c, 'sh', '-c',
                       f'printf host-canary > {canary_dir}/canary && printf deno-canary > {deno_canary}')
                alpha_seg = identities['test_alpha'] if args.contract == 'projected' else 'test_alpha'
                beta_seg = identities['test_beta'] if args.contract == 'projected' else 'test_beta'
                oversize_mb = '6' if args.contract == 'projected' else '11'
                fs_params = {
                    'deno_canary': deno_canary,
                    'other_tenant': f'/home/deno/runtime/code/{beta_seg}/{"1" * 64}/imported/index.ts',
                    'other_fn': f'/home/deno/runtime/code/{alpha_seg}/{"1" * 64}/imported/index.ts',
                    'oversize_mb': oversize_mb,
                }
                fs_query = '&'.join(f'{k}={v}' for k, v in fs_params.items())
                fs_scope = client.get(
                    f'{nginx_origin}/functions/v1/fs_scope?{fs_query}',
                    headers=gw_headers(f'/functions/v1/fs_scope?{fs_query}'),
                )
                assert fs_scope.status_code == 200, (fs_scope.status_code, fs_scope.text, '\n'.join(
                    l for l in subprocess.run(['docker', 'logs', '--tail', '400', runtime_c], capture_output=True, text=True).stderr.splitlines()
                    if 'early termination' not in l)[-3800:])
                fs_results = {k: v.split(':')[0] for k, v in fs_scope.json().items()}
                assert fs_results == {
                    'read_etc_hostname': 'blocked', 'read_traversal_etc': 'blocked',
                    'read_supervisor_deno_dir': 'blocked', 'read_other_tenant_code': 'blocked',
                    'read_other_function_code': 'blocked', 'read_tenant_config': 'blocked',
                    'read_symlink_etc': 'blocked', 'read_symlink_canary': 'blocked',
                    'write_traversal_canary': 'blocked', 'write_symlink_canary': 'blocked',
                    'write_outside_tmp': 'blocked', 'read_private_tmp_before_write': 'blocked',
                    'write_private_tmp': 'allowed', 'read_private_tmp': 'allowed', 'temp_dir': 'allowed',
                    'tmp_within_quota': 'allowed', 'tmp_oversize': 'blocked',
                }, fs_results
                # Nothing reached the real filesystem outside the worker's private tmpfs, and DENO_DIR stayed writable
                assert docker('exec', runtime_c, 'cat', f'{canary_dir}/canary') == 'host-canary'
                assert docker('exec', runtime_c, 'cat', deno_canary) == 'deno-canary'
                assert docker('exec', runtime_c, 'sh', '-c', f'ls {canary_dir}') == 'canary'
                assert docker('exec', runtime_c, 'sh', '-c', 'ls /tmp/owned /tmp/esc-read /tmp/within 2>/dev/null | wc -l') == '0'
                # Another tenant - and a later worker of the same tenant - get their own private tmpfs
                beta_fs_params = {
                    'deno_canary': deno_canary,
                    'other_tenant': f'/home/deno/runtime/code/{alpha_seg}/{"1" * 64}/imported/index.ts',
                    'other_fn': f'/home/deno/runtime/code/{beta_seg}/{"1" * 64}/imported/index.ts',
                    'oversize_mb': oversize_mb,
                }
                for fs_url, fs_headers in (
                    (f'{rt_origin}/fs_scope?{"&".join(f"{k}={v}" for k, v in beta_fs_params.items())}', beta_hdrs),
                    (f'{nginx_origin}/functions/v1/fs_scope?{fs_query}', gw_headers(f'/functions/v1/fs_scope?{fs_query}')),
                ):
                    other_fs = client.get(fs_url, headers=fs_headers)
                    assert other_fs.status_code == 200, other_fs.text
                    other_results = other_fs.json()
                    assert other_results['read_private_tmp_before_write'] == 'blocked:NotFound', other_results
                    assert other_results['read_other_tenant_code'].startswith('blocked'), other_results
                    assert other_results['read_symlink_canary'].startswith('blocked'), other_results
                    assert other_results['tmp_oversize'].startswith('blocked'), other_results
                record('worker_filesystem_scope_isolated')

                # 9. Per-function verify_jwt=false webhook admission & protected isolation
                wh_hdrs = {'Stripe-Signature': 't=1,v1=sig123'}
                if args.contract == 'projected':
                    wh_hdrs.update({
                        'X-Gateway-Admission': 'a' * 43,
                        'X-Admission-URI': f'/{refs["test_alpha"]}/functions/v1/webhook',
                        'X-Admission-Method': 'POST',
                    })
                wh = client.post(f'{nginx_origin}/functions/v1/webhook', content='{"event":"paid"}', headers=wh_hdrs)
                assert wh.status_code == 200, wh.text
                assert wh.json()['sig'] == 't=1,v1=sig123' and wh.json()['payload'] == '{"event":"paid"}', wh.json()
                wh_custom = client.post(
                    f'{nginx_origin}/functions/v1/webhook',
                    content='ok',
                    headers={**gw_headers('/functions/v1/webhook', method='POST'), 'Authorization': 'Bearer external-provider-token'},
                )
                assert wh_custom.status_code == 200 and wh_custom.json()['auth'] == 'Bearer external-provider-token', wh_custom.text
                forged = client.post(f'{nginx_origin}/functions/v1/webhook', headers={**wh_hdrs, 'apikey': 'forged-bad-key'})
                assert forged.status_code == 403, forged.text
                prot = client.get(f'{nginx_origin}/functions/v1/imported', headers={
                    k: v for k, v in gw_headers('/functions/v1/imported').items() if k not in {'apikey', 'Authorization'}
                })
                assert prot.status_code in {401, 403}, prot.text
                beta_anon = client.post(f'{rt_origin}/webhook', headers={
                    'X-Project-Name': 'test_beta', 'X-Project-Ref': refs['test_beta'], 'X-Project-UUID': identities['test_beta'],
                })
                assert beta_anon.status_code in {401, 403}, beta_anon.text
                for internal_path in ('__logs', '__event-ingest', '__health', '%5F%5Flogs'):
                    internal = client.get(f'{nginx_origin}/functions/v1/{internal_path}', headers=gw_headers('/functions/v1/x'))
                    assert internal.status_code == 404, (internal_path, internal.status_code, internal.text)
                record('per_function_verify_jwt_webhook_and_isolation')

                # 10. Event worker console/boot capture, HMAC logs endpoint & redaction
                def logs_headers(project: str) -> dict[str, str]:
                    ts = str(int(time.time()))
                    ident = identities[project]
                    ref = refs[project]
                    secret = f'{project}-synthetic-secret'
                    if args.contract == 'projected':
                        payload = f'edge-logs-v1\n{project}\n{ident}\n{ref}\n{ts}'.encode('utf-8')
                        hdrs = {'X-Project-Name': project, 'X-Project-Ref': ref}
                    else:
                        payload = f'edge-logs-v1\n{project}\n{ident}\n{ts}'.encode('utf-8')
                        hdrs = {'X-Project-Name': project, 'X-Project-UUID': ident}
                    sig = hmac.new(secret.encode('utf-8'), payload, hashlib.sha256).hexdigest()
                    hdrs['X-Logs-Timestamp'] = ts
                    hdrs['X-Logs-Signature'] = sig
                    return hdrs

                logged = client.get(f'{nginx_origin}/functions/v1/log_test', headers=gw_headers('/functions/v1/log_test'))
                assert logged.status_code == 200 and logged.json().get('logged') is True, logged.text

                alpha_logs: list[dict] = []
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    lr = client.get(f'{rt_origin}/__logs', params={'function': 'log_test', 'limit': '50'}, headers=logs_headers('test_alpha'))
                    assert lr.status_code == 200, lr.text
                    alpha_logs = lr.json()['logs']
                    if any(e.get('source') == 'worker' and 'worker-log-entry' in e.get('message', '') for e in alpha_logs):
                        break
                    time.sleep(0.2)

                worker_msgs = [e for e in alpha_logs if e.get('source') == 'worker']
                assert any('worker-log-entry' in e.get('message', '') for e in worker_msgs), alpha_logs
                assert any(e.get('level') == 'warn' and 'worker-warn-bearer' in e.get('message', '') for e in worker_msgs), alpha_logs
                assert any(e.get('level') == 'error' and 'worker-error-secret' in e.get('message', '') for e in worker_msgs), alpha_logs
                joined_msgs = '\n'.join(e.get('message', '') for e in alpha_logs)
                for secret_val in ('sec_alpha_999', 'tok_alpha_123', 'live-bearer-secret-999', 'test_alpha-synthetic-secret'):
                    assert secret_val not in joined_msgs, f'Secret {secret_val} leaked in logs: {joined_msgs}'
                assert '[REDACTED]' in joined_msgs, joined_msgs

                # Reject forged /__logs signature, forwarded headers, external /__event-ingest, and keep beta isolated
                bad_sig = logs_headers('test_alpha')
                bad_sig['X-Logs-Signature'] = '0' * 64
                assert client.get(f'{rt_origin}/__logs', headers=bad_sig).status_code == 403
                assert client.get(f'{rt_origin}/__logs', headers={**logs_headers('test_alpha'), 'X-Forwarded-For': '1.2.3.4'}).status_code == 403
                assert client.post(f'{rt_origin}/__event-ingest', json={'event_type': 'Log'}, headers={'X-Event-Token': '0' * 64}).status_code == 403
                assert client.get(f'{rt_origin}/__logs', params={'function': 'log_test'}, headers=logs_headers('test_beta')).json()['logs'] == []
                record('event_worker_logs_and_redaction')

                # 11. Pre-bundled npm:/jsr: ESZIP executes offline with permissions and event-worker logs
                eszip_res = client.get(f'{nginx_origin}/functions/v1/npm_jsr', headers=gw_headers('/functions/v1/npm_jsr'))
                assert eszip_res.status_code == 200, eszip_res.text
                ep = eszip_res.json()
                assert ep == {'ms': 3600000, 'fmt': '2.05 kB', 'blockedRead': True, 'blockedNet': True}, ep
                eszip_logs: list[dict] = []
                deadline = time.time() + 5.0
                while time.time() < deadline:
                    lr = client.get(f'{rt_origin}/__logs', params={'function': 'npm_jsr', 'limit': '20'}, headers=logs_headers('test_alpha'))
                    if lr.status_code == 200 and any('eszip-worker-log' in e.get('message', '') for e in lr.json()['logs']):
                        eszip_logs = lr.json()['logs']
                        break
                    time.sleep(0.2)
                assert any('eszip-worker-log' in e.get('message', '') for e in eszip_logs), eszip_logs
                record('npm_jsr_eszip_offline_execution')

                # 12. Private authenticated npm (Basic + subpath + @scope) & JSR (Bearer + custom CA TLS) via edge-bundler -> offline ESZIP execution
                priv_res = client.get(f'{nginx_origin}/functions/v1/priv_pkg', headers=gw_headers('/functions/v1/priv_pkg'))
                assert priv_res.status_code == 200, priv_res.text
                pp = priv_res.json()
                assert pp == {'npm': 'priv-npm:ok', 'jsr': 'priv-jsr:ok', 'blockedNet': True}, pp
                record('private_registries_tls_custom_ca_bundler_and_offline_eszip')

                # 12b. Fake Upgrade: websocket requests to non-WebSocket functions must not lock concurrency slots
                settle()
                ws_sample_key = base64.b64encode(b'the sample nonce').decode('ascii')
                fake_ws_beta_partial = {**beta_hdrs, 'Upgrade': 'websocket'}
                fake_ws_beta_full = {
                    **beta_hdrs,
                    'Upgrade': 'websocket',
                    'Connection': 'Upgrade',
                    'Sec-WebSocket-Key': ws_sample_key,
                    'Sec-WebSocket-Version': '13',
                }
                for _ in range(2):
                    r_partial = client.get(f'{rt_origin}/imported', headers=fake_ws_beta_partial)
                    assert r_partial.status_code == 200, (r_partial.status_code, r_partial.text)
                for _ in range(2):
                    r_beta_full = client.get(f'{rt_origin}/imported', headers=fake_ws_beta_full)
                    assert r_beta_full.status_code != 101, (r_beta_full.status_code, r_beta_full.text)
                fake_ws_alpha_full = {
                    **gw_headers('/functions/v1/imported'),
                    'Upgrade': 'websocket',
                    'Connection': 'Upgrade',
                    'Sec-WebSocket-Key': ws_sample_key,
                    'Sec-WebSocket-Version': '13',
                }
                for _ in range(2):
                    r_alpha_full = client.get(f'{nginx_origin}/functions/v1/imported', headers=fake_ws_alpha_full)
                    assert r_alpha_full.status_code != 101, (r_alpha_full.status_code, r_alpha_full.text)
                time.sleep(0.5)
                post_fake_codes: list[int] = []

                def probe_after_fake(target_url: str, target_headers: dict[str, str]):
                    with httpx.Client(trust_env=False, timeout=5) as own:
                        post_fake_codes.append(own.get(target_url, headers=target_headers).status_code)

                post_fake_t0 = time.monotonic()
                post_fake_threads = [
                    threading.Thread(
                        target=guarded(probe_after_fake),
                        args=(f'{nginx_origin}/functions/v1/imported', gw_headers('/functions/v1/imported')),
                    )
                    for _ in range(2)
                ] + [
                    threading.Thread(target=guarded(probe_after_fake), args=(f'{rt_origin}/imported', beta_hdrs))
                    for _ in range(2)
                ]
                for t in post_fake_threads:
                    t.start()
                for t in post_fake_threads:
                    t.join()
                post_fake_elapsed = time.monotonic() - post_fake_t0
                assert not failures, failures
                assert post_fake_codes == [200, 200, 200, 200] and post_fake_elapsed < 1.5, (
                    post_fake_codes, post_fake_elapsed,
                )
                record('fake_websocket_upgrade_does_not_lock_slots')

                # 13. WebSocket upgrade through Project Nginx + ESM .wasm module execution.
                # Kept last: an upgraded isolate is only ended by the wall clock, so it holds its slot for a while.
                wasm_http = client.get(f'{nginx_origin}/functions/v1/ws_wasm', headers=gw_headers('/functions/v1/ws_wasm'))
                assert wasm_http.status_code == 200 and wasm_http.json().get('wasmSum') == 42, wasm_http.text

                import asyncio
                import inspect
                import websockets

                ws_url = nginx_origin.replace('http://', 'ws://', 1) + '/functions/v1/ws_wasm'
                ws_headers = gw_headers('/functions/v1/ws_wasm')
                hdr_kw = 'additional_headers' if 'additional_headers' in inspect.signature(websockets.connect).parameters else 'extra_headers'

                async def run_ws_echo() -> str:
                    async with websockets.connect(ws_url, **{hdr_kw: ws_headers}) as ws:
                        await ws.send('hello')
                        return str(await asyncio.wait_for(ws.recv(), timeout=5))

                ws_reply = asyncio.run(run_ws_echo())
                assert ws_reply == 'ws-wasm:hello:42', ws_reply
                record('websocket_gateway_and_wasm_module_execution')

            if args.result:
                args.result.write_text(json.dumps({'contract': args.contract, 'image': args.edge_image, 'checks': checks}, indent=2))
            print(f'Completed {len(checks)} Edge Functions runtime capability checks.', flush=True)
        finally:
            for name in reversed(names):
                subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True)
            if built_bundler_img:
                subprocess.run(['docker', 'rmi', '-f', bundler_img], capture_output=True)
            subprocess.run(['docker', 'network', 'rm', network], capture_output=True)


if __name__ == '__main__':
    main()
