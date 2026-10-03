"""Real Authelia/OpenResty/browser acceptance, isolated from the installed stack.

All credentials and certificates are synthetic. No existing .env, user directory,
Docker socket, host trust store or installed project is mounted. Test-only handlers
are injected into the production nginx configuration; identity/CSRF/TLS aren't mocked.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path
import secrets
import subprocess
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, data: bytes | None = None) -> str:
    result = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = result.stdout.decode('utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed ({result.returncode}): {output}')
    return output.strip()


def fixture_archive() -> bytes:
    # Narrow tracked source allowlist. In particular, never include local .envs,
    # private docs, tarefas.md, .git, or runtime files from studio/authelia.
    paths = ['tools/configure_studio_runtime.py', 'studio/nginx/nginx.conf',
             'studio/nginx/docker-entrypoint.sh', 'studio/authelia/configuration.yml.template',
             'studio/authelia/users_database.yml.example', 'studio/authelia/ids.yml.example',
             'tests/integration/test_studio_real_session.py',
             'studio/redis/start-sessions.sh', 'studio/redis/healthcheck.sh',
             'tests/integration/fixtures/studio_session_probe.conf']
    paths += run('git', '-C', str(ROOT), 'ls-files', 'studio/nginx/lua').splitlines()
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as archive:
        for name in paths:
            if not (ROOT / name).is_file():
                continue
            value = (ROOT / name).read_bytes()
            item = tarfile.TarInfo(name)
            item.size = len(value)
            item.mode = 0o755 if name.endswith('.sh') else 0o644
            archive.addfile(item, io.BytesIO(value))
    return payload.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio-image', required=True)
    parser.add_argument('--authelia-image', required=True)
    parser.add_argument('--redis-image', required=True)
    parser.add_argument('--runtime-image', required=True, help='Linux Python + openssl image')
    parser.add_argument('--browser-image', required=True, help='Built studio_session_browser.Dockerfile')
    parser.add_argument('--ui-image', required=True, help='Production Supabase Studio image')
    args = parser.parse_args()
    for image in (args.studio_image, args.authelia_image, args.redis_image, args.runtime_image, args.browser_image, args.ui_image):
        if run('docker', 'image', 'inspect', image, '--format', '{{.Os}}') != 'linux':
            raise RuntimeError('Existing Linux images required')
    suffix = uuid.uuid4().hex[:12]
    network = 'studio-session-' + suffix
    volume = 'studio-session-config-' + suffix
    containers: list[str] = []
    networks: list[str] = []
    volumes: list[str] = []
    try:
        run('docker', 'network', 'create', network)
        networks.append(network)
        sessions_network = 'studio-sessions-' + suffix
        run('docker', 'network', 'create', '--internal', sessions_network)
        networks.append(sessions_network)
        run('docker', 'volume', 'create', volume)
        volumes.append(volume)
        seed = 'studio-session-seed-' + suffix
        run('docker', 'create', '--name', seed, '--pull=never', '-v', volume + ':/fixture',
            '--entrypoint', 'sleep', args.runtime_image, 'infinity')
        containers.append(seed)
        run('docker', 'start', seed)
        run('docker', 'exec', '-i', seed, 'tar', '-xf', '-', '-C', '/fixture', data=fixture_archive())
        run('docker', 'exec', seed, 'python', '/fixture/tools/configure_studio_runtime.py',
            '--studio-origin', 'https://studio.p1.test', '--force')
        password = secrets.token_urlsafe(24)
        output = run('docker', 'run', '--rm', '--pull=never', args.authelia_image,
                     'authelia', 'crypto', 'hash', 'generate', 'argon2', '--password', password)
        digest = next(line.split('Digest: ', 1)[1] for line in output.splitlines() if 'Digest: ' in line)
        credentials = json.dumps({'username': 'p1_admin', 'password': password})
        # Render only fixture plumbing; keep production auth proxy/CSRF handlers.
        script = '''import json, pathlib, sys
root=pathlib.Path('/fixture')
config=root/'studio/authelia'
(config/'users_database.yml').write_text('users:\\n  p1_admin:\\n    displayname: P1 Admin\\n    password: '+sys.argv[1]+'\\n    email: p1_admin@example.test\\n    groups: [active, admin]\\n')
(root/'browser-credentials.json').write_text(sys.argv[2])
path=root/'studio/nginx/nginx.conf'
text=path.read_text().replace('worker_processes auto;', 'worker_processes 2;')
text=text.replace('error_log /var/log/studio_error.log debug;', 'error_log /dev/stderr notice;')
probe=(root/'tests/integration/fixtures/studio_session_probe.conf').read_text()
text=text.replace('        location = /api/config {', probe+'\\n        location = /api/config {', 1)
attack=''' + repr('''
    server {
        listen 444 ssl;
        ssl_certificate /config/ssl/server.pem;
        ssl_certificate_key /config/ssl/server.key;
        location / {
            default_type text/html;
            return 200 '<form method="POST" action="https://studio.p1.test/api/csrf-probe" target="result"><input name="action" value="disable"></form><iframe name="result"></iframe>';
        }
    }
''') + '''
index=text.rfind('}')
text=text[:index]+attack+text[index:]
path.write_text(text)
'''
        run('docker', 'exec', seed, 'python', '-c', script, digest, credentials)
        config_path = run('docker', 'volume', 'inspect', volume, '--format', '{{.Mountpoint}}')
        # Engine-local binds are synthetic files in our unique named volume.
        config = config_path + '/studio/authelia'
        secrets_path = config_path + '/studio/secrets/authelia'
        redis = 'studio-session-redis-' + suffix
        redis_volume = 'studio-session-redis-data-' + suffix
        run('docker', 'volume', 'create', redis_volume)
        volumes.append(redis_volume)
        run('docker', 'create', '--name', redis, '--pull=never', '--network', sessions_network,
            '--network-alias', 'redis-sessions', '--read-only', '--tmpfs', '/tmp:rw,mode=1777',
            '--memory', '384m', '--cpus', '0.5',
            '-v', redis_volume + ':/data',
            '-v', secrets_path + '/REDIS_SESSION_PASSWORD:/run/secrets/REDIS_SESSION_PASSWORD:ro',
            '-v', config_path + '/studio/redis:/scripts:ro', '--entrypoint', 'sh',
            args.redis_image, '/scripts/start-sessions.sh')
        containers.append(redis)
        run('docker', 'start', redis)
        deadline = time.monotonic() + 30
        while subprocess.run(['docker', 'exec', redis, 'sh', '/scripts/healthcheck.sh'], capture_output=True).returncode:
            if time.monotonic() > deadline:
                raise RuntimeError('Redis session readiness failed')
            time.sleep(0.5)
        authelia = 'studio-session-authelia-' + suffix
        secret_args = []
        for name, variable in [('JWT_SECRET', 'IDENTITY_VALIDATION_RESET_PASSWORD_JWT'),
                               ('SESSION_SECRET', 'SESSION'), ('STORAGE_ENCRYPTION_KEY', 'STORAGE_ENCRYPTION_KEY')]:
            key = 'AUTHELIA_' + variable + ('_SECRET_FILE' if name != 'STORAGE_ENCRYPTION_KEY' else '_FILE')
            secret_args += ['-v', f'{secrets_path}/{name}:/run/secrets/{name}:ro', '-e', f'{key}=/run/secrets/{name}']
        run('docker', 'create', '--name', authelia, '--pull=never', '--network', network,
            '--network-alias', 'authelia', '-v', config + ':/config', *secret_args,
            '-v', secrets_path + '/REDIS_SESSION_PASSWORD:/run/secrets/REDIS_SESSION_PASSWORD:ro',
            '-e', 'AUTHELIA_SESSION_REDIS_PASSWORD_FILE=/run/secrets/REDIS_SESSION_PASSWORD',
            '-e', 'AUTHELIA_SESSION_REDIS_HOST=redis-sessions',
            args.authelia_image, 'authelia', '--config=/config/configuration.runtime.yml')
        containers.append(authelia)
        run('docker', 'network', 'connect', sessions_network, authelia)
        run('docker', 'start', authelia)
        nginx = 'studio-session-nginx-' + suffix
        studio = 'studio-session-ui-' + suffix
        # The actual Studio avoids replacing its upstream with a mock.
        run('docker', 'create', '--name', studio, '--pull=never', '--network', network,
            '--network-alias', 'studio', '-e', 'HOSTNAME=0.0.0.0',
            args.ui_image)
        containers.append(studio)
        run('docker', 'start', studio)
        env = {'STUDIO_SERVICE_KEY_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
               'STUDIO_GATEWAY_HMAC_SECRET': secrets.token_hex(32), 'PROJECTS_API_HMAC_SECRET': secrets.token_hex(32),
               'STUDIO_ANALYTICS_HMAC_SECRET': secrets.token_hex(32), 'NGINX_HMAC_SECRET': secrets.token_hex(32),
               'SERVER_DOMAIN': 'https://studio.p1.test', 'SERVICE_KEY_VERIFY_TLS': 'true',
               'AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE': '/var/run/authelia-cli-secrets/JWT_SECRET',
               'AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE': '/var/run/authelia-cli-secrets/STORAGE_ENCRYPTION_KEY',
               'STUDIO_BOOTSTRAP_TOKEN_FILE': '/run/secrets/STUDIO_BOOTSTRAP_TOKEN'}
        env_args = [part for key, value in env.items() for part in ('-e', key + '=' + value)]
        mounts = ['-v', config + ':/config', '-v', config_path + '/studio/nginx/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro',
                  '-v', config_path + '/studio/nginx/docker-entrypoint.sh:/usr/local/bin/docker-entrypoint.sh:ro']
        for name in ('JWT_SECRET', 'STORAGE_ENCRYPTION_KEY', 'STUDIO_BOOTSTRAP_TOKEN'):
            mounts += ['-v', f'{secrets_path}/{name}:/run/secrets/{name}:ro']
        run('docker', 'create', '--name', nginx, '--pull=never', '--network', network,
            '--network-alias', 'studio.p1.test', '--network-alias', 'nginx', *env_args, *mounts, args.studio_image)
        containers.append(nginx)
        # Merge current source without hiding installed Lua dependencies.
        run('docker', 'cp', str(ROOT / 'studio/nginx/lua') + '/.', nginx + ':/usr/local/openresty/lualib/')
        run('docker', 'start', nginx)
        deadline = time.monotonic() + 90
        while True:
            probe = subprocess.run(['docker', 'exec', nginx, 'curl', '--silent', '--fail', '--cacert', '/config/ssl/ca.pem',
                                    'https://authelia:9091/auth/api/health'], capture_output=True)
            if probe.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Real Authelia readiness failed: ' + run('docker', 'logs', authelia))
            time.sleep(0.5)
        browser = 'studio-session-browser-' + suffix
        run('docker', 'create', '--name', browser, '--pull=never', '--network', network, '--shm-size', '256m',
            '-e', 'NO_PROXY=studio.p1.test',
            '-v', config + '/ssl/ca.pem:/fixture/studio/authelia/ssl/ca.pem:ro',
            '-v', config_path + '/browser-credentials.json:/fixture/browser-credentials.json:ro',
            '-v', config_path + '/tests/integration/test_studio_real_session.py:/test.py:ro',
            args.browser_image, '/test.py')
        containers.append(browser)
        print(run('docker', 'start', '-a', browser))
        if int(run('docker', 'inspect', browser, '--format', '{{.State.ExitCode}}')):
            raise RuntimeError('Required real session test failed')
    except BaseException:
        for name in containers:
            if '-nginx-' in name or '-authelia-' in name:
                print(run('docker', 'logs', '--tail', '25', name))
        raise
    finally:
        cleanup_errors = []
        for name in reversed(containers):
            try:
                print(run('docker', 'rm', '-f', '-v', name))
            except RuntimeError as error:
                cleanup_errors.append(str(error))
        for name in reversed(networks):
            try:
                print(run('docker', 'network', 'rm', name))
            except RuntimeError as error:
                cleanup_errors.append(str(error))
        for name in reversed(volumes):
            try:
                print(run('docker', 'volume', 'rm', name))
            except RuntimeError as error:
                cleanup_errors.append(str(error))
        if cleanup_errors:
            raise RuntimeError('Disposable fixture cleanup failed: ' + '; '.join(cleanup_errors))


if __name__ == '__main__':
    main()
