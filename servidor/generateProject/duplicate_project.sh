#!/usr/bin/env bash
# duplicate_project.sh - COM DEBUG DETALHADO
set -euo pipefail

die() { echo "❌  $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

set -a
source "$PROJECT_ROOT/secrets/.env"
source "$PROJECT_ROOT/.env"
set +a

[[ -z "${JWT_SECRET:-}" ]] && { echo "JWT_SECRET ausente"; exit 1; }

ORIGINAL_PROJECT="${1:-}"
NEW_PROJECT="${2:-}"
COPY_MODE="${3:-schema-only}"

[[ -z "$ORIGINAL_PROJECT" ]] && { echo "Uso: $0 <original_project> <new_project> [with-data|schema-only]"; exit 1; }
[[ -z "$NEW_PROJECT" ]] && { echo "Uso: $0 <original_project> <new_project> [with-data|schema-only]"; exit 1; }

ORIGINAL_PROJECT=$(echo "$ORIGINAL_PROJECT" | tr '[:upper:]' '[:lower:]')
NEW_PROJECT=$(echo "$NEW_PROJECT" | tr '[:upper:]' '[:lower:]')

[[ "$NEW_PROJECT" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "Nome deve começar com letra minúscula/_ e conter só minúsculas, dígitos ou _ (3–40 chars)"

[[ "$NEW_PROJECT" == *.* ]] && die "Nome não pode conter ponto (.)"

RESERVED=(
  select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback
)
for word in "${RESERVED[@]}"; do
  [[ "$NEW_PROJECT" == "$word" ]] && die "'$NEW_PROJECT' é palavra reservada."
done

ORIGINAL_DB="_supabase_$ORIGINAL_PROJECT"
NEW_DB="_supabase_$NEW_PROJECT"

docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname = '$ORIGINAL_DB';" | grep -q 1 \
  || die "Banco original '$ORIGINAL_DB' não encontrado"

[[ -d "$PROJECT_ROOT/projects/$NEW_PROJECT" ]] \
  && die "Projeto '$NEW_PROJECT' já existe em projects/"

echo "✔️  Nome de projeto validado: $NEW_PROJECT"
echo "✔️  Modo: $COPY_MODE"

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

duplicate_db() {
  local original_db="$1"
  local new_db="$2"
  local mode="$3"
  
  echo "💾 Copiando banco de dados..."
  
  echo "   Criando banco $new_db vazio..."
  docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "CREATE DATABASE $new_db;" || die "Falha ao criar banco $new_db"
  
  echo "   Garantindo que roles existem..."
  docker exec supabase-db psql -U supabase_admin -d postgres <<-EOSQL
    DO \$\$
    BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pgbouncer') THEN
        EXECUTE 'CREATE ROLE pgbouncer LOGIN PASSWORD ''$POSTGRES_PASSWORD''';
      END IF;
      
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticator') THEN
        EXECUTE 'CREATE ROLE authenticator LOGIN PASSWORD ''$POSTGRES_PASSWORD'' NOINHERIT';
      END IF;
      
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
        EXECUTE 'CREATE ROLE supabase_auth_admin LOGIN PASSWORD ''$POSTGRES_PASSWORD''';
      END IF;
      
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
        EXECUTE 'CREATE ROLE supabase_storage_admin LOGIN PASSWORD ''$POSTGRES_PASSWORD''';
      END IF;
    END \$\$;
EOSQL
  
  local dump_file="/tmp/dump_${ORIGINAL_PROJECT}_$(date +%s).sql"
  
  if [[ "$mode" == "with-data" ]]; then
    echo "   Fazendo dump completo (schema + dados + storage)..."
    docker exec supabase-db pg_dump -U supabase_admin -d "$original_db" \
        > "$dump_file" || die "Falha ao fazer dump"
  else
    echo "   Fazendo dump schema-only..."
    docker exec supabase-db pg_dump -U supabase_admin -d "$original_db" \
        --schema=auth --schema=storage --schema-only \
        > "$dump_file" || die "Falha ao fazer dump auth/storage"
    
    docker exec supabase-db pg_dump -U supabase_admin -d "$original_db" \
        --exclude-schema=auth --exclude-schema=storage --schema-only \
        >> "$dump_file" || die "Falha ao fazer dump public schema"
  fi
  
  echo "✔️  Dump criado: $dump_file ($(du -h "$dump_file" | cut -f1))"
  
  echo "   Restaurando dump..."
  docker exec -i supabase-db psql -U supabase_admin -d "$new_db" \
    < "$dump_file" || die "Falha ao restaurar dump"
  
  echo "   Marcando migrations como executadas..."
  docker exec supabase-db psql -U supabase_admin -d "$new_db" <<-EOSQL
    UPDATE auth.schema_migrations SET dirty = false WHERE dirty = true;
    UPDATE storage.migrations SET dirty = false WHERE dirty = true;
    ALTER DATABASE $new_db SET search_path TO public, auth, storage, extensions;
EOSQL
  
  rm -f "$dump_file"
  echo "✔️  Banco duplicado com sucesso"
}

NGINX_PORT=$(generate_unique_port)
META_PORT=$(generate_unique_port)

template_to_file() {
  local template="$1" outfile="$2"
  sed \
    -e "s|{{anon_key}}|$ANON_TOKEN|g" \
    -e "s|{{service_role_key}}|$SERVICE_TOKEN|g" \
    -e "s|{{project_id}}|$NEW_PROJECT|g" \
    -e "s|{{nginx_port}}|$NGINX_PORT|g" \
    -e "s|{{meta_port}}|$META_PORT|g" \
    "$template" > "$outfile"
}

realtime_tenant() {
  echo "🔄 Criando tenant Realtime..."
  docker_must_exist realtime-dev.supabase-realtime
  
  local response
  response=$(docker exec realtime-dev.supabase-realtime sh -c "curl -s -w '\n%{http_code}' -X POST http://localhost:4000/api/tenants \
    -H 'Content-Type: application/json' \
    -H 'Authorization: Bearer $ANON_TOKEN' \
    -d '{
      \"tenant\":{
        \"name\":\"$NEW_PROJECT\",
        \"external_id\":\"$NEW_PROJECT\",
        \"jwt_secret\":\"$JWT_SECRET\",
        \"max_concurrent_users\":\"$MAX_CONCURRENT_USERS\",
        \"extensions\":[{
          \"type\":\"postgres_cdc_rls\",
          \"settings\":{
            \"db_name\":\"_supabase_$NEW_PROJECT\",
            \"db_host\":\"$POSTGRES_HOST\",
            \"db_user\":\"supabase_admin\",
            \"db_password\":\"$POSTGRES_PASSWORD\",
            \"db_port\":\"$POSTGRES_PORT\",
            \"region\":\"us-west-1\",
            \"poll_interval_ms\":100,
            \"poll_max_record_bytes\":1048576,
            \"ssl_enforced\":false,
            \"slot_name\":\"supabase_realtime_replication_slot_$NEW_PROJECT\"
          }}]}}'" 2>&1)
  
  local http_code=$(echo "$response" | tail -n1)
  local body=$(echo "$response" | head -n-1)
  
  echo "   HTTP Status: $http_code"
  echo "   Response: $body"
  
  if [[ "$http_code" != "200" && "$http_code" != "201" ]]; then
    echo "⚠️  AVISO: Falha ao criar tenant Realtime (HTTP $http_code)"
    echo "   Body: $body"
    return 1
  fi
  
  echo "✔️  Realtime tenant criado"
}

supavisor_tenant() {
  echo "🔄 Criando tenant Supavisor..."
  docker_must_exist supabase-pooler
  
  local pg_version; pg_version="$(get_pg_version)"
  local json
  json=$(jq -n \
    --arg id         "$NEW_PROJECT" \
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
  
  local response
  response=$(docker exec supabase-pooler curl -s -w '\n%{http_code}' -X PUT "http://localhost:4000/api/tenants/$NEW_PROJECT" \
       -H 'Content-Type: application/json' \
       -H "Authorization: Bearer $ANON_TOKEN" \
       -d "$json" 2>&1)
  
  local http_code=$(echo "$response" | tail -n1)
  local body=$(echo "$response" | head -n-1)
  
  echo "   HTTP Status: $http_code"
  echo "   Response: $body"
  
  if [[ "$http_code" != "200" && "$http_code" != "201" ]]; then
    echo "⚠️  AVISO: Falha ao criar tenant Supavisor (HTTP $http_code)"
    echo "   Body: $body"
    return 1
  fi
  
  echo "✔️  Supavisor tenant criado"
}

now_epoch=$(date +%s)
iat=$now_epoch
exp=$((now_epoch + (8 * 365 * 24 * 3600)))

ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$NEW_PROJECT\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$NEW_PROJECT\",\"iat\":$iat,\"exp\":$exp}" "$JWT_SECRET")

OUT_DIR="$PROJECT_ROOT/projects/$NEW_PROJECT"
mkdir -p "$OUT_DIR/nginx" "$OUT_DIR/pooler"

echo "📝 Gerando templates..."
template_to_file "$SCRIPT_DIR/nginxtemplate"      "$OUT_DIR/nginx/nginx_${NEW_PROJECT}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate"       "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
echo "✔️  Templates gerados"

duplicate_db "$ORIGINAL_DB" "$NEW_DB" "$COPY_MODE"

if [[ "$COPY_MODE" == "with-data" ]]; then
  ORIGINAL_STORAGE="$PROJECT_ROOT/projects/$ORIGINAL_PROJECT/storage"
  if [[ -d "$ORIGINAL_STORAGE" ]]; then
    echo "📦 Copiando storage com TAR (preservando xattrs)..."
    
    mkdir -p "$OUT_DIR/storage"
    
    (cd "$ORIGINAL_STORAGE" && tar --xattrs --xattrs-include='*' --acls -cpf - .) | \
      (cd "$OUT_DIR/storage" && tar --xattrs --xattrs-include='*' --acls -xpf -)
    
    if [ $? -eq 0 ]; then
      echo "✔️  Storage copiado ($(du -sh "$OUT_DIR/storage" | cut -f1))"
    else
      die "Falha ao copiar storage com tar"
    fi
  else
    echo "⚠️  Storage original não encontrado"
    mkdir -p "$OUT_DIR/storage/stub/stub"
  fi
else
  echo "📁 Criando estrutura de storage vazia..."
  mkdir -p "$OUT_DIR/storage/stub/stub"
fi

echo ""
echo "🔧 Configurando tenants..."
realtime_tenant || echo "⚠️  Continuando sem Realtime..."
supavisor_tenant || echo "⚠️  Continuando sem Supavisor..."

echo ""
echo "🚀 Subindo containers com Docker Compose..."
cd "$OUT_DIR"

# Capturar output completo do docker compose
echo "   Executando: docker compose up --build -d"
compose_output=$(docker compose -p "$NEW_PROJECT" \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up --build -d 2>&1)

compose_exit_code=$?

echo "$compose_output"

if [ $compose_exit_code -ne 0 ]; then
  echo ""
  echo "❌  ERRO: Docker Compose falhou (exit code: $compose_exit_code)"
  echo ""
  echo "📋 Output completo:"
  echo "$compose_output"
  die "Falha ao subir containers"
fi

echo ""
echo "✅  Projeto $NEW_PROJECT configurado com sucesso!"
echo "   Porta NGINX: $NGINX_PORT"
echo "   Porta Meta: $META_PORT"
echo ""
echo "🔍 Verificando containers..."
docker ps --filter "name=$NEW_PROJECT"

echo ""
echo "NGINX_PORT=$NGINX_PORT"
