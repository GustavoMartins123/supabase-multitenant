"""Mandatory auth/SQL/directory checks on an exclusively disposable Docker cluster.

Never accepts an external DSN. The SQL tests alter cluster grants. The directory
harness mocks Authelia's ID exporter, not the YAML/lock/sequence/HMAC protocol.
This does not claim full Authelia/Traefik/Storage end-to-end coverage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> str:
    return subprocess.check_output(list(args), text=True, stderr=subprocess.STDOUT)


def mount(source: Path, target: str) -> list[str]:
    return ['--mount', f'type=bind,src={source.resolve()},dst={target},readonly']


def port(container: str, service: str) -> str:
    return json.loads(run('docker', 'inspect', container))[0]['NetworkSettings']['Ports'][service][0]['HostPort']


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres-image', required=True)
    parser.add_argument('--postgres-user', required=True)
    parser.add_argument('--studio-image', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', args.postgres_user):
        parser.error('canonical PostgreSQL user required')
    for image in (args.postgres_image, args.studio_image):
        if run('docker', 'image', 'inspect', image, '--format', '{{.Os}}').strip() != 'linux':
            raise RuntimeError('existing Linux image required')
    suffix = uuid.uuid4().hex[:12]
    database = 'auth-security-db-' + suffix
    directory = 'auth-security-directory-' + suffix
    password = secrets.token_hex(24)
    started: list[str] = []
    try:
        run('docker', 'run', '-d', '--pull=never', '--name', database, '-p', '127.0.0.1::5432',
            '-e', 'POSTGRES_USER=' + args.postgres_user, '-e', 'POSTGRES_PASSWORD=' + password,
            '-e', 'POSTGRES_DB=postgres', args.postgres_image)
        started.append(database)
        deadline = time.monotonic() + 180
        while True:
            # initdb's temporary server accepts Unix sockets before the final
            # TCP server is ready. Prove the same transport the tests will use.
            probe = subprocess.run(['docker', 'exec', database, 'pg_isready', '-h', '127.0.0.1', '-U', args.postgres_user, '-d', 'postgres'], capture_output=True)
            if probe.returncode == 0:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('PostgreSQL startup timeout: ' + run('docker', 'logs', database))
            time.sleep(0.5)
        fixtures = ROOT / 'tests/integration/fixtures'
        run('docker', 'run', '-d', '--pull=never', '--name', directory, '-p', '127.0.0.1::8080', '--tmpfs', '/config',
            '-e', 'PROJECTS_API_HMAC_SECRET=' + '2' * 64, '-e', 'STUDIO_GATEWAY_HMAC_SECRET=' + '1' * 64,
            '-e', 'NGINX_HMAC_SECRET=' + 'n' * 48, '-e', 'SERVER_DOMAIN=http://127.0.0.1:8080',
            *mount(ROOT / 'studio/nginx/lua', '/workspace/studio/nginx/lua'),
            *mount(fixtures / 'studio_directory.nginx.conf', '/workspace/tests/integration/fixtures/studio_directory.nginx.conf'),
            *mount(fixtures / 'studio_directory_start.sh', '/workspace/tests/integration/fixtures/studio_directory_start.sh'),
            *mount(fixtures / 'fernet_clock_probe.lua', '/workspace/tests/integration/fixtures/fernet_clock_probe.lua'),
            *mount(fixtures / 'identifiers_batch_probe.lua', '/workspace/tests/integration/fixtures/identifiers_batch_probe.lua'),
            '--entrypoint', 'sh', args.studio_image, '/workspace/tests/integration/fixtures/studio_directory_start.sh')
        started.append(directory)
        url = 'http://127.0.0.1:' + port(directory, '8080/tcp')
        deadline = time.monotonic() + 60
        while True:
            try:
                urllib.request.urlopen(url + '/internal/users/directory', timeout=2).close()
            except urllib.error.HTTPError as error:
                error.close()
                if error.code == 401:
                    break
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('OpenResty startup timeout: ' + run('docker', 'logs', directory))
            time.sleep(0.5)
        dsn = f'postgresql://{args.postgres_user}:{password}@127.0.0.1:{port(database, "5432/tcp")}/postgres'
        issued = int(run('docker', 'exec', directory, 'date', '+%s').strip())
        key = Fernet.generate_key()
        cipher = Fernet(key)
        tokens = {'key': key.decode(),
                  'valid': cipher.encrypt_at_time(b'sb_secret_synthetic', issued).decode(),
                  'future': cipher.encrypt_at_time(b'sb_secret_synthetic', issued + 60).decode(),
                  'expired': cipher.encrypt_at_time(b'sb_secret_synthetic', issued - 120).decode()}
        checked = subprocess.run(['docker', 'exec', '-i', directory, '/usr/local/openresty/bin/resty',
                                  '-I', '/workspace/studio/nginx/lua',
                                  '/workspace/tests/integration/fixtures/fernet_clock_probe.lua'],
                                 input=json.dumps(tokens), text=True, capture_output=True)
        if checked.returncode:
            raise RuntimeError('Required actual OpenResty Fernet clock/interoperability checks failed')
        print(checked.stdout.strip())
        checked = subprocess.run(['docker', 'exec', directory, '/usr/local/openresty/bin/resty',
                                  '-I', '/workspace/studio/nginx/lua',
                                  '/workspace/tests/integration/fixtures/identifiers_batch_probe.lua'],
                                 text=True, capture_output=True)
        if checked.returncode:
            raise RuntimeError('Required actual OpenResty identity batch checks failed: ' + checked.stderr)
        print(checked.stdout.strip())
        # Separate interpreters preserve each module's import-time environment.
        script = '''import importlib.util, os, sys, unittest
os.environ['CONTROL_PLANE_TEST_DSN'] = sys.argv[2]
os.environ['TENANT_SQL_TEST_ADMIN_DSN'] = sys.argv[2]
os.environ['STUDIO_DIRECTORY_TEST_URL'] = sys.argv[3]
spec = importlib.util.spec_from_file_location('required_security_test', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
sys.exit(0 if result.wasSuccessful() and not result.skipped and result.testsRun > 0 else 1)
'''
        for relative in ('tests/smoke/test_authorization_behavior.py', 'tests/integration/test_studio_directory.py',
                         'tests/integration/test_tenant_sql_isolation.py'):
            # Stream output; do not include the synthetic DSN in failure messages.
            status = subprocess.call([sys.executable, '-c', script, str(ROOT / relative), dsn, url])
            if status != 0:
                raise RuntimeError('required checks failed or skipped: ' + relative)
    finally:
        for container in reversed(started):
            print(run('docker', 'rm', '-f', '-v', container).strip())


if __name__ == '__main__':
    main()
