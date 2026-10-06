#!/usr/bin/env bash

# Shared Storage Vectors lifecycle helpers.
# This file is sourced by generate_project.sh, duplicate_project.sh,
# rename_project.sh and operations/setup_vector_bucket_wrapper.sh.

VECTOR_LIFECYCLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VECTOR_SCRIPTS_DIR="$(dirname "$VECTOR_LIFECYCLE_DIR")"

# shellcheck disable=SC1091
source "$VECTOR_LIFECYCLE_DIR/storage_multitenant.sh"

vector_fail() {
  echo "❌ $*" >&2
  return 1
}

vector_validate_s3_credentials() {
  [[ "${S3_PROTOCOL_CREDENTIAL_ID:-}" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || { vector_fail "S3_PROTOCOL_CREDENTIAL_ID ausente ou invalido"; return 1; }
  [[ "${S3_PROTOCOL_ACCESS_KEY_ID:-}" =~ ^[0-9a-fA-F]{32}$ ]] \
    || { vector_fail "S3_PROTOCOL_ACCESS_KEY_ID ausente ou invalido"; return 1; }
  [[ "${S3_PROTOCOL_ACCESS_KEY_SECRET:-}" =~ ^[0-9a-fA-F]{64}$ ]] \
    || { vector_fail "S3_PROTOCOL_ACCESS_KEY_SECRET ausente ou invalido"; return 1; }
}

vector_validate_database() {
  local database="$1"
  [[ -n "${POSTGRES_USER:-}" ]] || { vector_fail "POSTGRES_USER ausente"; return 1; }
  docker inspect supabase-db >/dev/null 2>&1 \
    || { vector_fail "Container supabase-db nao encontrado"; return 1; }

  docker exec -i supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$database" <<'SQL' || return 1
DO $vector_check$
DECLARE
  installed_version text;
  installed_schema text;
BEGIN
  SELECT e.extversion, n.nspname
    INTO installed_version, installed_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
   WHERE e.extname = 'vector';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION 'database was created without pgvector';
  END IF;
  IF installed_schema <> 'public' THEN
    RAISE EXCEPTION 'pgvector must be installed in public, found %', installed_schema;
  END IF;
  IF string_to_array(installed_version, '.')::int[] < ARRAY[0, 7, 0]::int[] THEN
    RAISE EXCEPTION 'pgvector >= 0.7.0 required, found %', installed_version;
  END IF;
END
$vector_check$;
SQL

  docker exec -i supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$database" <<'SQL' || return 1
DO $storage_admin_search_path_check$
BEGIN
  SET LOCAL search_path = storage, public;
  IF to_regtype('halfvec') IS NULL THEN
    RAISE EXCEPTION
      'halfvec nao resolve sob search_path=storage,public; supabase_storage_admin nao vai conseguir criar Vector Buckets';
  END IF;
END
$storage_admin_search_path_check$;
SQL
}

# A duplicacao de banco pode carregar FDWs, endpoints e segredos Vault do projeto
# original. Eles nunca devem sobreviver no clone: o clone recebe outro par SigV4
# e recria apenas os wrappers correspondentes aos buckets que realmente existem.
vector_strip_copied_wrappers() {
  local database="$1"
  [[ -n "${POSTGRES_USER:-}" ]] || { vector_fail "POSTGRES_USER ausente"; return 1; }

  docker exec -i supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$database" <<'SQL' || return 1
DO $drop_vector_wrappers$
DECLARE
  wrapper_record record;
  server_record record;
BEGIN
  FOR wrapper_record IN
    SELECT w.fdwname
      FROM pg_foreign_data_wrapper w
      JOIN pg_proc p ON p.oid = w.fdwhandler
     WHERE p.proname = 's3_vectors_fdw_handler'
  LOOP
    FOR server_record IN
      SELECT s.srvname
        FROM pg_foreign_server s
        JOIN pg_foreign_data_wrapper w ON w.oid = s.srvfdw
       WHERE w.fdwname = wrapper_record.fdwname
    LOOP
      EXECUTE format('DROP SERVER IF EXISTS %I CASCADE', server_record.srvname);
    END LOOP;
    EXECUTE format('DROP FOREIGN DATA WRAPPER IF EXISTS %I CASCADE', wrapper_record.fdwname);
  END LOOP;
END
$drop_vector_wrappers$;

DO $drop_vector_secrets$
BEGIN
  IF to_regclass('vault.secrets') IS NOT NULL THEN
    DELETE FROM vault.secrets
     WHERE name LIKE '%\_fdw\_vault\_access\_key\_id' ESCAPE '\'
        OR name LIKE '%\_fdw\_vault\_secret\_access\_key' ESCAPE '\';
  END IF;
END
$drop_vector_secrets$;
SQL
}

# O nome fisico do pgvector inclui o tenant imutavel antes do hash. Um clone
# with-data precisa renomear essas tabelas para seu novo UUID; metadata logica
# nao e alterada. A operacao e transacional e falha diante de estado ambiguo.
vector_rekey_physical_tables() {
  local database="$1" source_tenant="$2" destination_tenant="$3"
  [[ -n "${POSTGRES_USER:-}" ]] || { vector_fail "POSTGRES_USER ausente"; return 1; }
  storage_validate_tenant_id "$source_tenant" \
    || { vector_fail "tenant de origem invalido para rekey"; return 1; }
  storage_validate_tenant_id "$destination_tenant" \
    || { vector_fail "tenant de destino invalido para rekey"; return 1; }
  [[ "$source_tenant" != "$destination_tenant" ]] || return 0
  command -v python3 >/dev/null 2>&1 || { vector_fail "python3 nao esta instalado"; return 1; }

  docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "$database" -c \
    "COPY (SELECT bucket_id, name FROM storage.vector_indexes ORDER BY bucket_id, name) TO STDOUT WITH (FORMAT csv)" \
    | python3 "$STORAGE_LIFECYCLE_DIR/vector_rekey_sql.py" "$source_tenant" "$destination_tenant" \
    | docker exec -i supabase-db psql -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" -d "$database"
}

# shellcheck disable=SC2120
vector_wait_storage() {
  local attempts="${1:-60}"
  storage_wait_global "$attempts"
}

vector_list_buckets() {
  local tenant_id="$1" service_key="$2"
  storage_list_vector_buckets "$tenant_id" "$service_key"
}

vector_validate_storage_api() {
  local tenant_id="$1" service_key="$2" access_key="$3" secret_key="$4"
  local s3_enabled="$5" vectors_enabled="$6"
  # shellcheck disable=SC2119
  vector_wait_storage || return 1
  storage_validate_tenant "$tenant_id" "$service_key" "$access_key" "$secret_key" \
    "$s3_enabled" "$vectors_enabled"
}

vector_sync_project_wrappers() {
  local project_id="$1"
  local buckets
  local operation="$VECTOR_SCRIPTS_DIR/operations/setup_vector_bucket_wrapper.sh"

  [[ -f "$operation" ]] \
    || { vector_fail "Operacao de wrapper ausente: $operation"; return 1; }

  storage_validate_bool VECTOR_BUCKETS_ENABLED "${VECTOR_BUCKETS_ENABLED:-}" || return 1
  if [[ "$VECTOR_BUCKETS_ENABLED" == "false" ]]; then
    echo "Storage Vectors desabilitado para $project_id"
    return 0
  fi

  storage_validate_tenant_id "${PROJECT_UUID:-}" || return 1
  [[ -n "${SERVICE_ROLE_KEY_PROJETO:-}" ]] \
    || { vector_fail "SERVICE_ROLE_KEY_PROJETO ausente"; return 1; }
  buckets="$(vector_list_buckets "$PROJECT_UUID" "$SERVICE_ROLE_KEY_PROJETO")" || return 1
  if [[ -z "$buckets" ]]; then
    echo "ℹ️  Nenhum vector bucket para sincronizar em $project_id"
    return 0
  fi

  while IFS= read -r bucket_name; do
    [[ -n "$bucket_name" ]] || continue
    bash "$operation" "$project_id" "$bucket_name" || return 1
  done <<< "$buckets"
}
