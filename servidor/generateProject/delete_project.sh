#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-}"
[[ -z "$PROJECT_ID" ]] && { echo "Uso: $0 <project_id>"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"

if [ -d "$PROJECT_DIR" ]; then
  rm -rf "$PROJECT_DIR"
  echo "✅ Diretório $PROJECT_DIR removido com sucesso."
else
  echo "⚠️ Diretório $PROJECT_DIR não encontrado."
fi
