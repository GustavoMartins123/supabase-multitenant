#!/usr/bin/env bash
set -euo pipefail

if [[ -x /usr/local/bin/configure-pg-hba.sh ]]; then
  /usr/local/bin/configure-pg-hba.sh
fi

exec /usr/local/bin/docker-entrypoint.sh "$@"
