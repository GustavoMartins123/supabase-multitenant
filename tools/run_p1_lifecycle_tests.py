"""Physical privileged lifecycle drill on a disposable production-derived stack.

Requires a free Docker engine namespace for canonical lifecycle container/network
names. Refuses collisions; never accepts installation paths or external DSNs.
This is not the browser/API authorization matrix. Docker socket access is granted
only to the privileged disposable test executor, never to an HTTP component.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import uuid

from run_studio_session_tests import run

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'codex.p1.run'
RESERVED_CONTAINERS = {
    'supabase-db', 'supabase-pooler', 'realtime-dev.supabase-realtime', 'supabase-edge-functions',
    'supabase-storage-global', 'shared-storage-data-plane', 'supabase-imgproxy-global',
    'projects-api', 'key-authorizer', 'postgres-meta-global', 'control-plane-migrations',
    'supabase-analytics', 'supabase-vector-global', 'supabase-studio', 'nginx', 'authelia',
    'traefik-traefik-1', 'traefik-geoip-api-1', 'supabase-traefik-config-watcher', 'traefik-deny-service',
}
RESERVED_NETWORKS = {'rede-supabase', 'supabase-storage-control', 'supabase-storage-data-plane',
                     'supabase-storage-gateways', 'supabase-analytics-internal'}


def archive(extra_sources: tuple[str, ...] = ()) -> bytes:
    allowed = ('servidor/generateProject/', 'servidor/volumes/db/', 'servidor/volumes/functions/',
               'servidor/volumes/pooler/', 'servidor/volumes/storage-proxy/', 'servidor/api-internal/app/',
               'servidor/auth_template/', 'servidor/host-agent/hostagent/')
    exact = {'servidor/.env.example', 'servidor/docker-compose.yml', 'servidor/docker-compose-api.yml',
             'servidor/docker-compose.single-node.yml', 'servidor/docker-compose.split-node.yml',
             'servidor/key-authorizer/app.py',
             'tools/configure_api_resource_profiles.py'}
    paths = [p for p in run('git', '-C', str(ROOT), 'ls-files').splitlines()
             if (p in exact or p.startswith(allowed)) and (ROOT / p).is_file()]
    paths += ['tests/integration/fixtures/p1_lifecycle.py', 'tests/integration/fixtures/functions_probe/index.ts',
              'servidor/generateProject/lib/vector_rekey_sql.py']
    paths.extend(extra_sources)
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w') as tar:
        for name in sorted(set(paths)):
            content = (ROOT / name).read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            entry.mode = 0o755 if name.endswith('.sh') else 0o644
            tar.addfile(entry, io.BytesIO(content))
    return payload.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executor-image', required=True)
    args = parser.parse_args()
    execute(args.executor_image)


def execute(executor_image: str, *, fixture_arguments: tuple[str, ...] = (),
            extra_sources: tuple[str, ...] = (), result_file: Path | None = None) -> None:
    assert isinstance(sys.stdout, io.TextIOWrapper) and isinstance(sys.stderr, io.TextIOWrapper), 'CLI text streams required'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    collisions = RESERVED_CONTAINERS & set(run('docker', 'ps', '-a', '--format', '{{.Names}}').splitlines())
    collisions |= RESERVED_NETWORKS & set(run('docker', 'network', 'ls', '--format', '{{.Name}}').splitlines())
    if collisions:
        raise RuntimeError('Refusing installed/colliding resources: ' + ', '.join(sorted(collisions)))
    if run('docker', 'image', 'inspect', executor_image, '--format', '{{.Os}}') != 'linux':
        raise RuntimeError('Existing Linux executor image required')
    suffix = uuid.uuid4().hex[:12]
    selector = LABEL + '=' + suffix
    volume = 'p1-lifecycle-root-' + suffix
    executor = 'p1-lifecycle-executor-' + suffix
    try:
        run('docker', 'volume', 'create', '--label', selector, volume)
        path = run('docker', 'volume', 'inspect', volume, '--format', '{{.Mountpoint}}')
        if not path.startswith('/var/lib/docker/volumes/' + volume + '/') or not path.endswith('/_data'):
            raise RuntimeError('Unexpected engine volume path; no secondary path permitted')
        run('docker', 'create', '--name', executor, '--pull=never', '--label', selector,
            '-v', volume + ':' + path, '-v', '/var/run/docker.sock:/var/run/docker.sock',
            '--entrypoint', 'sleep', executor_image, 'infinity')
        run('docker', 'start', executor)
        run('docker', 'exec', '-i', executor, 'tar', '-xf', '-', '-C', path, data=archive(extra_sources))
        # Stream test output to private caller log, do not hide a failure or a skip.
        status = subprocess.call(['docker', 'exec', executor, 'python',
                                  path + '/tests/integration/fixtures/p1_lifecycle.py', path, suffix, *fixture_arguments])
        if result_file is not None:
            artifact = subprocess.run(['docker', 'exec', executor, 'cat', path + '/p1-result.json'],
                                      capture_output=True, text=True, encoding='utf-8')
            if artifact.returncode == 0:
                result_file.parent.mkdir(parents=True, exist_ok=True)
                result_file.write_text(artifact.stdout, encoding='utf-8')
            elif status == 0:
                raise RuntimeError('Completed acceptance result is missing')
            else:
                print('No completed acceptance artifact; the drill failed before reporting results')
        if status:
            for container in run('docker', 'ps', '-aq', '--filter', 'label=' + selector).splitlines():
                if run('docker', 'inspect', container, '--format', '{{.Name}}') != '/' + executor:
                    print(run('docker', 'inspect', container, '--format', '{{.Name}}'))
                    print(run('docker', 'logs', '--tail', '45', container))
            raise RuntimeError('Physical lifecycle drill failed')
    finally:
        # Cleanup exclusively labelled resources, verifying ownership again before removal.
        errors = []
        for kind, listing, removal in [('container', ['ps', '-aq'], ['rm', '-f', '-v']),
                                       ('image', ['image', 'ls', '-q'], ['image', 'rm']),
                                       ('network', ['network', 'ls', '-q'], ['network', 'rm']),
                                       ('volume', ['volume', 'ls', '-q'], ['volume', 'rm'])]:
            try:
                identifiers = list(dict.fromkeys(run('docker', *listing, '--filter', 'label=' + selector).splitlines()))
                for identifier in identifiers:
                    record = json.loads(run('docker', kind, 'inspect', identifier))[0]
                    labels = record['Config']['Labels'] if kind in {'container', 'image'} else record['Labels']
                    if not labels or labels.get(LABEL) != suffix:
                        raise RuntimeError('Cleanup ownership proof failed: ' + identifier)
                    print(run('docker', *removal, identifier))
            except RuntimeError as error:
                errors.append(str(error))
        if errors:
            raise RuntimeError('Explicit fixture cleanup failure: ' + '; '.join(errors))


if __name__ == '__main__':
    main()
