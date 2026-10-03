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
    renamed = 'p1_renamed_' + suffix
    copied = 'p1_copy_' + suffix
    for image in ('servidor-db:latest', 'servidor-realtime:latest', 'servidor-control-plane-migrations:latest',
                  'supabase/edge-runtime:v1.74.2', 'supabase/supavisor:2.9.7', 'supabase/storage-api:v1.61.12',
                  'nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim', 'darthsim/imgproxy:v4.0.11',
                  'supabase/gotrue:v2.193.0-rc.3', 'postgrest/postgrest:v14.14'):
        assert run('docker', 'image', 'inspect', image, '--format', '{{.Os}}') == 'linux', image
    env_file = server / '.env'
    text = (server / '.env.example').read_text()
    values = {'POSTGRES_PORT': '5432', 'POSTGRES_SHM_SIZE': '256m', 'HOST_PROJECT_ROOT': str(root),
              'FUNCTIONS_VERIFY_JWT': 'true', 'NUM_ACCEPTORS': '4',
              'REALTIME_ERL_AFLAGS': '"+S 2:2 -proto_dist inet_tcp"',
              'POOLER_ERL_AFLAGS': '"+S 2:2 -proto_dist inet_tcp"',
              'SERVER_DOMAIN': 'https://server.p1.test', 'SERVER_PROTO': 'https',
              'PROJECTS_API_ALLOWED_IP_RANGES': '172.50.0.0/16',
              'PUSH_API_URL': 'https://studio.p1.test/api/internal/push',
              'PROJECTS_API_PORT': '18000', 'PG_META_PORT': '8080',
              'STUDIO_CACHE_INVALIDATION_URL': 'https://studio.p1.test', 'PROJECTS_API_STOP_GRACE_PERIOD': '30s'}
    for key in ('POSTGRES_PASSWORD', 'META_GUEST_PASSWORD', 'KEY_AUTHORIZER_DB_PASSWORD',
                'PLATFORM_APP_DB_PASSWORD', 'META_ADMIN_DB_PASSWORD', 'HOST_AGENT_DB_PASSWORD',
                'PLATFORM_READER_DB_PASSWORD', 'JWT_SECRET', 'NGINX_HMAC_SECRET',
                'STUDIO_GATEWAY_HMAC_SECRET', 'PROJECTS_API_HMAC_SECRET', 'HOST_AGENT_HMAC_SECRET',
                'PG_META_CRYPTO_KEY', 'SECRET_KEY_BASE'):
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
                             str(server / 'api-internal/app/opaque_keys.py') + ':/app/opaque_keys.py:ro']
    # Migrations are explicitly completed before startup below.
    authorizer.pop('depends_on')
    model['services']['key-authorizer'] = authorizer
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
    run(*compose, 'up', '-d', '--wait', '--wait-timeout', '180', *services, 'key-authorizer', cwd=server)

    owner = str(uuid.uuid4())
    first_uuid, second_uuid = str(uuid.uuid4()), str(uuid.uuid4())
    sql(f"INSERT INTO users(id,authelia_username) VALUES('{owner}','fixture_owner');")

    gateway_tokens: dict[str, str] = {}

    def seed(ref: str, tenant: str) -> None:
        sql(f"INSERT INTO projects(id,tenant_uuid,name,owner_id) VALUES('{tenant}','{tenant}','{ref}','{owner}');")
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
                    await bootstrap_project_opaque_keys(connection, project_id=uuid.UUID(tenant),
                                                        created_by=uuid.UUID(owner), gateway_token=token)
            finally:
                await connection.close()
        asyncio.run(activate())

    def lifecycle(script: str, *arguments: str) -> None:
        print('Running real lifecycle', script, flush=True)
        if script in {'generate_project.sh', 'duplicate_project.sh'}:
            ref = arguments[0] if script == 'generate_project.sh' else arguments[1]
            run('env', 'API_GATEWAY_TOKEN_PROJETO=' + gateway_tokens[ref], 'bash',
                str(server / 'generateProject' / script), *arguments, cwd=server)
        else:
            run('bash', str(server / 'generateProject' / script), *arguments, cwd=server)

    def check_projection(ref: str, tenant: str) -> dict[str, str]:
        path = server / '.functions-tenants' / (ref + '.json')
        result = json.loads(path.read_text())
        env = environment(server / 'projects' / ref / '.env')
        assert result == {'project_ref': ref, 'project_uuid': tenant,
                          'anon_key': env['ANON_KEY_PROJETO'], 'service_role_key': env['SERVICE_ROLE_KEY_PROJETO'],
                          'jwt_secret': env['JWT_SECRET_PROJETO']}
        assert path.stat().st_mode & 0o777 == 0o600
        data = run('curl', '--fail', '--silent', '--show-error', '-H', 'X-Project-Ref: ' + ref,
                   '-H', 'Authorization: Bearer ' + result['service_role_key'],
                   'http://supabase-edge-functions:9000/p1_probe')
        returned = json.loads(data)['env']
        assert returned['SUPABASE_SERVICE_ROLE_KEY'] == result['service_role_key']
        assert returned['SUPABASE_ANON_KEY'] == result['anon_key']
        assert returned['JWT_SECRET'] == result['jwt_secret']
        assert not {'POSTGRES_PASSWORD', 'DATABASE_URL', 'HOST_AGENT_HMAC_SECRET'} & returned.keys()
        print('Projection and real Edge worker verified:', ref, flush=True)
        return result

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
        host = 'supabase-nginx-' + ref + ':8080'
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

    def check_object(ref: str) -> None:
        assert object_request(ref, 'GET', '/object/p1-files/original.txt', '', 'text/plain') == 'original object'

    # Executor must join the server network, but no HTTP service gets its socket.
    executor = 'p1-lifecycle-executor-' + suffix
    run('docker', 'network', 'connect', 'rede-supabase', executor)
    seed(project, first_uuid)
    lifecycle('generate_project.sh', project, first_uuid, 'false')
    initial = check_projection(project, first_uuid)
    for script, arguments in [('generate_project.sh', ('p1_missing_' + suffix, str(uuid.uuid4()), 'false')),
                              ('duplicate_project.sh', (project, 'p1_missing_' + suffix, 'with-data', str(uuid.uuid4()), first_uuid))]:
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
    sql('CREATE TABLE public.lifecycle_marker(id int primary key, value text); INSERT INTO public.lifecycle_marker VALUES(1,\'original\');', '_supabase_' + project)
    object_request(project, 'POST', '/bucket', '{"id":"p1-files","name":"p1-files","public":false}', 'application/json')
    object_request(project, 'POST', '/object/p1-files/original.txt', 'original object', 'text/plain')
    check_object(project)
    vector_request(project, 'CreateVectorBucket', {'vectorBucketName': 'p1-vectors'})
    vector_request(project, 'CreateIndex', {**vector_identity, 'dataType': 'float32', 'dimension': 3, 'distanceMetric': 'cosine'})
    vector_request(project, 'PutVectors', {**vector_identity, 'vectors': [{'key': 'original', 'data': {'float32': [1, 0, 0]}}]})
    check_vector(project)
    seed(copied, second_uuid)
    lifecycle('duplicate_project.sh', project, copied, 'with-data', second_uuid, first_uuid)
    check_projection(copied, second_uuid)
    check_vector(copied)
    check_object(copied)
    check_signed_gateway(copied, copied, 200)
    check_signed_gateway(copied, copied, 403, tamper=True)
    check_signed_gateway(copied, project, 403)
    print('Real SigV4 gateway: valid signature accepted; forged signature and cross-tenant credential denied', flush=True)
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + copied) == 'original'
    lifecycle('rename_project.sh', project, renamed)
    assert not (server / '.functions-tenants' / (project + '.json')).exists()
    assert (server / '.functions-locks' / (project + '.withdrawn')).is_file()
    check_projection(renamed, first_uuid)
    check_vector(renamed)
    check_object(renamed)
    lifecycle('rotate_key.sh', renamed)
    rotated = check_projection(renamed, first_uuid)
    # rotate_key renews the internal JWT pair, not the tenant signing secret.
    assert rotated['jwt_secret'] == initial['jwt_secret']
    assert rotated['anon_key'] != initial['anon_key']
    assert rotated['service_role_key'] != initial['service_role_key']
    check_projection(copied, second_uuid)
    backup, safety = str(uuid.uuid4()), str(uuid.uuid4())
    lifecycle('backup_project.sh', renamed, backup)
    sql("UPDATE public.lifecycle_marker SET value='changed';", '_supabase_' + renamed)
    object_request(renamed, 'PUT', '/object/p1-files/original.txt', 'changed object', 'text/plain')
    lifecycle('restore_project.sh', renamed, backup, safety)
    assert sql('SELECT value FROM public.lifecycle_marker WHERE id=1;', '_supabase_' + renamed) == 'original'
    check_projection(renamed, first_uuid)
    check_vector(renamed)
    check_object(renamed)
    # The file-removal primitive explicitly requires containers to be gone.
    run('docker', 'compose', '-p', renamed, '--env-file', '../../.env', '--env-file', '.env', 'down', cwd=server / 'projects' / renamed)
    lifecycle('delete_project.sh', renamed)
    assert not (server / 'projects' / renamed).exists()
    assert not (server / '.functions-tenants' / (renamed + '.json')).exists()
    assert (server / '.functions-locks' / (renamed + '.withdrawn')).is_file()
    check_projection(copied, second_uuid)
    config = json.loads(run('docker', 'inspect', 'supabase-edge-functions'))[0]
    assert {m['Destination'] for m in config['Mounts']} == {'/home/deno/functions', '/home/deno/tenant-config'}
    assert config['Config']['Env'] and not any(e.startswith(('POSTGRES_PASSWORD=', 'JWT_SECRET=', 'SUPABASE_SERVICE_ROLE_KEY=')) for e in config['Config']['Env'])
    print('PASS physical create / duplicate / rename / rotate / backup / restore / delete-files + Edge inventory', flush=True)


if __name__ == '__main__':
    main()
