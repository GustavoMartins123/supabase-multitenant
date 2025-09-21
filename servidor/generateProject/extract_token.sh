#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_NAME="${1:?Usage: $0 <nome_do_projeto>}"
PROJECT_DIR="/docker/projects/$PROJECT_NAME"


grep -E '^(ANON_KEY_PROJETO|SERVICE_ROLE_KEY_PROJETO)=' "$PROJECT_DIR/.env"
