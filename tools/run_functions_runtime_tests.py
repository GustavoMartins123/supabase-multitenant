"""Exercise Edge Functions runtime streaming, CORS, waitUntil, internal services, deno.json and limits."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
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
}


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
        .replace('${SUPABASE_NETWORK_SUBNET}', subnet))
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
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()

    prefix = f'functions-rt-test-{uuid.uuid4().hex[:8]}'
    network = prefix
    names: list[str] = []
    checks: list[str] = []

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
            target.write_text(content, encoding='utf-8')

        (fixture / 'canary.py').write_text(CANARY_AND_AUTH, encoding='utf-8')
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
            for fn in ('stream', 'slow', 'wait_until', 'internal_calls', 'imported', 'remote_import', 'check_env'):
                shutil.copytree(code / fn, code_root / fn)
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
            (runtime / 'tenants' / f'{project}.json').write_text(json.dumps(tenant_doc))

        try:
            docker('network', 'create', '--label', 'functions.runtime-fixture=true', network)
            net_info = json.loads(docker('network', 'inspect', network))[0]
            subnet = net_info['IPAM']['Config'][0]['Subnet']

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
                '-e', 'DENO_DIR=/tmp/deno', '-e', 'VERIFY_JWT=true',
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges:true',
                '--tmpfs', '/tmp:rw,nosuid,size=128m',
                '-v', f'{hosts}:/etc/hosts:rw',
                '-v', f'{code / "main"}:/home/deno/main:ro',
                '-v', f'{runtime}:/home/deno/runtime:ro',
                '-p', '127.0.0.1::9000',
            ]
            if args.contract == 'projected':
                rt_cmd += ['-v', f'{config}:/home/deno/tenant-config:ro']
            rt_cmd += [args.edge_image, 'start', '--main-service', '/home/deno/main']
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

                # 7. Per-project concurrency (2) and global concurrency (4)
                codes: list[int] = []
                def slow_alpha():
                    r = client.get(f'{nginx_origin}/functions/v1/slow?ms=700', headers=gw_headers('/functions/v1/slow?ms=700'))
                    codes.append(r.status_code)
                threads = [threading.Thread(target=slow_alpha), threading.Thread(target=slow_alpha)]
                for t in threads:
                    t.start()
                time.sleep(0.18)
                third_alpha = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                assert third_alpha.status_code == 429 and third_alpha.json()['code'] == 'function_concurrency_limit', third_alpha.text
                assert third_alpha.headers.get('access-control-allow-origin') == 'http://localhost:3000'
                beta_hdrs = {
                    'apikey': internal_tokens['test_beta']['anon'],
                    'Authorization': 'Bearer ' + internal_tokens['test_beta']['anon'],
                    'X-Project-Name': 'test_beta',
                    'X-Project-Ref': refs['test_beta'],
                    'X-Project-UUID': identities['test_beta'],
                }
                beta_ok = client.get(f'{rt_origin}/imported', headers=beta_hdrs)
                assert beta_ok.status_code == 200, beta_ok.text
                for t in threads:
                    t.join()
                assert codes == [200, 200], codes
                recovered = client.get(f'{nginx_origin}/functions/v1/imported', headers=gw_headers('/functions/v1/imported'))
                assert recovered.status_code == 200, recovered.text
                record('concurrency_limits_and_slot_recovery')

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

            if args.result:
                args.result.write_text(json.dumps({'contract': args.contract, 'image': args.edge_image, 'checks': checks}, indent=2))
            print(f'Completed {len(checks)} Edge Functions runtime capability checks.', flush=True)
        finally:
            for name in reversed(names):
                subprocess.run(['docker', 'rm', '-f', '-v', name], capture_output=True)
            subprocess.run(['docker', 'network', 'rm', network], capture_output=True)


if __name__ == '__main__':
    main()
