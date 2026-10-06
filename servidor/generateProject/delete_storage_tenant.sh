#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "ERRO: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC2034
PROJECT_ROOT="$SERVER_ROOT"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/functions_config.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/storage_multitenant.sh"

PROJECT_ID="${1:-}"
echo "HOST_AGENT_PROGRESS=delete_storage:validate"
TENANT_ID="$(tr '[:upper:]' '[:lower:]' <<<"${2:-}")"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "project_id invalido"
storage_validate_tenant_id "$TENANT_ID" || die "tenant_uuid invalido"
functions_config_lock "$PROJECT_ID"

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
functions_config_withdraw "$PROJECT_ID"
echo "HOST_AGENT_PROGRESS=delete_storage:remove_tenant"
storage_delete_tenant_registry "$TENANT_ID" || die "Falha ao excluir tenant Storage"
echo "HOST_AGENT_PROGRESS=delete_storage:remove_objects"
storage_remove_tenant_namespace "$TENANT_ID" || die "Falha ao remover namespace Storage"
echo "HOST_AGENT_PROGRESS=delete_storage:verify"
storage_assert_tenant_absent "$TENANT_ID" || die "Tenant Storage ainda existe"

echo "Tenant Storage $TENANT_ID e seu namespace foram removidos."
