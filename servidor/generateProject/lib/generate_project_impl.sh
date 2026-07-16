#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"

TRANSACTION_DIR="$PROJECT_ROOT/.generate_transaction_$$"
CREATED_DIRS=()
CREATED_DB=""
CREATED_REALTIME_TENANT=""
CREATED_SUPAVISOR_TENANT=""
COMPOSE_STARTED=0

init_transaction() {
  mkdir -p "$TRANSACTION_DIR"
  echo "🔄 Sistema de transação inicializado"
}

register_created_dir() { CREATED_DIRS+=("$1"); }
register_created_db() { CREATED_DB="$1"; }
register_realtime_tenant() { CREATED_REALTIME_TENANT="$1"; }
register_supavisor_tenant() { CREATED_SUPAVISOR_TENANT="$1"; }

commit_transaction() {
  rm -rf "$TRANSACTION_DIR"
  echo "✅ Transação confirmada. Backups removidos."
}

rollback_transaction() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Erro detectado! Revertendo alterações..."

  if [[ "$COMPOSE_STARTED" -eq 1 && -n "${OUT_DIR:-}" && -d "$OUT_DIR" ]]; then
    (cd "$OUT_DIR" && docker compose -p "$PROJECT_ID" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 || true
  fi

  if [[ -n "$CREATED_SUPAVISOR_TENANT" ]]; then
    docker exec supabase-pooler curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$CREATED_SUPAVISOR_TENANT" >/dev/null 2>&1 || true
  fi
  if [[ -n "$CREATED_REALTIME_TENANT" ]]; then
    docker exec realtime-dev.supabase-realtime curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$CREATED_REALTIME_TENANT" >/dev/null 2>&1 || true
  fi
  if [[ -n "$CREATED_DB" ]]; then
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$CREATED_DB' AND pid <> pg_backend_pid(); DROP DATABASE IF EXISTS $CREATED_DB;" \
      >/dev/null 2>&1 || true
  fi
  for ((idx=${#CREATED_DIRS[@]}-1; idx>=0; idx--)); do
    rm -rf "${CREATED_DIRS[idx]}"
  done
  rm -rf "$TRANSACTION_DIR"
  echo "⚠️  Todas as alterações foram revertidas."
  exit "$status"
}
trap rollback_transaction ERR
trap 'rollback_transaction 143' TERM
trap 'rollback_transaction 130' INT
trap 'rollback_transaction 129' HUP

set -a
source "$PROJECT_ROOT/.env"
set +a

[[ -n "${JWT_SECRET:-}" ]] || die "JWT_SECRET ausente"
[[ -n "${SERVER_URL:-}" ]] || die "SERVER_URL ausente"

PROJECT_ID="${1:-}"
PROJECT_UUID="${2:-}"
[[ -n "$PROJECT_ID" && -n "$PROJECT_UUID" ]] \
  || die "Uso: $0 <project_id> <project_uuid>"

PROJECT_ID="$(echo "$PROJECT_ID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "Nome deve começar com letra minúscula/_ e conter só minúsculas, dígitos ou _ (3–40 chars)"
[[ "$PROJECT_ID" != *.* ]] || die "Nome não pode conter ponto (.)"

RESERVED=(default select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback)
for word in "${RESERVED[@]}"; do
  [[ "$PROJECT_ID" != "$word" ]] || die "'$PROJECT_ID' é palavra reservada."
done

OUT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
[[ ! -e "$OUT_DIR" ]] || die "Projeto '$PROJECT_ID' já existe em projects/"

docker_must_exist() {
  docker inspect "$1" >/dev/null 2>&1 || die "Contêiner $1 não encontrado"
}

generate_jwt() {
  local payload="$1" secret="$2"
  local header='{"alg":"HS256","typ":"JWT"}'
  local header_b64 payload_b64 signature
  header_b64=$(printf '%s' "$header" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  payload_b64=$(printf '%s' "$payload" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  signature=$(printf '%s' "$header_b64.$payload_b64" \
    | openssl dgst -binary -sha256 -hmac "$secret" \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  printf '%s' "$header_b64.$payload_b64.$signature"
}

get_pg_version() {
  docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT version();" \
    | awk '{print $2}'
}

generate_db() {
  local db="_supabase_$PROJECT_ID"
  [[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$db';" | tr -d '[:space:]')" == "0" ]] \
    || die "Banco $db já existe"

  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "CREATE DATABASE $db TEMPLATE _supabase_template;"
  register_created_db "$db"
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "REVOKE CONNECT, TEMPORARY ON DATABASE $db FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE $db TO pgbouncer; GRANT CONNECT, TEMPORARY ON DATABASE $db TO authenticator; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $db TO supabase_storage_admin; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $db TO supabase_auth_admin;"
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "ALTER ROLE supabase_storage_admin IN DATABASE $db SET search_path = storage, public;"
  vector_validate_database "$db" || die "Banco do projeto sem suporte a Storage Vectors"
}

normalize_public_base_url() {
  local url="${1%/}" proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then printf '%s' "$url"; return; fi
  printf '%s://%s' "${proto:-https}" "$url"
}
escape_sed_replacement() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }

PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$PROJECT_ID"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"

template_to_file() {
  local template="$1" output="$2"
  sed \
    -e "s|{{anon_key}}|$(escape_sed_replacement "$ANON_TOKEN")|g" \
    -e "s|{{service_role_key}}|$(escape_sed_replacement "$SERVICE_TOKEN")|g" \
    -e "s|{{project_id}}|$(escape_sed_replacement "$PROJECT_ID")|g" \
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

realtime_tenant() {
  docker_must_exist realtime-dev.supabase-realtime
  local payload response http_code body
  payload=$(jq -cn \
    --arg uuid "$PROJECT_UUID" --arg secret "$JWT_SECRET_PROJETO" \
    --arg db "_supabase_$PROJECT_ID" --arg host "$POSTGRES_HOST" \
    --arg port "$POSTGRES_PORT" --arg password "$POSTGRES_PASSWORD" \
    --arg slot "supabase_realtime_replication_slot_$PROJECT_ID" \
    --argjson max_users "${MAX_CONCURRENT_USERS:-200}" \
    '{tenant:{name:$uuid,external_id:$uuid,jwt_secret:$secret,max_concurrent_users:$max_users,extensions:[{type:"postgres_cdc_rls",settings:{db_name:$db,db_host:$host,db_user:"supabase_admin",db_password:$password,db_port:$port,region:"us-west-1",poll_interval_ms:100,poll_max_record_bytes:1048576,ssl_enforced:false,slot_name:$slot}}]}}')
  response=$(docker exec realtime-dev.supabase-realtime curl -sS -w '\n%{http_code}' \
    -X POST http://localhost:4000/api/tenants \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $ANON_TOKEN" \
    -d "$payload")
  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | head -n-1)
  [[ "$http_code" == "200" || "$http_code" == "201" ]] \
    || die "Falha ao criar tenant Realtime (HTTP $http_code): $body"
  register_realtime_tenant "$PROJECT_UUID"
}

supavisor_tenant() {
  docker_must_exist supabase-pooler
  local pg_version payload response http_code body
  pg_version="$(get_pg_version)"
  payload=$(jq -cn \
    --arg id "$PROJECT_ID" --arg host "$POSTGRES_HOST" --arg port "$POSTGRES_PORT" \
    --arg password "$POSTGRES_PASSWORD" --arg version "$pg_version" \
    '{tenant:{external_id:$id,db_host:$host,db_port:$port,db_database:("_supabase_"+$id),ip_version:"auto",enforce_ssl:false,require_user:false,auth_query:"SELECT * FROM pgbouncer.get_auth($1)",default_max_clients:800,default_pool_size:40,default_parameter_status:{server_version:$version},users:[{db_user:"pgbouncer",db_password:$password,mode_type:"transaction",pool_size:40,is_manager:true}]}}')
  response=$(docker exec supabase-pooler curl -sS -w '\n%{http_code}' \
    -X PUT "http://localhost:4000/api/tenants/$PROJECT_ID" \
    -H 'Content-Type: application/json' -H "Authorization: Bearer $GLOBAL_ANON_TOKEN" \
    -d "$payload")
  http_code=$(echo "$response" | tail -n1)
  body=$(echo "$response" | head -n-1)
  [[ "$http_code" == "200" || "$http_code" == "201" || "$http_code" == "204" ]] \
    || die "Falha ao criar tenant Supavisor (HTTP $http_code): $body"
  register_supavisor_tenant "$PROJECT_ID"
}

JWT_SECRET_PROJETO=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n\r')
now_epoch=$(date +%s)
exp=$((now_epoch + (3 * 30 * 24 * 3600)))
ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
GLOBAL_ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET")
CONFIG_TOKEN_PROJETO=$(openssl rand -hex 32 | tr -d '\n\r')
unset S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET
vector_ensure_s3_credentials || die "Falha ao gerar credenciais SigV4 do projeto"

init_transaction
mkdir -p "$OUT_DIR/storage/stub/stub" "$OUT_DIR/nginx" "$OUT_DIR/pooler"
register_created_dir "$OUT_DIR"

template_to_file "$SCRIPT_DIR/nginxtemplate" "$OUT_DIR/nginx/nginx_${PROJECT_ID}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate" "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
chmod 644 "$OUT_DIR/.env" "$OUT_DIR/nginx/nginx_${PROJECT_ID}.conf"

generate_db
realtime_tenant
supavisor_tenant

COMPOSE_STARTED=1
(
  cd "$OUT_DIR"
  docker compose -p "$PROJECT_ID" --env-file ../../.env --env-file .env up --build -d
)
vector_validate_storage_api "$PROJECT_ID" || die "Storage Vectors nao iniciou corretamente"

echo "✅  Projeto $PROJECT_ID configurado com Storage Vectors e SigV4"
commit_transaction
