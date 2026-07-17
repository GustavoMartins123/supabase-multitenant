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
for variable in JWT_SECRET PROJECT_UUID; do
  [[ -n "${!variable:-}" ]] || die "$variable ausente"
done
PROJECT_UUID="$(echo "$PROJECT_UUID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT_UUID" =~ $UUID_RE ]] || die "PROJECT_UUID invalido"

for container in supabase-db supabase-pooler; do
  docker inspect "$container" >/dev/null 2>&1 || die "Container $container ausente"
done
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco $DB nao encontrado"

DEST_DIR="$BACKUPS_ROOT/$PROJECT_UUID/$BACKUP_ID"
[[ ! -e "$DEST_DIR" ]] || die "Ponto $BACKUP_ID ja existe"
mkdir -p "$BACKUPS_ROOT/$PROJECT_UUID"

STOPPED_CONTAINERS=""

restart_stopped() {
  [[ -n "$STOPPED_CONTAINERS" ]] || return 0
  backup_start_project_containers "$PROJECT" "$STOPPED_CONTAINERS" || return 1
}

on_error() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Backup falhou; religando servicos do projeto..." >&2
  rm -rf "${DEST_DIR}.tmp"
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
backup_progress services_stopped

say "Capturando banco e storage..."
backup_capture "$PROJECT" "$PROJECT_DIR" "$DEST_DIR"

say "Religando servicos do projeto..."
restart_stopped || die "Backup concluido, mas falhou ao religar servicos"
STOPPED_CONTAINERS=""
backup_progress services_restarted

trap - ERR TERM INT HUP
ok "BACKUP_COMPLETE ${PROJECT} id=${BACKUP_ID}"
