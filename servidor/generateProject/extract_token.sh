#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
PROJECT_NAME="${1:?Usage: $0 <nome_do_projeto>}"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] || {
  echo "nome de projeto invalido: $PROJECT_NAME" >&2
  exit 1
}
PROJECT_DIR="/docker/projects/$PROJECT_NAME"


grep -E '^(ANON_KEY_PROJETO|SERVICE_ROLE_KEY_PROJETO|CONFIG_TOKEN_PROJETO)=' "$PROJECT_DIR/.env"
