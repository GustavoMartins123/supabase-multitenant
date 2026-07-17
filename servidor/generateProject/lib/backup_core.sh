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
  for service in nginx storage imgproxy rest auth meta; do
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
  for service in meta auth rest imgproxy storage nginx; do
    name="supabase-$service-$project"
    if [[ -n "$only" ]] && ! grep -qx "$name" <<< "$only"; then
      continue
    fi
    docker inspect "$name" >/dev/null 2>&1 || continue
    docker start "$name" >/dev/null || return 1
  done
}

backup_capture() {
  local project="$1" project_dir="$2" dest_dir="$3"
  local db="_supabase_$project"
  local tmp_dir="${dest_dir}.tmp"
  local realtime_tables pg_version created_at

  rm -rf "$tmp_dir"
  mkdir -p "$tmp_dir"

  backup_progress database_started
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" \
    --exclude-schema=realtime | gzip > "$tmp_dir/db.sql.gz"
  backup_progress database_dumped
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" \
    --schema=realtime --schema-only 2>/dev/null | gzip > "$tmp_dir/realtime-structure.sql.gz" || true
  docker exec supabase-db pg_dump -U supabase_admin -d "$db" --data-only \
    -t 'realtime.schema_migrations' 2>/dev/null | gzip > "$tmp_dir/realtime-migrations.sql.gz" || true
  backup_progress realtime_dumped

  realtime_tables=$(docker exec supabase-db psql -U supabase_admin -d "$db" -tAc \
    "SELECT string_agg(format('%I.%I', schemaname, tablename), ',') FROM pg_publication_tables WHERE pubname = 'supabase_realtime';" \
    2>/dev/null || true)
  pg_version=$(docker exec supabase-db psql -U supabase_admin -d postgres -tAc "SHOW server_version;" | tr -d '[:space:]')
  created_at=$(date +%s)

  backup_progress storage_started
  if [[ -d "$project_dir/storage" ]]; then
    (cd "$project_dir/storage" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
      | gzip > "$tmp_dir/storage.tar.gz"
  else
    mkdir -p "$tmp_dir/empty-storage/stub/stub"
    (cd "$tmp_dir/empty-storage" && tar -cpf - .) | gzip > "$tmp_dir/storage.tar.gz"
    rm -rf "$tmp_dir/empty-storage"
  fi
  backup_progress storage_archived

  jq -n \
    --arg uuid "$PROJECT_UUID" \
    --arg ref "$project" \
    --arg pg "$pg_version" \
    --arg tables "${realtime_tables:-}" \
    --argjson created "$created_at" \
    '{format: 1, project_uuid: $uuid, project_ref: $ref, pg_version: $pg, realtime_tables: $tables, created_at: $created}' \
    > "$tmp_dir/manifest.json"

  mv "$tmp_dir" "$dest_dir"
  backup_progress backup_published
}
