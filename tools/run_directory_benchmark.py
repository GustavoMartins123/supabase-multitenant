"""Microbenchmark real canonical directory snapshots, never installation/auth load.

Only synthetic complete YAML/identity files are copied into a labelled tmpfs
container. Missing images/modules or invalid snapshots are explicit errors.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import subprocess
import uuid

from run_studio_session_tests import run

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--studio-image', required=True)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    if run('docker', 'image', 'inspect', args.studio_image, '--format', '{{.Os}}').strip() != 'linux':
        raise RuntimeError('Existing Linux OpenResty image required')
    name = 'directory-benchmark-' + uuid.uuid4().hex[:12]
    label = 'codex.directory.benchmark'
    results = []
    run('docker', 'create', '--name', name, '--pull=never', '--label', label + '=' + name,
        '--tmpfs', '/config:rw,mode=1777', '--entrypoint', 'sleep', args.studio_image, 'infinity')
    try:
        run('docker', 'start', name)
        # Engine-local copy avoids Windows filesystem latency in the measurement.
        run('docker', 'cp', str(ROOT / 'studio/nginx/lua') + '/.', name + ':/usr/local/openresty/lualib/')
        run('docker', 'cp', str(ROOT / 'tests/integration/fixtures/directory_benchmark.lua'), name + ':/probe.lua')
        for count in (25, 100, 500):
            users = {'bench_' + str(n): {'displayname': 'Synthetic benchmark', 'email': f'bench{n}@example.test',
                                        'groups': ['active'], 'password': 'not-a-login-credential'} for n in range(count)}
            ids = [{'username': username, 'identifier': str(uuid.uuid5(uuid.NAMESPACE_DNS, username)),
                    'service': 'openid', 'sector': ''} for username in users]
            for filename, document in [('users_database.yml', {'users': users}), ('ids.yml', {'identifiers': ids})]:
                # Docker's archive API is not the writer for a running tmpfs.
                # Write through the container namespace, using only fixed filenames.
                run('docker', 'exec', '-i', name, 'sh', '-c', 'cat > /config/' + filename,
                    data=json.dumps(document).encode())
            checked = subprocess.run(['docker', 'exec', '-e', 'DIRECTORY_BENCHMARK_USERS=' + str(count), name,
                                      '/usr/local/openresty/bin/resty', '/probe.lua'], capture_output=True, text=True)
            if checked.returncode:
                raise RuntimeError('Directory benchmark failed: ' + checked.stderr)
            result = json.loads(checked.stdout)
            result['median_ms'] = round(statistics.median(m['milliseconds'] for m in result['measurements']), 2)
            results.append(result)
            print(json.dumps(result), flush=True)
        image = json.loads(run('docker', 'inspect', name))[0]['Image']
    finally:
        record = json.loads(run('docker', 'inspect', name))[0]
        if record['Config']['Labels'][label] != name:
            raise RuntimeError('Benchmark cleanup ownership check failed')
        run('docker', 'rm', '-f', '-v', name)
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps({'method': 'production read_locked(false); 5 rounds; engine-local tmpfs',
                                     'image': image, 'results': results}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
