#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "ERRO: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/storage_multitenant.sh"

PROJECT_ID="${1:-}"
TENANT_ID="$(tr '[:upper:]' '[:lower:]' <<<"${2:-}")"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "project_id invalido"
storage_validate_tenant_id "$TENANT_ID" || die "tenant_uuid invalido"

PROJECT_ENV="$SERVER_ROOT/projects/$PROJECT_ID/.env"
GLOBAL_ENV="$SERVER_ROOT/.env"
[[ -f "$GLOBAL_ENV" ]] || die "Ambiente global ausente"
[[ -f "$PROJECT_ENV" ]] || die "Ambiente do projeto ausente"
set -a
# shellcheck disable=SC1090
source "$GLOBAL_ENV"
set +a
ENV_TENANT="$(grep -m1 '^PROJECT_UUID=' "$PROJECT_ENV" | cut -d= -f2- \
  | tr '[:upper:]' '[:lower:]')"
storage_validate_tenant_id "$ENV_TENANT" || die "PROJECT_UUID do ambiente invalido"
[[ "$ENV_TENANT" == "$TENANT_ID" ]] \
  || die "tenant_uuid nao pertence ao projeto solicitado"
storage_assert_project_identity "$PROJECT_ID" "$TENANT_ID" \
  || die "tenant_uuid diverge do control plane"

storage_wait_global || die "Storage compartilhado indisponivel"
storage_delete_tenant "$TENANT_ID" || die "Falha ao excluir tenant Storage"
storage_assert_tenant_absent "$TENANT_ID" || die "Tenant Storage ainda existe"

echo "Tenant Storage $TENANT_ID e seu namespace foram removidos."
