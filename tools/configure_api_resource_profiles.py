"""Generate the API's non-secret, exact-allowlist resource configuration."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import tempfile

KEYS = tuple(f'PROJECT_RES_{profile}_{dimension}' for profile in ('SMALL', 'MEDIUM', 'LARGE', 'CUSTOM') for dimension in ('MEMORY', 'CPUS', 'PIDS'))


def render(source: str) -> str:
    values = {}
    for line in source.splitlines():
        key, separator, value = line.partition('=')
        if key not in KEYS:
            continue
        if not separator or key in values or value != value.strip():
            raise ValueError(f'Non-canonical resource setting: {key}')
        pattern = {'MEMORY': r'[1-9][0-9]*(?:\.[0-9]+)?[kKmMgG]', 'CPUS': r'[0-9]+(?:\.[0-9]{1,2})?', 'PIDS': r'[1-9][0-9]*'}[key.rsplit('_', 1)[1]]
        if not re.fullmatch(pattern, value) or (key.endswith('_CPUS') and float(value) <= 0):
            raise ValueError(f'Invalid resource setting: {key}')
        values[key] = value
    if set(values) != set(KEYS):
        raise ValueError('Resource profile settings are incomplete')
    return ''.join(f'{key}={values[key]}\n' for key in KEYS)


def configure(source: Path, output: Path) -> None:
    if source.resolve() == output.resolve():
        raise ValueError('Source and output must be different files')
    rendered = render(source.read_text(encoding='utf-8'))
    fd, temp = tempfile.mkstemp(prefix=output.name + '.', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as file:
            file.write(rendered)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp, 0o644)
        os.replace(temp, output)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        configure(args.source, args.output)
    except (OSError, ValueError) as exc:
        parser.exit(1, f'Resource profile configuration failed: {exc}\n')
    print('API resource profiles generated; no server secrets exported')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
