#!/usr/bin/env bash
set -Eeuo pipefail

die() { echo "❌  $*" >&2; return 1; }
say() { echo "ℹ️  $*"; }
ok() { echo "✅ $*"; }

OLD_NAME="${1:-}"
NEW_NAME="${2:-}"
[[ -n "$OLD_NAME" && -n "$NEW_NAME" ]] || die "Uso: $0 <old_name> <new_name>"
[[ "$OLD_NAME" != "$NEW_NAME" ]] || die "Nome novo e igual ao atual"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PROJECTS_ROOT="/docker/projects"
OLD_DIR="$PROJECTS_ROOT/$OLD_NAME"
NEW_DIR="$PROJECTS_ROOT/$NEW_NAME"
OLD_DB="_supabase_$OLD_NAME"
NEW_DB="_supabase_$NEW_NAME"
META_DB="${POSTGRES_DB:-postgres}"
BACKUP_DIR="$(mktemp -d /tmp/rename-project.XXXXXX)"

MUTATION_STARTED=0
OLD_COMPOSE_STOPPED=0
RENAMED_DB=0
RENAMED_SLOT=0
REALTIME_UPDATED=0
SUPAVISOR_OLD_DELETED=0
SUPAVISOR_UPDATED=0
MOVED_DIR=0
META_UPDATED=0
NEW_COMPOSE_STARTED=0
SLOT_PLUGIN=""

cleanup() { rm -rf "$BACKUP_DIR"; }

compose_old() {
  ( cd "$OLD_DIR" && docker compose -p "$OLD_NAME" \
      --env-file ../../.env --env-file .env "$@" )
}

compose_new() {
  ( cd "$NEW_DIR" && docker compose -p "$NEW_NAME" \
      --env-file ../../.env --env-file .env "$@" )
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

http_code() {
  local container="$1" method="$2" path="$3" token="$4" payload="${5:-}"
  local args=(exec "$container" curl -sS -o /dev/null -w '%{http_code}'
    -X "$method" "http://localhost:4000$path"
    -H "Authorization: Bearer $token")
  if [[ -n "$payload" ]]; then
    args+=(-H 'Content-Type: application/json' -d "$payload")
  fi
  docker "${args[@]}"
}

accepted_code() {
  local code="$1"
  shift
  local accepted
  for accepted in "$@"; do
    [[ "$code" == "$accepted" ]] && return 0
  done
  return 1
}

build_realtime_payload() {
  local project_name="$1"
  local slot_name="supabase_realtime_replication_slot_$project_name"
  slot_name="${slot_name:0:63}"
  jq -cn \
    --arg uuid "$PROJECT_UUID" \
    --arg secret "$JWT_SECRET_PROJETO" \
    --arg db "_supabase_$project_name" \
    --arg host "$POSTGRES_HOST" \
    --arg port "$POSTGRES_PORT" \
    --arg password "$POSTGRES_PASSWORD" \
    --arg slot "$slot_name" \
    --argjson max_users "${MAX_CONCURRENT_USERS:-200}" \
    '{tenant:{name:$uuid,external_id:$uuid,jwt_secret:$secret,
      max_concurrent_users:$max_users,extensions:[{type:"postgres_cdc_rls",
      settings:{db_name:$db,db_host:$host,db_user:"supabase_admin",
      db_password:$password,db_port:$port,region:"us-west-1",
      poll_interval_ms:100,poll_max_record_bytes:1048576,
      ssl_enforced:false,slot_name:$slot}}]}}'
}

build_supavisor_payload() {
  local project_name="$1"
  jq -cn \
    --arg id "$project_name" \
    --arg host "$POSTGRES_HOST" \
    --arg port "$POSTGRES_PORT" \
    --arg password "$POSTGRES_PASSWORD" \
    --arg version "$PG_VERSION" \
    '{tenant:{external_id:$id,db_host:$host,db_port:$port,
      db_database:("_supabase_"+$id),ip_version:"auto",enforce_ssl:false,
      require_user:false,auth_query:"SELECT * FROM pgbouncer.get_auth($1)",
      default_max_clients:800,default_pool_size:40,
      default_parameter_status:{server_version:$version},users:[{
      db_user:"pgbouncer",db_password:$password,mode_type:"transaction",
      pool_size:40,is_manager:true}]}}'
}

restore_slot() {
  local current_slot="$1" target_slot="$2" plugin="$3" db="$4"
  local pid
  pid=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
    "SELECT active_pid FROM pg_replication_slots WHERE slot_name = '$current_slot';" \
    | tr -d '[:space:]')
  [[ -z "$pid" ]] || docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "SELECT pg_terminate_backend($pid);" >/dev/null
  docker exec supabase-db psql -U supabase_admin -d postgres -c \
    "SELECT pg_drop_replication_slot('$current_slot') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$current_slot');" >/dev/null
  docker exec supabase-db psql -U supabase_admin -d "$db" -c \
    "SELECT pg_create_logical_replication_slot('$target_slot', '$plugin');" >/dev/null
}

rollback_on_error() {
  local status="${1:-$?}"
  trap - ERR TERM INT HUP
  set +e
  if [[ "$MUTATION_STARTED" -eq 0 ]]; then
    cleanup
    exit "$status"
  fi

  local rollback_failed=0 code old_slot_exists
  echo "❌ Rename falhou; revertendo alteracoes..." >&2

  if [[ "$NEW_COMPOSE_STARTED" -eq 1 && -d "$NEW_DIR" ]]; then
    compose_new down --remove-orphans >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$META_UPDATED" -eq 1 ]]; then
    docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$META_DB" -c \
      "UPDATE projects SET name = '$OLD_NAME' WHERE name = '$NEW_NAME'; UPDATE jobs SET project = '$OLD_NAME' WHERE project = '$NEW_NAME';" \
      >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$MOVED_DIR" -eq 1 && -d "$NEW_DIR" ]]; then
    mv "$NEW_DIR" "$OLD_DIR" || rollback_failed=1
    rm -f "$OLD_DIR/nginx/nginx_${NEW_NAME}.conf"
    cp -a "$BACKUP_DIR/." "$OLD_DIR/" 2>/dev/null || rollback_failed=1
  fi
  if [[ "$SUPAVISOR_UPDATED" -eq 1 ]]; then
    docker exec supabase-db psql -U supabase_admin -d "$META_DB" -c \
      "DELETE FROM _supavisor.users WHERE tenant_external_id = '$NEW_NAME'; DELETE FROM _supavisor.tenants WHERE external_id = '$NEW_NAME';" \
      >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$SUPAVISOR_OLD_DELETED" -eq 1 ]]; then
    code=$(http_code supabase-pooler PUT "/api/tenants/$OLD_NAME" \
      "$GLOBAL_ANON_TOKEN" "$SUPAVISOR_OLD_PAYLOAD" 2>/dev/null)
    accepted_code "$code" 200 201 204 || rollback_failed=1
  fi
  if [[ "$REALTIME_UPDATED" -eq 1 ]]; then
    code=$(http_code realtime-dev.supabase-realtime PUT \
      "/api/tenants/$PROJECT_UUID" "$ANON_KEY_PROJETO" \
      "$REALTIME_OLD_PAYLOAD" 2>/dev/null)
    accepted_code "$code" 200 201 204 || rollback_failed=1
  fi
  if [[ "$RENAMED_SLOT" -eq 1 ]]; then
    pid=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
      "SELECT active_pid FROM pg_replication_slots WHERE slot_name = '$NEW_SLOT';" \
      | tr -d '[:space:]')
    [[ -z "$pid" ]] || docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend($pid);" >/dev/null 2>&1
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "SELECT pg_drop_replication_slot('$NEW_SLOT') WHERE EXISTS (SELECT 1 FROM pg_replication_slots WHERE slot_name = '$NEW_SLOT');" \
      >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$RENAMED_DB" -eq 1 ]]; then
    docker exec supabase-db psql -U supabase_admin -d postgres -c \
      "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$NEW_DB' AND pid <> pg_backend_pid(); ALTER DATABASE \"$NEW_DB\" RENAME TO \"$OLD_DB\";" \
      >/dev/null 2>&1 || rollback_failed=1
  fi
  if [[ "$RENAMED_SLOT" -eq 1 ]]; then
    old_slot_exists=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
      "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$OLD_SLOT';" \
      | tr -d '[:space:]')
    if [[ "$old_slot_exists" == "0" ]]; then
      docker exec supabase-db psql -U supabase_admin -d "$OLD_DB" -c \
        "SELECT pg_create_logical_replication_slot('$OLD_SLOT', '$SLOT_PLUGIN');" \
        >/dev/null 2>&1 || rollback_failed=1
    fi
  fi
  if [[ "$OLD_COMPOSE_STOPPED" -eq 1 && -d "$OLD_DIR" ]]; then
    compose_old up -d >/dev/null 2>&1 || rollback_failed=1
  fi

  if [[ "$rollback_failed" -eq 0 ]]; then
    echo "ROLLBACK_COMPLETE ${NEW_NAME}=${OLD_NAME}" >&2
  else
    echo "ROLLBACK_INCOMPLETE ${NEW_NAME}=${OLD_NAME}" >&2
  fi
  cleanup
  exit "$status"
}

trap rollback_on_error ERR
trap 'rollback_on_error 143' TERM
trap 'rollback_on_error 130' INT
trap 'rollback_on_error 129' HUP
trap cleanup EXIT

NAME_RE='^[a-z_][a-z0-9_]{2,39}$'
[[ "$OLD_NAME" =~ $NAME_RE && "$NEW_NAME" =~ $NAME_RE ]] \
  || die "Nomes devem usar minusculas, digitos ou _ (3-40 caracteres)"
RESERVED=(default select from where insert update delete table create drop join group order limit into index view trigger procedure function database schema primary foreign key constraint unique null not and or in like between exists having union inner left right outer cross on as case when then else end if while for begin commit rollback)
for word in "${RESERVED[@]}"; do
  [[ "$NEW_NAME" != "$word" ]] || die "'$NEW_NAME' e palavra reservada"
done

for command in docker jq openssl sed; do
  command -v "$command" >/dev/null || die "Comando obrigatorio ausente: $command"
done
[[ -f "$PROJECT_ROOT/.env" ]] || die "Arquivo $PROJECT_ROOT/.env ausente"
[[ -d "$OLD_DIR" ]] || die "Diretorio $OLD_DIR nao encontrado"
[[ ! -e "$NEW_DIR" ]] || die "Destino $NEW_DIR ja existe"
for template in nginxtemplate .envtemplate dockercomposetemplate poolertemplate Dockerfile; do
  [[ -f "$SCRIPT_DIR/$template" ]] || die "Template ausente: $template"
done
for file in .env docker-compose.yml Dockerfile pooler/pooler.exs; do
  [[ -f "$OLD_DIR/$file" ]] || die "Arquivo do projeto ausente: $file"
done

source "$PROJECT_ROOT/.env"
source "$OLD_DIR/.env"

for variable in POSTGRES_HOST POSTGRES_PASSWORD POSTGRES_PORT SERVER_URL \
  JWT_SECRET JWT_SECRET_PROJETO PROJECT_UUID ANON_KEY_PROJETO \
  SERVICE_ROLE_KEY_PROJETO CONFIG_TOKEN_PROJETO; do
  [[ -n "${!variable:-}" ]] || die "$variable ausente"
done

docker inspect supabase-db >/dev/null 2>&1 || die "Container supabase-db ausente"
docker inspect supabase-pooler >/dev/null 2>&1 || die "Container supabase-pooler ausente"
docker inspect realtime-dev.supabase-realtime >/dev/null 2>&1 \
  || die "Container Realtime ausente"

META_DB="${POSTGRES_DB:-postgres}"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$OLD_DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Banco $OLD_DB nao encontrado"
[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$NEW_DB';" | tr -d '[:space:]')" == "0" ]] \
  || die "Banco $NEW_DB ja existe"
[[ "$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc "SELECT count(*) FROM projects WHERE name = '$OLD_NAME';" | tr -d '[:space:]')" == "1" ]] \
  || die "Projeto $OLD_NAME nao encontrado na metadata"
[[ "$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc "SELECT count(*) FROM projects WHERE name = '$NEW_NAME';" | tr -d '[:space:]')" == "0" ]] \
  || die "Projeto $NEW_NAME ja existe na metadata"

cp -a "$OLD_DIR/.env" "$BACKUP_DIR/.env"
cp -a "$OLD_DIR/docker-compose.yml" "$BACKUP_DIR/docker-compose.yml"
cp -a "$OLD_DIR/Dockerfile" "$BACKUP_DIR/Dockerfile"
mkdir -p "$BACKUP_DIR/nginx" "$BACKUP_DIR/pooler"
cp -a "$OLD_DIR/nginx/." "$BACKUP_DIR/nginx/"
cp -a "$OLD_DIR/pooler/pooler.exs" "$BACKUP_DIR/pooler/pooler.exs"

PG_VERSION=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
  "SHOW server_version_num;" | tr -d '[:space:]')
now=$(date +%s)
GLOBAL_ANON_TOKEN=$(generate_jwt \
  "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$((now + 3600))}" \
  "$JWT_SECRET")
REALTIME_OLD_PAYLOAD=$(build_realtime_payload "$OLD_NAME")
REALTIME_NEW_PAYLOAD=$(build_realtime_payload "$NEW_NAME")
SUPAVISOR_OLD_PAYLOAD=$(build_supavisor_payload "$OLD_NAME")
SUPAVISOR_NEW_PAYLOAD=$(build_supavisor_payload "$NEW_NAME")
OLD_SLOT="supabase_realtime_replication_slot_${OLD_NAME}"
NEW_SLOT="supabase_realtime_replication_slot_${NEW_NAME}"
OLD_SLOT="${OLD_SLOT:0:63}"
NEW_SLOT="${NEW_SLOT:0:63}"

say "Parando stack antiga..."
MUTATION_STARTED=1
OLD_COMPOSE_STOPPED=1
compose_old down --remove-orphans

code=$(http_code realtime-dev.supabase-realtime POST \
  "/api/tenants/$PROJECT_UUID/shutdown" "$ANON_KEY_PROJETO")
accepted_code "$code" 200 202 204 404 \
  || die "Realtime nao aceitou shutdown (HTTP $code)"
code=$(http_code supabase-pooler GET "/api/tenants/$OLD_NAME/terminate" \
  "$GLOBAL_ANON_TOKEN")
accepted_code "$code" 200 204 404 \
  || die "Supavisor nao encerrou os pools antigos (HTTP $code)"

say "Renomeando database $OLD_DB -> $NEW_DB..."
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$OLD_DB' AND pid <> pg_backend_pid(); ALTER DATABASE \"$OLD_DB\" RENAME TO \"$NEW_DB\";" \
  >/dev/null
RENAMED_DB=1

if [[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_replication_slots WHERE slot_name = '$OLD_SLOT';" | tr -d '[:space:]')" == "1" ]]; then
  SLOT_PLUGIN=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc \
    "SELECT plugin FROM pg_replication_slots WHERE slot_name = '$OLD_SLOT';" | tr -d '[:space:]')
  RENAMED_SLOT=1
  restore_slot "$OLD_SLOT" "$NEW_SLOT" "$SLOT_PLUGIN" "$NEW_DB"
fi

say "Atualizando tenant Realtime estavel $PROJECT_UUID..."
code=$(http_code realtime-dev.supabase-realtime PUT \
  "/api/tenants/$PROJECT_UUID" "$ANON_KEY_PROJETO" "$REALTIME_NEW_PAYLOAD")
accepted_code "$code" 200 201 204 || die "Falha no Realtime (HTTP $code)"
REALTIME_UPDATED=1

realtime_matches=$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc \
  "SELECT count(*) FROM _realtime.extensions WHERE tenant_external_id = '$PROJECT_UUID' AND settings->>'slot_name' = '$NEW_SLOT';" \
  | tr -d '[:space:]')
[[ "$realtime_matches" -ge 1 ]] \
  || die "Realtime nao persistiu o slot do novo slug"

say "Recriando tenant Supavisor $OLD_NAME -> $NEW_NAME..."
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$META_DB" -c \
  "DELETE FROM _supavisor.users WHERE tenant_external_id = '$OLD_NAME'; DELETE FROM _supavisor.tenants WHERE external_id = '$OLD_NAME';" \
  >/dev/null
SUPAVISOR_OLD_DELETED=1
code=$(http_code supabase-pooler PUT "/api/tenants/$NEW_NAME" \
  "$GLOBAL_ANON_TOKEN" "$SUPAVISOR_NEW_PAYLOAD")
accepted_code "$code" 200 201 204 || die "Falha no Supavisor (HTTP $code)"
SUPAVISOR_UPDATED=1
supavisor_matches=$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc \
  "SELECT count(*) FROM _supavisor.tenants WHERE external_id = '$NEW_NAME' AND db_database = '$NEW_DB';" \
  | tr -d '[:space:]')
supavisor_old=$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc \
  "SELECT count(*) FROM _supavisor.tenants WHERE external_id = '$OLD_NAME';" \
  | tr -d '[:space:]')
supavisor_users=$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc \
  "SELECT count(*) FROM _supavisor.users WHERE tenant_external_id = '$NEW_NAME';" \
  | tr -d '[:space:]')
[[ "$supavisor_matches" == "1" && "$supavisor_old" == "0" && "$supavisor_users" -ge 1 ]] \
  || die "Supavisor nao persistiu a troca de external_id/database"

say "Movendo diretorio e regenerando configuracao..."
mv "$OLD_DIR" "$NEW_DIR"
MOVED_DIR=1

escape_sed_replacement() { printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'; }
normalize_public_base_url() {
  local url="${1%/}" proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then printf '%s' "$url"; return; fi
  printf '%s://%s' "${proto:-https}" "$url"
}
PUBLIC_BASE_URL=$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$NEW_NAME"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"

template_to_file() {
  local template="$1" output="$2"
  sed \
    -e "s|{{anon_key}}|$(escape_sed_replacement "$ANON_KEY_PROJETO")|g" \
    -e "s|{{service_role_key}}|$(escape_sed_replacement "$SERVICE_ROLE_KEY_PROJETO")|g" \
    -e "s|{{project_id}}|$(escape_sed_replacement "$NEW_NAME")|g" \
    -e "s|{{project_uuid}}|$(escape_sed_replacement "$PROJECT_UUID")|g" \
    -e "s|{{config_token}}|$(escape_sed_replacement "$CONFIG_TOKEN_PROJETO")|g" \
    -e "s|{{jwt_secret}}|$(escape_sed_replacement "$JWT_SECRET_PROJETO")|g" \
    -e "s|{{server_url}}|$(escape_sed_replacement "$SERVER_URL")|g" \
    -e "s|{{public_base_url}}|$(escape_sed_replacement "$PUBLIC_BASE_URL")|g" \
    -e "s|{{project_public_url}}|$(escape_sed_replacement "$PROJECT_PUBLIC_URL")|g" \
    -e "s|{{project_auth_external_url}}|$(escape_sed_replacement "$PROJECT_AUTH_EXTERNAL_URL")|g" \
    -e "s|{{project_root}}|$(escape_sed_replacement "${HOST_PROJECT_ROOT:-}")|g" \
    -e "s|{{logflare_api_key}}|$(escape_sed_replacement "${LOGFLARE_API_KEY:-}")|g" \
    "$template" > "$output"
}

rm -f "$NEW_DIR/nginx/nginx_${OLD_NAME}.conf"
template_to_file "$SCRIPT_DIR/nginxtemplate" "$NEW_DIR/nginx/nginx_${NEW_NAME}.conf"
template_to_file "$SCRIPT_DIR/.envtemplate" "$NEW_DIR/.env"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$NEW_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/poolertemplate" "$NEW_DIR/pooler/pooler.exs"
template_to_file "$SCRIPT_DIR/Dockerfile" "$NEW_DIR/Dockerfile"
chmod 600 "$NEW_DIR/.env" "$NEW_DIR/nginx/nginx_${NEW_NAME}.conf"

grep -qx "PROJECT_ID=$NEW_NAME" "$NEW_DIR/.env" \
  || die "PROJECT_ID nao foi atualizado no .env"
if grep -En "\{\{[a-z_]+\}\}" "$NEW_DIR/.env" "$NEW_DIR/docker-compose.yml" \
  "$NEW_DIR/nginx/nginx_${NEW_NAME}.conf" >/dev/null 2>&1; then
  die "Configuracao regenerada ainda contem placeholders"
fi

say "Atualizando metadata e jobs..."
updated=$(docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$META_DB" -tAc \
  "WITH changed AS (UPDATE projects SET name = '$NEW_NAME' WHERE name = '$OLD_NAME' RETURNING name) SELECT count(*) FROM changed;" \
  | tr -d '[:space:]')
[[ "$updated" == "1" ]] || die "Metadata nao atualizou exatamente um projeto"
META_UPDATED=1
docker exec supabase-db psql -v ON_ERROR_STOP=1 -U supabase_admin -d "$META_DB" -c \
  "UPDATE jobs SET project = '$NEW_NAME' WHERE project = '$OLD_NAME';" >/dev/null

say "Subindo stack com o novo slug..."
NEW_COMPOSE_STARTED=1
compose_new up --build -d

[[ "$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname = '$NEW_DB';" | tr -d '[:space:]')" == "1" ]] \
  || die "Verificacao final do database falhou"
[[ "$(docker exec supabase-db psql -U supabase_admin -d "$META_DB" -tAc "SELECT count(*) FROM projects WHERE name = '$NEW_NAME';" | tr -d '[:space:]')" == "1" ]] \
  || die "Verificacao final da metadata falhou"
running_services=$(compose_new ps --status running --services | wc -l | tr -d '[:space:]')
[[ "$running_services" -gt 0 ]] || die "Nenhum servico do novo projeto esta rodando"

trap - ERR TERM INT HUP
cleanup
trap - EXIT
ok "RENAMED ${OLD_NAME}=${NEW_NAME} path=/${OLD_NAME}->/${NEW_NAME} uuid=${PROJECT_UUID}"
