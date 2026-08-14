#!/usr/bin/env bash

backup_progress() {
  printf 'HOST_AGENT_PROGRESS=backup:%s\n' "$1"
}

backup_generate_jwt() {
  local payload="$1" secret="$2" header='{"alg":"HS256","typ":"JWT"}'
  local header_b64 payload_b64 signature
  header_b64=$(printf '%s' "$header" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  payload_b64=$(printf '%s' "$payload" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  signature=$(printf '%s' "$header_b64.$payload_b64" \
    | openssl dgst -binary -sha256 -hmac "$secret" \
    | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  printf '%s' "$header_b64.$payload_b64.$signature"
}

backup_http_code() {
  local container="$1" method="$2" path="$3" token="$4" payload="${5:-}"
  local args=(exec "$container" curl -sS -o /dev/null -w '%{http_code}'
    -X "$method" "http://localhost:4000$path" -H "Authorization: Bearer $token")
  [[ -z "$payload" ]] || args+=(-H 'Content-Type: application/json' -d "$payload")
  docker "${args[@]}"
}

backup_accepted_code() {
  local code="$1"; shift
  local accepted
  for accepted in "$@"; do [[ "$code" == "$accepted" ]] && return 0; done
  return 1
}

backup_stop_project_containers() {
  local project="$1"
  local service name state
  for service in nginx rest auth meta; do
    name="supabase-$service-$project"
    state="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null || true)"
    if [[ "$state" == "true" ]]; then
      docker stop "$name" >/dev/null
      echo "$name"
    fi
  done
}

backup_start_project_containers() {
  local project="$1" only="${2:-}"
  local service name
  for service in meta auth rest nginx; do
    name="supabase-$service-$project"
    if [[ -n "$only" ]] && ! grep -qx "$name" <<< "$only"; then
      continue
    fi
    docker inspect "$name" >/dev/null 2>&1 || continue
    docker start "$name" >/dev/null || return 1
  done
}

backup_capture() {
  local project="$1" dest_dir="$2"
  local db="_supabase_$project"
  local tmp_dir="${dest_dir}.tmp"
  local realtime_tables pg_version created_at storage_namespace

  rm -rf "$tmp_dir"
  mkdir -p "$tmp_dir"

  backup_progress database_started
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" \
    --exclude-schema=realtime | gzip > "$tmp_dir/db.sql.gz"
  backup_progress database_dumped
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" \
    --schema=realtime --schema-only | gzip > "$tmp_dir/realtime-structure.sql.gz"
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" --data-only \
    -t 'realtime.schema_migrations' | gzip > "$tmp_dir/realtime-migrations.sql.gz"
  backup_progress realtime_dumped

  realtime_tables=$(docker exec supabase-db psql -U supabase_admin -d "$db" -tAc \
    "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_publication_tables WHERE pubname = 'supabase_realtime';")
  pg_version=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SHOW server_version;" | tr -d '[:space:]')
  created_at=$(date +%s)

  backup_progress storage_started
  storage_namespace="$(storage_assert_namespace_target "$PROJECT_UUID")"
  [[ -d "$storage_namespace" ]] \
    || { echo "Namespace Storage do tenant ausente" >&2; return 1; }
  storage_validate_file_tree "$storage_namespace" "namespace do backup" \
    || return 1
  (cd "$storage_namespace" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
    | gzip > "$tmp_dir/storage.tar.gz"
  storage_validate_namespace_archive "$tmp_dir/storage.tar.gz"
  backup_progress storage_archived

  jq -n \
    --arg uuid "$PROJECT_UUID" \
    --arg ref "$project" \
    --arg pg "$pg_version" \
    --arg tables "${realtime_tables:-}" \
    --argjson created "$created_at" \
    '{format: 2, project_uuid: $uuid, storage_tenant_id: $uuid, storage_layout: "tenant-namespace", project_ref: $ref, pg_version: $pg, realtime_tables: $tables, created_at: $created}' \
    > "$tmp_dir/manifest.json"

  mv "$tmp_dir" "$dest_dir"
  backup_progress backup_published
}
