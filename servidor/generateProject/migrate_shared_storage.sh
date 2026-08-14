#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

die() { echo "ERRO MIGRACAO: $*" >&2; exit 1; }
say() { echo "[storage-migration] $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$SERVER_ROOT")"
REPORTS_ROOT="$SERVER_ROOT/storage-migration-reports"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"

for command in docker jq openssl python3 tar gzip sed grep systemctl; do
  command -v "$command" >/dev/null 2>&1 || die "$command nao esta instalado"
done
[[ -f "$SERVER_ROOT/.env" ]] || die "servidor/.env ausente"
[[ -f "$SERVER_ROOT/.env.example" ]] || die "servidor/.env.example ausente"
[[ -f "$SERVER_ROOT/.storage.env.example" ]] || die ".storage.env.example ausente"
[[ -d "$SERVER_ROOT/projects" ]] || die "diretorio de projetos ausente"

mkdir -p "$REPORTS_ROOT"
REPORTS_ROOT="$(cd "$REPORTS_ROOT" && pwd -P)"

if [[ "${1:-}" == "--resume" ]]; then
  [[ -n "${2:-}" && $# -eq 2 ]] || die "Uso: $0 [--resume <report_dir>]"
  RUN_DIR="$(cd "$2" && pwd -P)"
  [[ "$(dirname "$RUN_DIR")" == "$REPORTS_ROOT" ]] \
    || die "report_dir fora de $REPORTS_ROOT"
else
  [[ $# -eq 0 ]] || die "Uso: $0 [--resume <report_dir>]"
  RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  RUN_DIR="$REPORTS_ROOT/$RUN_ID"
  mkdir "$RUN_DIR"
  RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"
fi
mkdir -p "$RUN_DIR/state" "$RUN_DIR/config-before" \
  "$RUN_DIR/old-storage" "$RUN_DIR/old-backups"
chmod 700 "$RUN_DIR"
[[ ! -f "$RUN_DIR/COMPLETE" ]] \
  || die "esta migracao ja foi concluida; nao reutilize o report_dir"
SUMMARY="$RUN_DIR/summary.tsv"
[[ -f "$SUMMARY" ]] || printf 'scope\tid\tstatus\tdetail\n' > "$SUMMARY"

PROJECTS_API_MARKER="$RUN_DIR/projects-api.was-running"
PROJECTS_API_OVERRIDE_MARKER="$RUN_DIR/projects-api.compose-override"
HOST_AGENT_MARKER="$RUN_DIR/host-agent.was-active"
PROJECTS_API_WAS_RUNNING=0
HOST_AGENT_WAS_ACTIVE=0
[[ -f "$PROJECTS_API_MARKER" ]] && PROJECTS_API_WAS_RUNNING=1
[[ -f "$HOST_AGENT_MARKER" ]] && HOST_AGENT_WAS_ACTIVE=1
LIFECYCLE_QUIESCED=0
MIGRATION_MUTATIONS_STARTED=0

report() {
  local scope="$1" id="$2" status="$3" detail="$4"
  detail="${detail//$'\t'/ }"
  detail="${detail//$'\n'/ }"
  printf '%s\t%s\t%s\t%s\n' "$scope" "$id" "$status" "$detail" >> "$SUMMARY"
}

run_systemctl() {
  if [[ "$(id -u)" -eq 0 ]]; then
    systemctl "$@"
  else
    command -v sudo >/dev/null 2>&1 \
      || die "sudo e obrigatorio para controlar o host-agent"
    sudo systemctl "$@"
  fi
}

active_lifecycle_counts() {
  local table exists count jobs=0 commands=0
  for table in jobs host_agent_commands; do
    exists="$(docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
      "SELECT to_regclass('public.$table') IS NOT NULL;" | tr -d '[:space:]')"
    if [[ "$exists" == "t" ]]; then
      count="$(docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
        "SELECT count(*) FROM $table WHERE status IN ('queued','running');" \
        | tr -d '[:space:]')"
      [[ "$count" =~ ^[0-9]+$ ]] || die "contagem invalida em $table"
      if [[ "$table" == "jobs" ]]; then jobs="$count"; else commands="$count"; fi
    elif [[ "$exists" != "f" ]]; then
      die "nao foi possivel inspecionar $table"
    fi
  done
  printf '%s\t%s\n' "$jobs" "$commands"
}

restart_projects_api_without_rebuild() {
  [[ "$PROJECTS_API_WAS_RUNNING" -eq 1 ]] || return 0
  docker start projects-api >/dev/null
  PROJECTS_API_WAS_RUNNING=0
}

capture_projects_api_override() {
  local config_files override="" has_single=0 has_split=0
  config_files="$(docker inspect -f \
    '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' \
    projects-api)" || die "nao foi possivel identificar a topologia da Projects API"
  [[ "$config_files" == *"docker-compose.single-node.yml"* ]] && has_single=1
  [[ "$config_files" == *"docker-compose.split-node.yml"* ]] && has_split=1
  if [[ "$has_single" -eq 1 && "$has_split" -eq 0 ]]; then
    override="docker-compose.single-node.yml"
  elif [[ "$has_single" -eq 0 && "$has_split" -eq 1 ]]; then
    override="docker-compose.split-node.yml"
  else
    die "topologia da Projects API ausente ou ambigua nos labels do Compose"
  fi
  printf '%s\n' "$override" > "$PROJECTS_API_OVERRIDE_MARKER"
}

read_projects_api_override() {
  local -a lines=()
  [[ -f "$PROJECTS_API_OVERRIDE_MARKER" ]] \
    || die "marcador de topologia da Projects API ausente"
  mapfile -t lines < "$PROJECTS_API_OVERRIDE_MARKER"
  [[ "${#lines[@]}" -eq 1 ]] \
    || die "marcador de topologia da Projects API invalido"
  case "${lines[0]}" in
    docker-compose.single-node.yml|docker-compose.split-node.yml)
      printf '%s' "${lines[0]}"
      ;;
    *) die "override da Projects API nao suportado" ;;
  esac
}

quiesce_lifecycle() {
  local counts jobs commands
  counts="$(active_lifecycle_counts)"
  IFS=$'\t' read -r jobs commands <<<"$counts"
  [[ "$jobs" == "0" && "$commands" == "0" ]] \
    || die "existem jobs lifecycle ativos (jobs=$jobs commands=$commands); aguarde e execute novamente"

  if [[ "$(docker inspect -f '{{.State.Running}}' projects-api 2>/dev/null || true)" == "true" ]]; then
    capture_projects_api_override
    PROJECTS_API_WAS_RUNNING=1
    : > "$PROJECTS_API_MARKER"
    docker stop --time 30 projects-api >/dev/null
  fi

  # Fecha a pequena janela entre o primeiro preflight e o stop da API. Se
  # houve corrida, a API original volta e nenhuma mutacao de migracao comeca.
  counts="$(active_lifecycle_counts)"
  IFS=$'\t' read -r jobs commands <<<"$counts"
  if [[ "$jobs" != "0" || "$commands" != "0" ]]; then
    restart_projects_api_without_rebuild || true
    die "lifecycle iniciou durante a quiescencia (jobs=$jobs commands=$commands); aguarde sua conclusao"
  fi

  if systemctl is-active --quiet supabase-host-agent; then
    HOST_AGENT_WAS_ACTIVE=1
    : > "$HOST_AGENT_MARKER"
    run_systemctl stop supabase-host-agent
  fi
  LIFECYCLE_QUIESCED=1
  report infrastructure lifecycle quiesced "Projects API e host-agent sem jobs ativos"
}

resume_lifecycle_after_success() {
  local status="" attempts api_override
  if [[ "$PROJECTS_API_WAS_RUNNING" -eq 1 ]]; then
    api_override="$(read_projects_api_override)"
    (cd "$SERVER_ROOT" && docker compose \
      -f docker-compose-api.yml -f "$api_override" \
      --env-file .env up --build -d projects-api)
    for attempts in $(seq 1 60); do
      status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
        projects-api 2>/dev/null || true)"
      [[ "$status" == "healthy" ]] && break
      [[ "$status" != "unhealthy" && "$status" != "exited" && "$status" != "dead" ]] \
        || die "Projects API terminou com status $status apos a migracao"
      sleep 2
    done
    [[ "$status" == "healthy" ]] \
      || die "Projects API nao ficou saudavel apos a migracao"
    PROJECTS_API_WAS_RUNNING=0
  fi
  if [[ "$HOST_AGENT_WAS_ACTIVE" -eq 1 ]]; then
    run_systemctl start supabase-host-agent
    systemctl is-active --quiet supabase-host-agent \
      || die "host-agent nao ficou ativo apos a migracao"
    HOST_AGENT_WAS_ACTIVE=0
  fi
  LIFECYCLE_QUIESCED=0
  report infrastructure lifecycle resumed "runtime novo iniciado apos conversao integral"
}

migration_exit() {
  local status="$?"
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    if [[ "$MIGRATION_MUTATIONS_STARTED" -eq 0 ]]; then
      restart_projects_api_without_rebuild || true
      if [[ "$HOST_AGENT_WAS_ACTIVE" -eq 1 ]]; then
        run_systemctl start supabase-host-agent >/dev/null 2>&1 || true
      fi
    elif [[ "$LIFECYCLE_QUIESCED" -eq 1 ]]; then
      if [[ "$(docker inspect -f '{{.State.Running}}' projects-api 2>/dev/null || true)" == "true" ]]; then
        docker stop --time 30 projects-api >/dev/null 2>&1 || true
      fi
      if systemctl is-active --quiet supabase-host-agent; then
        run_systemctl stop supabase-host-agent >/dev/null 2>&1 || true
      fi
      report migration all blocked \
        "estado parcial: Projects API e host-agent permaneceram parados; corrija e use --resume"
      say "Migracao interrompida. Projects API e host-agent permanecem parados para impedir runtime misto; corrija o erro e use --resume $RUN_DIR."
    fi
  fi
  exit "$status"
}
trap migration_exit EXIT

canonical_env_value() {
  local file="$1" key="$2" assignment_count value
  [[ -f "$file" ]] || return 1
  assignment_count="$(grep -c "^${key}=" "$file" || true)"
  [[ "$assignment_count" == "1" ]] || return 1
  value="$(sed -n "s/^${key}=//p" "$file")"
  [[ -n "$value" && "$value" != *$'\r'* ]] || return 1
  printf '%s' "$value"
}

ensure_global_storage_config() {
  local target="$SERVER_ROOT/.env" example="$SERVER_ROOT/.env.example"
  local temp key value count
  local keys=(
    STORAGE_IMAGE STORAGE_DATA_PLANE_PROXY_IMAGE STORAGE_TENANT_DB_USER STORAGE_BACKEND
    STORAGE_FILE_BACKEND_PATH STORAGE_INTERNAL_BUCKET STORAGE_S3_REGION
    STORAGE_FILE_SIZE_LIMIT STORAGE_FILE_SIZE_LIMIT_STANDARD
    STORAGE_TENANT_MAX_CONNECTIONS STORAGE_TENANT_POOL_IDLE_MS
    STORAGE_TENANT_HOST_REGEXP STORAGE_IMAGE_TRANSFORMATION_ENABLED
    STORAGE_VECTOR_ENABLED STORAGE_VECTOR_MAX_BUCKETS STORAGE_VECTOR_MAX_INDEXES
    STORAGE_LOG_LEVEL IMGPROXY_IMAGE IMGPROXY_BIND
    IMGPROXY_LOCAL_FILESYSTEM_ROOT IMGPROXY_USE_ETAG
    IMGPROXY_ENABLE_WEBP_DETECTION
  )

  if [[ ! -f "$RUN_DIR/config-before/server.env" ]]; then
    cp -a "$target" "$RUN_DIR/config-before/server.env"
  fi
  temp="$(mktemp "$RUN_DIR/.server-env.XXXXXX")"
  cp "$target" "$temp"
  for key in "${keys[@]}"; do
    count="$(grep -c "^${key}=" "$temp" || true)"
    [[ "$count" -le 1 ]] || die "$key duplicada em servidor/.env"
    if [[ "$count" == "0" ]]; then
      value="$(canonical_env_value "$example" "$key")" \
        || die "$key ausente em servidor/.env.example"
      printf '%s=%s\n' "$key" "$value" >> "$temp"
    fi
  done
  chmod 600 "$temp"
  mv "$temp" "$target"
}

ensure_storage_secrets() {
  local target="$SERVER_ROOT/.storage.env" admin_key encryption_key
  if [[ ! -f "$target" ]]; then
    admin_key="$(openssl rand -hex 32)"
    encryption_key="$(openssl rand -hex 32)"
    printf 'SERVER_ADMIN_API_KEYS=%s\nAUTH_ENCRYPTION_KEY=%s\n' \
      "$admin_key" "$encryption_key" > "$target"
    chmod 600 "$target"
  fi
  admin_key="$(canonical_env_value "$target" SERVER_ADMIN_API_KEYS)" \
    || die "SERVER_ADMIN_API_KEYS ausente ou duplicada"
  encryption_key="$(canonical_env_value "$target" AUTH_ENCRYPTION_KEY)" \
    || die "AUTH_ENCRYPTION_KEY ausente ou duplicada"
  [[ "$admin_key" =~ ^[0-9a-f]{64}$ ]] || die "SERVER_ADMIN_API_KEYS invalida"
  [[ "$encryption_key" =~ ^[0-9a-f]{64}$ ]] || die "AUTH_ENCRYPTION_KEY invalida"
}

create_registry_database() {
  set -a
  # shellcheck disable=SC1090
  source "$SERVER_ROOT/.env"
  set +a
  docker inspect supabase-db >/dev/null 2>&1 || die "supabase-db nao esta rodando"
  docker exec -i supabase-db psql -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" <<'SQL'
SELECT 'CREATE DATABASE "_supabase_storage"'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = '_supabase_storage'
)\gexec
REVOKE ALL ON DATABASE "_supabase_storage" FROM PUBLIC;
GRANT ALL PRIVILEGES ON DATABASE "_supabase_storage" TO supabase_admin;
SQL
}

start_global_storage() {
  (cd "$SERVER_ROOT" && docker compose -f docker-compose.yml --env-file .env \
    up -d db supavisor imgproxy storage storage-data-plane)
  storage_wait_global || die "Storage compartilhado nao iniciou"
}

tenant_exists() {
  local tenant_id="$1" payload
  payload="$(storage_admin_request GET "/tenants/$tenant_id" "200,404")"
  [[ -n "$payload" ]]
}

render_project_files() {
  local project="$1" project_dir="$SERVER_ROOT/projects/$1"
  PYTHONPATH="$SERVER_ROOT/host-agent" python3 - "$SERVER_ROOT" "$project" <<'PY'
import pathlib
import sys
from hostagent.templates import sync_project_generated_files

root = pathlib.Path(sys.argv[1]).resolve()
project = sys.argv[2]
sync_project_generated_files(
    root=root,
    scripts_dir=root / "generateProject",
    project_dir=root / "projects" / project,
    project=project,
)
PY
}

render_project_env() {
  local project="$1" old_env="$2" output="$3" credential_id="$4"
  local access_key="$5" secret_key="$6"
  jq -cn \
    --arg anon_key "$ANON_KEY_PROJETO" \
    --arg service_role_key "$SERVICE_ROLE_KEY_PROJETO" \
    --arg project_id "$project" \
    --arg project_uuid "$PROJECT_UUID" \
    --arg config_token "$CONFIG_TOKEN_PROJETO" \
    --arg jwt_secret "$JWT_SECRET_PROJETO" \
    --arg api_gateway_token "$API_GATEWAY_TOKEN_PROJETO" \
    --arg server_url "$SERVER_URL" \
    --arg public_base_url "$PUBLIC_BASE_URL" \
    --arg project_public_url "$PROJECT_PUBLIC_URL" \
    --arg project_auth_external_url "$PROJECT_AUTH_EXTERNAL_URL" \
    --arg project_root "$HOST_PROJECT_ROOT" \
    --arg s3_protocol_credential_id "$credential_id" \
    --arg s3_protocol_access_key_id "$access_key" \
    --arg s3_protocol_access_key_secret "$secret_key" \
    '{anon_key:$anon_key, service_role_key:$service_role_key,
      project_id:$project_id, project_uuid:$project_uuid,
      config_token:$config_token, jwt_secret:$jwt_secret,
      api_gateway_token:$api_gateway_token, server_url:$server_url,
      public_base_url:$public_base_url, project_public_url:$project_public_url,
      project_auth_external_url:$project_auth_external_url,
      project_root:$project_root,
      s3_protocol_credential_id:$s3_protocol_credential_id,
      s3_protocol_access_key_id:$s3_protocol_access_key_id,
      s3_protocol_access_key_secret:$s3_protocol_access_key_secret}' \
    | python3 "$SCRIPT_DIR/render_migrated_project_env.py" \
      "$SCRIPT_DIR/.envtemplate" "$old_env" "$output"
}

normalize_public_base_url() {
  local url="${1%/}" proto="$2"
  if [[ "$url" =~ ^https?:// ]]; then printf '%s' "$url"; return; fi
  [[ "$proto" == "http" || "$proto" == "https" ]] \
    || die "SERVER_PROTO invalido"
  printf '%s://%s' "$proto" "$url"
}

# Conversao exclusiva desta ferramenta: o runtime novo nunca aceita o tenant
# historico "stub". O hash deve ser refeito porque o nome fisico do pgvector
# incorpora o tenant no indexName oficial do Storage.
migration_rekey_vector_physical_tables() {
  local database="$1" source_tenant="$2" destination_tenant="$3"
  [[ -n "${POSTGRES_USER:-}" ]] || die "POSTGRES_USER ausente"
  [[ "$source_tenant" == "stub" || "$source_tenant" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || die "tenant de origem invalido para conversao vetorial"
  [[ "$destination_tenant" == "stub" || "$destination_tenant" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || die "tenant de destino invalido para conversao vetorial"
  [[ "$source_tenant" != "$destination_tenant" ]] || return 0

  docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "$database" -c \
    "COPY (SELECT bucket_id, name FROM storage.vector_indexes ORDER BY bucket_id, name) TO STDOUT WITH (FORMAT csv)" \
    | python3 -c '
import csv
import hashlib
import sys

source, destination = sys.argv[1:]
print("BEGIN;")
for bucket, index in csv.reader(sys.stdin):
    def physical(tenant):
        value = f"pgvector__{bucket}".encode() + b"\0" + f"{tenant}-{index}".encode()
        return "vector_" + hashlib.sha256(value).hexdigest()[:24]
    old = physical(source)
    new = physical(destination)
    print(f"""
DO $rekey$
BEGIN
  IF to_regclass('\''storage_vectors.{old}'\'') IS NOT NULL
     AND to_regclass('\''storage_vectors.{new}'\'') IS NULL THEN
    ALTER TABLE storage_vectors.{old} RENAME TO {new};
    IF to_regclass('\''storage_vectors.{old}_hnsw'\'') IS NOT NULL THEN
      ALTER INDEX storage_vectors.{old}_hnsw RENAME TO {new}_hnsw;
    END IF;
  ELSIF to_regclass('\''storage_vectors.{old}'\'') IS NULL
        AND to_regclass('\''storage_vectors.{new}'\'') IS NOT NULL THEN
    NULL;
  ELSE
    RAISE EXCEPTION '\''ambiguous vector table rekey: {old} -> {new}'\'';
  END IF;
END
$rekey$;
""")
print("COMMIT;")
' "$source_tenant" "$destination_tenant" \
    | docker exec -i supabase-db psql -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" -d "$database"
}

restore_project_config() {
  local project="$1" archive="$RUN_DIR/config-before/$1.tar.gz"
  local project_dir="$SERVER_ROOT/projects/$1"
  [[ -s "$archive" ]] || return 1
  (cd "$project_dir" && tar -xzf "$archive")
}

restore_old_storage_if_needed() {
  local project="$1" project_dir="$SERVER_ROOT/projects/$1"
  local old_storage="$project_dir/storage" archive="$RUN_DIR/old-storage/$1.tar.gz"
  [[ ! -e "$old_storage" ]] || return 0
  [[ -s "$archive" ]] || return 1
  (cd "$project_dir" && tar --xattrs --xattrs-include='*' --acls \
    -xzpf "$archive")
}

rollback_partial_project() {
  local project="$1" project_dir="$SERVER_ROOT/projects/$1" tenant_id="$2"
  say "Revertendo estado parcial detectado de $project..."
  if [[ -f "$project_dir/docker-compose.yml" && -f "$project_dir/.env" ]]; then
    (cd "$project_dir" && docker compose -p "$project" \
      --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 || true
  fi
  storage_delete_tenant "$tenant_id" || return 1
  migration_rekey_vector_physical_tables "_supabase_$project" "$tenant_id" stub || return 1
  restore_project_config "$project" || return 1
  restore_old_storage_if_needed "$project" || return 1
  (cd "$project_dir" && docker compose -p "$project" \
    --env-file ../../.env --env-file .env up -d) >/dev/null || return 1
  printf 'ROLLED_BACK\n' > "$RUN_DIR/state/$project"
}

migrate_project() (
  set -Eeuo pipefail
  local project="$1" project_dir="$SERVER_ROOT/projects/$1"
  local env_file="$project_dir/.env" compose_file="$project_dir/docker-compose.yml"
  local state_file="$RUN_DIR/state/$project" config_archive="$RUN_DIR/config-before/$project.tar.gz"
  local old_storage="$project_dir/storage" old_namespace="$project_dir/storage/stub/stub"
  local credential_row credential_id access_key secret_key current_state=""
  local storage_owned=0 vector_rekeyed=0 config_changed=0

  [[ -f "$env_file" && -f "$compose_file" ]] \
    || { report project "$project" failed "configuracao ausente"; return 1; }
  [[ "$project" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || return 1

  set -a
  # shellcheck disable=SC1090
  source "$SERVER_ROOT/.env"
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  PROJECT_UUID="$(tr '[:upper:]' '[:lower:]' <<<"${PROJECT_UUID:-}")"
  storage_validate_tenant_id "$PROJECT_UUID" || return 1
  for variable in JWT_SECRET_PROJETO ANON_KEY_PROJETO SERVICE_ROLE_KEY_PROJETO \
    CONFIG_TOKEN_PROJETO API_GATEWAY_TOKEN_PROJETO FILE_SIZE_LIMIT \
    ENABLE_IMAGE_TRANSFORMATION; do
    [[ -n "${!variable:-}" ]] || { report project "$project" failed "$variable ausente"; return 1; }
  done
  if [[ -z "${VECTOR_BUCKETS_ENABLED:-}" ]]; then
    [[ "${VECTOR_ENABLED:-}" == "true" || "${VECTOR_ENABLED:-}" == "false" ]] \
      || { report project "$project" failed "VECTOR_ENABLED antigo invalido"; return 1; }
    VECTOR_BUCKETS_ENABLED="$VECTOR_ENABLED"
  fi
  if [[ -z "${S3_PROTOCOL_ENABLED:-}" ]]; then
    S3_PROTOCOL_ENABLED="$(canonical_env_value "$SCRIPT_DIR/.envtemplate" S3_PROTOCOL_ENABLED)"
  fi
  storage_validate_bool S3_PROTOCOL_ENABLED "$S3_PROTOCOL_ENABLED" || return 1
  storage_validate_bool VECTOR_BUCKETS_ENABLED "$VECTOR_BUCKETS_ENABLED" || return 1
  if [[ -z "${VECTOR_MAX_BUCKETS:-}" ]]; then
    VECTOR_MAX_BUCKETS="$(canonical_env_value "$SCRIPT_DIR/.envtemplate" VECTOR_MAX_BUCKETS)"
  fi
  if [[ -z "${VECTOR_MAX_INDEXES:-}" ]]; then
    VECTOR_MAX_INDEXES="$(canonical_env_value "$SCRIPT_DIR/.envtemplate" VECTOR_MAX_INDEXES)"
  fi
  PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
  PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$project"
  PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"
  export PROJECT_UUID SERVICE_ROLE_KEY_PROJETO

  storage_assert_project_identity "$project" "$PROJECT_UUID" \
    || { report project "$project" failed "tenant UUID diverge do control plane"; return 1; }

  if ! grep -Eq 'container_name:[[:space:]]*supabase-(storage|imgproxy)-' "$compose_file" \
    && [[ "${S3_PROTOCOL_CREDENTIAL_ID:-}" =~ ^[0-9a-f-]{36}$ ]] \
    && tenant_exists "$PROJECT_UUID" \
    && [[ -d "$(storage_assert_namespace_target "$PROJECT_UUID")" ]]; then
    vector_validate_s3_credentials || return 1
    storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
      "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
      "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" || return 1
    storage_assert_project_gateway "$PROJECT_UUID" "$project" "$SERVICE_ROLE_KEY_PROJETO" \
      || return 1
    printf 'COMPLETE\n' > "$state_file"
    report project "$project" already-migrated "tenant validado"
    return 0
  fi

  [[ -f "$state_file" ]] && current_state="$(head -n1 "$state_file")"
  if [[ -n "$current_state" && "$current_state" != "COMPLETE" \
      && "$current_state" != "ROLLED_BACK" ]]; then
    rollback_partial_project "$project" "$PROJECT_UUID" \
      || { report project "$project" blocked "rollback parcial falhou"; return 1; }
    set -a
    # shellcheck disable=SC1090
    source "$SERVER_ROOT/.env"
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  elif tenant_exists "$PROJECT_UUID"; then
    report project "$project" blocked "tenant existente sem estado de migracao"
    return 1
  fi

  [[ -d "$old_namespace" && ! -L "$old_storage" && ! -L "$old_namespace" ]] \
    || { report project "$project" failed "layout antigo storage/stub/stub ausente"; return 1; }
  if [[ ! -s "$config_archive" ]]; then
    (cd "$project_dir" && tar --exclude='./storage' -czf "$config_archive" .)
  fi
  printf 'PREPARED\n' > "$state_file"

  rollback_current() {
    local status="${1:-1}" rollback_failed=0
    trap - ERR TERM INT HUP
    set +e
    say "Falha em $project; revertendo somente este projeto..."
    if [[ -f "$project_dir/docker-compose.yml" && -f "$project_dir/.env" ]]; then
      (cd "$project_dir" && docker compose -p "$project" \
        --env-file ../../.env --env-file .env down --remove-orphans) >/dev/null 2>&1 \
        || rollback_failed=1
    fi
    if [[ "$storage_owned" -eq 1 ]]; then
      storage_delete_tenant "$PROJECT_UUID" >/dev/null 2>&1 || rollback_failed=1
    fi
    if [[ "$vector_rekeyed" -eq 1 ]]; then
      migration_rekey_vector_physical_tables "_supabase_$project" "$PROJECT_UUID" stub \
        >/dev/null 2>&1 || rollback_failed=1
    fi
    if [[ "$config_changed" -eq 1 ]]; then
      restore_project_config "$project" >/dev/null 2>&1 || rollback_failed=1
    fi
    restore_old_storage_if_needed "$project" >/dev/null 2>&1 || rollback_failed=1
    if [[ "$rollback_failed" -eq 0 ]]; then
      (cd "$project_dir" && docker compose -p "$project" \
        --env-file ../../.env --env-file .env up -d) >/dev/null 2>&1 \
        || rollback_failed=1
    fi
    if [[ "$rollback_failed" -eq 0 ]]; then
      printf 'ROLLED_BACK\n' > "$state_file"
      report project "$project" failed "alteracoes revertidas"
    else
      printf 'ROLLBACK_INCOMPLETE\n' > "$state_file"
      report project "$project" blocked "rollback incompleto; use --resume"
    fi
    exit "$status"
  }
  trap 'rollback_current $?' ERR
  trap 'rollback_current 143' TERM
  trap 'rollback_current 130' INT
  trap 'rollback_current 129' HUP

  say "Migrando projeto $project ($PROJECT_UUID)..."
  (cd "$project_dir" && docker compose -p "$project" \
    --env-file ../../.env --env-file .env down --remove-orphans)

  storage_assert_tenant_absent "$PROJECT_UUID"
  storage_owned=1
  storage_clone_tenant_namespace_from_legacy() {
    local destination
    storage_validate_file_tree "$old_namespace" "namespace Storage antigo" \
      || return 1
    destination="$(storage_assert_namespace_target "$PROJECT_UUID")"
    [[ ! -e "$destination" ]] || return 1
    mkdir -p "$destination"
    (cd "$old_namespace" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
      | (cd "$destination" && tar --xattrs --xattrs-include='*' --acls -xpf -)
  }
  storage_clone_tenant_namespace_from_legacy
  printf 'OBJECTS_COPIED\n' > "$state_file"

  migration_rekey_vector_physical_tables "_supabase_$project" stub "$PROJECT_UUID"
  vector_rekeyed=1
  printf 'VECTORS_REKEYED\n' > "$state_file"

  storage_provision_tenant "$PROJECT_UUID" "$project" "$JWT_SECRET_PROJETO" \
    "$ANON_KEY_PROJETO" "$SERVICE_ROLE_KEY_PROJETO" "$FILE_SIZE_LIMIT" \
    "$ENABLE_IMAGE_TRANSFORMATION" "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
    "$VECTOR_MAX_BUCKETS" "$VECTOR_MAX_INDEXES"
  printf 'TENANT_REGISTERED\n' > "$state_file"

  credential_row="$(storage_create_s3_credentials "$PROJECT_UUID")"
  IFS=$'\t' read -r credential_id access_key secret_key <<<"$credential_row"
  S3_PROTOCOL_CREDENTIAL_ID="$credential_id"
  S3_PROTOCOL_ACCESS_KEY_ID="$access_key"
  S3_PROTOCOL_ACCESS_KEY_SECRET="$secret_key"
  export S3_PROTOCOL_CREDENTIAL_ID S3_PROTOCOL_ACCESS_KEY_ID \
    S3_PROTOCOL_ACCESS_KEY_SECRET
  vector_validate_s3_credentials

  render_project_env "$project" "$env_file" "$env_file" \
    "$credential_id" "$access_key" "$secret_key"
  config_changed=1
  render_project_files "$project"
  printf 'CONFIG_RENDERED\n' > "$state_file"

  (cd "$project_dir" && docker compose -p "$project" \
    --env-file ../../.env --env-file .env up --build -d)
  storage_validate_tenant "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO" \
    "$access_key" "$secret_key" "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED"
  storage_assert_project_gateway "$PROJECT_UUID" "$project" "$SERVICE_ROLE_KEY_PROJETO"
  vector_sync_project_wrappers "$project"
  printf 'VALIDATED\n' > "$state_file"

  (cd "$project_dir" && tar --xattrs --xattrs-include='*' --acls \
    -czf "$RUN_DIR/old-storage/$project.tar.gz" storage)
  old_storage_parent="$(cd "$(dirname "$old_storage")" && pwd -P)"
  [[ "$old_storage_parent" == "$(cd "$project_dir" && pwd -P)" ]] || return 1
  rm -rf -- "$old_storage"

  trap - ERR TERM INT HUP
  printf 'COMPLETE\n' > "$state_file"
  report project "$project" migrated \
    "tenant=$PROJECT_UUID credential=${credential_id:0:8} objects=isolated"
  say "Projeto $project migrado e validado."
)

drop_temp_database() {
  local database="$1"
  docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database' AND pid <> pg_backend_pid(); DROP DATABASE IF EXISTS \"$database\";" \
    >/dev/null
}

convert_backup() (
  set -Eeuo pipefail
  local backup_dir="$1" manifest="$1/manifest.json" format tenant backup_id
  local state_key state_file stage extract old_saved temp_db
  [[ -f "$manifest" ]] || return 0
  format="$(jq -r '.format // empty' "$manifest")"
  [[ "$format" != "2" ]] || return 0
  [[ "$format" == "1" ]] || { report backup "$backup_dir" failed "formato desconhecido"; return 1; }
  tenant="$(jq -r '.project_uuid // empty' "$manifest" | tr '[:upper:]' '[:lower:]')"
  storage_validate_tenant_id "$tenant" || return 1
  backup_id="$(basename "$backup_dir")"
  [[ "$backup_id" =~ ^[0-9a-f-]{36}$ ]] || return 1
  [[ "$(basename "$(dirname "$backup_dir")")" == "$tenant" ]] || return 1
  [[ -s "$backup_dir/db.sql.gz" && -s "$backup_dir/storage.tar.gz" ]] || return 1
  storage_validate_namespace_archive "$backup_dir/storage.tar.gz" || return 1

  state_key="backup-${tenant}-${backup_id}"
  state_file="$RUN_DIR/state/$state_key"
  [[ "$(head -n1 "$state_file" 2>/dev/null || true)" != "COMPLETE" ]] || return 0
  stage="${backup_dir}.shared-storage-stage.$$"
  extract="$(mktemp -d /tmp/storage-backup-migration.XXXXXX)"
  old_saved="$RUN_DIR/old-backups/$tenant/$backup_id"
  temp_db="_storage_migrate_${backup_id//-/}"
  temp_db="${temp_db:0:55}"
  mkdir -p "$stage" "$(dirname "$old_saved")"
  cp -a "$backup_dir/." "$stage/"
  trap 'drop_temp_database "$temp_db" >/dev/null 2>&1 || true; rm -rf -- "$stage" "$extract"' EXIT

  tar -xzf "$backup_dir/storage.tar.gz" -C "$extract"
  [[ -d "$extract/stub/stub" && ! -L "$extract/stub" ]] \
    || { report backup "$backup_id" failed "layout stub/stub ausente"; return 1; }
  (cd "$extract/stub/stub" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
    | gzip > "$stage/storage.tar.gz"
  storage_validate_namespace_archive "$stage/storage.tar.gz"

  drop_temp_database "$temp_db"
  docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d postgres -c "CREATE DATABASE \"$temp_db\";" >/dev/null
  gunzip -c "$backup_dir/db.sql.gz" \
    | docker exec -i supabase-db psql -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" -d "$temp_db" >/dev/null
  migration_rekey_vector_physical_tables "$temp_db" stub "$tenant"
  docker exec supabase-db pg_dump -U "$POSTGRES_USER" -d "$temp_db" \
    --exclude-schema=realtime | gzip > "$stage/db.sql.gz"
  drop_temp_database "$temp_db"

  jq --arg tenant "$tenant" '.format = 2
      | .project_uuid = $tenant
      | .storage_tenant_id = $tenant
      | .storage_layout = "tenant-namespace"' \
    "$backup_dir/manifest.json" > "$stage/manifest.json"
  [[ "$(jq -r '.storage_tenant_id' "$stage/manifest.json" | tr '[:upper:]' '[:lower:]')" == "$tenant" ]] \
    || return 1

  mv "$backup_dir" "$old_saved"
  mv "$stage" "$backup_dir"
  printf 'COMPLETE\n' > "$state_file"
  report backup "$backup_id" converted "tenant=$tenant format=2"
  rm -rf -- "$extract"
  trap - EXIT
)

say "Relatorio interno: $RUN_DIR"
set -a
# shellcheck disable=SC1090
source "$SERVER_ROOT/.env"
set +a
docker inspect supabase-db >/dev/null 2>&1 || die "supabase-db nao esta rodando"
quiesce_lifecycle
MIGRATION_MUTATIONS_STARTED=1
ensure_global_storage_config
storage_require_canonical_global_config \
  || die "Configuracao global do Storage nao corresponde ao contrato suportado"
ensure_storage_secrets
create_registry_database
start_global_storage
report infrastructure global ready "registry e containers compartilhados saudaveis"

project_count=0
shopt -s nullglob
for project_dir in "$SERVER_ROOT"/projects/*/; do
  project="$(basename "$project_dir")"
  [[ "$project" == ".gitkeep" ]] && continue
  migrate_project "$project"
  project_count=$((project_count + 1))
done

backup_count=0
for saved_backup in "$RUN_DIR"/old-backups/*/*; do
  [[ -d "$saved_backup" ]] || continue
  saved_tenant="$(basename "$(dirname "$saved_backup")")"
  saved_id="$(basename "$saved_backup")"
  restore_destination="$SERVER_ROOT/backups/$saved_tenant/$saved_id"
  if [[ ! -e "$restore_destination" ]]; then
    mkdir -p "$(dirname "$restore_destination")"
    mv "$saved_backup" "$restore_destination"
    report backup "$saved_id" recovered "original restaurado apos interrupcao"
  fi
done
for orphan_stage in "$SERVER_ROOT"/backups/*/*.shared-storage-stage.*; do
  [[ -d "$orphan_stage" && ! -L "$orphan_stage" ]] || continue
  orphan_parent="$(cd "$(dirname "$orphan_stage")" && pwd -P)"
  [[ "$(dirname "$orphan_parent")" == "$(cd "$SERVER_ROOT/backups" && pwd -P)" ]] \
    || die "staging de backup fora da raiz esperada"
  rm -rf -- "$orphan_stage"
done
for backup_dir in "$SERVER_ROOT"/backups/*/*/; do
  convert_backup "${backup_dir%/}"
  backup_count=$((backup_count + 1))
done

resume_lifecycle_after_success
printf 'COMPLETE\n' > "$RUN_DIR/COMPLETE"
report migration all complete "projects=$project_count backups_scanned=$backup_count"
say "Migracao concluida: $project_count projeto(s); $backup_count backup(s) verificado(s)."
say "Consulte $SUMMARY. Os artefatos anteriores permanecem apenas no relatorio interno para rollback operacional."
