"""Integrated disposable acceptance. Test plumbing never overrides auth code."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import time
import urllib.request
import urllib.error

import yaml

from p1_lifecycle import environment, run, sql


def validate(root: Path, suffix: str, topology: str, values: dict[str, str], benchmark: bool) -> None:
    server = root / 'servidor'
    labels = {'codex.p1.run': suffix}
    for image in ('studio-nginx:latest', 'authelia/authelia:4.39.20', 'codex-p1-browser:local',
                  'ghcr.io/gustavomartins123/multitenant-studio:20290c7-context-v3', 'traefik:v3.7.6',
                  'servidor-projects-api:latest', 'supabase/postgres-meta:v0.96.1'):
        assert run('docker', 'image', 'inspect', image, '--format', '{{.Os}}') == 'linux', image
    wire = 'p1-https-link-' + suffix
    front = 'rede-supabase' if topology == 'single' else 'p1-studio-node-' + suffix
    run('docker', 'network', 'create', '--label', 'codex.p1.run=' + suffix,
        '--subnet', '172.52.0.0/24', wire)
    if topology == 'split':
        run('docker', 'network', 'create', '--label', 'codex.p1.run=' + suffix, front)
    executor = 'p1-lifecycle-executor-' + suffix
    run('docker', 'network', 'connect', wire, executor)
    if topology == 'split':
        run('docker', 'network', 'connect', front, executor)

    run('python', str(root / 'tools/configure_studio_runtime.py'), '--studio-origin', 'https://studio.p1.test', '--force')
    config = root / 'studio/authelia'
    secret_dir = root / 'studio/secrets/authelia'
    actors = ('owner', 'admin', 'member', 'exmember', 'disabled', 'global', 'outsider')
    credentials = {actor: {'username': 'p1_' + actor, 'password': secrets.token_urlsafe(24)} for actor in actors}
    users = {}
    for actor in actors:
        output = run('docker', 'run', '--rm', '--pull=never', 'authelia/authelia:4.39.20',
                     'authelia', 'crypto', 'hash', 'generate', 'argon2', '--password', credentials[actor]['password'])
        digest = next(line.split('Digest: ', 1)[1] for line in output.splitlines() if 'Digest: ' in line)
        users['p1_' + actor] = {'displayname': 'P1 ' + actor, 'password': digest,
                               'email': 'p1_' + actor + '@example.test',
                               'groups': ['active', 'admin'] if actor == 'global' else ['active']}
    (config / 'users_database.yml').write_text(yaml.safe_dump({'users': users}), encoding='utf-8')
    # Only the normal synthetic account directory is writable by Studio.
    os.chmod(config / 'users_database.yml', 0o666)
    browser_config = root / 'p1-browser'
    browser_config.mkdir()
    (browser_config / 'credentials.json').write_text(json.dumps(credentials), encoding='utf-8')
    shutil.copy2(config / 'ssl/ca.pem', browser_config / 'ca.pem')
    shutil.copy2(config / 'ssl/ca.pem', server / 'certs/ca.pem')
    module_spec = importlib.util.spec_from_file_location('studio_config', root / 'tools/configure_studio_runtime.py')
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    tls = server / 'traefik/certs/traefik'
    module.issue_server_certificate(tls, host='server.p1.test', ca_certificate=config / 'ssl/ca.pem', ca_key=secret_dir / 'ca.key')
    shutil.copy2(tls / 'server.pem', tls / 'tls.crt')
    shutil.copy2(tls / 'server.key', tls / 'tls.key')
    env_path = server / '.env'
    env_text = env_path.read_text(encoding='utf-8')
    for key, value in {'TRAEFIK_ENABLE_TLS': 'true', 'TRAEFIK_TLS_MODE': 'file',
                       'PROJECTS_API_ALLOWED_IP_RANGES': '172.50.0.0/16,172.52.0.0/24'}.items():
        assert re.search(rf'(?m)^{key}=.*$', env_text), key
        env_text = re.sub(rf'(?m)^{key}=.*$', lambda _: key + '=' + value, env_text)
    env_path.write_text(env_text, encoding='utf-8')
    # Synthetic optional logging credentials. The actual API env surface is
    # derived from production Compose, not replaced with a global .env mount.
    (server / '.analytics.env').write_text('\n'.join(k + '=' + secrets.token_hex(32) for k in
        ('LOGFLARE_PUBLIC_ACCESS_TOKEN', 'LOGFLARE_PRIVATE_ACCESS_TOKEN', 'LOGFLARE_DB_ENCRYPTION_KEY')) + '\n', encoding='utf-8')

    def create(name: str, image: str, network: str, *args: str, command: tuple[str, ...] = ()) -> str:
        identifier = run('docker', 'create', '--name', name, '--pull=never', '--label', 'codex.p1.run=' + suffix,
                         '--network', network, *args, image, *command)
        run('docker', 'start', identifier)
        return name

    secret_args = []
    for name, variable in [('JWT_SECRET', 'IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE'),
                           ('SESSION_SECRET', 'SESSION_SECRET_FILE'), ('STORAGE_ENCRYPTION_KEY', 'STORAGE_ENCRYPTION_KEY_FILE')]:
        secret_args += ['-v', f'{secret_dir}/{name}:/run/secrets/{name}:ro', '-e', f'AUTHELIA_{variable}=/run/secrets/{name}']
    create('p1-authelia-' + suffix, 'authelia/authelia:4.39.20', front,
           '--network-alias', 'authelia', '-v', str(config) + ':/config', *secret_args,
           command=('authelia', '--config=/config/configuration.runtime.yml'))
    create('p1-ui-' + suffix, 'ghcr.io/gustavomartins123/multitenant-studio:20290c7-context-v3', front,
           '--network-alias', 'studio', '-e', 'HOSTNAME=0.0.0.0')
    nginx_config = root / 'studio/nginx/nginx.conf'
    text = nginx_config.read_text(encoding='utf-8').replace('worker_processes auto;', 'worker_processes 2;')
    text = text.replace('error_log /var/log/studio_error.log debug;', 'error_log /dev/stderr notice;')
    text = text.replace('        location = /api/config {', '''        location = /session-test {
            auth_request off;
            default_type text/html;
            return 200 '<!doctype html><title>P1 integration</title>';
        }
        location = /api/config {''', 1)
    nginx_config.write_text(text, encoding='utf-8')
    studio_env = {k: values[k] for k in ('STUDIO_SERVICE_KEY_ENCRYPTION_KEY', 'NGINX_HMAC_SECRET',
                                        'STUDIO_GATEWAY_HMAC_SECRET', 'PROJECTS_API_HMAC_SECRET')}
    studio_env.update(SERVER_DOMAIN='https://server.p1.test', SERVICE_KEY_VERIFY_TLS='true',
                      STUDIO_ANALYTICS_HMAC_SECRET=secrets.token_hex(32),
                      STUDIO_BOOTSTRAP_TOKEN_FILE='/run/secrets/STUDIO_BOOTSTRAP_TOKEN',
                      AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE='/var/run/authelia-cli-secrets/JWT_SECRET',
                      AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE='/var/run/authelia-cli-secrets/STORAGE_ENCRYPTION_KEY')
    args = [part for key, value in studio_env.items() for part in ('-e', key + '=' + value)]
    for name in ('JWT_SECRET', 'STORAGE_ENCRYPTION_KEY', 'STUDIO_BOOTSTRAP_TOKEN'):
        args += ['-v', f'{secret_dir}/{name}:/run/secrets/{name}:ro']
    nginx = 'p1-nginx-' + suffix
    run('docker', 'create', '--name', nginx, '--pull=never', '--label', 'codex.p1.run=' + suffix,
        '--network', front, '--network-alias', 'studio.p1.test', '-v', str(config) + ':/config',
        '-v', str(nginx_config) + ':/usr/local/openresty/nginx/conf/nginx.conf:ro',
        '-v', str(root / 'studio/nginx/docker-entrypoint.sh') + ':/usr/local/bin/docker-entrypoint.sh:ro',
        *args, 'studio-nginx:latest')
    run('docker', 'cp', str(root / 'studio/nginx/lua') + '/.', nginx + ':/usr/local/openresty/lualib/')
    run('docker', 'network', 'connect', '--alias', 'studio.p1.test', wire, nginx)
    run('docker', 'start', nginx)

    # Production route generator and local guard; GeoIP/logging services are not
    # part of this authorization drill. Middleware plumbing has no auth bypass.
    middleware_file = server / 'traefik/p1-middlewares.yml'
    middleware_file.write_text(yaml.safe_dump({'http': {'middlewares': {
        'security-headers': {'headers': {'contentTypeNosniff': True}},
        'rate-limit': {'rateLimit': {'average': 80, 'burst': 160}},
        'api-security-chain': {'chain': {'middlewares': ['security-headers']}}}}}), encoding='utf-8')
    dynamic = server / 'traefik/dynamic'
    create('p1-route-watcher-' + suffix, 'codex-p1-executor:local', 'rede-supabase',
           '-v', str(server / 'traefik') + ':/fixture/traefik', '-v', str(env_path) + ':/fixture/server.env:ro',
           '-v', str(server / 'projects') + ':/fixture/projects:ro', '--entrypoint', 'python',
           command=('/fixture/traefik/render_dynamic_config.py', '--watch', '--root-env', '/fixture/server.env',
                    '--projects-dir', '/fixture/projects', '--middlewares-file', '/fixture/traefik/p1-middlewares.yml',
                    '--tls-cert-dir', '/fixture/traefik/certs/traefik', '--output', '/fixture/traefik/dynamic/routes.yml'))
    deadline = time.monotonic() + 20
    while not (dynamic / 'routes.yml').is_file():
        assert time.monotonic() < deadline, 'Route watcher startup timeout'
        time.sleep(0.2)
    traefik_static = server / 'traefik/p1-static.yml'
    traefik_static.write_text(yaml.safe_dump({
        'entryPoints': {'web': {'address': ':80'}, 'websecure': {'address': ':443'}},
        'providers': {'file': {'directory': str(dynamic), 'watch': True}},
        'experimental': {'localPlugins': {'supabaseguard': {'moduleName': 'github.com/GustavoMartins123/supabaseguard'}}},
        'accessLog': {'format': 'json'}, 'log': {'level': 'INFO'},
        'global': {'checkNewVersion': False, 'sendAnonymousUsage': False}}), encoding='utf-8')
    traefik = create('p1-traefik-' + suffix, 'traefik:v3.7.6', 'rede-supabase',
                     '-v', str(server / 'traefik') + ':' + str(server / 'traefik') + ':ro',
                     '-v', str(tls) + ':/certs/traefik:ro',
                     '-v', str(server / 'traefik/plugins-local') + ':/plugins-local:ro',
                     command=('--configFile=' + str(traefik_static),))
    run('docker', 'network', 'connect', '--alias', 'server.p1.test', wire, traefik)

    # Derive the real API service and explicitly select the canonical topology.
    model = yaml.safe_load((server / 'p1-compose.yml').read_text(encoding='utf-8'))
    api = yaml.safe_load((server / 'docker-compose-api.yml').read_text(encoding='utf-8'))['services']['projects-api']
    overlay = yaml.safe_load((server / f'docker-compose.{"single-node" if topology == "single" else "split-node"}.yml').read_text(encoding='utf-8'))
    assert overlay['services']['projects-api']['networks'] == ['rede-supabase', 'analytics-internal']
    api.pop('build')
    api.update(image='servidor-projects-api:latest', labels=labels, logging={'driver': 'json-file'}, restart='no',
               networks=['rede-supabase', 'p1-link'])
    api.pop('depends_on')
    api['volumes'] += [str(server / 'api-internal/app') + ':/docker/app:ro']
    model['services'] = {'projects-api': api}
    model['networks']['p1-link'] = {'external': True, 'name': wire}
    (server / 'p1-api-compose.yml').write_text(yaml.safe_dump(model), encoding='utf-8')
    run('docker', 'compose', '-p', 'p1-api-' + suffix, '--env-file', str(env_path),
        '-f', str(server / 'p1-api-compose.yml'), 'up', '-d', '--wait', '--wait-timeout', '90', cwd=server)
    agent = create('p1-host-agent-' + suffix, 'codex-p1-executor:local', 'rede-supabase',
                   '-v', 'p1-lifecycle-root-' + suffix + ':' + str(root),
                   '-v', '/var/run/docker.sock:/var/run/docker.sock', '-e', 'PYTHONPATH=' + str(server / 'host-agent'),
                   '--entrypoint', 'python', command=('-m', 'hostagent', '--root', str(server)))
    run('docker', 'network', 'connect', wire, agent)
    context = ssl.create_default_context(cafile=str(server / 'certs/ca.pem'))
    try:
        urllib.request.urlopen('https://server.p1.test/api/projects', context=context, timeout=10)
    except urllib.error.HTTPError as error:
        assert error.code == 401, error.read().decode()
    else:
        raise AssertionError('Unsigned API request accepted')
    try:
        urllib.request.urlopen('https://server.p1.test/api/projects', context=ssl.create_default_context(), timeout=10)
    except urllib.error.URLError as error:
        assert isinstance(error.reason, ssl.SSLCertVerificationError), error
    else:
        raise AssertionError('Untrusted server CA accepted')
    print('PASS actual Traefik TLS file schema, trusted CA and untrusted CA rejection', flush=True)
    browser = create('p1-browser-' + suffix, 'codex-p1-browser:local', front,
                     '--network-alias', 'p1-browser', '-v', str(browser_config) + ':/fixture:ro',
                     '-v', str(root / 'tests/integration/fixtures/p1_browser_driver.py') + ':/driver.py:ro',
                     '--entrypoint', 'python', command=('/driver.py',))
    deadline = time.monotonic() + 90
    while True:
        try:
            urllib.request.urlopen('http://p1-browser:8765', timeout=2).close()
            break
        except OSError:
            assert time.monotonic() < deadline, 'Browser driver startup timeout'
            time.sleep(0.5)

    def request(actor: str, method: str, path: str, body=None, *, headers=None, step_up=False) -> dict:
        command = {'actor': actor, 'method': method, 'path': path, 'headers': headers or {}, 'step_up': step_up}
        if body is not None:
            command['body'] = body
        try:
            response = urllib.request.urlopen(urllib.request.Request('http://p1-browser:8765', data=json.dumps(command).encode(),
                                                          headers={'Content-Type': 'application/json'}), timeout=120)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Browser controller failed: ' + error.read().decode()) from error
        with response:
            return json.load(response)

    def expect(actor: str, method: str, path: str, status: int, body=None, **kwargs):
        response = request(actor, method, path, body, **kwargs)
        assert response['status'] == status, (actor, method, path, response)
        return json.loads(response['body']) if response['body'] else None

    def job(actor: str, method: str, path: str, body=None, **kwargs):
        queued = expect(actor, method, path, 202, body, **kwargs)
        wait_job(actor, queued, 'done')
        return queued

    def wait_job(actor, queued, expected_status):
        deadline = time.monotonic() + 600
        while True:
            try:
                record = expect(actor, 'GET', '/api/projects/status/' + queued['job_id'], 200)
            except AssertionError:
                print('FAIL job audit:', sql("SELECT jsonb_build_object('status',status,'error_code',error_code,"
                      "'stderr_tail',stderr_tail,'stdout_tail',stdout_tail) FROM host_agent_commands WHERE job_id='" + queued['job_id'] + "';"), flush=True)
                raise
            if record['status'] in {'done', 'failed', 'cancelled'}:
                assert record['status'] == expected_status, record
                return record
            assert time.monotonic() < deadline, ('job timeout', record)
            time.sleep(1)

    print('REAL END-TO-END TOPOLOGY:', topology, flush=True)
    alpha, beta, renamed = 'e2e_a_' + suffix, 'e2e_b_' + suffix, 'e2e_r_' + suffix
    expect('anonymous', 'GET', '/api/projects', 401)
    job('owner', 'POST', '/api/projects', {'name': alpha, 'resource_profile': 'small'})
    print('PASS real browser -> Lua -> Traefik -> API -> signed host-agent create', flush=True)
    def projection(ref):
        env = environment(server / 'projects' / ref / '.env')
        path = server / '.functions-tenants' / (ref + '.json')
        record = json.loads(path.read_text(encoding='utf-8'))
        assert record == {'project_ref': ref, 'project_uuid': env['PROJECT_UUID'],
                          'anon_key': env['ANON_KEY_PROJETO'], 'service_role_key': env['SERVICE_ROLE_KEY_PROJETO'],
                          'jwt_secret': env['JWT_SECRET_PROJETO']}
        assert path.stat().st_mode & 0o777 == 0o600
        worker = json.loads(run('curl', '--fail', '--silent', '--show-error', '-H', 'X-Project-Ref: ' + ref,
                              '-H', 'Authorization: Bearer ' + record['service_role_key'],
                              'http://supabase-edge-functions:9000/p1_probe'))['env']
        assert worker['SUPABASE_SERVICE_ROLE_KEY'] == record['service_role_key']
        assert worker['SUPABASE_ANON_KEY'] == record['anon_key']
        assert worker['JWT_SECRET'] == record['jwt_secret']
        assert not {'POSTGRES_PASSWORD', 'DATABASE_URL', 'HOST_AGENT_HMAC_SECRET'} & worker.keys()
        return record

    def storage_seed(ref, method, path, body):
        # Privileged data preparation only. All permission checks use the browser.
        env = environment(server / 'projects' / ref / '.env')
        script = '''let input='';process.stdin.setEncoding('utf8');
process.stdin.on('data',data=>input+=data);process.stdin.on('end',async()=>{
const [tenant,method,path]=process.argv.slice(1), split=input.indexOf('\\n');
const response=await fetch('http://127.0.0.1:5000'+path,{method,
headers:{authorization:'Bearer '+input.slice(0,split),'content-type':'application/json',
'x-forwarded-host':tenant+'.storage.internal'},body:input.slice(split+1),signal:AbortSignal.timeout(15000)});
if(!response.ok){console.error(response.status+': '+await response.text());process.exit(1);}
});'''
        run('docker', 'exec', '-i', 'supabase-storage-global', 'node', '-e', script, env['PROJECT_UUID'], method, path,
            data=env['SERVICE_ROLE_KEY_PROJETO'] + '\n' + json.dumps(body))

    def private_object(ref):
        signed = expect('owner', 'POST', '/api/platform/storage/' + ref + '/buckets/p1-files/objects/sign-multi',
                        200, {'paths': ['original.json'], 'expiresIn': 60})
        assert len(signed) == 1 and signed[0]['path'] == 'original.json', signed
        url = signed[0]['signedUrl']
        assert url.startswith('https://studio.p1.test/storage/v1/' + ref + '/object/sign/p1-files/original.json?')
        assert expect('owner', 'GET', url, 200) == {'value': 'original'}

    initial = projection(alpha)
    step = expect('owner', 'POST', '/api/security/step-up', 200,
                  {'action': 'create_secret_key', 'project': alpha, 'resource': 'p1-external'}, step_up=True)['step_up_token']
    external = expect('owner', 'POST', '/api/projects/' + alpha + '/api-key-slots', 201,
                      {'name': 'p1-external', 'kind': 'secret', 'allowed_services': ['rest', 'graphql', 'storage']},
                      headers={'X-Step-Up-Token': step})
    assert external['api_key'].startswith('sb_secret_')
    def external_request(ref, key, status):
        target = 'https://server.p1.test/' + ref + '/rest/v1/lifecycle_marker?select=id,value'
        raw = urllib.request.Request(target, headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                       'X-Forwarded-Host': initial['project_uuid'] + '.storage.internal'})
        try:
            with urllib.request.urlopen(raw, context=context, timeout=10) as response:
                actual = response.status
        except urllib.error.HTTPError as error:
            actual = error.code
        assert actual == status, ('external opaque/JWT status', ref, actual, status)
    ids = {actor: sql("SELECT id FROM users WHERE authelia_username='p1_" + actor + "';") for actor in actors}
    assert all(ids.values())
    for actor, role in [('admin', 'admin'), ('member', 'member'), ('exmember', 'admin'), ('disabled', 'admin')]:
        expect('owner', 'POST', '/api/projects/' + alpha + '/members', 200, {'user_id': ids[actor], 'role': role})
    sql("CREATE TABLE public.lifecycle_marker(id int primary key,value text); "
        "INSERT INTO public.lifecycle_marker VALUES(1,'original'); GRANT ALL ON public.lifecycle_marker TO service_role; "
        "NOTIFY pgrst,'reload schema';", '_supabase_' + alpha)
    time.sleep(2)  # PostgREST schema notification propagation, not authorization cache.
    external_request(alpha, external['api_key'], 200)
    external_request(alpha, initial['service_role_key'], 403)
    rest = '/api/platform/projects/' + alpha + '/api/rest/lifecycle_marker?select=id,value'
    graphql = '/api/platform/projects/' + alpha + '/api/graphql'
    buckets = '/api/platform/storage/' + alpha + '/buckets'
    vectors = '/api/platform/storage/' + alpha + '/vector-buckets'
    # Repeated authorization validation, not a performance measurement/report.
    expect('owner', 'GET', rest, 200)
    command = {'actor': 'owner', 'method': 'GET', 'path': rest, 'headers': {},
               'benchmark': {'samples': 3, 'concurrency': 1}}
    with urllib.request.urlopen(urllib.request.Request('http://p1-browser:8765', data=json.dumps(command).encode(),
                                headers={'Content-Type': 'application/json'}), timeout=60) as response:
        repeated = json.load(response)
    normal = request('owner', 'GET', rest)
    assert all(m['status'] == 200 for m in repeated['measurements']), (repeated, 'normal_status', normal['status'])
    for actor in ('owner', 'admin', 'exmember', 'disabled', 'global'):
        assert expect(actor, 'GET', rest, 200) == [{'id': 1, 'value': 'original'}]
        assert 'data' in expect(actor, 'POST', graphql, 200, {'query': '{ __typename }'})
        expect(actor, 'GET', buckets, 200)
        expect(actor, 'GET', vectors, 200)
    for actor in ('member', 'outsider'):
        for method, path, body in [('GET', rest, None), ('POST', graphql, {'query': '{ __typename }'}),
                                   ('GET', buckets, None), ('GET', vectors, None)]:
            expect(actor, method, path, 404, body)
    expect('member', 'POST', '/api/projects/' + alpha + '/members', 403, {'user_id': ids['outsider'], 'role': 'admin'})
    expect('admin', 'POST', '/api/projects/' + alpha + '/members', 403, {'user_id': ids['exmember'], 'role': 'member'})
    expect('admin', 'POST', '/api/projects/' + alpha + '/members', 409, {'user_id': ids['owner'], 'role': 'member'})
    expect('member', 'POST', '/api/projects/' + alpha + '/rotate-key', 403)
    expect('owner', 'DELETE', '/api/projects/' + alpha, 403)
    expect('global', 'DELETE', '/api/projects/' + alpha, 403)  # No step-up grant.
    expect('owner', 'GET', rest, 409, headers={'X-Studio-Project-Ref': beta})
    expect('owner', 'POST', buckets, 200, {'id': 'p1-files', 'public': False})
    expect('owner', 'POST', vectors, 200, {'bucketName': 'p1-vectors'})
    expect('admin', 'POST', vectors + '/p1-vectors/indexes', 200,
           {'indexName': 'p1-index', 'dataType': 'float32', 'dimension': 3, 'distanceMetric': 'cosine'})
    indexes = expect('owner', 'GET', vectors + '/p1-vectors/indexes', 200)['indexes']
    assert len(indexes) == 1 and indexes[0]['dimension'] == 3 and indexes[0]['distanceMetric'] == 'cosine', indexes
    storage_seed(alpha, 'POST', '/object/p1-files/original.json', {'value': 'original'})
    storage_seed(alpha, 'POST', '/vector/PutVectors', {'vectorBucketName': 'p1-vectors', 'indexName': 'p1-index',
                 'vectors': [{'key': 'original', 'data': {'float32': [1, 0, 0]}}]})
    assert expect('owner', 'POST', buckets + '/p1-files/objects/list', 200, {'path': ''})[0]['name'] == 'original.json'
    private_object(alpha)
    expect('owner', 'DELETE', '/api/projects/' + alpha + '/members/' + ids['exmember'], 200)
    for method, path, body in [('GET', rest, None), ('POST', graphql, {'query': '{ __typename }'}),
                               ('GET', buckets, None), ('GET', vectors, None)]:
        expect('exmember', method, path, 404, body)  # Same already-issued real cookie, no delay.
    users['p1_disabled']['disabled'] = True
    (config / 'users_database.yml').write_text(yaml.safe_dump({'users': users}), encoding='utf-8')
    expect('disabled', 'GET', '/api/projects', 401)
    expect('disabled', 'GET', rest, 401)
    print('PASS real REST/GraphQL/Storage/Vectors role matrix and immediate membership/directory revocation', flush=True)

    # A legitimately queued command must be reauthorized against the live
    # directory by the agent, not merely trust the API's earlier decision.
    expect('owner', 'POST', '/api/projects/' + alpha + '/members', 200, {'user_id': ids['exmember'], 'role': 'admin'})
    run('docker', 'pause', agent)
    denied = expect('exmember', 'POST', '/api/projects/' + alpha + '/rotate-key', 202)
    deadline = time.monotonic() + 30
    while sql("SELECT count(*) FROM host_agent_commands WHERE job_id='" + denied['job_id'] + "' AND status='queued';") != '1':
        assert time.monotonic() < deadline
        time.sleep(0.2)
    users['p1_exmember']['disabled'] = True
    (config / 'users_database.yml').write_text(yaml.safe_dump({'users': users}), encoding='utf-8')
    run('docker', 'unpause', agent)
    wait_job('global', denied, 'failed')
    assert sql("SELECT error_code FROM host_agent_commands WHERE job_id='" + denied['job_id'] + "';") == 'authorization_denied:directory_revoked'
    assert projection(alpha) == initial
    print('PASS queued API command revoked at actual agent HTTPS authorization boundary', flush=True)

    callback_ca = server / 'certs/ca.pem'
    trusted_ca = callback_ca.read_bytes()
    run('openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1', '-subj', '/CN=Untrusted P1 CA',
        '-keyout', str(root / 'fault-ca.key'), '-out', str(root / 'fault-ca.pem'))
    callback_ca.write_bytes((root / 'fault-ca.pem').read_bytes())
    expect('owner', 'GET', rest, 503)  # Lua trusts server, API rejects callback certificate.
    callback_ca.write_bytes(trusted_ca)
    expect('owner', 'GET', rest, 200)
    run('docker', 'pause', agent)
    denied = expect('owner', 'POST', '/api/projects/' + alpha + '/rotate-key', 202)
    deadline = time.monotonic() + 30
    while sql("SELECT count(*) FROM host_agent_commands WHERE job_id='" + denied['job_id'] + "' AND status='queued';") != '1':
        assert time.monotonic() < deadline
        time.sleep(0.2)
    callback_ca.write_bytes((root / 'fault-ca.pem').read_bytes())
    run('docker', 'unpause', agent)
    deadline = time.monotonic() + 30
    while sql("SELECT status FROM host_agent_commands WHERE job_id='" + denied['job_id'] + "';") != 'failed':
        assert time.monotonic() < deadline
        time.sleep(0.2)
    assert sql("SELECT error_code FROM host_agent_commands WHERE job_id='" + denied['job_id'] + "';") == 'authorization_denied:directory_unavailable'
    callback_ca.write_bytes(trusted_ca)
    wait_job('owner', denied, 'failed')
    assert projection(alpha) == initial
    print('PASS API and agent callback reject wrong CA without stale grants or physical mutation', flush=True)

    job('owner', 'POST', '/api/projects/duplicate', {'original_name': alpha, 'new_name': beta, 'copy_data': True})
    projection(beta)
    external_request(beta, external['api_key'], 403)
    private_object(beta)
    assert 'data' in expect('owner', 'POST', '/api/platform/projects/' + beta + '/api/graphql', 200, {'query': '{ __typename }'})
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + beta) == 'original'
    assert expect('owner', 'GET', '/api/platform/storage/' + beta + '/vector-buckets/p1-vectors/indexes', 200)['indexes'][0]['dimension'] == 3
    expect('admin', 'GET', '/api/platform/storage/' + beta + '/buckets', 404)  # Membership isn't copied.
    job('admin', 'POST', '/api/projects/' + alpha + '/rename', {'new_name': renamed})
    assert not (server / '.functions-tenants' / (alpha + '.json')).exists()
    projection(renamed)
    job('admin', 'POST', '/api/projects/' + renamed + '/rotate-key')
    rotated = projection(renamed)
    assert rotated['service_role_key'] != initial['service_role_key'] and rotated['jwt_secret'] == initial['jwt_secret']
    backup = job('admin', 'POST', '/api/projects/' + renamed + '/restore-points', {'title': 'P1 verified point'})
    sql("UPDATE public.lifecycle_marker SET value='changed';", '_supabase_' + renamed)
    storage_seed(renamed, 'PUT', '/object/p1-files/original.json', {'value': 'changed'})
    restore_path = '/api/projects/' + renamed + '/restore-points/' + backup['restore_point_id'] + '/restore'
    expect('admin', 'POST', restore_path, 403)
    job('owner', 'POST', restore_path)
    projection(renamed)
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + renamed) == 'original'
    private_object(renamed)
    assert 'data' in expect('owner', 'POST', '/api/platform/projects/' + renamed + '/api/graphql', 200, {'query': '{ __typename }'})
    restored_rest = '/api/platform/projects/' + renamed + '/api/rest/lifecycle_marker?select=id,value'
    assert expect('owner', 'GET', restored_rest, 200) == [{'id': 1, 'value': 'original'}]
    print('PASS API + signed agent duplicate / rename / JWT renewal / backup / restore', flush=True)

    api_inventory = json.loads(run('docker', 'inspect', 'projects-api'))[0]
    assert {m['Destination'] for m in api_inventory['Mounts']} == {'/docker/projects', '/docker/push-certs', '/docker/resource-profiles.env', '/docker/app'}
    assert not any(e.startswith(('POSTGRES_PASSWORD=', 'SERVER_ADMIN_API_KEYS=', 'API_GATEWAY_TOKEN_PROJETO=')) for e in api_inventory['Config']['Env'])
    edge_inventory = json.loads(run('docker', 'inspect', 'supabase-edge-functions'))[0]
    assert {m['Destination'] for m in edge_inventory['Mounts']} == {'/home/deno/functions', '/home/deno/tenant-config'}
    assert all(m['RW'] is False for m in edge_inventory['Mounts'])
    assert not any(e.startswith(('POSTGRES_PASSWORD=', 'JWT_SECRET=', 'SUPABASE_SERVICE_ROLE_KEY=')) for e in edge_inventory['Config']['Env'])
    if topology == 'split':
        nginx_inventory = json.loads(run('docker', 'inspect', nginx))[0]
        assert set(nginx_inventory['NetworkSettings']['Networks']) == {front, wire}
    print('PASS actual API/Functions mount and environment isolation', flush=True)

    # API outage must deny even with a warm administrative credential and real cookie.
    run('docker', 'stop', 'projects-api')
    expect('owner', 'GET', restored_rest, 503)
    run('docker', 'start', 'projects-api')
    deadline = time.monotonic() + 60
    while run('docker', 'inspect', 'projects-api', '--format', '{{.State.Health.Status}}') != 'healthy':
        assert time.monotonic() < deadline
        time.sleep(1)
    expect('owner', 'GET', restored_rest, 200)
    for prefix in ('supabase_realtime_messages_replication_slot_', 'supabase_realtime_replication_slot_'):
        slot = (prefix + renamed)[:63]
        sql("SELECT pg_create_logical_replication_slot('" + slot + "','pgoutput');", '_supabase_' + renamed)
    assert sql("SELECT count(*) FROM pg_replication_slots WHERE database='_supabase_" + renamed + "';") == '2'
    assert sql("SELECT rolreplication FROM pg_roles WHERE rolname='platform_meta_admin';") == 'f'
    foreign_slot = ('supabase_realtime_replication_slot_' + beta)[:63]
    sql("SELECT pg_create_logical_replication_slot('" + foreign_slot + "','pgoutput');", '_supabase_' + renamed)
    scope_check = '''import asyncio,os,asyncpg,sys
async def main():
    conn=await asyncpg.connect(os.environ['META_ADMIN_DSN'])
    try:
        for project,slot in [(sys.argv[1],'unrelated_slot'),('bad-project','unrelated_slot'),
                             (None,'unrelated_slot'),(sys.argv[1],None),(sys.argv[2],sys.argv[3])]:
            try: await conn.fetchval('SELECT public.drop_project_replication_slot($1,$2)',project,slot)
            except asyncpg.InsufficientPrivilegeError: pass
            else: raise AssertionError('Out-of-scope slot accepted')
    finally: await conn.close()
    conn=await asyncpg.connect(os.environ['DB_DSN'])
    try:
        try: await conn.fetchval('SELECT public.drop_project_replication_slot($1,$2)',sys.argv[1],
                                ('supabase_realtime_replication_slot_'+sys.argv[1])[:63])
        except asyncpg.InsufficientPrivilegeError: pass
        else: raise AssertionError('platform_app received privileged slot cleanup')
    finally: await conn.close()
asyncio.run(main())'''
    run('docker', 'exec', 'projects-api', 'python', '-c', scope_check, renamed, beta, foreign_slot)
    assert sql("SELECT count(*) FROM pg_replication_slots WHERE slot_name='" + foreign_slot + "';") == '1'
    sql("SELECT pg_drop_replication_slot('" + foreign_slot + "');")
    token = expect('global', 'POST', '/api/security/step-up', 200,
                   {'action': 'delete_project', 'project': renamed, 'resource': renamed}, step_up=True)['step_up_token']
    job('global', 'DELETE', '/api/projects/' + renamed, headers={'X-Step-Up-Token': token})
    assert not (server / 'projects' / renamed).exists()
    assert not (server / '.functions-tenants' / (renamed + '.json')).exists()
    assert sql("SELECT count(*) FROM pg_database WHERE datname='_supabase_" + renamed + "';") == '0'
    assert sql("SELECT count(*) FROM projects WHERE name='" + renamed + "';") == '0'
    assert not (server / 'volumes/storage/objects' / initial['project_uuid']).exists()
    assert sql("SELECT count(*) FROM _realtime.tenants WHERE external_id='" + initial['project_uuid'] + "';") == '0'
    assert sql("SELECT count(*) FROM _supavisor.tenants WHERE external_id='" + renamed + "';") == '0'
    assert sql("SELECT count(*) FROM pg_replication_slots WHERE database='_supabase_" + renamed + "';") == '0'
    expect('owner', 'GET', restored_rest, 404)
    projection(beta)
    assert expect('owner', 'GET', '/api/platform/projects/' + beta + '/api/rest/lifecycle_marker?select=id,value', 200)[0]['value'] == 'original'
    print('PASS step-up protected full API/agent delete; surviving tenant still works', flush=True)
    access_log = run('docker', 'logs', traefik)
    assert 'projects-api@file' in access_log and 'project-' + beta + '@file' in access_log
    result = {'topology': topology, 'validated': ['real-session', 'tls-ca', 'role-matrix', 'immediate-revocation',
              'rest-graphql-storage-vectors', 'api-agent-lifecycle', 'queued-agent-revocation', 'callback-wrong-ca',
              'full-delete', 'api-outage', 'mount-isolation', 'external-opaque-tenant-isolation',
              'replication-slot-scope'], 'benchmark': None}
    if benchmark:
        from p1_benchmark import measure
        result['benchmark'] = measure(suffix, {
            'rest': {'method': 'GET', 'path': '/api/platform/projects/' + beta + '/api/rest/lifecycle_marker?select=id,value'},
            'graphql': {'method': 'POST', 'path': '/api/platform/projects/' + beta + '/api/graphql',
                        'body': {'query': '{ __typename }'}},
            'storage-buckets': {'method': 'GET', 'path': '/api/platform/storage/' + beta + '/buckets'},
            'vector-indexes': {'method': 'GET', 'path': '/api/platform/storage/' + beta + '/vector-buckets/p1-vectors/indexes'},
            'api-projects': {'method': 'GET', 'path': '/api/projects'},
        })
    (root / 'p1-result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    if benchmark and result['benchmark']['errors']:
        raise RuntimeError('Benchmark recorded HTTP errors; no successful performance claim permitted')
