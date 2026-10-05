"""Linux-only physical script drill. Only the isolated host runner may invoke it."""
from __future__ import annotations

import base64
import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid
import urllib.error
import urllib.request

import yaml


def run(*args: str, data: str | None = None, cwd: Path | None = None) -> str:
    result = subprocess.run(args, input=data, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed ({result.returncode}):\n{result.stdout[-16000:]}')
    return result.stdout.strip()


def sql(statement: str, database: str = 'postgres') -> str:
    return run('docker', 'exec', '-i', 'supabase-db', 'psql', '-X', '-q', '-t', '-A',
               '-v', 'ON_ERROR_STOP=1', '-U', 'supabase_admin', '-d', database, data=statement)


def environment(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if re.match(r'^[A-Z][A-Z0-9_]*=', line):
            key, value = line.split('=', 1)
            result[key] = value.strip('"')
    return result


def main() -> None:
    root = Path(sys.argv[1]).resolve(strict=True)
    suffix = sys.argv[2]
    assert re.fullmatch(r'[0-9a-f]{12}', suffix)
    assert root == Path('/var/lib/docker/volumes/p1-lifecycle-root-' + suffix + '/_data')
    server = root / 'servidor'
    labels = {'codex.p1.run': suffix}
    project = 'p1_' + suffix
    new_ref = 'b' * 20
    copied = 'p1_copy_' + suffix
    for image in ('servidor-db:latest', 'servidor-realtime:latest', 'servidor-control-plane-migrations:latest',
                  'supabase/edge-runtime:v1.74.2', 'supabase/supavisor:2.9.7', 'supabase/storage-api:v1.61.12',
                  'nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim', 'darthsim/imgproxy:v4.0.11',
                  'supabase/gotrue:v2.193.0-rc.3', 'postgrest/postgrest:v14.14', 'redis:8.2.2-alpine'):
        assert run('docker', 'image', 'inspect', image, '--format', '{{.Os}}') == 'linux', image
    env_file = server / '.env'
    text = (server / '.env.example').read_text()
    values = {'POSTGRES_PORT': '5432', 'POSTGRES_SHM_SIZE': '256m', 'HOST_PROJECT_ROOT': str(root),
              'FUNCTIONS_VERIFY_JWT': 'true', 'NUM_ACCEPTORS': '4',
              'REALTIME_ERL_AFLAGS': '"+S 2:2 -proto_dist inet_tcp"',
              'POOLER_ERL_AFLAGS': '"+S 2:2 -proto_dist inet_tcp"',
              'SERVER_DOMAIN': 'https://server.p1.test', 'SERVER_URL': 'server.p1.test', 'SERVER_PROTO': 'https',
              'PROJECTS_API_ALLOWED_IP_RANGES': '172.50.0.0/16',
              'PUSH_API_URL': 'https://studio.p1.test/api/internal/push',
               'PROJECTS_API_PORT': '18000', 'PG_META_PORT': '8080',
               'ACCESS_ADMIN_CIDRS': '172.50.0.0/16',
               'STUDIO_CACHE_INVALIDATION_URL': 'https://studio.p1.test', 'PROJECTS_API_STOP_GRACE_PERIOD': '30s'}
    for key in ('POSTGRES_PASSWORD', 'META_GUEST_PASSWORD', 'KEY_AUTHORIZER_DB_PASSWORD',
                'PLATFORM_APP_DB_PASSWORD', 'META_ADMIN_DB_PASSWORD', 'HOST_AGENT_DB_PASSWORD',
                'PLATFORM_READER_DB_PASSWORD', 'CLIENT_CONFIGURATION_DB_PASSWORD', 'JWT_SECRET', 'NGINX_HMAC_SECRET',
                'STUDIO_GATEWAY_HMAC_SECRET', 'PROJECTS_API_HMAC_SECRET', 'HOST_AGENT_HMAC_SECRET',
                'PG_META_CRYPTO_KEY', 'SECRET_KEY_BASE', 'ACCESS_ADMISSION_SECRET',
                'ACCESS_RATE_REDIS_PASSWORD'):
        values[key] = secrets.token_hex(32)
    values['DB_ENC_KEY'] = secrets.token_hex(8)
    values['VAULT_ENC_KEY'] = secrets.token_hex(16)
    values['PG_META_CRYPTO_KEY'] = secrets.token_hex(16)
    for key in ('STUDIO_SERVICE_KEY_ENCRYPTION_KEY', 'PROJECT_SECRETS_MASTER_KEY'):
        values[key] = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    for key, value in values.items():
        pattern = rf'(?m)^{key}=.*$'
        text = re.sub(pattern, lambda _: key + '=' + value, text) if re.search(pattern, text) else text + '\n' + key + '=' + value
    env_file.write_text(text + '\n')
    assert not re.search(r'<[A-Z_]+>', text), 'unresolved example placeholder'
    os.chmod(env_file, 0o600)
    (server / '.storage.env').write_text('SERVER_ADMIN_API_KEYS=' + secrets.token_hex(32) + '\nAUTH_ENCRYPTION_KEY=' + secrets.token_hex(32) + '\n')
    os.chmod(server / '.storage.env', 0o600)
    for name in ('projects', '.functions-tenants', 'volumes/storage/objects', 'certs'):
        (server / name).mkdir(parents=True, exist_ok=True)
    os.chown(server / 'volumes/storage', 1000, 1000)
    os.chown(server / 'volumes/storage/objects', 1000, 1000)
    (server / 'volumes/db/platform-capacity.conf').write_text('# disposable test\n')
    os.chmod(server / '.functions-tenants', 0o700)
    run('python', str(root / 'tools/configure_api_resource_profiles.py'), '--source', str(env_file),
        '--output', str(server / '.resource-profiles.env'))
    services = ('db', 'realtime', 'supavisor', 'functions', 'storage', 'imgproxy', 'storage-data-plane')
    model = yaml.safe_load((server / 'docker-compose.yml').read_text())
    model['services'] = {name: model['services'][name] for name in services}
    for name, service in model['services'].items():
        if 'build' in service:
            service.pop('build')
            service['image'] = {'db': 'servidor-db:latest', 'realtime': 'servidor-realtime:latest'}[name]
        service['logging'] = {'driver': 'json-file'}
        service['labels'] = labels.copy()
        service['restart'] = 'no'
    for network in model['networks'].values():
        network['labels'] = labels.copy()
    assert model['volumes']['db-config'] is None
    model['volumes']['db-config'] = {'name': 'p1-db-config-' + suffix, 'labels': labels.copy()}
    migrations = yaml.safe_load((server / 'docker-compose-api.yml').read_text())['services']['control-plane-migrations']
    migrations.pop('build')
    migrations.update(image='servidor-control-plane-migrations:latest', logging={'driver': 'json-file'}, labels=labels.copy())
    migrations['volumes'] = [str(server / 'api-internal/app') + ':/docker/app:ro']
    model['services']['control-plane-migrations'] = migrations
    authorizer = yaml.safe_load((server / 'docker-compose-api.yml').read_text())['services']['key-authorizer']
    authorizer.pop('build')
    authorizer.update(image='servidor-key-authorizer:latest', logging={'driver': 'json-file'},
                      labels=labels.copy(), restart='no')
    authorizer['volumes'] = [str(server / 'key-authorizer/app.py') + ':/app/app.py:ro',
                             str(server / 'key-authorizer/admission.py') + ':/app/admission.py:ro',
                             str(server / 'api-internal/app/opaque_keys.py') + ':/app/opaque_keys.py:ro',
                             str(server / 'api-internal/app/access_policy.py') + ':/app/access_policy.py:ro',
                             str(server / 'api-internal/app/data') + ':/app/data:ro']
    # Migrations are explicitly completed before startup below.
    authorizer.pop('depends_on')
    model['services']['key-authorizer'] = authorizer
    traffic_redis = yaml.safe_load((server / 'docker-compose-api.yml').read_text())['services']['traffic-redis']
    traffic_redis.update(logging={'driver': 'json-file'}, labels=labels.copy(), restart='no')
    model['services']['traffic-redis'] = traffic_redis
    api_model = yaml.safe_load((server / 'docker-compose-api.yml').read_text())
    referenced = {name for service in model['services'].values()
                  for name in (service.get('networks') or []) if isinstance(name, str)}
    for name in sorted(referenced - set(model['networks'])):
        definition = dict(api_model['networks'][name])
        definition['labels'] = labels.copy()
        model['networks'][name] = definition
    model['volumes']['traffic-rate-data'] = {'name': 'p1-traffic-rate-' + suffix, 'labels': labels.copy()}
    (server / 'p1-compose.yml').write_text(yaml.safe_dump(model, sort_keys=False))
    # Add only test resource ownership/logging plumbing to generated projects.
    template = server / 'generateProject/dockercomposetemplate'
    project_model = yaml.safe_load(template.read_text())
    for service in project_model['services'].values():
        service['labels'] = labels.copy()
        service['logging'] = {'driver': 'json-file'}
        service['restart'] = 'no'
    template.write_text(yaml.safe_dump(project_model, sort_keys=False))
    project_dockerfile = server / 'generateProject/Dockerfile'
    project_dockerfile.write_text(project_dockerfile.read_text() + '\nLABEL codex.p1.run=' + suffix + '\n')
    probe = server / 'volumes/functions/p1_probe'
    probe.mkdir()
    (probe / 'index.ts').write_bytes((root / 'tests/integration/fixtures/functions_probe/index.ts').read_bytes())
    compose = ['docker', 'compose', '-p', 'p1-' + suffix, '--env-file', str(env_file), '-f', str(server / 'p1-compose.yml')]
    print('Starting physical disposable server stack (privileged script boundary, no browser/API claim)', flush=True)
    run(*compose, 'up', '-d', 'db', cwd=server)
    deadline = time.monotonic() + 180
    while subprocess.run(['docker', 'exec', 'supabase-db', 'pg_isready', '-h', '127.0.0.1', '-U', 'supabase_admin', '-d', 'postgres'], stdout=subprocess.DEVNULL).returncode:
        if time.monotonic() > deadline:
            raise RuntimeError('PostgreSQL TCP readiness timeout: ' + run('docker', 'logs', 'supabase-db'))
        time.sleep(1)
    run(*compose, 'run', '--rm', '--no-deps', 'control-plane-migrations', cwd=server)
    run(*compose, 'up', '-d', '--wait', '--wait-timeout', '180', *services, 'traffic-redis', 'key-authorizer', cwd=server)

    if len(sys.argv) > 3:
        assert sys.argv[3] == 'end-to-end' and sys.argv[4] in {'single', 'split'}
        from p1_end_to_end import validate
        run('docker', 'network', 'connect', 'rede-supabase', 'p1-lifecycle-executor-' + suffix)
        validate(root, suffix, sys.argv[4], values, '--benchmark' in sys.argv[5:])
        return

    owner = str(uuid.uuid4())
    first_uuid, second_uuid = str(uuid.uuid4()), str(uuid.uuid4())
    sql(f"INSERT INTO users(id,authelia_username) VALUES('{owner}','fixture_owner');")

    gateway_tokens: dict[str, str] = {}
    public_refs: dict[str, str] = {}
    opaque_keys: dict[str, str] = {}

    def seed(ref: str, tenant: str) -> None:
        public_refs[ref] = "a" * 20 if ref == project else ("c" * 20 if ref == copied else "d" * 20)
        sql(f"INSERT INTO projects(id,tenant_uuid,name,display_name,owner_id,public_ref) VALUES('{tenant}','{tenant}','{ref}','{ref}','{owner}','{public_refs[ref]}');")
        # Same canonical activation primitive/order used by the API before it
        # dispatches create/duplicate. This fixture does not authorize an actor.
        token = secrets.token_hex(32)
        gateway_tokens[ref] = token
        os.environ.update(environment(env_file))
        os.environ['DB_DSN'] = f"postgresql://supabase_admin:{values['POSTGRES_PASSWORD']}@{os.environ['POSTGRES_HOST']}:5432/postgres"
        os.environ['LOGFLARE_PRIVATE_ACCESS_TOKEN'] = secrets.token_hex(32)
        sys.path.insert(0, str(server / 'api-internal'))
        import asyncpg
        from app.opaque_key_service import bootstrap_project_opaque_keys

        async def activate() -> None:
            connection = await asyncpg.connect(os.environ['DB_DSN'])
            try:
                async with connection.transaction():
                    issued = await bootstrap_project_opaque_keys(connection, project_id=uuid.UUID(tenant),
                                                        created_by=uuid.UUID(owner), gateway_token=token)
                    opaque_keys[ref] = issued[1].token
            finally:
                await connection.close()
        asyncio.run(activate())

    def lifecycle(script: str, *arguments: str) -> None:
        print('Running real lifecycle', script, flush=True)
        child_env = os.environ.copy()
        if script in {'generate_project.sh', 'duplicate_project.sh'}:
            ref = arguments[0] if script == 'generate_project.sh' else arguments[1]
            arguments = ((*arguments[:2], public_refs[ref], *arguments[2:])
                         if script == 'generate_project.sh' else (*arguments, public_refs[ref]))
            child_env['API_GATEWAY_TOKEN_PROJETO'] = gateway_tokens[ref]
        else:
            ref = arguments[0]
        sys.path.insert(0, str(server / 'host-agent'))
        from hostagent.commands import (
            RunningCommandState, CommandContext, _run_lifecycle_script,
            CREATE_PROGRESS_EVENTS, DUPLICATE_PROGRESS_EVENTS, ROTATE_PROGRESS_EVENTS,
            REFERENCE_PROGRESS_EVENTS, BACKUP_PROGRESS_EVENTS, RESTORE_PROGRESS_EVENTS,
            DELETE_FILES_PROGRESS_EVENTS,
        )
        contracts = {
            'generate_project.sh': ('create', 'create_project', CREATE_PROGRESS_EVENTS, 5, 70),
            'duplicate_project.sh': ('duplicate', 'duplicate_project', DUPLICATE_PROGRESS_EVENTS, 5, 70),
            'rotate_key.sh': ('rotate_keys', 'rotate_keys', ROTATE_PROGRESS_EVENTS, 10, 80),
            'rename_project.sh': ('rename', 'rename_project', REFERENCE_PROGRESS_EVENTS, 5, 95),
            'backup_project.sh': ('backup', 'backup_project', BACKUP_PROGRESS_EVENTS, 5, 95),
            'restore_project.sh': ('restore', 'restore_project', RESTORE_PROGRESS_EVENTS, 5, 90),
            'delete_project.sh': ('delete', 'delete_project_files', DELETE_FILES_PROGRESS_EVENTS, 82, 89),
        }
        if script not in contracts:
            run('bash', str(server / 'generateProject' / script), *arguments, cwd=server)
            return

        async def observe() -> None:
            import asyncpg
            from app.jobs import configure_jobs, set_job_status
            from app.project_backgrounds import _fail_job_from_command, _job_progress_mirror
            from app.host_agent import wait_command
            from app.job_watch import job_change_hub, job_snapshot
            from hostagent import db
            action, command, events, lower, upper = contracts[script]
            pool = await asyncpg.create_pool(os.environ['DB_DSN'], min_size=1, max_size=3)
            async def provider():
                return pool
            configure_jobs(provider)
            queue = asyncio.Queue()
            updates = []
            job, intent = uuid.uuid4(), uuid.uuid4()
            identity = await pool.fetchrow('SELECT id, public_ref FROM projects WHERE name=$1', ref)
            await pool.execute("""INSERT INTO jobs(job_id,project,project_uuid,public_ref,created_by,action,status,progress)
                VALUES($1,$2,$3,$4,$5,$6,'running',$7)""", job, ref, identity['id'], identity['public_ref'], uuid.UUID(owner), action, lower)
            await pool.execute("""INSERT INTO host_agent_commands(id,job_id,project,project_uuid,command,issued_at,signature,
                timeout_seconds,status,worker_id) VALUES($1,$2,$3,$4,$5,$6,'privileged-fixture',1800,'running','fixture')""",
                intent, job, ref, identity['id'], command, int(time.time()))
            mirror = _job_progress_mirror(str(job), start_progress=lower, end_progress=upper)
            class ObservedState(RunningCommandState):
                def report(self, **kw):
                    super().report(**kw)
                    queue.put_nowait((self.progress, self.current_step, self.message))
            state = ObservedState()
            ctx = CommandContext(SimpleNamespace(root=server, scripts_dir=server / 'generateProject'), state, 1800, command)
            await job_change_hub.start(os.environ['DB_DSN'])
            async def persist():
                while (update := await queue.get()) is not None:
                    progress, step, message = update
                    assert await db.heartbeat_command(pool, intent, 'fixture', 60, progress=progress, current_step=step, message=message)
                    record = await pool.fetchrow('SELECT * FROM host_agent_commands WHERE id=$1', intent)
                    version = job_change_hub.version
                    await mirror(record)
                    await asyncio.wait_for(job_change_hub.wait(version, 2), 3)
                    snapshot = await job_snapshot(pool, {'db_user_id': uuid.UUID(owner), 'is_global_admin': False}, [job])
                    item = next(item for item in snapshot['items'] if item['job_id'] == str(job))
                    assert item['progress'] == lower + progress * (upper - lower) // 100
                    assert item['current_step'] == step and item['message'] == message
                    assert item['status'] == 'running' and item['progress'] < 100
                    updates.append(item)
                    print(f"Live job phase {action}: {item['progress']}% {step}", flush=True)
            consumer = asyncio.create_task(persist())
            try:
                outcome, _ = await _run_lifecycle_script(ctx, script, list(arguments), env=child_env,
                                                        error_code='fixture_failed', progress_events=events)
                queue.put_nowait(None)
                await consumer
                assert outcome.status == 'done', state.stderr_tail()
                assert len(updates) >= 2, (script, updates)
                assert all(a['progress'] <= b['progress'] for a, b in zip(updates, updates[1:]))
                assert await db.finish_command(pool, intent, 'fixture', status='done', progress=state.progress, current_step=state.current_step)
                completed = await pool.fetchrow('SELECT * FROM host_agent_commands WHERE id=$1', intent)
                assert completed['progress'] == 100 and completed['current_step'] == 'completed'
                await set_job_status(str(job), 'done', current_step='completed')
                snapshot = await job_snapshot(pool, {'db_user_id': uuid.UUID(owner), 'is_global_admin': False}, [job])
                item = next(item for item in snapshot['items'] if item['job_id'] == str(job))
                assert item['status'] == 'done' and item['progress'] == 100
                if action == 'create':
                    failed_job, failed_intent = uuid.uuid4(), uuid.uuid4()
                    await pool.execute("""INSERT INTO jobs(job_id,project,project_uuid,public_ref,created_by,action,status,progress)
                        VALUES($1,$2,$3,$4,$5,'duplicate','running',5)""",
                        failed_job, ref, identity['id'], identity['public_ref'], uuid.UUID(owner))
                    await pool.execute("""INSERT INTO host_agent_commands(id,job_id,project,project_uuid,command,issued_at,
                        signature,timeout_seconds,status,worker_id) VALUES($1,$2,$3,$4,'duplicate_project',$5,
                        'privileged-fixture',1800,'running','fixture')""",
                        failed_intent, failed_job, ref, identity['id'], int(time.time()))
                    assert await db.finish_command(pool, failed_intent, 'fixture', status='failed', exit_code=4,
                                                   error_code='fixture_restore_failed', progress=40,
                                                   current_step='restore_database', message='Fixture failure before heartbeat')
                    record = await wait_command(pool, failed_intent,
                                                on_progress=_job_progress_mirror(str(failed_job), start_progress=5, end_progress=70))
                    assert record['progress'] == 40 and record['current_step'] == 'restore_database'
                    await _fail_job_from_command(str(failed_job), record, default_error='fixture_failed',
                                                 message_prefix='Fixture failed')
                    snapshot = await job_snapshot(pool, {'db_user_id': uuid.UUID(owner), 'is_global_admin': False}, [failed_job])
                    item = next(item for item in snapshot['items'] if item['job_id'] == str(failed_job))
                    assert (item['status'], item['progress'], item['current_step']) == ('failed', 31, 'restore_database')
                    print('Terminal failure before heartbeat preserved in persisted job snapshot', flush=True)
            finally:
                if not consumer.done():
                    consumer.cancel()
                    await asyncio.gather(consumer, return_exceptions=True)
                await job_change_hub.close()
                await pool.close()
        asyncio.run(observe())

    def check_projection(ref: str, tenant: str) -> dict[str, str]:
        path = server / '.functions-tenants' / (ref + '.json')
        result = json.loads(path.read_text())
        env = environment(server / 'projects' / ref / '.env')
        assert result == {'project_ref': public_refs[ref], 'technical_name': ref, 'project_uuid': tenant,
                          'anon_key': env['ANON_KEY_PROJETO'], 'service_role_key': env['SERVICE_ROLE_KEY_PROJETO'],
                          'jwt_secret': env['JWT_SECRET_PROJETO']}
        assert path.stat().st_mode & 0o777 == 0o600
        data = run('curl', '--fail', '--silent', '--show-error', '-H', 'X-Project-Ref: ' + public_refs[ref], '-H', 'X-Project-Name: ' + ref,
                   '-H', 'Authorization: Bearer ' + result['service_role_key'],
                   'http://supabase-edge-functions:9000/p1_probe')
        returned = json.loads(data)['env']
        assert returned['SUPABASE_SERVICE_ROLE_KEY'] == result['service_role_key']
        assert returned['SUPABASE_ANON_KEY'] == result['anon_key']
        assert returned['JWT_SECRET'] == result['jwt_secret']
        assert not {'POSTGRES_PASSWORD', 'DATABASE_URL', 'HOST_AGENT_HMAC_SECRET'} & returned.keys()
        print('Projection and real Edge worker verified:', ref, flush=True)
        return result

    def admission_headers(ref: str, uri: str, method: str = 'GET', api_key: str = '') -> dict[str, str]:
        payload = json.dumps({'project_ref': ref, 'gateway_token': gateway_tokens[ref],
                              'uri': '/' + public_refs[ref] + uri, 'method': method,
                              'client_ip': '172.50.200.10', 'api_key': api_key, 'authorization': ''})
        headers = run('curl', '--silent', '--show-error', '--fail', '--output', '/dev/null', '--dump-header', '-',
                      '--request', 'POST', '--header', 'X-Admission-Secret: ' + os.environ['ACCESS_ADMISSION_SECRET'],
                      '--header', 'Content-Type: application/json', '--data-binary', '@-',
                      'http://key-authorizer:18010/v1/admit', data=payload)
        ticket = next(line.split(':', 1)[1].strip() for line in headers.splitlines()
                      if line.lower().startswith('x-gateway-admission:'))
        return {'X-Gateway-Admission': ticket, 'X-Admission-Uri': '/' + public_refs[ref] + uri,
                'X-Admission-Method': method}

    def curl_headers(values: dict[str, str]) -> list[str]:
        return [item for name, value in values.items() for item in ('-H', name + ': ' + value)]

    def check_gateway(ref: str, marker: bool = True) -> None:
        env = environment(server / 'projects' / ref / '.env')
        assert env['API_EXTERNAL_URL'] == 'https://server.p1.test/' + public_refs[ref] + '/auth/v1'
        auth = json.loads(run('curl', '--fail', '--silent', '--show-error',
                              '-H', 'apikey: ' + opaque_keys[ref],
                              *curl_headers(admission_headers(ref, '/auth/v1/health', 'GET', opaque_keys[ref])),
                              'http://supabase-nginx-' + ref + ':8080/auth/v1/health'))
        assert auth['name'] == 'GoTrue'
        if marker:
            sql("NOTIFY pgrst, 'reload schema';", '_supabase_' + ref)
            deadline = time.monotonic() + 20
            while True:
                try:
                    request = urllib.request.Request(
                        'http://supabase-nginx-' + ref + ':8080/rest/v1/lifecycle_marker?select=value',
                        headers={'apikey': opaque_keys[ref],
                                 **admission_headers(ref, '/rest/v1/lifecycle_marker?select=value', 'GET', opaque_keys[ref])})
                    with urllib.request.urlopen(request, timeout=10) as response:
                        assert json.load(response) == [{'value': 'original'}]
                    break
                except urllib.error.HTTPError as error:
                    if error.code != 404 or time.monotonic() > deadline:
                        raise
                    time.sleep(0.2)
        print('Real Auth and REST gateway verified:', public_refs[ref], flush=True)

    def vector_request(ref: str, operation: str, payload: dict) -> dict | None:
        env = environment(server / 'projects' / ref / '.env')
        # Direct privileged Storage API: mutation endpoints intentionally return
        # an empty 200, while read endpoints have JSON. No synthetic body needed.
        command = '''let input='';process.stdin.setEncoding('utf8');
process.stdin.on('data', data => input+=data);
process.stdin.on('end', async () => {
const [tenant, operation] = process.argv.slice(1);
const index = input.indexOf('\\n'); const key=input.slice(0,index);
const response=await fetch('http://127.0.0.1:5000/vector/'+operation, {
method:'POST', headers:{'content-type':'application/json', authorization:'Bearer '+key,
apikey:key, 'x-forwarded-host':tenant+'.storage.internal'}, body:input.slice(index+1),
signal:AbortSignal.timeout(10000)});
const body=await response.text();
if(!response.ok){ console.error('Vector '+operation+' HTTP '+response.status+': '+body);process.exit(1);}
process.stdout.write(JSON.stringify({status:response.status,body}));
});'''
        response = json.loads(run('docker', 'exec', '-i', 'supabase-storage-global', 'node', '-e', command,
                                  env['PROJECT_UUID'], operation,
                                  data=env['SERVICE_ROLE_KEY_PROJETO'] + '\n' + json.dumps(payload)))
        if response['body'] == '':
            assert response['status'] == 200 and operation in {'CreateVectorBucket', 'CreateIndex', 'PutVectors'}
            return None
        return json.loads(response['body'])

    vector_identity = {'vectorBucketName': 'p1-vectors', 'indexName': 'p1-index'}

    def check_vector(ref: str) -> None:
        response = vector_request(ref, 'GetVectors', {**vector_identity, 'keys': ['original'], 'returnData': True})
        assert response is not None
        assert response['vectors'][0]['key'] == 'original'
        assert response['vectors'][0]['data']['float32'] == [1, 0, 0]

    def check_signed_gateway(ref: str, credential_ref: str, expected: int,
                             *, tamper: bool = False) -> None:
        env = environment(server / 'projects' / credential_ref / '.env')
        host = 'supabase-nginx-' + ref + ':8081'
        path, body = '/vector/ListVectorBuckets', b'{}'
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        day = stamp[:8]
        scope = day + '/' + os.environ['STORAGE_S3_REGION'] + '/s3vectors/aws4_request'
        digest = hashlib.sha256(body).hexdigest()
        signed = 'content-type;host;x-amz-content-sha256;x-amz-date'
        headers = f'content-type:application/json\nhost:{host}\nx-amz-content-sha256:{digest}\nx-amz-date:{stamp}\n'
        canonical = '\n'.join(['POST', path, '', headers, signed, digest])
        to_sign = '\n'.join(['AWS4-HMAC-SHA256', stamp, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        key = ('AWS4' + env['S3_PROTOCOL_ACCESS_KEY_SECRET']).encode()
        for item in (day, os.environ['STORAGE_S3_REGION'], 's3vectors', 'aws4_request'):
            key = hmac.digest(key, item.encode(), 'sha256')
        signature = hmac.new(key, to_sign.encode(), 'sha256').hexdigest()
        if tamper:
            signature = ('0' if signature[0] != '0' else '1') + signature[1:]
        request = urllib.request.Request('http://' + host + path, data=body, headers={
            'Content-Type': 'application/json', 'Host': host, 'X-Amz-Date': stamp,
            'X-Amz-Content-Sha256': digest,
            # A source credential must not select its tenant through a clone gateway.
            'X-Forwarded-Host': env['PROJECT_UUID'] + '.storage.internal',
            'Authorization': f'AWS4-HMAC-SHA256 Credential={env["S3_PROTOCOL_ACCESS_KEY_ID"]}/{scope}, SignedHeaders={signed}, Signature={signature}',
        })
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                status, content = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, content = error.code, error.read()
        assert status == expected, (ref, credential_ref, status, content)
        assert isinstance(json.loads(content), dict)

    def object_request(ref: str, method: str, path: str, body: str, mime: str) -> str:
        env = environment(server / 'projects' / ref / '.env')
        command = '''let input='';process.stdin.setEncoding('utf8');
process.stdin.on('data', data=>input+=data);
process.stdin.on('end', async()=>{
const [tenant, method, path, mime]=process.argv.slice(1);
const index=input.indexOf('\\n'), key=input.slice(0,index);
const response=await fetch('http://127.0.0.1:5000'+path,{method,
headers:{authorization:'Bearer '+key,'content-type':mime,'x-forwarded-host':tenant+'.storage.internal'},
body:method==='GET'?undefined:input.slice(index+1),signal:AbortSignal.timeout(10000)});
const body=await response.text();if(!response.ok){console.error(response.status+': '+body);process.exit(1);}
process.stdout.write(body);});'''
        return run('docker', 'exec', '-i', 'supabase-storage-global', 'node', '-e', command,
                   env['PROJECT_UUID'], method, path, mime, data=env['SERVICE_ROLE_KEY_PROJETO'] + '\n' + body)

    def check_internal_auth_boundary(ref: str) -> None:
        env = environment(server / 'projects' / ref / '.env')
        for method, authorization, expected in [('POST', None, 403),
                                                 ('POST', 'Bearer ' + env['SERVICE_ROLE_KEY_PROJETO'], 403),
                                                 ('GET', None, 405)]:
            request = urllib.request.Request('http://supabase-nginx-' + ref + ':8081/vector/ListVectorBuckets',
                                             data=b'{}' if method == 'POST' else None, method=method)
            if authorization:
                request.add_header('Authorization', authorization)
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    status = response.status
            except urllib.error.HTTPError as error:
                status = error.code
            assert status == expected, (method, status)

    def check_object(ref: str) -> None:
        assert object_request(ref, 'GET', '/object/p1-files/original.txt', '', 'text/plain') == 'original object'

    # Executor must join the server network, but no HTTP service gets its socket.
    executor = 'p1-lifecycle-executor-' + suffix
    run('docker', 'network', 'connect', 'rede-supabase', executor)
    seed(project, first_uuid)
    lifecycle('generate_project.sh', project, first_uuid, 'false')
    initial = check_projection(project, first_uuid)
    for script, arguments in [('generate_project.sh', ('p1_missing_' + suffix, str(uuid.uuid4()), 'd' * 20, 'false')),
                              ('duplicate_project.sh', (project, 'p1_missing_' + suffix, 'with-data', str(uuid.uuid4()), first_uuid, 'd' * 20))]:
        for token in (None, 'not-a-canonical-gateway-token'):
            child_env = os.environ.copy()
            child_env.pop('API_GATEWAY_TOKEN_PROJETO', None)
            if token is not None:
                child_env['API_GATEWAY_TOKEN_PROJETO'] = token
            result = subprocess.run(['bash', str(server / 'generateProject' / script), *arguments],
                                    capture_output=True, text=True, env=child_env, cwd=server)
            assert result.returncode != 0 and 'API_GATEWAY_TOKEN_PROJETO canonico' in result.stderr
            assert not (server / 'projects' / ('p1_missing_' + suffix)).exists()
            assert sql("SELECT count(*) FROM pg_database WHERE datname='_supabase_p1_missing_" + suffix + "';") == '0'
    print('Missing/invalid gateway tokens fail closed before physical mutation', flush=True)
    sql("""CREATE TABLE public.lifecycle_marker(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, value text);
        INSERT INTO public.lifecycle_marker(value) VALUES('original');
        CREATE TABLE public.lifecycle_serial(id bigserial PRIMARY KEY, value text);
        INSERT INTO public.lifecycle_serial(value) VALUES('original');
        CREATE SEQUENCE public.lifecycle_independent;""", '_supabase_' + project)
    object_request(project, 'POST', '/bucket', '{"id":"p1-files","name":"p1-files","public":false}', 'application/json')
    object_request(project, 'POST', '/object/p1-files/original.txt', 'original object', 'text/plain')
    check_object(project)
    check_gateway(project)
    vector_request(project, 'CreateVectorBucket', {'vectorBucketName': 'p1-vectors'})
    vector_request(project, 'CreateIndex', {**vector_identity, 'dataType': 'float32', 'dimension': 3, 'distanceMetric': 'cosine'})
    vector_request(project, 'PutVectors', {**vector_identity, 'vectors': [{'key': 'original', 'data': {'float32': [1, 0, 0]}}]})
    check_vector(project)
    lifecycle('operations/setup_vector_bucket_wrapper.sh', project, 'p1-vectors')
    sql("CREATE SCHEMA vector_client; IMPORT FOREIGN SCHEMA \"p1-vectors\" FROM SERVER p1_vectors_fdw_server INTO vector_client OPTIONS(strict 'true');", '_supabase_' + project)
    assert sql('SELECT count(*) FROM vector_client.p1_index;', '_supabase_' + project) == '1'
    seed(copied, second_uuid)
    lifecycle('duplicate_project.sh', project, copied, 'with-data', second_uuid, first_uuid)
    check_projection(copied, second_uuid)
    check_gateway(copied)
    check_vector(copied)
    check_object(copied)
    check_signed_gateway(copied, copied, 200)
    check_signed_gateway(copied, copied, 403, tamper=True)
    check_signed_gateway(copied, project, 403)
    check_internal_auth_boundary(copied)
    clone_db = '_supabase_' + copied
    clone_role = 'tenant_meta_' + second_uuid.replace('-', '')
    source_role = 'tenant_meta_' + first_uuid.replace('-', '')
    assert sql(f"SELECT has_database_privilege('{source_role}', current_database(), 'CONNECT');", clone_db) == 'f'
    owners = sql("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('lifecycle_marker','lifecycle_marker_id_seq','lifecycle_serial','lifecycle_serial_id_seq','lifecycle_independent') AND c.relowner=" + "'" + clone_role + "'::regrole;", clone_db)
    assert owners == '5', owners
    assert sql("INSERT INTO public.lifecycle_marker(value) VALUES('clone') RETURNING id;", clone_db).splitlines()[0] == '2'
    assert sql("INSERT INTO public.lifecycle_serial(value) VALUES('clone') RETURNING id;", clone_db).splitlines()[0] == '2'
    sql("CREATE SCHEMA vector_client_clone; IMPORT FOREIGN SCHEMA \"p1-vectors\" FROM SERVER p1_vectors_fdw_server INTO vector_client_clone OPTIONS(strict 'true');", clone_db)
    assert sql('SELECT count(*) FROM vector_client_clone.p1_index;', clone_db) == '1'
    assert sql("SELECT count(*) FROM pg_foreign_table;", clone_db) == '1'
    assert sql("SELECT bool_and(srvoptions::text LIKE '%:8081/vector%') FROM pg_foreign_server;", clone_db) == 't'
    vector_request(copied, 'PutVectors', {**vector_identity, 'vectors': [{'key': 'clone-only', 'data': {'float32': [0, 1, 0]}}]})
    assert sql('SELECT count(*) FROM vector_client_clone.p1_index;', clone_db) == '2'
    assert sql('SELECT count(*) FROM vector_client.p1_index;', '_supabase_' + project) == '1'
    run('docker', 'stop', 'supabase-nginx-' + copied)
    try:
        failed_probe = subprocess.run(['bash', str(server / 'generateProject/operations/setup_vector_bucket_wrapper.sh'),
                                       copied, 'p1-vectors'], capture_output=True, text=True, cwd=server)
        assert failed_probe.returncode != 0
        assert sql("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'vector_wrapper_probe_%';", clone_db) == '0'
    finally:
        run('docker', 'start', 'supabase-nginx-' + copied)
    assert sql('SELECT count(*) FROM vector_client_clone.p1_index;', clone_db) == '2'
    print('Real SigV4 gateway: valid signature accepted; forged signature and cross-tenant credential denied', flush=True)
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + copied) == 'original'
    job_id = str(uuid.uuid4())
    sql(f'''INSERT INTO jobs(job_id,project,project_uuid,created_by,action,status,public_ref,payload) VALUES('{job_id}','{project}','{first_uuid}','{owner}','rename','running','{public_refs[project]}','{{"actor_user_id":"{owner}","old_ref":"{public_refs[project]}","new_ref":"{new_ref}"}}'::jsonb);''')
    sql(f"INSERT INTO project_reference_history(project_id,old_ref,new_ref,status,actor_user_id,job_id) VALUES('{first_uuid}','{public_refs[project]}','{new_ref}','running','{owner}','{job_id}');")
    old_ref = public_refs[project]
    lifecycle('rename_project.sh', project, first_uuid, first_uuid, old_ref, new_ref)
    public_refs[project] = new_ref
    assert sql(f"SELECT public_ref FROM projects WHERE id='{first_uuid}';") == new_ref
    assert sql(f"SELECT public_ref FROM jobs WHERE job_id='{job_id}';") == old_ref
    assert (server / 'projects' / project).is_dir()
    assert not (server / 'projects' / new_ref).exists()
    status = run('curl', '--silent', '-o', '/dev/null', '-w', '%{http_code}',
                 '-H', 'X-Project-Ref: ' + old_ref, '-H', 'X-Project-Name: ' + project,
                 '-H', 'Authorization: Bearer ' + initial['service_role_key'],
                 'http://supabase-edge-functions:9000/p1_probe')
    assert status == '503', status
    sql(f"UPDATE project_reference_history SET status='succeeded' WHERE job_id='{job_id}'; UPDATE jobs SET status='done' WHERE job_id='{job_id}';")
    check_projection(project, first_uuid)
    check_gateway(project)
    check_vector(project)
    check_object(project)
    lifecycle('rotate_key.sh', project)
    rotated = check_projection(project, first_uuid)
    # rotate_key renews the internal JWT pair, not the tenant signing secret.
    assert rotated['jwt_secret'] == initial['jwt_secret']
    assert rotated['anon_key'] != initial['anon_key']
    assert rotated['service_role_key'] != initial['service_role_key']
    assert sql('SELECT count(*) FROM vector_client.p1_index;', '_supabase_' + project) == '1'
    check_projection(copied, second_uuid)
    backup, safety = str(uuid.uuid4()), str(uuid.uuid4())
    lifecycle('backup_project.sh', project, backup)
    sql("UPDATE public.lifecycle_marker SET value='changed';", '_supabase_' + project)
    object_request(project, 'PUT', '/object/p1-files/original.txt', 'changed object', 'text/plain')
    vector_request(project, 'PutVectors', {**vector_identity, 'vectors': [{'key': 'original', 'data': {'float32': [0, 0, 1]}}]})
    lifecycle('restore_project.sh', project, backup, safety)
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + project) == 'original'
    check_projection(project, first_uuid)
    check_gateway(project)
    check_vector(project)
    check_object(project)
    assert sql('SELECT count(*) FROM vector_client.p1_index;', '_supabase_' + project) == '1'
    assert sql('SELECT count(*) FROM vector_client_clone.p1_index;', clone_db) == '2'
    # The file-removal primitive explicitly requires containers to be gone.
    run('docker', 'compose', '-p', project, '--env-file', '../../.env', '--env-file', '.env', 'down', cwd=server / 'projects' / project)
    lifecycle('delete_project.sh', project)
    assert not (server / 'projects' / project).exists()
    assert not (server / '.functions-tenants' / (project + '.json')).exists()
    assert (server / '.functions-locks' / (project + '.withdrawn')).is_file()
    check_projection(copied, second_uuid)
    schema_only = 'schema_copy_' + suffix
    third_uuid = str(uuid.uuid4())
    seed(schema_only, third_uuid)
    lifecycle('duplicate_project.sh', copied, schema_only, 'schema-only', third_uuid, second_uuid)
    check_projection(schema_only, third_uuid)
    check_gateway(schema_only, marker=False)
    assert sql('SELECT count(*) FROM public.lifecycle_marker;', '_supabase_' + schema_only) == '0'
    assert sql('SELECT count(*) FROM storage.objects;', '_supabase_' + schema_only) == '0'
    assert sql('SELECT count(*) FROM storage.vector_indexes;', '_supabase_' + schema_only) == '0'
    assert sql("SELECT count(*) FROM pg_tables WHERE schemaname='storage_vectors' AND tablename <> 'migrations';", '_supabase_' + schema_only) == '0'
    assert sql('SELECT count(*) FROM pg_foreign_server;', '_supabase_' + schema_only) == '0'
    vector_request(schema_only, 'CreateVectorBucket', {'vectorBucketName': 'fresh-vectors'})
    vector_request(schema_only, 'CreateIndex', {'vectorBucketName': 'fresh-vectors', 'indexName': 'fresh-index', 'dataType': 'float32', 'dimension': 3, 'distanceMetric': 'cosine'})
    lifecycle('operations/setup_vector_bucket_wrapper.sh', schema_only, 'fresh-vectors')
    check_signed_gateway(schema_only, copied, 403)
    config = json.loads(run('docker', 'inspect', 'supabase-edge-functions'))[0]
    assert {m['Destination'] for m in config['Mounts']} == {'/home/deno/functions', '/home/deno/tenant-config'}
    assert config['Config']['Env'] and not any(e.startswith(('POSTGRES_PASSWORD=', 'JWT_SECRET=', 'SUPABASE_SERVICE_ROLE_KEY=')) for e in config['Config']['Env'])
    print('PASS physical create / duplicate / rename / rotate / backup / restore / delete-files + Edge inventory', flush=True)


if __name__ == '__main__':
    main()
