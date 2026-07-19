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

database_exists() {
  local db="$1" count
  count="$(docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin \
    -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$db';" \
    | tr -d '[:space:]')" || return 2
  [[ "$count" == "1" ]]
}

drop_project_replication_slots() {
  local project="$1" raw_slot slot
  local slots=(
    "supabase_realtime_messages_replication_slot_$project"
    "supabase_realtime_replication_slot_$project"
  )
  for raw_slot in "${slots[@]}"; do
    slot="${raw_slot:0:63}"
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend(active_pid) FROM pg_replication_slots WHERE slot_name = '$slot' AND active_pid IS NOT NULL;" \
      >/dev/null || return 1
    sleep 1
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
      "SELECT pg_drop_replication_slot(slot_name) FROM pg_replication_slots WHERE slot_name = '$slot';" \
      >/dev/null || return 1
  done
}

drop_project_database() {
  local db="$1" remaining

  # Bloqueia reconexoes do Supavisor entre o terminate e o DROP.
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "ALTER DATABASE \"$db\" ALLOW_CONNECTIONS false;" >/dev/null || return 1
  drop_project_replication_slots "$PROJECT_ID" || return 1
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db' AND pid <> pg_backend_pid();" \
    >/dev/null || return 1
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "DROP DATABASE IF EXISTS \"$db\";" >/dev/null || return 1

  remaining="$(docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin \
    -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$db';" \
    | tr -d '[:space:]')" || return 1
  [[ "$remaining" == "0" ]]
}

delete_tenant_api() {
  local container="$1" tenant="$2" token="$3" code
  code="$(docker exec "$container" curl -sS -o /dev/null -w '%{http_code}' \
    -X DELETE "http://localhost:4000/api/tenants/$tenant" \
    -H "Authorization: Bearer $token")" || return 1
  [[ "$code" == "200" || "$code" == "202" || "$code" == "204" || "$code" == "404" ]]
}

delete_tenant_metadata() {
  local project="$1" realtime_uuid="${2:-}"
  local realtime_sql=""
  if [[ -n "$realtime_uuid" ]]; then
    realtime_sql="
      DELETE FROM _realtime.extensions WHERE tenant_external_id = '$realtime_uuid';
      DELETE FROM _realtime.tenants WHERE external_id = '$realtime_uuid';"
  fi
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "$realtime_sql
     DELETE FROM _supavisor.users WHERE tenant_external_id = '$project';
     DELETE FROM _supavisor.tenants WHERE external_id = '$project';" \
    >/dev/null
}

rollback_transaction() {
  local status="${1:-$?}"
  local rollback_failed=0
  trap - ERR TERM INT HUP
  set +e
  echo "❌ Erro detectado! Revertendo alterações..."

  if [[ "$COMPOSE_STARTED" -eq 1 && -n "${OUT_DIR:-}" && -d "$OUT_DIR" ]]; then
    (cd "$OUT_DIR" && docker compose -p "$PROJECT_ID" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 \
      || rollback_failed=1
  fi

  if [[ -n "$CREATED_SUPAVISOR_TENANT" ]]; then
    delete_tenant_api supabase-pooler "$CREATED_SUPAVISOR_TENANT" "$GLOBAL_ANON_TOKEN" \
      || rollback_failed=1
  fi
  if [[ -n "$CREATED_REALTIME_TENANT" ]]; then
    delete_tenant_api realtime-dev.supabase-realtime "$CREATED_REALTIME_TENANT" "$ANON_TOKEN" \
      || rollback_failed=1
  fi
  if [[ -n "$CREATED_SUPAVISOR_TENANT" || -n "$CREATED_REALTIME_TENANT" ]]; then
    delete_tenant_metadata "$PROJECT_ID" "$CREATED_REALTIME_TENANT" \
      || rollback_failed=1
  fi
  if [[ -n "$CREATED_DB" ]]; then
    drop_project_database "$CREATED_DB" || rollback_failed=1
  fi
  for ((idx=${#CREATED_DIRS[@]}-1; idx>=0; idx--)); do
    rm -rf "${CREATED_DIRS[idx]}" || rollback_failed=1
  done
  rm -rf "$TRANSACTION_DIR" || rollback_failed=1

  if [[ "$rollback_failed" -eq 0 ]]; then
    echo "HOST_AGENT_ROLLBACK_COMPLETE=1"
    echo "⚠️  Todas as alterações foram revertidas."
  else
    echo "HOST_AGENT_ROLLBACK_FAILED=1" >&2
    echo "❌ Rollback físico incompleto; os resíduos foram preservados para diagnóstico." >&2
  fi
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
RECOVER_STALE="${3:-false}"
STALE_TENANT_UUIDS=("${@:4}")
[[ -n "$PROJECT_ID" && -n "$PROJECT_UUID" ]] \
  || die "Uso: $0 <project_id> <project_uuid> [recover_stale] [stale_tenant_uuid ...]"
[[ "$PROJECT_UUID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
  || die "project_uuid inválido"
[[ "$RECOVER_STALE" == "true" || "$RECOVER_STALE" == "false" ]] \
  || die "recover_stale deve ser true ou false"
for stale_uuid in "${STALE_TENANT_UUIDS[@]}"; do
  [[ "$stale_uuid" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
    || die "stale_tenant_uuid inválido"
done

PROJECT_ID="$(echo "$PROJECT_ID" | tr '[:upper:]' '[:lower:]')"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "Nome deve começar com letra minúscula/_ e conter só minúsculas, dígitos ou _ (3–40 chars)"
[[ "$PROJECT_ID" != *.* ]] || die "Nome não pode conter ponto (.)"

RESERVED=(default select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback)
for word in "${RESERVED[@]}"; do
  [[ "$PROJECT_ID" != "$word" ]] || die "'$PROJECT_ID' é palavra reservada."
done

OUT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"

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
  local db="_supabase_$PROJECT_ID" exists_status
  if database_exists "$db"; then
    echo "HOST_AGENT_STALE_STATE=database:$db" >&2
    die "Banco $db já existe"
  else
    exists_status=$?
    [[ "$exists_status" -eq 1 ]] || die "Falha ao consultar existência do banco $db"
  fi

  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "CREATE DATABASE $db TEMPLATE _supabase_template;"
  register_created_db "$db"
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "REVOKE CONNECT, TEMPORARY ON DATABASE $db FROM PUBLIC; GRANT CONNECT, TEMPORARY ON DATABASE $db TO pgbouncer; GRANT CONNECT, TEMPORARY ON DATABASE $db TO authenticator; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $db TO supabase_storage_admin; GRANT CONNECT, TEMPORARY, CREATE ON DATABASE $db TO supabase_auth_admin;"
  docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
    "ALTER ROLE supabase_storage_admin IN DATABASE $db SET search_path = storage, public;"
  vector_validate_database "$db" || die "Banco do projeto sem suporte a Storage Vectors"
}

cleanup_stale_state() {
  local db="_supabase_$PROJECT_ID" old_uuid="" stale_uuid exists_status
  local container_ids
  local -a stale_containers=()

  echo "HOST_AGENT_PROGRESS=create:cleanup_stale"
  if [[ -d "$OUT_DIR" ]]; then
    if [[ -f "$OUT_DIR/.env" ]]; then
      old_uuid="$(grep -m1 '^PROJECT_UUID=' "$OUT_DIR/.env" | cut -d= -f2- | tr -d '\r' || true)"
      if [[ -n "$old_uuid" && ! "$old_uuid" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
        echo "HOST_AGENT_ROLLBACK_FAILED=stale_project_uuid" >&2
        return 1
      fi
    fi
    (cd "$OUT_DIR" && docker compose -p "$PROJECT_ID" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 \
      || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_compose" >&2; return 1; }
  elif [[ -e "$OUT_DIR" ]]; then
    echo "HOST_AGENT_ROLLBACK_FAILED=stale_path" >&2
    return 1
  fi

  # Um rollback antigo pode ter removido o diretório mesmo quando o compose
  # down falhou. O label do Compose permite localizar somente os containers
  # deste projeto sem depender dos arquivos que já sumiram.
  container_ids="$(docker ps -aq \
    --filter "label=com.docker.compose.project=$PROJECT_ID")" \
    || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_container_check" >&2; return 1; }
  if [[ -n "$container_ids" ]]; then
    mapfile -t stale_containers <<< "$container_ids"
    docker rm -f "${stale_containers[@]}" >/dev/null \
      || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_containers" >&2; return 1; }
  fi

  delete_tenant_metadata "$PROJECT_ID" "$old_uuid" \
    || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_metadata" >&2; return 1; }
  for stale_uuid in "${STALE_TENANT_UUIDS[@]}"; do
    [[ "$stale_uuid" == "$old_uuid" ]] && continue
    delete_tenant_metadata "$PROJECT_ID" "$stale_uuid" \
      || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_metadata" >&2; return 1; }
  done
  if database_exists "$db"; then
    drop_project_database "$db" \
      || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_database" >&2; return 1; }
  else
    exists_status=$?
    if [[ "$exists_status" -ne 1 ]]; then
      echo "HOST_AGENT_ROLLBACK_FAILED=stale_database_check" >&2
      return 1
    fi
  fi
  if [[ -e "$OUT_DIR" ]]; then
    rm -rf "$OUT_DIR" \
      || { echo "HOST_AGENT_ROLLBACK_FAILED=stale_files" >&2; return 1; }
  fi
  echo "HOST_AGENT_STALE_STATE_RECOVERED=1"
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
  # Registra a intenção antes da chamada: um timeout/HTTP 5xx pode ocorrer
  # depois de o serviço ter persistido o tenant.
  register_realtime_tenant "$PROJECT_UUID"
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
}

supavisor_tenant() {
  docker_must_exist supabase-pooler
  local pg_version payload response http_code body
  # PUT também pode ter sido aplicado antes de uma falha de transporte.
  register_supavisor_tenant "$PROJECT_ID"
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
}

JWT_SECRET_PROJETO=$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n\r')
now_epoch=$(date +%s)
exp=$((now_epoch + (3 * 30 * 24 * 3600)))
ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
SERVICE_TOKEN=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
GLOBAL_ANON_TOKEN=$(generate_jwt "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now_epoch,\"exp\":$exp}" "$JWT_SECRET")
CONFIG_TOKEN_PROJETO=$(openssl rand -hex 32 | tr -d '\n\r')

if [[ "$RECOVER_STALE" == "true" ]]; then
  cleanup_stale_state || die "Não foi possível limpar resíduos da tentativa anterior"
else
  stale_db_status=0
  if [[ -e "$OUT_DIR" ]]; then
    echo "HOST_AGENT_STALE_STATE=files:$OUT_DIR" >&2
    die "Projeto '$PROJECT_ID' já existe em projects/"
  fi
  if database_exists "_supabase_$PROJECT_ID"; then
    echo "HOST_AGENT_STALE_STATE=database:_supabase_$PROJECT_ID" >&2
    die "Banco _supabase_$PROJECT_ID já existe"
  else
    stale_db_status=$?
    [[ "$stale_db_status" -eq 1 ]] \
      || die "Falha ao consultar estado do banco _supabase_$PROJECT_ID"
  fi
fi

unset S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET
vector_ensure_s3_credentials || die "Falha ao gerar credenciais SigV4 do projeto"

init_transaction
echo "HOST_AGENT_PROGRESS=create:transaction_initialized"
mkdir -p "$OUT_DIR/storage/stub/stub" "$OUT_DIR/nginx" "$OUT_DIR/pooler"
register_created_dir "$OUT_DIR"

template_to_file "$SCRIPT_DIR/nginxtemplate" "$OUT_DIR/nginx/nginx_${PROJECT_ID}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate" "$OUT_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$OUT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$OUT_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$OUT_DIR/Dockerfile"
chmod 644 "$OUT_DIR/.env" "$OUT_DIR/nginx/nginx_${PROJECT_ID}.conf"
echo "HOST_AGENT_PROGRESS=create:files_rendered"

generate_db
echo "HOST_AGENT_PROGRESS=create:database_created"
realtime_tenant
echo "HOST_AGENT_PROGRESS=create:realtime_created"
supavisor_tenant
echo "HOST_AGENT_PROGRESS=create:supavisor_created"

COMPOSE_STARTED=1
(
  cd "$OUT_DIR"
  docker compose -p "$PROJECT_ID" --env-file ../../.env --env-file .env up --build -d
)
echo "HOST_AGENT_PROGRESS=create:services_started"
vector_validate_storage_api "$PROJECT_ID" || die "Storage Vectors nao iniciou corretamente"
echo "HOST_AGENT_PROGRESS=create:storage_verified"

echo "✅  Projeto $PROJECT_ID configurado com Storage Vectors e SigV4"
commit_transaction
