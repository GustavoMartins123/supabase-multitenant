#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "ERRO: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"

PROJECT_ID="${1:-}"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "Uso: $0 <project_id>"
PROJECT_DIR="$SERVER_ROOT/projects/$PROJECT_ID"
[[ -f "$SERVER_ROOT/.env" ]] || die "Ambiente global ausente"
[[ -f "$PROJECT_DIR/.env" ]] || die "Ambiente do projeto ausente"

set -a
# shellcheck disable=SC1090
source "$SERVER_ROOT/.env"
# shellcheck disable=SC1090
source "$PROJECT_DIR/.env"
set +a

PROJECT_UUID="$(tr '[:upper:]' '[:lower:]' <<<"${PROJECT_UUID:-}")"
storage_validate_tenant_id "$PROJECT_UUID" || die "PROJECT_UUID invalido"
for variable in FILE_SIZE_LIMIT ENABLE_IMAGE_TRANSFORMATION S3_PROTOCOL_ENABLED \
  VECTOR_BUCKETS_ENABLED \
  VECTOR_MAX_BUCKETS VECTOR_MAX_INDEXES SERVICE_ROLE_KEY_PROJETO \
  S3_PROTOCOL_CREDENTIAL_ID S3_PROTOCOL_ACCESS_KEY_ID \
  S3_PROTOCOL_ACCESS_KEY_SECRET; do
  [[ -n "${!variable:-}" ]] || die "$variable ausente"
done

vector_validate_s3_credentials || die "Credenciais SigV4 invalidas"
storage_wait_global || die "Storage compartilhado indisponivel"
storage_patch_tenant_settings "$PROJECT_UUID" "$FILE_SIZE_LIMIT" \
  "$ENABLE_IMAGE_TRANSFORMATION" "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  "$VECTOR_MAX_BUCKETS" "$VECTOR_MAX_INDEXES" \
  || die "Falha ao atualizar configuracao do tenant"
storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant nao ficou saudavel apos atualizar settings"
storage_assert_project_gateway "$PROJECT_UUID" "$PROJECT_ID" "$SERVICE_ROLE_KEY_PROJETO" \
  || die "Nginx nao resolveu o tenant apos atualizar settings"

echo "Tenant Storage $PROJECT_UUID atualizado sem reiniciar o servico global."
