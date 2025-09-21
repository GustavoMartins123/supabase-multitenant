#!/usr/bin/env bash
# generate_project.sh
set -euo pipefail

die() { echo "❌  $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

set -a
source "$PROJECT_ROOT/secrets/.env"
source "$PROJECT_ROOT/.env"
set +a

[[ -z "${JWT_SECRET:-}" ]] && { echo "JWT_SECRET ausente"; exit 1; }

PROJECT_ID="${1:-}"
[[ -z "$PROJECT_ID" ]] && { echo "Uso: $0 <project_id>"; exit 1; }

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


is_port_in_use() {
  local port="$1"
  if lsof -i :"$port" > /dev/null 2>&1; then
    return 0 
  else
    return 1 
  fi
}

generate_unique_port() {
  local port
  local max_attempts=20
  local attempt=0
  while [ $attempt -lt $max_attempts ]; do
    port=$(( RANDOM % 10000 + 4000 ))
    if ! is_port_in_use "$port"; then
      echo "$port"
      return
    fi
    echo "Porta $port está em uso, tentando outra..." >&2
    attempt=$((attempt + 1))
  done
  echo "Erro: Não foi possível encontrar uma porta livre após $max_attempts tentativas." >&2
  exit 1
}


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
  echo "Banco $db criado com sucesso"
}

# porta aleatória 4000-14000
NGINX_PORT=$(generate_unique_port)
META_PORT=$(generate_unique_port)

template_to_file() {
  local template="$1" outfile="$2"
  sed \
    -e "s|{{anon_key}}|$ANON_TOKEN|g" \
    -e "s|{{service_role_key}}|$SERVICE_TOKEN|g" \
    -e "s|{{project_id}}|$PROJECT_ID|g" \
    -e "s|{{nginx_port}}|$NGINX_PORT|g" \
    -e "s|{{meta_port}}|$META_PORT|g" \
    "$template" > "$outfile"
}

realtime_tenant() {
  docker_must_exist realtime-dev.supabase-realtime
  docker exec realtime-dev.supabase-realtime sh -c "curl -s -X POST http://localhost:4000/api/tenants \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer $ANON_TOKEN' \
    -d '{
      \"tenant\":{
        \"name\":\"$PROJECT_ID\",
        \"external_id\":\"$PROJECT_ID\",
        \"jwt_secret\":\"$JWT_SECRET\",
        \"max_concurrent_users\":\"$MAX_CONCURRENT_USERS\",
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
          }}]}}'"
  echo "Realtime tenant criado"
}

supavisor_tenant() {
    docker_must_exist supabase-pooler
    
    local pg_version; pg_version="$(get_pg_version)"
    
    # Construção manual do JSON
    local json='{
        "tenant": {
            "external_id": "'"$PROJECT_ID"'",
            "db_host": "'"$POSTGRES_HOST"'",
            "db_port": "'"$POSTGRES_PORT"'",
            "db_database": "_supabase_'"$PROJECT_ID"'",
            "ip_version": "auto",
            "enforce_ssl": false,
            "require_user": false,
            "auth_query": "SELECT * FROM pgbouncer.get_auth($1)",
            "default_max_clients": 600,
            "default_pool_size": '"$POOLER_DEFAULT_POOL_SIZE"',
            "default_parameter_status": {
                "server_version": "'"$pg_version"'"
            },
            "users": [
                {
                    "db_user": "pgbouncer",
                    "db_password": "'"$POSTGRES_PASSWORD"'",
                    "mode_type": "transaction",
                    "pool_size": '"$POOLER_DEFAULT_POOL_SIZE"',
                    "is_manager": true
                }
            ]
        }
    }'
    
    docker exec supabase-pooler curl -s -X PUT "http://localhost:4000/api/tenants/$PROJECT_ID" \
        -H 'Content-Type: application/json' \
        -H "Authorization: Bearer $ANON_TOKEN" \
        -d "$json"
    
    echo "Supavisor tenant criado com pool_size: $POOLER_DEFAULT_POOL_SIZE"
}

now_epoch=$(date +%s)
iat=$now_epoch
exp=$((now_epoch + (8 * 365 * 24 * 3600)))

ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_ID\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_ID\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET")

OUT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
mkdir -p "$OUT_DIR/storage/stub/stub" "$OUT_DIR/nginx"  "$OUT_DIR/pooler"

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
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up --build -d || die "Erro ao subir docker compose para $PROJECT_ID"

echo "✅  Projeto $PROJECT_ID configurado com sucesso (porta $NGINX_PORT)"

echo "NGINX_PORT=$NGINX_PORT"
