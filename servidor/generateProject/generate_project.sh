#!/usr/bin/env bash
# generate_project.sh
set -euo pipefail

die() { echo "❌  $*" >&2; return 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

TRANSACTION_DIR="$PROJECT_ROOT/.generate_transaction_$$"
MODIFIED_FILES=()
CREATED_DIRS=()
CREATED_DB=""
CREATED_REALTIME_TENANT=""
CREATED_SUPAVISOR_TENANT=""

init_transaction() {
  mkdir -p "$TRANSACTION_DIR"
  echo "🔄 Sistema de transação inicializado"
}

register_created_dir() {
  local dir="$1"
  CREATED_DIRS+=("$dir")
}

register_created_db() {
  CREATED_DB="$1"
}

register_realtime_tenant() {
  CREATED_REALTIME_TENANT="$1"
}

register_supavisor_tenant() {
  CREATED_SUPAVISOR_TENANT="$1"
}

commit_transaction() {
  if [[ -d "$TRANSACTION_DIR" ]]; then
    rm -rf "$TRANSACTION_DIR"
    echo "✅ Transação confirmada. Backups removidos."
  fi
}

rollback_transaction() {
  echo "❌ Erro detectado! Revertendo alterações..."
  
  for ((idx=${#CREATED_DIRS[@]}-1; idx>=0; idx--)); do
    local dir="${CREATED_DIRS[idx]}"
    if [[ -d "$dir" ]]; then
      echo "   Removendo diretório: $dir"
      rm -rf "$dir"
    fi
  done
  
  if [[ -n "$CREATED_DB" ]]; then
    echo "   Removendo banco de dados: $CREATED_DB"
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "DROP DATABASE IF EXISTS $CREATED_DB;" 2>/dev/null || true
  fi
  
  if [[ -n "$CREATED_REALTIME_TENANT" ]]; then
    echo "   Removendo tenant Realtime: $CREATED_REALTIME_TENANT"
    docker exec realtime-dev.supabase-realtime curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$CREATED_REALTIME_TENANT" 2>/dev/null || true
  fi
  
  if [[ -n "$CREATED_SUPAVISOR_TENANT" ]]; then
    echo "   Removendo tenant Supavisor: $CREATED_SUPAVISOR_TENANT"
    docker exec supabase-pooler curl -s -X DELETE \
      "http://localhost:4000/api/tenants/$CREATED_SUPAVISOR_TENANT" 2>/dev/null || true
  fi
  
  if [[ -d "$TRANSACTION_DIR" ]]; then
    rm -rf "$TRANSACTION_DIR"
  fi
  
  echo "⚠️  Todas as alterações foram revertidas."
  exit 1
}

trap rollback_transaction ERR

set -a
source "$PROJECT_ROOT/.env"
set +a

[[ -z "${JWT_SECRET:-}" ]] && { echo "JWT_SECRET ausente"; exit 1; }
[[ -z "${SERVER_URL:-}" ]] && { echo "SERVER_URL ausente"; exit 1; }

PROJECT_ID="${1:-}"
PROJECT_UUID="${2:-}"
[[ -z "$PROJECT_ID" ]] && { echo "Uso: $0 <project_id> <project_uuid>"; exit 1; }
[[ -z "$PROJECT_UUID" ]] && { echo "Uso: $0 <project_id> <project_uuid>"; exit 1; }

PROJECT_ID_LOWER=$(echo "$PROJECT_ID" | tr '[:upper:]' '[:lower:]')

[[ "$PROJECT_ID_LOWER" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "Nome deve começar com letra minúscula/_ e conter só minúsculas, dígitos ou _ (3–40 chars)"

[[ "$PROJECT_ID_LOWER" == *.* ]] && die "Nome não pode conter ponto (.)"


RESERVED=(
  select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback
)
for word in "${RESERVED[@]}"; do
  [[ "$PROJECT_ID_LOWER" == "$word" ]] && die "'$PROJECT_ID_LOWER' é palavra reservada."
done

[[ -d "$PROJECT_ROOT/projects/$PROJECT_ID_LOWER" ]] \
  && die "Projeto '$PROJECT_ID_LOWER' já existe em projects/"

PROJECT_ID="$PROJECT_ID_LOWER"
echo "✔️  Nome de projeto validado: $PROJECT_ID"


docker_must_exist() {
  docker inspect "$1" >/dev/null 2>&1 || die "Contêiner $1 não encontrado"
}

generate_jwt() {
  local payload="$1" secret="$2"
  local header='{"alg":"HS256","typ":"JWT"}'
  b64() { printf '%s' "$1" | openssl base64 -A | tr '+/' '-_' | tr -d '='; }
  local header_b64 payload_b64 signature
  header_b64=$(b64 "$header")
  payload_b64=$(b64 "$payload")
  signature=$(printf '%s' "$header_b64.$payload_b64" \
              | openssl dgst -binary -sha256 -hmac "$secret" \
              | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  echo "$header_b64.$payload_b64.$signature"
}

get_pg_version() {
  docker exec supabase-db \
    psql -U supabase_admin -d postgres -tAc "SELECT version();" \
    | awk '{print $2}'
}

generate_db() {
  local db="_supabase_$1"
  docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
    "SELECT 1 FROM pg_database WHERE datname = '$db';" | grep -q 1 && {
      echo "Banco $db já existe"; return; }
  
  docker exec supabase-db \
    psql -U supabase_admin -d postgres -c "CREATE DATABASE $db TEMPLATE _supabase_template;"
  
  register_created_db "$db"
  
  echo "Garantindo permissões básicas no banco $db..."
  docker exec supabase-db \
    psql -U supabase_admin -d postgres -c "GRANT CREATE ON DATABASE $db TO supabase_storage_admin; GRANT CREATE ON DATABASE $db TO supabase_auth_admin;"
  
  echo "Banco $db criado com sucesso"
}

normalize_public_base_url() {
  local url="${1%/}"
  local proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then
    echo "$url"
    return
  fi
  if [[ -n "$proto" ]]; then
    url="${proto}://$url"
  else
    url="https://$url"
  fi
  echo "$url"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$PROJECT_ID"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"

template_to_file() {
  local template="$1" outfile="$2"
  local anon_key service_role_key project_id project_uuid config_token jwt_secret
  local server_url public_base_url project_public_url project_auth_external_url project_root
  local logflare_api_key

  anon_key="$(escape_sed_replacement "$ANON_TOKEN")"
  service_role_key="$(escape_sed_replacement "$SERVICE_TOKEN")"
  project_id="$(escape_sed_replacement "$PROJECT_ID")"
  project_uuid="$(escape_sed_replacement "$PROJECT_UUID")"
  config_token="$(escape_sed_replacement "$CONFIG_TOKEN_PROJETO")"
  jwt_secret="$(escape_sed_replacement "$JWT_SECRET_PROJETO")"
  server_url="$(escape_sed_replacement "$SERVER_URL")"
  public_base_url="$(escape_sed_replacement "$PUBLIC_BASE_URL")"
  project_public_url="$(escape_sed_replacement "$PROJECT_PUBLIC_URL")"
  project_auth_external_url="$(escape_sed_replacement "$PROJECT_AUTH_EXTERNAL_URL")"
  project_root="$(escape_sed_replacement "$HOST_PROJECT_ROOT")"
  logflare_api_key="$(escape_sed_replacement "${LOGFLARE_API_KEY:-}")"

  sed \
    -e "s|{{anon_key}}|$anon_key|g" \
    -e "s|{{service_role_key}}|$service_role_key|g" \
    -e "s|{{project_id}}|$project_id|g" \
    -e "s|{{project_uuid}}|$project_uuid|g" \
    -e "s|{{config_token}}|$config_token|g" \
    -e "s|{{jwt_secret}}|$jwt_secret|g" \
    -e "s|{{server_url}}|$server_url|g" \
    -e "s|{{public_base_url}}|$public_base_url|g" \
    -e "s|{{project_public_url}}|$project_public_url|g" \
    -e "s|{{project_auth_external_url}}|$project_auth_external_url|g" \
    -e "s|{{project_root}}|$project_root|g" \
    -e "s|{{logflare_api_key}}|$logflare_api_key|g" \
    "$template" > "$outfile"
}

realtime_tenant() {
  docker_must_exist realtime-dev.supabase-realtime
  local response
  response=$(docker exec realtime-dev.supabase-realtime sh -c "curl -s -w '\n%{http_code}' -X POST http://localhost:4000/api/tenants \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer $ANON_TOKEN' \
    -d '{
      \"tenant\":{
        \"name\":\"$PROJECT_UUID\",
        \"external_id\":\"$PROJECT_UUID\",
        \"jwt_secret\":\"$JWT_SECRET_PROJETO\",
        \"max_concurrent_users\":${MAX_CONCURRENT_USERS:-200},
        \"extensions\":[{
          \"type\":\"postgres_cdc_rls\",
          \"settings\":{
            \"db_name\":\"_supabase_$PROJECT_ID\",
            \"db_host\":\"$POSTGRES_HOST\",
            \"db_user\":\"supabase_admin\",
            \"db_password\":\"$POSTGRES_PASSWORD\",
            \"db_port\":\"$POSTGRES_PORT\",
            \"region\":\"us-west-1\",
            \"poll_interval_ms\":100,
            \"poll_max_record_bytes\":1048576,
            \"ssl_enforced\":false,
            \"slot_name\":\"supabase_realtime_replication_slot_$PROJECT_ID\"
          }}]}}'" 2>&1)

  local http_code
  http_code=$(echo "$response" | tail -n1)
  local body
  body=$(echo "$response" | head -n-1)

  if [[ "$http_code" != "200" && "$http_code" != "201" ]]; then
    echo "⚠️  AVISO: Falha ao criar tenant Realtime (HTTP $http_code)"
    echo "   Body: $body"
  else
    register_realtime_tenant "$PROJECT_UUID"
    echo "✔️  Realtime tenant criado com UUID: $PROJECT_UUID"
  fi
}

supavisor_tenant() {
  docker_must_exist supabase-pooler
  local pg_version; pg_version="$(get_pg_version)"
  local json
  json=$(jq -n \
    --arg id         "$PROJECT_ID" \
    --arg host       "$POSTGRES_HOST" \
    --arg port       "$POSTGRES_PORT" \
    --arg dbpass     "$POSTGRES_PASSWORD" \
    --arg pgver      "$pg_version" \
    '{
       tenant:{
         external_id:$id,
         db_host:$host,
         db_port:$port,
         db_database:("_supabase_" + $id),
         ip_version:"auto",
         enforce_ssl:false,
         require_user:false,
         auth_query:"SELECT * FROM pgbouncer.get_auth($1)",
         default_max_clients:800,
         default_pool_size:40,
         default_parameter_status:{server_version:$pgver},
         users:[{
           db_user:"pgbouncer",
           db_password:$dbpass,
           mode_type:"transaction",
           pool_size:40,
           is_manager:true
         }]
       }
     }')
  docker exec supabase-pooler curl -s -X PUT "http://localhost:4000/api/tenants/$PROJECT_ID" \
       -H 'Content-Type: application/json' \
       -H "Authorization: Bearer $GLOBAL_ANON_TOKEN" \
       -d "$json"
  
  register_supavisor_tenant "$PROJECT_ID"
  echo "Supavisor tenant criado"
}

  OUT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
  if [[ -f "$OUT_DIR/.env" ]]; then
      source "$OUT_DIR/.env"
  fi

  if [[ -z "${JWT_SECRET_PROJETO:-}" ]]; then
      JWT_SECRET_PROJETO=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n\r')
  fi

echo "✔️  UUID do projeto: $PROJECT_UUID"

now_epoch=$(date +%s)
iat=$now_epoch
exp=$((now_epoch + (3 * 30 * 24 * 3600)))

ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
GLOBAL_ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET")
CONFIG_TOKEN_PROJETO=$(openssl rand -hex 32 | tr -d '\n\r')

init_transaction

mkdir -p "$OUT_DIR/storage/stub/stub" "$OUT_DIR/nginx"  "$OUT_DIR/pooler"
register_created_dir "$OUT_DIR"

template_to_file "$SCRIPT_DIR/nginxtemplate"      "$OUT_DIR/nginx/nginx_${PROJECT_ID}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate"       "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
echo "Arquivos de template gerados em $OUT_DIR"

generate_db "$PROJECT_ID"
realtime_tenant
supavisor_tenant

echo "🔄 Subindo projeto com Docker Compose..."

cd "$OUT_DIR"

docker compose -p "$PROJECT_ID" \
  --env-file ../../.env \
  --env-file .env \
  up --build -d || die "Erro ao subir docker compose para $PROJECT_ID"

echo "✅  Projeto $PROJECT_ID configurado com sucesso"

commit_transaction
