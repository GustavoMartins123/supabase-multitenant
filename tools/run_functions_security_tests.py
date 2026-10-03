"""Run mandatory Functions security checks with isolated synthetic Docker fixtures.

Images must already exist locally; this runner never downloads or uses production
configuration. Windows and Linux use the same explicit Docker test backend.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> str:
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed ({result.returncode}): {result.stdout}')
    return result.stdout


def mount(source: Path, target: str, readonly: bool = True) -> list[str]:
    return ['--mount', f'type=bind,src={source.resolve()},dst={target}' + (',readonly' if readonly else '')]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lifecycle-image', required=True)
    parser.add_argument('--edge-image', required=True)
    args = parser.parse_args()
    for image in (args.lifecycle_image, args.edge_image):
        if run('docker', 'image', 'inspect', image, '--format', '{{.Os}}').strip() != 'linux':
            raise SystemExit('Linux Docker image required')
    with tempfile.TemporaryDirectory(prefix='functions-security-') as name:
        fixture = Path(name)
        scripts = fixture / 'servidor/generateProject'
        (scripts / 'lib').mkdir(parents=True)
        for path in ('functions_config.py', 'lib/functions_config.sh',
                     'lib/backup_project_impl.sh', 'lib/restore_project_impl.sh'):
            shutil.copy2(ROOT / 'servidor/generateProject' / path, scripts / path)
        tests = fixture / 'tests/integration'
        tests.mkdir(parents=True)
        shutil.copy2(ROOT / 'tests/integration/test_functions_projection_lifecycle.py', tests)
        lifecycle_checks = '''import sys, unittest
suite = unittest.defaultTestLoader.discover('tests/integration', pattern='test_functions_projection_lifecycle.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() and not result.skipped and result.testsRun >= 7 else 1)
'''
        print(run('docker', 'run', '--rm', '--pull=never', '--entrypoint', 'python3', *mount(fixture, '/workspace'),
                  '-w', '/workspace', args.lifecycle_image, '-c', lifecycle_checks))
        server = fixture / 'runtime'
        for index, ref in enumerate(('test_alpha', 'test_beta')):
            directory = server / 'projects' / ref
            directory.mkdir(parents=True)
            (directory / '.env').write_text(f'PROJECT_ID={ref}\nPROJECT_UUID=11111111-1111-4111-8111-11111111111{index}\nPROJECT_PUBLIC_REF={chr(97+index)*20}\n'
                f'ANON_KEY_PROJETO=synthetic-anon-{ref}\nSERVICE_ROLE_KEY_PROJETO=synthetic-service-{ref}\n'
                f'JWT_SECRET_PROJETO={ref}-synthetic-jwt-secret-for-test-only\n'
                'POSTGRES_PASSWORD=synthetic-global-secret-never-project\n', encoding='utf-8')
        # Linux preserves ownership across bind mounts. Write the private files
        # as the test runner's UID, not root; Desktop/Windows uses its bind ACLs.
        user: list[str]
        if sys.platform == 'win32':
            user = []
        elif sys.platform == 'linux':
            user = ['--user', f'{os.getuid()}:{os.getgid()}']
        else:
            raise RuntimeError('this harness supports Windows/Desktop and Linux')
        print(run('docker', 'run', '--rm', '--pull=never', *user, '--entrypoint', 'python3', *mount(scripts / 'functions_config.py', '/config.py'),
                  *mount(server, '/fixture', readonly=False), args.lifecycle_image, '/config.py', '--root', '/fixture', 'sync'))
        functions = fixture / 'functions'
        for path in ('main', 'hello'):
            shutil.copytree(ROOT / 'servidor/volumes/functions' / path, functions / path)
        shutil.copytree(ROOT / 'tests/integration/fixtures/functions_probe', functions / 'probe')
        container = 'functions-security-' + uuid.uuid4().hex[:12]
        config = server / '.functions-tenants'
        started = False
        try:
            run('docker', 'run', '-d', '--pull=never', '--name', container, '-p', '127.0.0.1::9000', '-e', 'VERIFY_JWT=true',
                *mount(functions, '/home/deno/functions'), *mount(config, '/home/deno/tenant-config'),
                args.edge_image, 'start', '--main-service', '/home/deno/functions/main')
            started = True
            port = json.loads(run('docker', 'inspect', container))[0]['NetworkSettings']['Ports']['9000/tcp'][0]['HostPort']
            url = f'http://127.0.0.1:{port}'
            deadline = time.monotonic() + 180
            while True:
                try:
                    urllib.request.urlopen(url + '/hello', timeout=2).close()
                except urllib.error.HTTPError as error:
                    error.close()
                    if error.code == 400:
                        break
                except OSError:
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError('Edge Runtime startup timeout: ' + run('docker', 'logs', container))
                time.sleep(0.5)
            run('docker', 'exec', container, 'sh', '-ec', 'test ! -e /home/deno/projects; test ! -e /docker/.env')
            mounts = json.loads(run('docker', 'inspect', container))[0]['Mounts']
            if len(mounts) != 2 or any(m['RW'] for m in mounts):
                raise RuntimeError('unexpected supervisor mount contract')
            os.environ['FUNCTIONS_TENANT_TEST_URL'] = url
            os.environ['FUNCTIONS_PROJECTION_TEST_DIR'] = str(config)
            spec = importlib.util.spec_from_file_location('functions_security_boundary', ROOT / 'tests/integration/test_functions_tenant_boundary.py')
            if spec is None or spec.loader is None:
                raise RuntimeError('required boundary test module unavailable')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
            if not result.wasSuccessful() or result.skipped or result.testsRun != 6:
                raise RuntimeError('required Functions security checks failed or skipped')
        finally:
            if started:
                print(run('docker', 'rm', '-f', container).strip())


if __name__ == '__main__':
    main()
