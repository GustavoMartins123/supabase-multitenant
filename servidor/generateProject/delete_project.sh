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
  container_names="$(docker ps -a --format '{{.Names}}' 2>/dev/null)" \
    || { echo "docker indisponivel; delete_files abortado sem remover $PROJECT_DIR" >&2; exit 1; }
  leftover="$(printf '%s\n' "$container_names" \
    | grep -E "^(supabase-[a-z0-9]+-${PROJECT_ID}|${PROJECT_ID}-[a-z0-9_.-]+-[0-9]+)$" || true)"
  [[ -z "$leftover" ]] \
    || { echo "containers do projeto ainda existem; remova-os antes dos arquivos: $(printf '%s' "$leftover" | tr '\n' ' ')" >&2; exit 1; }
  rm -rf "$PROJECT_DIR"
  echo "✅ Diretório $PROJECT_DIR removido com sucesso."
else
  echo "⚠️ Diretório $PROJECT_DIR não encontrado."
fi

if [ -f "$SCRIPT_DIR/lib/platform_capacity.sh" ]; then
  source "$SCRIPT_DIR/lib/platform_capacity.sh"
  platform_apply_shared_limits "$PROJECT_ROOT/.env" \
    || echo "Aviso: limites da camada compartilhada nao foram reaplicados." >&2
fi
