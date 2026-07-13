#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"

ORIGINAL_PROJECT="${1:-}"
NEW_PROJECT="${2:-}"
COPY_MODE="${3:-schema-only}"
PROJECT_UUID="${4:-}"
[[ -n "$ORIGINAL_PROJECT" && -n "$NEW_PROJECT" && -n "$PROJECT_UUID" ]] \
  || die "Uso: $0 <original_project> <new_project> [with-data|schema-only] <project_uuid>"
[[ "$COPY_MODE" == "with-data" || "$COPY_MODE" == "schema-only" ]] \
  || die "copy_mode deve ser with-data ou schema-only"

ORIGINAL_PROJECT="$(echo "$ORIGINAL_PROJECT" | tr '[:upper:]' '[:lower:]')"
NEW_PROJECT="$(echo "$NEW_PROJECT" | tr '[:upper:]' '[:lower:]')"
[[ "$ORIGINAL_PROJECT" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || die "Projeto original invalido"
[[ "$NEW_PROJECT" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || die "Novo projeto invalido"

RESERVED=(default select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback)
for word in "${RESERVED[@]}"; do
  [[ "$NEW_PROJECT" != "$word" ]] || die "'$NEW_PROJECT' e palavra reservada"
done

set -a
source "$PROJECT_ROOT/.env"
set +a

[[ -n "${JWT_SECRET:-}" ]] || die "JWT_SECRET ausente"
[[ -n "${SERVER_URL:-}" ]] || die "SERVER_URL ausente"

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
COMPOSE_STARTED=0

cleanup_tmp() { rm -rf "$TMP_DIR"; }
rollback() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Duplicacao falhou; limpando recursos do clone..." >&2

  if [[ "$COMPOSE_STARTED" -eq 1 && -d "$OUT_DIR" ]]; then
    (cd "$OUT_DIR" && docker compose -p "$NEW_PROJECT" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_SUPAVISOR" -eq 1 ]]; then
    docker exec supabase-pooler curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$NEW_PROJECT" >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_REALTIME" -eq 1 ]]; then
    docker exec realtime-dev.supabase-realtime curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$PROJECT_UUID" >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_DB" -eq 1 ]]; then
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$NEW_DB' AND pid <> pg_backend_pid(); DROP DATABASE IF EXISTS $NEW_DB;" \
      >/dev/null 2>&1 || true
  fi
  if [[ "$CREATED_DIR" -eq 1 ]]; then rm -rf "$OUT_DIR"; fi
  cleanup_tmp
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
[[ ! -e "$OUT_DIR" ]] || die "Projeto $NEW_PROJECT ja existe"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$ORIGINAL_DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco original $ORIGINAL_DB nao encontrado"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$NEW_DB';" | tr -d '[:space:]')" == "0" ]] \
  || die "Banco $NEW_DB ja existe"

normalize_public_base_url() {
  local url="${1%/}" proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then printf '%s' "$url"; return; fi
  printf '%s://%s' "${proto:-https}" "$url"
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
unset S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET
vector_ensure_s3_credentials || die "Falha ao gerar credenciais SigV4 exclusivas do clone"

template_to_file() {
  local template="$1" output="$2"
  sed \
    -e "s|{{anon_key}}|$(escape_sed_replacement "$ANON_TOKEN")|g" \
    -e "s|{{service_role_key}}|$(escape_sed_replacement "$SERVICE_TOKEN")|g" \
    -e "s|{{project_id}}|$(escape_sed_replacement "$NEW_PROJECT")|g" \
    -e "s|{{project_uuid}}|$(escape_sed_replacement "$PROJECT_UUID")|g" \
    -e "s|{{config_token}}|$(escape_sed_replacement "$CONFIG_TOKEN_PROJETO")|g" \
    -e "s|{{jwt_secret}}|$(escape_sed_replacement "$JWT_SECRET_PROJETO")|g" \
    -e "s|{{server_url}}|$(escape_sed_replacement "$SERVER_URL")|g" \
    -e "s|{{public_base_url}}|$(escape_sed_replacement "$PUBLIC_BASE_URL")|g" \
    -e "s|{{project_public_url}}|$(escape_sed_replacement "$PROJECT_PUBLIC_URL")|g" \
    -e "s|{{project_auth_external_url}}|$(escape_sed_replacement "$PROJECT_AUTH_EXTERNAL_URL")|g" \
    -e "s|{{project_root}}|$(escape_sed_replacement "$HOST_PROJECT_ROOT")|g" \
    -e "s|{{s3_protocol_access_key_id}}|$(escape_sed_replacement "$S3_PROTOCOL_ACCESS_KEY_ID")|g" \
    -e "s|{{s3_protocol_access_key_secret}}|$(escape_sed_replacement "$S3_PROTOCOL_ACCESS_KEY_SECRET")|g" \
    "$template" > "$output"
}

mkdir -p "$OUT_DIR/nginx" "$OUT_DIR/pooler"
CREATED_DIR=1
template_to_file "$SCRIPT_DIR/nginxtemplate" "$OUT_DIR/nginx/nginx_${NEW_PROJECT}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate" "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
chmod 600 "$OUT_DIR/.env" "$OUT_DIR/nginx/nginx_${NEW_PROJECT}.conf"

realtime_tables=$(docker exec supabase-db psql -U supabase_admin -d "$ORIGINAL_DB" -tAc \
  "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_publication_tables WHERE pubname = 'supabase_realtime';" \
  2>/dev/null || true)

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "CREATE DATABASE $NEW_DB;"
CREATED_DB=1

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "REVOKE CONNECT, TEMPORARY ON DATABASE $NEW_DB FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE $NEW_DB TO pgbouncer; GRANT CONNECT, TEMPORARY ON DATABASE $NEW_DB TO authenticator; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $NEW_DB TO supabase_storage_admin; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $NEW_DB TO supabase_auth_admin;"

if [[ "$COPY_MODE" == "with-data" ]]; then
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --exclude-schema=realtime > "$DUMP_FILE"
else
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --schema=auth --schema=storage --schema-only > "$DUMP_FILE"
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
    --exclude-schema=auth --exclude-schema=storage --exclude-schema=realtime --schema-only >> "$DUMP_FILE"
  docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" --data-only \
    -t 'auth.schema_migrations' -t 'storage.migrations' >> "$DUMP_FILE" || true
fi

docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" \
  --schema=realtime --schema-only > "$RT_STRUCTURE_FILE" || true
docker exec supabase-db pg_dump -U supabase_admin -d "$ORIGINAL_DB" --data-only \
  -t 'realtime.schema_migrations' > "$RT_MIGRATIONS_FILE" 2>/dev/null || true

docker exec -i supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" < "$DUMP_FILE"
[[ ! -s "$RT_STRUCTURE_FILE" ]] || docker exec -i supabase-db psql -U supabase_admin -d "$NEW_DB" < "$RT_STRUCTURE_FILE"
[[ ! -s "$RT_MIGRATIONS_FILE" ]] || docker exec -i supabase-db psql -U supabase_admin -d "$NEW_DB" < "$RT_MIGRATIONS_FILE" || true

docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$NEW_DB" <<'SQL'
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
UPDATE auth.schema_migrations SET dirty = false WHERE dirty = true;
UPDATE storage.migrations SET dirty = false WHERE dirty = true;
SQL
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "ALTER DATABASE \"$NEW_DB\" SET search_path TO public, auth, storage, extensions;"

vector_validate_database "$NEW_DB" || die "Clone sem pgvector valido"
vector_strip_copied_wrappers "$NEW_DB" || die "Falha ao remover wrappers/segredos copiados"

docker exec supabase-db psql -U supabase_admin -d "$NEW_DB" -c \
  "TRUNCATE realtime.subscription RESTART IDENTITY CASCADE;" 2>/dev/null || true

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

if [[ "$COPY_MODE" == "with-data" && -d "$ORIGINAL_DIR/storage" ]]; then
  mkdir -p "$OUT_DIR/storage"
  (cd "$ORIGINAL_DIR/storage" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
    | (cd "$OUT_DIR/storage" && tar --xattrs --xattrs-include='*' --acls -xpf -)
else
  mkdir -p "$OUT_DIR/storage/stub/stub"
fi

realtime_payload=$(jq -cn \
  --arg uuid "$PROJECT_UUID" --arg secret "$JWT_SECRET_PROJETO" \
  --arg db "$NEW_DB" --arg host "$POSTGRES_HOST" --arg port "$POSTGRES_PORT" \
  --arg password "$POSTGRES_PASSWORD" --arg slot "supabase_realtime_replication_slot_$NEW_PROJECT" \
  --argjson max_users "${MAX_CONCURRENT_USERS:-200}" \
  '{tenant:{name:$uuid,external_id:$uuid,jwt_secret:$secret,max_concurrent_users:$max_users,extensions:[{type:"postgres_cdc_rls",settings:{db_name:$db,db_host:$host,db_user:"supabase_admin",db_password:$password,db_port:$port,region:"us-west-1",poll_interval_ms:100,poll_max_record_bytes:1048576,ssl_enforced:false,slot_name:$slot}}]}}')
response=$(docker exec realtime-dev.supabase-realtime curl -sS -w '\n%{http_code}' \
  -X POST http://localhost:4000/api/tenants -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $ANON_TOKEN" -d "$realtime_payload")
code=$(echo "$response" | tail -n1)
[[ "$code" == "200" || "$code" == "201" ]] || die "Falha no Realtime (HTTP $code)"
CREATED_REALTIME=1

pg_version=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT version();" | awk '{print $2}')
supavisor_payload=$(jq -cn \
  --arg id "$NEW_PROJECT" --arg host "$POSTGRES_HOST" --arg port "$POSTGRES_PORT" \
  --arg password "$POSTGRES_PASSWORD" --arg version "$pg_version" \
  '{tenant:{external_id:$id,db_host:$host,db_port:$port,db_database:("_supabase_"+$id),ip_version:"auto",enforce_ssl:false,require_user:false,auth_query:"SELECT * FROM pgbouncer.get_auth($1)",default_max_clients:800,default_pool_size:40,default_parameter_status:{server_version:$version},users:[{db_user:"pgbouncer",db_password:$password,mode_type:"transaction",pool_size:40,is_manager:true}]}}')
response=$(docker exec supabase-pooler curl -sS -w '\n%{http_code}' \
  -X PUT "http://localhost:4000/api/tenants/$NEW_PROJECT" -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GLOBAL_ANON_TOKEN" -d "$supavisor_payload")
code=$(echo "$response" | tail -n1)
[[ "$code" == "200" || "$code" == "201" || "$code" == "204" ]] || die "Falha no Supavisor (HTTP $code)"
CREATED_SUPAVISOR=1

COMPOSE_STARTED=1
(
  cd "$OUT_DIR"
  docker compose -p "$NEW_PROJECT" --env-file ../../.env --env-file .env up --build -d
)

storage_container="supabase-storage-$NEW_PROJECT"
for _ in $(seq 1 60); do
  status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$storage_container" 2>/dev/null || true)
  [[ "$status" == "healthy" ]] && break
  [[ "$status" == "unhealthy" || "$status" == "exited" || "$status" == "dead" ]] \
    && die "Storage do clone terminou com status $status"
  sleep 2
done
[[ "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$storage_container")" == "healthy" ]] \
  || die "Storage do clone nao ficou healthy"

vector_sync_project_wrappers "$NEW_PROJECT" || die "Falha ao recriar wrappers vetoriais do clone"

trap - ERR TERM INT HUP
cleanup_tmp
trap - EXIT
echo "✅ Projeto $NEW_PROJECT duplicado com credenciais SigV4 e wrappers isolados"
