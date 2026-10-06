"""Remove shared configuration credentials and regenerate stopped project gateways."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'servidor/host-agent'))
sys.path.insert(0, str(REPO / 'tools'))
from hostagent.envfile import read_canonical_env_value
from hostagent.templates import sync_project_generated_files
from migration_files import atomic_write, canonical_path
from migrate_project_public_refs import catalog


def stripped_environment(content: bytes) -> bytes:
    lines = content.splitlines(keepends=True)
    matches = []
    for index, line in enumerate(lines):
        if b'CONFIG_TOKEN_PROJETO' not in line:
            continue
        if not re.fullmatch(rb'CONFIG_TOKEN_PROJETO=[a-f0-9]{64}(?:\r?\n)?', line):
            raise RuntimeError('Non-canonical obsolete configuration credential')
        matches.append(index)
    if len(matches) > 1:
        raise RuntimeError('Duplicate obsolete configuration credential')
    return b''.join(line for index, line in enumerate(lines) if index not in matches)


def require_stopped(projects: list[dict]) -> None:
    for name in ('projects-api', *(f"supabase-nginx-{project['name']}" for project in projects)):
        result = subprocess.run(['docker','inspect','--format','{{.State.Running}}',name],
            text=True, capture_output=True, check=True)
        if result.stdout.strip() != 'false':
            raise RuntimeError('Stop Projects API and project gateways before migration')
    agent = subprocess.run(['systemctl','show','supabase-host-agent.service','--property=ActiveState','--value'],
        text=True, capture_output=True, check=True)
    if agent.stdout.strip() != 'inactive':
        raise RuntimeError('Stop host-agent before migration')


def migrate(root: Path, projects: list[dict], *, backup_dir: Path, apply: bool = False) -> int:
    root, backup_dir = canonical_path(root), canonical_path(backup_dir)
    snapshots = {}
    environments = {}
    for project in projects:
        directory = canonical_path(root / 'projects' / project['name'])
        if directory.parent != root / 'projects' or not directory.is_dir():
            raise RuntimeError('Canonical project directory is required')
        env = directory / '.env'
        for key, expected in (('PROJECT_ID', project['name']), ('PROJECT_UUID', str(project['tenant_uuid'])),
                              ('PROJECT_PUBLIC_REF', project['public_ref'])):
            if read_canonical_env_value(env, key) != expected:
                raise RuntimeError('Project environment identity does not match the registry')
        environments[env] = stripped_environment(env.read_bytes())
        for file in (env, directory / 'Dockerfile', directory / 'docker-compose.yml',
                     directory / 'nginx' / f"nginx_{project['name']}.conf"):
            canonical_path(file)
            if not file.is_file():
                raise RuntimeError('Generated project file is missing')
            snapshots[file] = (file.read_bytes(), stat.S_IMODE(file.stat().st_mode))
    if not apply:
        return len(projects)
    require_stopped(projects)
    backup_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = {}
    for file, (content, mode) in snapshots.items():
        backup = backup_dir / file.relative_to(root)
        backup.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write(backup, content, mode=0o600)
        manifest[str(file.relative_to(root))] = mode
    atomic_write(backup_dir / 'manifest.json', json.dumps(manifest, sort_keys=True).encode())
    try:
        for env, content in environments.items():
            atomic_write(env, content, mode=snapshots[env][1])
        for project in projects:
            sync_project_generated_files(root=root, scripts_dir=REPO / 'servidor/generateProject',
                project_dir=root / 'projects' / project['name'], project=project['name'])
        for file in snapshots:
            if b'CONFIG_TOKEN_PROJETO' in file.read_bytes():
                raise RuntimeError('Obsolete configuration credential survived migration')
    except BaseException:
        for file, (content, mode) in snapshots.items():
            atomic_write(file, content, mode=mode)
        raise
    return len(projects)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('server_root', type=Path)
    parser.add_argument('--backup-dir', required=True, type=Path)
    parser.add_argument('--apply', action='store_true')
    options = parser.parse_args()
    projects = catalog(options.server_root)
    count = migrate(options.server_root, projects, backup_dir=options.backup_dir, apply=options.apply)
    print(f"{'Updated' if options.apply else 'Validated'} {count} project gateways; no credential values printed.")


if __name__ == '__main__':
    main()
