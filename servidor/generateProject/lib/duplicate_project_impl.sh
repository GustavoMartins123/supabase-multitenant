#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"
source "$SCRIPT_DIR/lib/resource_profiles.sh"
source "$SCRIPT_DIR/lib/tenant_reader_role.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/backup_core.sh"

read_project_env_value() {
  local file="$1" key="$2" count value
  count="$(grep -c "^${key}=" "$file" || true)"
  [[ "$count" == "1" ]] || die "$key deve ter exatamente uma atribuicao em $file"
  value="$(sed -n "s/^${key}=//p" "$file")"
  [[ -n "$value" && "$value" != *$'\r'* ]] || die "$key invalido em $file"
  printf '%s' "$value"
}

ORIGINAL_PROJECT="${1:-}"
NEW_PROJECT="${2:-}"
COPY_MODE="${3:-}"
PROJECT_UUID="${4:-}"
[[ -n "$ORIGINAL_PROJECT" && -n "$NEW_PROJECT" && -n "$COPY_MODE" && -n "$PROJECT_UUID" ]] \
  || die "Uso: $0 <original_project> <new_project> <with-data|schema-only> <project_uuid>"
[[ "$COPY_MODE" == "with-data" || "$COPY_MODE" == "schema-only" ]] \
  || die "copy_mode deve ser with-data ou schema-only"

ORIGINAL_PROJECT="$(echo "$ORIGINAL_PROJECT" | tr '[:upper:]' '[:lower:]')"
NEW_PROJECT="$(echo "$NEW_PROJECT" | tr '[:upper:]' '[:lower:]')"
PROJECT_UUID="$(echo "$PROJECT_UUID" | tr '[:upper:]' '[:lower:]')"
[[ "$ORIGINAL_PROJECT" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || die "Projeto original invalido"
[[ "$NEW_PROJECT" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || die "Novo projeto invalido"
storage_validate_tenant_id "$PROJECT_UUID" || die "project_uuid invalido"

RESERVED=(default select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback)
for word in "${RESERVED[@]}"; do
  [[ "$NEW_PROJECT" != "$word" ]] || die "'$NEW_PROJECT' e palavra reservada"
done

RESERVED_ROUTES=(admin phpmyadmin xmlrpc actuator)
for word in "${RESERVED_ROUTES[@]}"; do
  [[ "$NEW_PROJECT" != "$word" ]] || die "'$NEW_PROJECT' e rota reservada"
done

set -a
source "$PROJECT_ROOT/.env"
set +a

for variable in POSTGRES_HOST POSTGRES_PASSWORD POSTGRES_PORT MAX_CONCURRENT_USERS \
  SERVER_URL JWT_SECRET HOST_PROJECT_ROOT; do
  [[ -n "${!variable:-}" ]] || die "$variable ausente"
done
[[ "$MAX_CONCURRENT_USERS" =~ ^[1-9][0-9]*$ ]] \
  || die "MAX_CONCURRENT_USERS deve ser um inteiro positivo"

ORIGINAL_DB="_supabase_$ORIGINAL_PROJECT"
NEW_DB="_supabase_$NEW_PROJECT"
OUT_DIR="$PROJECT_ROOT/projects/$NEW_PROJECT"
ORIGINAL_DIR="$PROJECT_ROOT/projects/$ORIGINAL_PROJECT"
TMP_DIR="$(mktemp -d /tmp/duplicate-project.XXXXXX)"
DUMP_FILE="$TMP_DIR/main.sql"
RT_STRUCTURE_FILE="$TMP_DIR/realtime-structure.sql"
RT_MIGRATIONS_FILE="$TMP_DIR/realtime-migrations.sql"

CREATED_DB=0
CREATED_DIR=0
CREATED_REALTIME=0
CREATED_SUPAVISOR=0
CREATED_STORAGE=0
COMPOSE_STARTED=0
SOURCE_CONTAINERS=""
SOURCE_STORAGE_QUIESCED=0

resume_source_project() {
  local failed=0
  if [[ "$SOURCE_STORAGE_QUIESCED" -eq 1 ]]; then
    storage_patch_tenant_connection "$ORIGINAL_UUID" "$ORIGINAL_PROJECT" || failed=1
    if [[ "$failed" -eq 0 ]]; then
      storage_validate_tenant "$ORIGINAL_UUID" "$ORIGINAL_SERVICE_ROLE_KEY" \
        "$ORIGINAL_S3_ACCESS_KEY" "$ORIGINAL_S3_SECRET_KEY" \
        "$ORIGINAL_S3_ENABLED" "$ORIGINAL_VECTOR_ENABLED" || failed=1
    fi
  fi
  if [[ -n "$SOURCE_CONTAINERS" ]]; then
    backup_start_project_containers "$ORIGINAL_PROJECT" "$SOURCE_CONTAINERS" \
      || failed=1
  fi
  if [[ "$failed" -eq 0 && -n "$SOURCE_CONTAINERS" ]]; then
    storage_assert_project_gateway "$ORIGINAL_UUID" "$ORIGINAL_PROJECT" \
      "$ORIGINAL_SERVICE_ROLE_KEY" || failed=1
  fi
  [[ "$failed" -eq 0 ]] || return 1
  SOURCE_STORAGE_QUIESCED=0
  SOURCE_CONTAINERS=""
}

cleanup_tmp() { rm -rf "$TMP_DIR"; }
rollback() {
  local status="${1:-$?}"
  local rollback_failed=0 remaining tenant_status raw_slot slot
  local -a replication_slots=(
    "supabase_realtime_messages_replication_slot_$NEW_PROJECT"
    "supabase_realtime_replication_slot_$NEW_PROJECT"
  )
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Duplicacao falhou; limpando recursos do clone..." >&2

  resume_source_project || rollback_failed=1

  if [[ "$COMPOSE_STARTED" -eq 1 && -d "$OUT_DIR" ]]; then
    (cd "$OUT_DIR" && docker compose -p "$NEW_PROJECT" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 \
      || rollback_failed=1
  fi
  if [[ "$CREATED_SUPAVISOR" -eq 1 ]]; then
    tenant_status="$(docker exec supabase-pooler curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
      "http://localhost:4000/api/tenants/$NEW_PROJECT" \
      -H "Authorization: Bearer $GLOBAL_ANON_TOKEN")" || rollback_failed=1
    [[ "$tenant_status" == "200" || "$tenant_status" == "202" \
      || "$tenant_status" == "204" || "$tenant_status" == "404" ]] \
      || rollback_failed=1
  fi
  if [[ "$CREATED_REALTIME" -eq 1 ]]; then
    tenant_status="$(docker exec realtime-dev.supabase-realtime curl -sS -o /dev/null -w '%{http_code}' -X DELETE \
      "http://localhost:4000/api/tenants/$PROJECT_UUID" \
      -H "Authorization: Bearer $ANON_TOKEN")" || rollback_failed=1
    [[ "$tenant_status" == "200" || "$tenant_status" == "202" \
      || "$tenant_status" == "204" || "$tenant_status" == "404" ]] \
      || rollback_failed=1
  fi
  if [[ "$CREATED_STORAGE" -eq 1 ]]; then
    if ! storage_delete_tenant "$PROJECT_UUID"; then
      rollback_failed=1
    else
      CREATED_STORAGE=0
    fi
  fi
  if [[ "$CREATED_SUPAVISOR" -eq 1 || "$CREATED_REALTIME" -eq 1 ]]; then
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "DELETE FROM _realtime.extensions WHERE tenant_external_id = '$PROJECT_UUID';
       DELETE FROM _realtime.tenants WHERE external_id = '$PROJECT_UUID';
       DELETE FROM _supavisor.users WHERE tenant_external_id = '$NEW_PROJECT';
       DELETE FROM _supavisor.tenants WHERE external_id = '$NEW_PROJECT';" \
      >/dev/null || rollback_failed=1
  fi
  if [[ "$CREATED_DB" -eq 1 && "$CREATED_STORAGE" -eq 0 ]]; then
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "ALTER DATABASE \"$NEW_DB\" ALLOW_CONNECTIONS false;" \
      >/dev/null || rollback_failed=1
    for raw_slot in "${replication_slots[@]}"; do
      slot="${raw_slot:0:63}"
      docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
        "SELECT pg_terminate_backend(active_pid) FROM pg_replication_slots WHERE slot_name = '$slot' AND active_pid IS NOT NULL;" \
        >/dev/null || rollback_failed=1
      sleep 1
      docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
        "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = '$slot';" \
        >/dev/null || rollback_failed=1
    done
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$NEW_DB' AND pid <> pg_backend_pid();" \
      >/dev/null || rollback_failed=1
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "DROP DATABASE IF EXISTS \"$NEW_DB\";" >/dev/null || rollback_failed=1
    remaining="$(docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin \
      -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$NEW_DB';" \
      | tr -d '[:space:]')" || rollback_failed=1
    [[ "$remaining" == "0" ]] || rollback_failed=1
  fi
  if [[ "$CREATED_DIR" -eq 1 && "$CREATED_STORAGE" -eq 0 ]]; then
    rm -rf "$OUT_DIR" || rollback_failed=1
  fi
  cleanup_tmp || rollback_failed=1
  if [[ "$rollback_failed" -eq 0 ]]; then
    echo "HOST_AGENT_ROLLBACK_COMPLETE=1"
  else
    echo "HOST_AGENT_ROLLBACK_FAILED=1" >&2
  fi
  exit "$status"
}
trap rollback ERR
trap 'rollback 143' TERM
trap 'rollback 130' INT
trap 'rollback 129' HUP
trap cleanup_tmp EXIT

for command in docker jq openssl sed tar; do
  command -v "$command" >/dev/null || die "Comando obrigatorio ausente: $command"
done
for container in supabase-db supabase-pooler realtime-dev.supabase-realtime; do
  docker inspect "$container" >/dev/null 2>&1 || die "Container $container ausente"
done
[[ -d "$ORIGINAL_DIR" ]] || die "Projeto original nao encontrado: $ORIGINAL_DIR"
[[ -f "$ORIGINAL_DIR/.env" ]] || die "Ambiente do projeto original ausente"
[[ ! -e "$OUT_DIR" ]] || die "Projeto $NEW_PROJECT ja existe"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$ORIGINAL_DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco original $ORIGINAL_DB nao encontrado"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$NEW_DB';" | tr -d '[:space:]')" == "0" ]] \
  || die "Banco $NEW_DB ja existe"

ORIGINAL_UUID="$(read_project_env_value "$ORIGINAL_DIR/.env" PROJECT_UUID \
  | tr '[:upper:]' '[:lower:]')"
storage_validate_tenant_id "$ORIGINAL_UUID" || die "PROJECT_UUID do projeto original invalido"
[[ "$ORIGINAL_UUID" != "$PROJECT_UUID" ]] \
  || die "Clone deve possuir tenant UUID diferente da origem"
ORIGINAL_SERVICE_ROLE_KEY="$(read_project_env_value "$ORIGINAL_DIR/.env" SERVICE_ROLE_KEY_PROJETO)"
ORIGINAL_S3_CREDENTIAL_ID="$(read_project_env_value "$ORIGINAL_DIR/.env" S3_PROTOCOL_CREDENTIAL_ID)"
ORIGINAL_S3_ACCESS_KEY="$(read_project_env_value "$ORIGINAL_DIR/.env" S3_PROTOCOL_ACCESS_KEY_ID)"
ORIGINAL_S3_SECRET_KEY="$(read_project_env_value "$ORIGINAL_DIR/.env" S3_PROTOCOL_ACCESS_KEY_SECRET)"
ORIGINAL_S3_ENABLED="$(read_project_env_value "$ORIGINAL_DIR/.env" S3_PROTOCOL_ENABLED)"
ORIGINAL_VECTOR_ENABLED="$(read_project_env_value "$ORIGINAL_DIR/.env" VECTOR_BUCKETS_ENABLED)"
storage_validate_bool S3_PROTOCOL_ENABLED "$ORIGINAL_S3_ENABLED" \
  || die "S3_PROTOCOL_ENABLED da origem invalido"
storage_validate_bool VECTOR_BUCKETS_ENABLED "$ORIGINAL_VECTOR_ENABLED" \
  || die "VECTOR_BUCKETS_ENABLED da origem invalido"
(
  S3_PROTOCOL_CREDENTIAL_ID="$ORIGINAL_S3_CREDENTIAL_ID"
  S3_PROTOCOL_ACCESS_KEY_ID="$ORIGINAL_S3_ACCESS_KEY"
  S3_PROTOCOL_ACCESS_KEY_SECRET="$ORIGINAL_S3_SECRET_KEY"
  vector_validate_s3_credentials
) || die "Credenciais SigV4 da origem invalidas"
storage_assert_project_identity "$ORIGINAL_PROJECT" "$ORIGINAL_UUID" \
  || die "Identidade Storage da origem diverge do control plane"
storage_assert_project_identity "$NEW_PROJECT" "$PROJECT_UUID" \
  || die "Identidade Storage do clone diverge do control plane"
storage_wait_global || die "Storage compartilhado indisponivel"
storage_validate_tenant "$ORIGINAL_UUID" "$ORIGINAL_SERVICE_ROLE_KEY" \
  "$ORIGINAL_S3_ACCESS_KEY" "$ORIGINAL_S3_SECRET_KEY" \
  "$ORIGINAL_S3_ENABLED" "$ORIGINAL_VECTOR_ENABLED" \
  || die "Tenant Storage da origem nao esta saudavel"
storage_assert_project_gateway "$ORIGINAL_UUID" "$ORIGINAL_PROJECT" \
  "$ORIGINAL_SERVICE_ROLE_KEY" || die "Nginx da origem nao resolveu seu tenant"
storage_assert_tenant_absent "$PROJECT_UUID" || die "Tenant UUID do clone ja existe"
CREATED_STORAGE=1

normalize_public_base_url() {
  local url="${1%/}" proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then printf '%s' "$url"; return; fi
  [[ "$proto" == "http" || "$proto" == "https" ]] \
    || die "SERVER_PROTO deve ser http ou https quando SERVER_URL nao inclui esquema"
  printf '%s://%s' "$proto" "$url"
}
escape_sed_replacement() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
generate_jwt() {
  local payload="$1" secret="$2" header='{"alg":"HS256","typ":"JWT"}'
  local header_b64 payload_b64 signature
  header_b64=$(printf '%s' "$header" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  payload_b64=$(printf '%s' "$payload" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  signature=$(printf '%s' "$header_b64.$payload_b64" \
    | openssl dgst -binary -sha256 -hmac "$secret" \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  printf '%s' "$header_b64.$payload_b64.$signature"
}

PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$NEW_PROJECT"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"
JWT_SECRET_PROJETO=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n\r')
now_epoch=$(date +%s)
exp=$((now_epoch + (3 * 30 * 24 * 3600)))
ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
GLOBAL_ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET")
CONFIG_TOKEN_PROJETO=$(openssl rand -hex 32 | tr -d '\n\r')
API_GATEWAY_TOKEN_PROJETO="${API_GATEWAY_TOKEN_PROJETO:-$(openssl rand -hex 32 | tr -d '\n\r')}"
FILE_SIZE_LIMIT="$(grep -m1 '^FILE_SIZE_LIMIT=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"
ENABLE_IMAGE_TRANSFORMATION="$(grep -m1 '^ENABLE_IMAGE_TRANSFORMATION=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"
S3_PROTOCOL_ENABLED="$(grep -m1 '^S3_PROTOCOL_ENABLED=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"
VECTOR_BUCKETS_ENABLED="$(grep -m1 '^VECTOR_BUCKETS_ENABLED=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"
VECTOR_MAX_BUCKETS="$(grep -m1 '^VECTOR_MAX_BUCKETS=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"
VECTOR_MAX_INDEXES="$(grep -m1 '^VECTOR_MAX_INDEXES=' "$SCRIPT_DIR/.envtemplate" | cut -d= -f2-)"

template_to_file() {
  local template="$1" output="$2"
  sed \
    -e "s|{{anon_key}}|$(escape_sed_replacement "$ANON_TOKEN")|g" \
    -e "s|{{service_role_key}}|$(escape_sed_replacement "$SERVICE_TOKEN")|g" \
    -e "s|{{project_id}}|$(escape_sed_replacement "$NEW_PROJECT")|g" \
    -e "s|{{project_uuid}}|$(escape_sed_replacement "$PROJECT_UUID")|g" \
    -e "s|{{config_token}}|$(escape_sed_replacement "$CONFIG_TOKEN_PROJETO")|g" \
    -e "s|{{jwt_secret}}|$(escape_sed_replacement "$JWT_SECRET_PROJETO")|g" \
    -e "s|{{api_gateway_token}}|$(escape_sed_replacement "$API_GATEWAY_TOKEN_PROJETO")|g" \
    -e "s|{{server_url}}|$(escape_sed_replacement "$SERVER_URL")|g" \
    -e "s|{{public_base_url}}|$(escape_sed_replacement "$PUBLIC_BASE_URL")|g" \
    -e "s|{{project_public_url}}|$(escape_sed_replacement "$PROJECT_PUBLIC_URL")|g" \
    -e "s|{{project_auth_external_url}}|$(escape_sed_replacement "$PROJECT_AUTH_EXTERNAL_URL")|g" \
    -e "s|{{project_root}}|$(escape_sed_replacement "$HOST_PROJECT_ROOT")|g" \
    -e "s|{{s3_protocol_credential_id}}|$(escape_sed_replacement "$S3_PROTOCOL_CREDENTIAL_ID")|g" \
    -e "s|{{s3_protocol_access_key_id}}|$(escape_sed_replacement "$S3_PROTOCOL_ACCESS_KEY_ID")|g" \
    -e "s|{{s3_protocol_access_key_secret}}|$(escape_sed_replacement "$S3_PROTOCOL_ACCESS_KEY_SECRET")|g" \
    "$template" > "$output"
}

mkdir -p "$OUT_DIR/nginx" "$OUT_DIR/pooler"
CREATED_DIR=1

realtime_tables=$(docker exec supabase-db psql -U supabase_admin -d "$ORIGINAL_DB" -tAc \
  "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_publication_tables WHERE pubname = 'supabase_realtime';")

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "CREATE DATABASE $NEW_DB;"
CREATED_DB=1

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "REVOKE CONNECT, TEMPORARY ON DATABASE $NEW_DB FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE $NEW_DB TO pgbouncer; GRANT CONNECT, TEMPORARY ON DATABASE $NEW_DB TO authenticator; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $NEW_DB TO supabase_storage_admin; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $NEW_DB TO supabase_auth_admin;"
  provision_platform_reader "$NEW_DB"

if [[ "$COPY_MODE" == "with-data" ]]; then
  for source_service in nginx rest auth meta; do
    source_name="supabase-$source_service-$ORIGINAL_PROJECT"
    if [[ "$(docker inspect -f '{{.State.Running}}' "$source_name" 2>/dev/null || true)" == "true" ]]; then
      SOURCE_CONTAINERS+="${SOURCE_CONTAINERS:+$'\n'}$source_name"
    fi
  done
  backup_stop_project_containers "$ORIGINAL_PROJECT" >/dev/null
  source_pool_code="$(backup_http_code supabase-pooler GET \
    "/api/tenants/$ORIGINAL_PROJECT/terminate" "$GLOBAL_ANON_TOKEN")"
  backup_accepted_code "$source_pool_code" 200 204 404 \
    || die "Supavisor nao encerrou pools da origem (HTTP $source_pool_code)"
  SOURCE_STORAGE_QUIESCED=1
  storage_quiesce_tenant "$ORIGINAL_UUID" "$ORIGINAL_PROJECT" \
    "$ORIGINAL_SERVICE_ROLE_KEY" || die "Storage nao bloqueou a data plane da origem"
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$ORIGINAL_DB' AND usename = 'supabase_storage_admin' AND pid <> pg_backend_pid();" \
    >/dev/null
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --exclude-schema=realtime > "$DUMP_FILE"
else
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --schema=auth --schema=storage --schema-only > "$DUMP_FILE"
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --exclude-schema=auth --exclude-schema=storage --exclude-schema=realtime --schema-only >> "$DUMP_FILE"
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" --data-only \
    -t 'auth.schema_migrations' -t 'storage.migrations' >> "$DUMP_FILE"
fi

docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
  --schema=realtime --schema-only > "$RT_STRUCTURE_FILE"
docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" --data-only \
  -t 'realtime.schema_migrations' > "$RT_MIGRATIONS_FILE"

if [[ "$COPY_MODE" == "with-data" ]]; then
  storage_clone_tenant_namespace "$ORIGINAL_UUID" "$PROJECT_UUID" \
    || die "Falha ao copiar objetos para o namespace do clone"
  resume_source_project || die "Clone capturado, mas a origem nao foi religada"
fi

docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" < "$DUMP_FILE"
[[ -s "$RT_STRUCTURE_FILE" ]] || die "Dump da estrutura Realtime ficou vazio"
[[ -s "$RT_MIGRATIONS_FILE" ]] || die "Dump das migrations Realtime ficou vazio"
docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" < "$RT_STRUCTURE_FILE"
docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" < "$RT_MIGRATIONS_FILE"

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
UPDATE auth.schema_migrations SET dirty = false WHERE dirty = true;
UPDATE storage.migrations SET dirty = false WHERE dirty = true;
SQL
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "ALTER DATABASE \"$NEW_DB\" SET search_path TO public, auth, storage, extensions;"

# supabase_storage_admin tem search_path=storage fixado em nivel de role pela
# imagem base do Postgres, o que tem precedencia sobre o ALTER DATABASE acima.
# Sem este override por role+banco, o Storage API nao enxerga o schema public
# onde o pgvector foi instalado e toda operacao de Vector Buckets (halfvec)
# falha com "type halfvec does not exist".
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "ALTER ROLE supabase_storage_admin IN DATABASE \"$NEW_DB\" SET search_path = storage, public;"

vector_validate_database "$NEW_DB" || die "Clone sem pgvector valido"
vector_strip_copied_wrappers "$NEW_DB" || die "Falha ao remover wrappers/segredos copiados"
if [[ "$COPY_MODE" == "with-data" ]]; then
  vector_rekey_physical_tables "$NEW_DB" "$ORIGINAL_UUID" "$PROJECT_UUID" \
    || die "Falha ao isolar tabelas fisicas de Storage Vectors do clone"
fi

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" -c \
  "TRUNCATE realtime.subscription RESTART IDENTITY CASCADE;"

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" <<'SQL'
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

if [[ -n "$realtime_tables" ]]; then
  IFS=',' read -ra tables <<< "$realtime_tables"
  for table_name in "${tables[@]}"; do
    [[ -n "$table_name" ]] || continue
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" -c \
      "ALTER PUBLICATION supabase_realtime ADD TABLE $table_name;"
  done
fi

if [[ "$COPY_MODE" == "schema-only" ]]; then
  storage_create_empty_tenant_namespace "$PROJECT_UUID" \
    || die "Falha ao criar namespace vazio do clone"
fi

realtime_payload=$(jq -cn \
  --arg uuid "$PROJECT_UUID" --arg secret "$JWT_SECRET_PROJETO" \
  --arg db "$NEW_DB" --arg host "$POSTGRES_HOST" --arg port "$POSTGRES_PORT" \
  --arg password "$POSTGRES_PASSWORD" --arg slot "supabase_realtime_replication_slot_$NEW_PROJECT" \
  --argjson max_users "$MAX_CONCURRENT_USERS" \
  '{tenant:{name:$uuid,external_id:$uuid,jwt_secret:$secret,max_concurrent_users:$max_users,extensions:[{type:"postgres_cdc_rls",settings:{db_name:$db,db_host:$host,db_user:"supabase_admin",db_password:$password,db_port:$port,region:"us-west-1",poll_interval_ms:100,poll_max_record_bytes:1048576,ssl_enforced:false,slot_name:$slot}}]}}')
CREATED_REALTIME=1
response=$(docker exec realtime-dev.supabase-realtime curl -sS -w '\n%{http_code}' \
  -X POST http://localhost:4000/api/tenants -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ANON_TOKEN" -d "$realtime_payload")
code=$(echo "$response" | tail -n1)
[[ "$code" == "200" || "$code" == "201" ]] || die "Falha no Realtime (HTTP $code)"

pg_version=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT version();" | awk '{print $2}')
supavisor_payload=$(jq -cn \
  --arg id "$NEW_PROJECT" --arg host "$POSTGRES_HOST" --arg port "$POSTGRES_PORT" \
  --arg password "$POSTGRES_PASSWORD" --arg version "$pg_version" \
  '{tenant:{external_id:$id,db_host:$host,db_port:$port,db_database:("_supabase_"+$id),ip_version:"auto",enforce_ssl:false,require_user:false,auth_query:"SELECT * FROM pgbouncer.get_auth($1)",default_max_clients:800,default_pool_size:40,default_parameter_status:{server_version:$version},users:[{db_user:"pgbouncer",db_password:$password,mode_type:"transaction",pool_size:40,is_manager:true}]}}')
CREATED_SUPAVISOR=1
response=$(docker exec supabase-pooler curl -sS -w '\n%{http_code}' \
  -X PUT "http://localhost:4000/api/tenants/$NEW_PROJECT" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GLOBAL_ANON_TOKEN" -d "$supavisor_payload")
code=$(echo "$response" | tail -n1)
[[ "$code" == "200" || "$code" == "201" || "$code" == "204" ]] || die "Falha no Supavisor (HTTP $code)"

storage_provision_tenant "$PROJECT_UUID" "$NEW_PROJECT" "$JWT_SECRET_PROJETO" \
  "$ANON_TOKEN" "$SERVICE_TOKEN" "$FILE_SIZE_LIMIT" \
  "$ENABLE_IMAGE_TRANSFORMATION" "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  "$VECTOR_MAX_BUCKETS" "$VECTOR_MAX_INDEXES" \
  || die "Falha ao registrar tenant Storage do clone"

IFS=$'\t' read -r S3_PROTOCOL_CREDENTIAL_ID S3_PROTOCOL_ACCESS_KEY_ID \
  S3_PROTOCOL_ACCESS_KEY_SECRET \
  <<<"$(storage_create_s3_credentials "$PROJECT_UUID")"
vector_validate_s3_credentials || die "Credenciais SigV4 do clone invalidas"
[[ "$S3_PROTOCOL_CREDENTIAL_ID" != "$ORIGINAL_S3_CREDENTIAL_ID" ]] \
  || die "Storage reutilizou o identificador SigV4 da origem"
[[ "$S3_PROTOCOL_ACCESS_KEY_ID" != "$ORIGINAL_S3_ACCESS_KEY" ]] \
  || die "Storage reutilizou a access key SigV4 da origem"
[[ "$S3_PROTOCOL_ACCESS_KEY_SECRET" != "$ORIGINAL_S3_SECRET_KEY" ]] \
  || die "Storage reutilizou o secret SigV4 da origem"
SERVICE_ROLE_KEY_PROJETO="$SERVICE_TOKEN"
export PROJECT_UUID SERVICE_ROLE_KEY_PROJETO S3_PROTOCOL_CREDENTIAL_ID \
  S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET

template_to_file "$SCRIPT_DIR/nginxtemplate" "$OUT_DIR/nginx/nginx_${NEW_PROJECT}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate" "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
template_to_file "$SCRIPT_DIR/.dockerignore" "$OUT_DIR/.dockerignore"
chmod 600 "$OUT_DIR/.env"
apply_project_resource_limits "$PROJECT_ROOT/.env" "$OUT_DIR/.env" "${PROJECT_RESOURCE_PROFILE_OVERRIDE:-}"
chmod 644 "$OUT_DIR/nginx/nginx_${NEW_PROJECT}.conf" "$OUT_DIR/.dockerignore"

COMPOSE_STARTED=1
(
  cd "$OUT_DIR"
  docker compose -p "$NEW_PROJECT" --env-file ../../.env --env-file .env up --build -d
)

vector_validate_storage_api "$PROJECT_UUID" "$SERVICE_TOKEN" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant Storage/S3/Vectors do clone nao ficou saudavel"
storage_assert_project_gateway "$PROJECT_UUID" "$NEW_PROJECT" "$SERVICE_TOKEN" \
  || die "Nginx do clone nao resolveu o tenant Storage correto"

vector_sync_project_wrappers "$NEW_PROJECT" || die "Falha ao recriar wrappers vetoriais do clone"

trap - ERR TERM INT HUP
cleanup_tmp
trap - EXIT
echo "✅ Projeto $NEW_PROJECT duplicado com credenciais SigV4 e wrappers isolados"
