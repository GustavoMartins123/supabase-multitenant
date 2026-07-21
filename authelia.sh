#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STUDIO_HOST="${1:-127.0.0.1}"
STUDIO_PORT="${2:-9091}"

exec python3 "$ROOT_DIR/tools/configure_studio_runtime.py" \
  --studio-origin "https://${STUDIO_HOST}:${STUDIO_PORT}" \
  --force
