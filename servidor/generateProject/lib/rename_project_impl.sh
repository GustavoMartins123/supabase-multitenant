#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ "${1:-}" =~ ^[a-z_][a-z0-9_]{2,39}$ && ( "$#" == 5 || ( "$#" == 6 && "${6:-}" == --recover-rollback ) ) ]] || { echo "Canonical rotation arguments required" >&2; exit 1; }
source "$SCRIPT_DIR/lib/functions_config.sh"
functions_config_lock "$1"
python3 "$SCRIPT_DIR/rotate_project_reference.py" "$@" \
  --lock-fd "$FUNCTIONS_GLOBAL_LOCK_FD" --tenant-lock-fd "${FUNCTIONS_TENANT_LOCK_FDS[$1]}"
