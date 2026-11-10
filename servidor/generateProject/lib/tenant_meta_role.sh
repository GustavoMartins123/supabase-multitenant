#!/usr/bin/env bash
# Privileged canonical provisioning; database/UUID must be explicit.
provision_tenant_meta_role() {
  local db="$1" tenant_uuid="${2,,}" meta_role meta_password storage_policy_key
  [[ "$db" =~ ^_supabase_[a-z_][a-z0-9_]{2,39}$ ]] || return 1
  [[ "$tenant_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || return 1
  [[ "${META_ADMIN_DB_PASSWORD:-}" =~ ^[A-Za-z0-9_-]{32,128}$ ]] || return 1
  meta_role="tenant_meta_${tenant_uuid//-/}"
  meta_password="$(printf 'tenant-meta-v1:%s' "$tenant_uuid" | openssl dgst -sha256 -hmac "$META_ADMIN_DB_PASSWORD" -r | cut -d' ' -f1)" || return 1
  [[ "$meta_password" =~ ^[0-9a-f]{64}$ ]] || return 1
  storage_policy_key="$(printf 'studio-storage-policies-v1:%s' "$tenant_uuid" | openssl dgst -sha256 -hmac "$META_ADMIN_DB_PASSWORD" -r | cut -d' ' -f1)" || return 1
  [[ "$storage_policy_key" =~ ^[0-9a-f]{64}$ ]] || return 1
  {
    printf "SELECT set_config('platform.storage_policy_key','%s',false);\n" "$storage_policy_key"
    cat "$PROJECT_ROOT/api-internal/app/tenant_meta_role.sql"
    printf "\nSELECT to_regclass('storage.objects') IS NOT NULL AS storage_policies_available \\gset\n\\if :storage_policies_available\n"
    cat "$PROJECT_ROOT/api-internal/app/studio_storage_policies.sql"
    printf '\n\\endif\n'
  } | docker exec -i supabase-db psql -q -v ON_ERROR_STOP=1 -1 -U supabase_admin -d "$db" \
    -v "meta_role=$meta_role" -v "meta_password=$meta_password" \
    >/dev/null
}
