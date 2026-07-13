#!/usr/bin/env bash

# Shared Storage Vectors lifecycle helpers.
# This file is sourced by generate_project.sh, duplicate_project.sh,
# rename_project.sh and operations/setup_vector_bucket_wrapper.sh.

VECTOR_LIFECYCLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VECTOR_SCRIPTS_DIR="$(dirname "$VECTOR_LIFECYCLE_DIR")"
VECTOR_SERVER_ROOT="$(dirname "$VECTOR_SCRIPTS_DIR")"

vector_fail() {
  echo "❌ $*" >&2
  return 1
}

vector_validate_s3_credentials() {
  [[ "${S3_PROTOCOL_ACCESS_KEY_ID:-}" =~ ^[0-9a-fA-F]{32}$ ]] \
    || vector_fail "S3_PROTOCOL_ACCESS_KEY_ID ausente ou invalido"
  [[ "${S3_PROTOCOL_ACCESS_KEY_SECRET:-}" =~ ^[0-9a-fA-F]{64}$ ]] \
    || vector_fail "S3_PROTOCOL_ACCESS_KEY_SECRET ausente ou invalido"
}

vector_ensure_s3_credentials() {
  command -v openssl >/dev/null 2>&1 \
    || vector_fail "openssl nao esta instalado"

  if [[ -z "${S3_PROTOCOL_ACCESS_KEY_ID:-}" ]]; then
    S3_PROTOCOL_ACCESS_KEY_ID="$(openssl rand -hex 16 | tr -d '\n\r')"
  fi
  if [[ -z "${S3_PROTOCOL_ACCESS_KEY_SECRET:-}" ]]; then
    S3_PROTOCOL_ACCESS_KEY_SECRET="$(openssl rand -hex 32 | tr -d '\n\r')"
  fi

  vector_validate_s3_credentials
  export S3_PROTOCOL_ACCESS_KEY_ID S3_PROTOCOL_ACCESS_KEY_SECRET
}

vector_validate_database() {
  local database="$1"
  docker inspect supabase-db >/dev/null 2>&1 \
    || vector_fail "Container supabase-db nao encontrado"

  docker exec -i supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-supabase_admin}" \
    -d "$database" <<'SQL'
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
}

# A duplicacao de banco pode carregar FDWs, endpoints e segredos Vault do projeto
# original. Eles nunca devem sobreviver no clone: o clone recebe outro par SigV4
# e recria apenas os wrappers correspondentes aos buckets que realmente existem.
vector_strip_copied_wrappers() {
  local database="$1"

  docker exec -i supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "${POSTGRES_USER:-supabase_admin}" \
    -d "$database" <<'SQL'
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

vector_list_buckets() {
  local project_id="$1"
  local storage_container="supabase-storage-$project_id"

  docker inspect "$storage_container" >/dev/null 2>&1 \
    || vector_fail "Container $storage_container nao encontrado"

  docker exec "$storage_container" node -e '
const key = process.env.SERVICE_KEY;
if (!key) {
  console.error("SERVICE_KEY ausente no Storage API");
  process.exit(2);
}
fetch("http://127.0.0.1:5000/vector/ListVectorBuckets", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${key}`,
    "apikey": key,
  },
  body: "{}",
}).then(async (response) => {
  const text = await response.text();
  if (!response.ok) {
    console.error(`ListVectorBuckets HTTP ${response.status}: ${text}`);
    process.exit(3);
  }
  const payload = JSON.parse(text);
  if (!Array.isArray(payload.vectorBuckets)) {
    console.error("Resposta sem vectorBuckets");
    process.exit(4);
  }
  for (const bucket of payload.vectorBuckets) {
    if (typeof bucket?.vectorBucketName !== "string") process.exit(5);
    console.log(bucket.vectorBucketName);
  }
}).catch((error) => {
  console.error(error);
  process.exit(6);
});
'
}

vector_sync_project_wrappers() {
  local project_id="$1"
  local buckets
  local operation="$VECTOR_SCRIPTS_DIR/operations/setup_vector_bucket_wrapper.sh"

  [[ -x "$operation" ]] \
    || vector_fail "Operacao de wrapper ausente ou sem permissao: $operation"

  buckets="$(vector_list_buckets "$project_id")"
  if [[ -z "$buckets" ]]; then
    echo "ℹ️  Nenhum vector bucket para sincronizar em $project_id"
    return 0
  fi

  while IFS= read -r bucket_name; do
    [[ -n "$bucket_name" ]] || continue
    "$operation" "$project_id" "$bucket_name"
  done <<< "$buckets"
}
