#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }
say() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

PROJECT="${1:-}"
BACKUP_ID="${2:-}"
SAFETY_BACKUP_ID="${3:-}"
[[ -n "$PROJECT" && -n "$BACKUP_ID" && -n "$SAFETY_BACKUP_ID" ]] \
  || die "Uso: $0 <project> <backup_id> <safety_backup_id>"

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
SAFETY_BACKUP_ID="$(echo "$SAFETY_BACKUP_ID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT" =~ $NAME_RE ]] || die "Projeto invalido"
[[ "$BACKUP_ID" =~ $UUID_RE ]] || die "backup_id invalido"
[[ "$SAFETY_BACKUP_ID" =~ $UUID_RE ]] || die "safety_backup_id invalido"
[[ "$BACKUP_ID" != "$SAFETY_BACKUP_ID" ]] || die "Ids de backup identicos"

for command in docker jq openssl tar gzip; do
  command -v "$command" >/dev/null || die "Comando obrigatorio ausente: $command"
done

PROJECT_DIR="$PROJECTS_ROOT/$PROJECT"
DB="_supabase_$PROJECT"
PRERESTORE_DB="${DB}_prerestore"
[[ -d "$PROJECT_DIR" ]] || die "Projeto nao encontrado: $PROJECT_DIR"
[[ -f "$PROJECT_ROOT/.env" ]] || die "Arquivo $PROJECT_ROOT/.env ausente"
[[ -f "$PROJECT_DIR/.env" ]] || die "Arquivo .env do projeto ausente"

set -a
source "$PROJECT_ROOT/.env"
source "$PROJECT_DIR/.env"
set +a
for variable in JWT_SECRET PROJECT_UUID ANON_KEY_PROJETO SERVICE_ROLE_KEY_PROJETO \
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
storage_assert_project_identity "$PROJECT" "$PROJECT_UUID" \
  || die "Identidade Storage diverge do control plane"

SRC_DIR="$BACKUPS_ROOT/$PROJECT_UUID/$BACKUP_ID"
SAFETY_DIR="$BACKUPS_ROOT/$PROJECT_UUID/$SAFETY_BACKUP_ID"
[[ -d "$SRC_DIR" ]] || die "Ponto de restauracao nao encontrado: $SRC_DIR"
[[ -f "$SRC_DIR/manifest.json" ]] || die "manifest.json ausente no ponto $BACKUP_ID"
[[ -s "$SRC_DIR/db.sql.gz" ]] || die "db.sql.gz ausente no ponto $BACKUP_ID"
[[ -s "$SRC_DIR/storage.tar.gz" ]] || die "storage.tar.gz ausente no ponto $BACKUP_ID"
[[ -s "$SRC_DIR/realtime-structure.sql.gz" ]] || die "realtime-structure.sql.gz ausente"
[[ -s "$SRC_DIR/realtime-migrations.sql.gz" ]] || die "realtime-migrations.sql.gz ausente"
[[ ! -e "$SAFETY_DIR" ]] || die "Ponto de seguranca $SAFETY_BACKUP_ID ja existe"

MANIFEST_UUID="$(jq -r '.project_uuid // empty' "$SRC_DIR/manifest.json" | tr '[:upper:]' '[:lower:]')"
[[ "$MANIFEST_UUID" == "$PROJECT_UUID" ]] \
  || die "Manifest pertence a outro projeto ($MANIFEST_UUID != $PROJECT_UUID)"
[[ "$(jq -r '.format // empty' "$SRC_DIR/manifest.json")" == "2" ]] \
  || die "Formato de backup nao suportado; converta-o com a ferramenta de migracao"
[[ "$(jq -r '.storage_tenant_id // empty' "$SRC_DIR/manifest.json" | tr '[:upper:]' '[:lower:]')" == "$PROJECT_UUID" ]] \
  || die "Manifest possui tenant Storage divergente"
[[ "$(jq -r '.storage_layout // empty' "$SRC_DIR/manifest.json")" == "tenant-namespace" ]] \
  || die "Layout de Storage do backup invalido"
storage_validate_namespace_archive "$SRC_DIR/storage.tar.gz" \
  || die "Archive Storage do backup invalido"
REALTIME_TABLES="$(jq -r '.realtime_tables // empty' "$SRC_DIR/manifest.json")"

for container in supabase-db supabase-pooler realtime-dev.supabase-realtime; do
  docker inspect "$container" >/dev/null 2>&1 || die "Container $container ausente"
done
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco $DB nao encontrado"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$PRERESTORE_DB';" | tr -d '[:space:]')" == "0" ]] \
  || die "Banco $PRERESTORE_DB ja existe; limpe restauracao anterior"
storage_wait_global || die "Storage compartilhado indisponivel"
storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant Storage atual nao esta saudavel"

STORAGE_TARGET="$(storage_assert_namespace_target "$PROJECT_UUID")"
STORAGE_PRERESTORE="${STORAGE_TARGET}.prerestore.$$"
[[ -d "$STORAGE_TARGET" ]] || die "Namespace Storage atual ausente"
[[ ! -e "$STORAGE_PRERESTORE" ]] || die "Staging anterior de Storage ainda existe"

SLOT="supabase_realtime_replication_slot_${PROJECT}"; SLOT="${SLOT:0:63}"
MSG_SLOT="supabase_realtime_messages_replication_slot_${PROJECT}"; MSG_SLOT="${MSG_SLOT:0:63}"
SLOT_PLUGIN=""

MUTATION_STARTED=0
SLOT_DROPPED=0
DB_RENAMED=0
NEW_DB_CREATED=0
STORAGE_SWAPPED=0
STORAGE_TENANT_QUIESCED=0

terminate_db_conns() {
  docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$1' AND pid <> pg_backend_pid();" >/dev/null
}

drop_slot_if_exists() {
  local slot="$1" pid
  [[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$slot';" | tr -d '[:space:]')" == "1" ]] || return 0
  pid=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
    "SELECT active_pid FROM pg_replication_slots WHERE slot_name = '$slot';" | tr -d '[:space:]')
  [[ -z "$pid" ]] || docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "SELECT pg_terminate_backend($pid);" >/dev/null
  docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "SELECT pg_drop_replication_slot('$slot');" >/dev/null
}

create_main_slot() {
  local db="$1"
  [[ -n "$SLOT_PLUGIN" ]] || return 0
  docker exec supabase-db psql -U supabase_admin -d "$db" -c \
    "SELECT pg_create_logical_replication_slot('$SLOT', '$SLOT_PLUGIN');" >/dev/null
}

rollback_on_error() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  if [[ "$MUTATION_STARTED" -eq 0 ]]; then exit "$status"; fi

  local rollback_failed=0
  echo "❌ Restore falhou; revertendo alteracoes..." >&2

  backup_stop_project_containers "$PROJECT" >/dev/null 2>&1

  if [[ "$STORAGE_SWAPPED" -eq 1 && -d "$STORAGE_PRERESTORE" ]]; then
    storage_remove_tenant_namespace "$PROJECT_UUID" >/dev/null 2>&1 \
      || rollback_failed=1
    if [[ ! -e "$STORAGE_TARGET" ]]; then
      mv "$STORAGE_PRERESTORE" "$STORAGE_TARGET" || rollback_failed=1
    else
      rollback_failed=1
    fi
  fi
  if [[ "$NEW_DB_CREATED" -eq 1 ]]; then
    terminate_db_conns "$DB" 2>/dev/null
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "DROP DATABASE IF EXISTS \"$DB\";" >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$DB_RENAMED" -eq 1 ]]; then
    terminate_db_conns "$PRERESTORE_DB" 2>/dev/null
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "ALTER DATABASE \"$PRERESTORE_DB\" RENAME TO \"$DB\";" >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$STORAGE_TENANT_QUIESCED" -eq 1 ]]; then
    storage_patch_tenant_connection "$PROJECT_UUID" "$PROJECT" \
      >/dev/null 2>&1 || rollback_failed=1
    storage_assert_tenant_health "$PROJECT_UUID" \
      >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$SLOT_DROPPED" -eq 1 && -n "$SLOT_PLUGIN" ]]; then
    create_main_slot "$DB" >/dev/null 2>&1 || rollback_failed=1
  fi
  backup_start_project_containers "$PROJECT" >/dev/null 2>&1 || rollback_failed=1

  [[ "$rollback_failed" -eq 0 ]] \
    && echo "ROLLBACK_COMPLETE ${PROJECT}=${BACKUP_ID}" >&2 \
    || echo "ROLLBACK_INCOMPLETE ${PROJECT}=${BACKUP_ID}" >&2
  exit "$status"
}
trap rollback_on_error ERR
trap 'rollback_on_error 143' TERM
trap 'rollback_on_error 130' INT
trap 'rollback_on_error 129' HUP

now=$(date +%s)
GLOBAL_ANON_TOKEN="$(backup_generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$((now + 3600))}" "$JWT_SECRET")"

say "Parando servicos do projeto $PROJECT..."
MUTATION_STARTED=1
backup_stop_project_containers "$PROJECT" >/dev/null
code="$(backup_http_code realtime-dev.supabase-realtime POST "/api/tenants/$PROJECT_UUID/shutdown" "$ANON_KEY_PROJETO")"
backup_accepted_code "$code" 200 202 204 404 || die "Realtime nao aceitou shutdown (HTTP $code)"
code="$(backup_http_code supabase-pooler GET "/api/tenants/$PROJECT/terminate" "$GLOBAL_ANON_TOKEN")"
backup_accepted_code "$code" 200 204 404 || die "Supavisor nao encerrou pools (HTTP $code)"
STORAGE_TENANT_QUIESCED=1
storage_quiesce_tenant "$PROJECT_UUID" "$PROJECT" "$SERVICE_ROLE_KEY_PROJETO" \
  || die "Storage nao bloqueou a data plane do tenant"
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND usename = 'supabase_storage_admin' AND pid <> pg_backend_pid();" \
  >/dev/null

say "Criando ponto de seguranca com o estado atual..."
backup_capture "$PROJECT" "$SAFETY_DIR"
echo "SAFETY_BACKUP_COMPLETE ${SAFETY_BACKUP_ID}" >&2

if [[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$SLOT';" | tr -d '[:space:]')" == "1" ]]; then
  SLOT_PLUGIN=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
    "SELECT plugin FROM pg_replication_slots WHERE slot_name = '$SLOT';" | tr -d '[:space:]')
  drop_slot_if_exists "$SLOT"
  SLOT_DROPPED=1
fi
drop_slot_if_exists "$MSG_SLOT"

say "Substituindo banco $DB..."
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB' AND pid <> pg_backend_pid(); ALTER DATABASE \"$DB\" RENAME TO \"$PRERESTORE_DB\";" >/dev/null
DB_RENAMED=1

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "CREATE DATABASE $DB;"
NEW_DB_CREATED=1
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "REVOKE CONNECT, TEMPORARY ON DATABASE $DB FROM PUBLIC;"

say "Restaurando dump do banco..."
gunzip -c "$SRC_DIR/db.sql.gz" \
  | docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" >/dev/null
gunzip -c "$SRC_DIR/realtime-structure.sql.gz" \
  | docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" >/dev/null
gunzip -c "$SRC_DIR/realtime-migrations.sql.gz" \
  | docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" >/dev/null

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
UPDATE auth.schema_migrations SET dirty = false WHERE dirty = true;
UPDATE storage.migrations SET dirty = false WHERE dirty = true;
SQL

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "ALTER DATABASE \"$DB\" SET search_path TO public, auth, storage, extensions;"
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "ALTER ROLE supabase_storage_admin IN DATABASE \"$DB\" SET search_path = storage, public;"

docker exec supabase-db psql -U supabase_admin -d "$DB" -c \
  "TRUNCATE realtime.subscription RESTART IDENTITY CASCADE;" >/dev/null

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" <<'SQL'
DO $part$
DECLARE d date; partition_name text;
BEGIN
  FOR d IN SELECT generate_series((current_date - interval '1 day')::date,(current_date + interval '3 days')::date,'1 day')::date
  LOOP
    partition_name := 'messages_' || to_char(d, 'YYYY_MM_DD');
    BEGIN
      EXECUTE format('CREATE TABLE IF NOT EXISTS realtime.%I PARTITION OF realtime.messages FOR VALUES FROM (%L) TO (%L)', partition_name, d::text, (d + 1)::text);
    EXCEPTION WHEN duplicate_table THEN NULL;
    END;
  END LOOP;
END
$part$;
DROP PUBLICATION IF EXISTS supabase_realtime;
DROP PUBLICATION IF EXISTS supabase_realtime_messages;
DROP PUBLICATION IF EXISTS supabase_realtime_messages_publication;
CREATE PUBLICATION supabase_realtime;
CREATE PUBLICATION supabase_realtime_messages_publication FOR TABLE realtime.messages;
SQL

if [[ -n "$REALTIME_TABLES" ]]; then
  IFS=',' read -ra tables <<< "$REALTIME_TABLES"
  for table_name in "${tables[@]}"; do
    [[ -n "$table_name" ]] || continue
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$DB" -c \
      "ALTER PUBLICATION supabase_realtime ADD TABLE $table_name;"
  done
fi

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "GRANT CONNECT, TEMPORARY ON DATABASE $DB TO pgbouncer; GRANT CONNECT, TEMPORARY ON DATABASE $DB TO authenticator; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $DB TO supabase_storage_admin; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $DB TO supabase_auth_admin;"

vector_validate_database "$DB" || die "Banco restaurado sem contrato pgvector valido"

if [[ "$SLOT_DROPPED" -eq 1 && -n "$SLOT_PLUGIN" ]]; then
  create_main_slot "$DB"
fi

say "Restaurando storage..."
mv "$STORAGE_TARGET" "$STORAGE_PRERESTORE"
STORAGE_SWAPPED=1
storage_extract_namespace_archive "$PROJECT_UUID" "$SRC_DIR/storage.tar.gz" \
  || die "Falha ao restaurar namespace Storage do tenant"

storage_patch_tenant_connection "$PROJECT_UUID" "$PROJECT" \
  || die "Storage nao reconectou ao banco restaurado"
storage_run_and_assert_migrations "$PROJECT_UUID" \
  || die "Migrations Storage falharam no banco restaurado"

say "Religando servicos do projeto..."
backup_start_project_containers "$PROJECT" || die "Falha ao religar servicos do projeto"
storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant Storage nao ficou saudavel apos restauracao"
storage_assert_project_gateway "$PROJECT_UUID" "$PROJECT" "$SERVICE_ROLE_KEY_PROJETO" \
  || die "Nginx nao resolveu o tenant Storage restaurado"
vector_sync_project_wrappers "$PROJECT" || die "Falha ao sincronizar wrappers vetoriais"

[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Verificacao final do database falhou"

trap - ERR TERM INT HUP
cleanup_failed=0
terminate_db_conns "$PRERESTORE_DB" 2>/dev/null || cleanup_failed=1
docker exec supabase-db psql -U supabase_admin -d postgres -c \
  "DROP DATABASE IF EXISTS \"$PRERESTORE_DB\";" >/dev/null 2>&1 \
  || cleanup_failed=1
rm -rf -- "$STORAGE_PRERESTORE" || cleanup_failed=1
if [[ "$cleanup_failed" -ne 0 ]]; then
  echo "RESTORE_CLEANUP_INCOMPLETE ${PROJECT}=${BACKUP_ID}" >&2
  die "Restore validado, mas a limpeza transacional ficou incompleta"
fi

ok "RESTORED ${PROJECT} ponto=${BACKUP_ID} seguranca=${SAFETY_BACKUP_ID}"
