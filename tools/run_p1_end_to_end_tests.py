"""Isolated real Studio/Authelia/Traefik/API/agent lifecycle and permission drill.

Split topology is simulated using disjoint Studio/server Docker networks and a
dedicated HTTPS link, not two physical machines. No installation path is accepted.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from run_p1_lifecycle_tests import ROOT, execute
from run_studio_session_tests import run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executor-image', required=True)
    parser.add_argument('--topology', required=True, choices=('single', 'split'))
    parser.add_argument('--benchmark', action='store_true', help='Measure only after every validation passes')
    parser.add_argument('--result', type=Path, required=True, help='Local result JSON, contains no credentials')
    args = parser.parse_args()
    extra = [p for p in run('git', '-C', str(ROOT), 'ls-files').splitlines()
             if p.startswith(('studio/nginx/lua/', 'servidor/host-agent/hostagent/',
                              'servidor/traefik/plugins-local/'))]
    extra += ['studio/nginx/nginx.conf', 'studio/nginx/docker-entrypoint.sh',
              'studio/authelia/configuration.yml.template', 'studio/authelia/users_database.yml.example',
              'studio/authelia/ids.yml.example', 'tools/configure_studio_runtime.py',
              'servidor/traefik/render_dynamic_config.py',
              'tests/integration/fixtures/p1_end_to_end.py', 'tests/integration/fixtures/p1_browser_driver.py',
              'tests/integration/fixtures/p1_benchmark.py']
    arguments = ('end-to-end', args.topology) + (('--benchmark',) if args.benchmark else ())
    execute(args.executor_image, fixture_arguments=arguments, extra_sources=tuple(extra), result_file=args.result)


if __name__ == '__main__':
    main()
