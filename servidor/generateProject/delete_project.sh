#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="${1:-}"
[[ -z "$PROJECT_ID" ]] && { echo "Uso: $0 <project_id>"; exit 1; }
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || { echo "project_id invalido" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECTS_ROOT="$(cd "$PROJECT_ROOT/projects" && pwd -P)"
PROJECT_DIR="$PROJECTS_ROOT/$PROJECT_ID"
[[ "$(dirname "$PROJECT_DIR")" == "$PROJECTS_ROOT" ]] \
  || { echo "Caminho do projeto fora da raiz permitida" >&2; exit 1; }

if [ -d "$PROJECT_DIR" ]; then
  rm -rf "$PROJECT_DIR"
  echo "✅ Diretório $PROJECT_DIR removido com sucesso."
else
  echo "⚠️ Diretório $PROJECT_DIR não encontrado."
fi
