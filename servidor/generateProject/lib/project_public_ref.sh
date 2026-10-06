#!/usr/bin/env bash

project_public_ref_validate() {
  local LC_ALL=C
  [[ "$1" =~ ^[a-z]{20}$ ]] || {
    echo 'PROJECT_PUBLIC_REF deve conter exatamente 20 letras minusculas' >&2
    return 1
  }
}

project_public_ref_read() {
  local file="$1" count canonical value
  [[ -f "$file" && ! -L "$file" ]] || return 1
  count="$(grep -Ec '^[[:space:]]*(export[[:space:]]+)?PROJECT_PUBLIC_REF[[:space:]]*=' "$file" || true)"
  canonical="$(grep -c '^PROJECT_PUBLIC_REF=' "$file" || true)"
  [[ "$count" == 1 && "$canonical" == 1 ]] || {
    echo 'PROJECT_PUBLIC_REF deve ter uma unica atribuicao canonica' >&2
    return 1
  }
  value="$(sed -n 's/^PROJECT_PUBLIC_REF=//p' "$file")"
  project_public_ref_validate "$value" || return 1
  printf '%s' "$value"
}

project_public_ref_assert() {
  local project="$1" tenant_uuid="$2" public_ref="$3" persisted
  [[ "$project" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || return 1
  [[ "$tenant_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || return 1
  project_public_ref_validate "$public_ref" || return 1
  [[ -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]] || return 1
  persisted="$(docker exec supabase-db psql -X -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc \
    "SELECT public_ref FROM projects WHERE name = '$project' AND tenant_uuid = '$tenant_uuid';")" || return 1
  [[ "$persisted" == "$public_ref" ]] || {
    echo 'PROJECT_PUBLIC_REF diverge da identidade do control plane' >&2
    return 1
  }
}
