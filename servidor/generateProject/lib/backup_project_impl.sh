#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }
say() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

PROJECT="${1:-}"
BACKUP_ID="${2:-}"
[[ -n "$PROJECT" && -n "$BACKUP_ID" ]] || die "Uso: $0 <project> <backup_id>"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECTS_ROOT="$PROJECT_ROOT/projects"
BACKUPS_ROOT="$PROJECT_ROOT/backups"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/backup_core.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"

NAME_RE='^[a-z_][a-z0-9_]{2,39}$'
UUID_RE='^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
PROJECT="$(echo "$PROJECT" | tr '[:upper:]' '[:lower:]')"
BACKUP_ID="$(echo "$BACKUP_ID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT" =~ $NAME_RE ]] || die "Projeto invalido"
[[ "$BACKUP_ID" =~ $UUID_RE ]] || die "backup_id invalido"

for command in docker jq openssl tar gzip; do
  command -v "$command" >/dev/null || die "Comando obrigatorio ausente: $command"
done

PROJECT_DIR="$PROJECTS_ROOT/$PROJECT"
DB="_supabase_$PROJECT"
[[ -d "$PROJECT_DIR" ]] || die "Projeto nao encontrado: $PROJECT_DIR"
[[ -f "$PROJECT_ROOT/.env" ]] || die "Arquivo $PROJECT_ROOT/.env ausente"
[[ -f "$PROJECT_DIR/.env" ]] || die "Arquivo .env do projeto ausente"

set -a
source "$PROJECT_ROOT/.env"
source "$PROJECT_DIR/.env"
set +a
for variable in JWT_SECRET PROJECT_UUID SERVICE_ROLE_KEY_PROJETO \
  S3_PROTOCOL_CREDENTIAL_ID S3_PROTOCOL_ACCESS_KEY_ID \
  S3_PROTOCOL_ACCESS_KEY_SECRET S3_PROTOCOL_ENABLED VECTOR_BUCKETS_ENABLED; do
  [[ -n "${!variable:-}" ]] || die "$variable ausente"
done
PROJECT_UUID="$(echo "$PROJECT_UUID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT_UUID" =~ $UUID_RE ]] || die "PROJECT_UUID invalido"
export PROJECT_UUID SERVICE_ROLE_KEY_PROJETO S3_PROTOCOL_CREDENTIAL_ID \
  S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET VECTOR_BUCKETS_ENABLED
storage_validate_bool VECTOR_BUCKETS_ENABLED "$VECTOR_BUCKETS_ENABLED" \
  || die "VECTOR_BUCKETS_ENABLED invalido"
storage_validate_bool S3_PROTOCOL_ENABLED "$S3_PROTOCOL_ENABLED" \
  || die "S3_PROTOCOL_ENABLED invalido"
vector_validate_s3_credentials || die "Credenciais SigV4 invalidas"
storage_wait_global || die "Storage compartilhado indisponivel"
storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant Storage nao esta saudavel"

for container in supabase-db supabase-pooler; do
  docker inspect "$container" >/dev/null 2>&1 || die "Container $container ausente"
done
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco $DB nao encontrado"

DEST_DIR="$BACKUPS_ROOT/$PROJECT_UUID/$BACKUP_ID"
[[ ! -e "$DEST_DIR" ]] || die "Ponto $BACKUP_ID ja existe"
mkdir -p "$BACKUPS_ROOT/$PROJECT_UUID"

STOPPED_CONTAINERS=""
STORAGE_POOL_DISCONNECTED=0

restart_stopped() {
  [[ -n "$STOPPED_CONTAINERS" ]] || return 0
  backup_start_project_containers "$PROJECT" "$STOPPED_CONTAINERS" || return 1
}

reconnect_storage_pool() {
  [[ "$STORAGE_POOL_DISCONNECTED" -eq 1 ]] || return 0
  storage_patch_tenant_connection "$PROJECT_UUID" "$PROJECT" || return 1
  storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
    "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
    "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" || return 1
  STORAGE_POOL_DISCONNECTED=0
}

on_error() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Backup falhou; religando servicos do projeto..." >&2
  rm -rf "${DEST_DIR}.tmp"
  reconnect_storage_pool || echo "⚠️ Nao foi possivel religar o pool Storage de $PROJECT" >&2
  restart_stopped || echo "⚠️ Nao foi possivel religar todos os servicos de $PROJECT" >&2
  exit "$status"
}
trap on_error ERR
trap 'on_error 143' TERM
trap 'on_error 130' INT
trap 'on_error 129' HUP

now=$(date +%s)
GLOBAL_ANON_TOKEN="$(backup_generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$((now + 3600))}" "$JWT_SECRET")"

say "Parando servicos do projeto $PROJECT..."
STOPPED_CONTAINERS="$(backup_stop_project_containers "$PROJECT")"
code="$(backup_http_code supabase-pooler GET "/api/tenants/$PROJECT/terminate" "$GLOBAL_ANON_TOKEN")"
backup_accepted_code "$code" 200 204 404 || die "Supavisor nao encerrou pools (HTTP $code)"
storage_disconnect_tenant_pool "$PROJECT_UUID" \
  || die "Storage nao encerrou o pool do tenant"
STORAGE_POOL_DISCONNECTED=1
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND usename = 'supabase_storage_admin' AND pid <> pg_backend_pid();" \
  >/dev/null
backup_progress services_stopped

say "Capturando banco e storage..."
backup_capture "$PROJECT" "$DEST_DIR"

say "Religando servicos do projeto..."
reconnect_storage_pool || die "Backup concluido, mas falhou ao religar pool Storage"
restart_stopped || die "Backup concluido, mas falhou ao religar servicos"
STOPPED_CONTAINERS=""
backup_progress services_restarted

trap - ERR TERM INT HUP
ok "BACKUP_COMPLETE ${PROJECT} id=${BACKUP_ID}"
