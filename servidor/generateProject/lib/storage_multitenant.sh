#!/usr/bin/env bash

# Lifecycle do Storage API compartilhado. Todas as mutacoes de tenant passam
# pela API administrativa oficial; nenhuma tabela do registry e editada aqui.

STORAGE_LIFECYCLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORAGE_SERVER_ROOT="$(dirname "$(dirname "$STORAGE_LIFECYCLE_DIR")")"
STORAGE_GLOBAL_CONTAINER="supabase-storage-global"
STORAGE_DATA_PLANE_CONTAINER="shared-storage-data-plane"
STORAGE_OBJECT_ROOT="$STORAGE_SERVER_ROOT/volumes/storage/objects"
STORAGE_SUPPORTED_IMAGE="supabase/storage-api:v1.61.12"
STORAGE_SUPPORTED_DATA_PLANE_IMAGE="nginxinc/nginx-unprivileged:1.31.2-alpine3.23-slim"
STORAGE_SUPPORTED_TENANT_DB_USER="supabase_storage_admin"
STORAGE_SUPPORTED_TENANT_HOST_REGEXP='^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})[.]storage[.]internal$'

storage_fail() {
  echo "ERRO Storage: $*" >&2
  return 1
}

storage_require_command() {
  command -v "$1" >/dev/null 2>&1 || storage_fail "$1 nao esta instalado"
}

storage_validate_tenant_id() {
  [[ "$1" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || storage_fail "tenant id deve ser um UUID canonico em minusculas"
}

storage_validate_project_ref() {
  [[ "$1" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
    || storage_fail "project_ref invalido para Storage: $1"
}

storage_validate_bool() {
  [[ "$2" == "true" || "$2" == "false" ]] \
    || storage_fail "$1 deve ser true ou false"
}

storage_validate_positive_integer() {
  [[ "$2" =~ ^[1-9][0-9]*$ ]] || storage_fail "$1 deve ser um inteiro positivo"
}

storage_percent_encode() {
  storage_require_command jq || return 1
  printf '%s' "$1" | jq -sRr @uri
}

storage_global_env_value() {
  local key="$1" file="$STORAGE_SERVER_ROOT/.env" count value
  [[ -f "$file" ]] || {
    storage_fail "arquivo global $file ausente"
    return 1
  }
  count="$(grep -c "^${key}=" "$file" || true)"
  [[ "$count" == "1" ]] || {
    storage_fail "$key deve ter exatamente uma atribuicao canonica em $file"
    return 1
  }
  value="$(sed -n "s/^${key}=//p" "$file")"
  [[ -n "$value" && "$value" != *$'\r'* && "$value" == "${value# }" \
    && "$value" == "${value% }" ]] || {
    storage_fail "$key possui valor global invalido"
    return 1
  }
  printf '%s' "$value"
}

# O lifecycle fisico abaixo opera exatamente sobre o contrato file oficial:
# /var/lib/storage/<bucket interno>/<tenant>/<bucket>/<objeto>. Qualquer outro
# backend/layout deve falhar antes de uma mutacao, nunca ser tratado como se
# fosse equivalente.
storage_require_canonical_global_config() {
  local image proxy_image backend backend_path internal_bucket tenant_db_user tenant_host_regexp
  image="$(storage_global_env_value STORAGE_IMAGE)" || return 1
  proxy_image="$(storage_global_env_value STORAGE_DATA_PLANE_PROXY_IMAGE)" \
    || return 1
  backend="$(storage_global_env_value STORAGE_BACKEND)" || return 1
  backend_path="$(storage_global_env_value STORAGE_FILE_BACKEND_PATH)" || return 1
  internal_bucket="$(storage_global_env_value STORAGE_INTERNAL_BUCKET)" || return 1
  tenant_db_user="$(storage_global_env_value STORAGE_TENANT_DB_USER)" || return 1
  tenant_host_regexp="$(storage_global_env_value STORAGE_TENANT_HOST_REGEXP)" || return 1
  [[ "$image" == "$STORAGE_SUPPORTED_IMAGE" ]] || {
    storage_fail "STORAGE_IMAGE deve ser $STORAGE_SUPPORTED_IMAGE"
    return 1
  }
  [[ "$proxy_image" == "$STORAGE_SUPPORTED_DATA_PLANE_IMAGE" ]] || {
    storage_fail "STORAGE_DATA_PLANE_PROXY_IMAGE deve ser $STORAGE_SUPPORTED_DATA_PLANE_IMAGE"
    return 1
  }
  [[ "$backend" == "file" ]] || {
    storage_fail "STORAGE_BACKEND deve ser file para o lifecycle tenant-aware"
    return 1
  }
  [[ "$backend_path" == "/var/lib/storage" ]] || {
    storage_fail "STORAGE_FILE_BACKEND_PATH deve ser /var/lib/storage"
    return 1
  }
  [[ "$internal_bucket" == "objects" ]] || {
    storage_fail "STORAGE_INTERNAL_BUCKET deve ser objects"
    return 1
  }
  [[ "$tenant_db_user" == "$STORAGE_SUPPORTED_TENANT_DB_USER" ]] || {
    storage_fail "STORAGE_TENANT_DB_USER deve ser $STORAGE_SUPPORTED_TENANT_DB_USER"
    return 1
  }
  [[ "$tenant_host_regexp" == "$STORAGE_SUPPORTED_TENANT_HOST_REGEXP" ]] || {
    storage_fail "STORAGE_TENANT_HOST_REGEXP diverge do contrato UUID fail-closed"
    return 1
  }
}

storage_assert_global_container_contract() {
  local running_image attached_networks attached_count
  storage_require_canonical_global_config || return 1
  running_image="$(docker inspect -f '{{.Config.Image}}' \
    "$STORAGE_GLOBAL_CONTAINER" 2>/dev/null)" || {
    storage_fail "container $STORAGE_GLOBAL_CONTAINER nao encontrado"
    return 1
  }
  [[ "$running_image" == "$STORAGE_SUPPORTED_IMAGE" ]] || {
    storage_fail "container Storage executa imagem nao suportada: $running_image"
    return 1
  }
  attached_networks="$(docker inspect -f \
    '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    "$STORAGE_GLOBAL_CONTAINER")" || return 1
  attached_count="$(grep -c '[^[:space:]]' <<<"$attached_networks" || true)"
  [[ "$attached_count" == "2" ]] || {
    storage_fail "Storage global deve possuir exatamente duas redes internas"
    return 1
  }
  grep -Fxq 'supabase-storage-control' <<<"$attached_networks" || {
    storage_fail "Storage global nao esta conectado a rede interna de controle"
    return 1
  }
  grep -Fxq 'supabase-storage-data-plane' <<<"$attached_networks" || {
    storage_fail "Storage global nao esta conectado a rede interna da data plane"
    return 1
  }
  ! grep -Fxq 'rede-supabase' <<<"$attached_networks" || {
    storage_fail "Storage global nao pode estar conectado diretamente a rede dos projetos"
    return 1
  }
  ! grep -Fxq 'supabase-storage-gateways' <<<"$attached_networks" || {
    storage_fail "Storage global nao pode estar conectado diretamente aos gateways de projeto"
    return 1
  }
}

storage_assert_data_plane_container_contract() {
  local running_image attached_networks attached_count
  storage_require_canonical_global_config || return 1
  running_image="$(docker inspect -f '{{.Config.Image}}' \
    "$STORAGE_DATA_PLANE_CONTAINER" 2>/dev/null)" || {
    storage_fail "container $STORAGE_DATA_PLANE_CONTAINER nao encontrado"
    return 1
  }
  [[ "$running_image" == "$STORAGE_SUPPORTED_DATA_PLANE_IMAGE" ]] || {
    storage_fail "proxy da data plane executa imagem nao suportada: $running_image"
    return 1
  }
  attached_networks="$(docker inspect -f \
    '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    "$STORAGE_DATA_PLANE_CONTAINER")" || return 1
  attached_count="$(grep -c '[^[:space:]]' <<<"$attached_networks" || true)"
  [[ "$attached_count" == "2" ]] || {
    storage_fail "proxy da data plane deve possuir exatamente duas redes internas"
    return 1
  }
  grep -Fxq 'supabase-storage-gateways' <<<"$attached_networks" || {
    storage_fail "proxy da data plane nao esta conectado a rede exclusiva dos gateways"
    return 1
  }
  grep -Fxq 'supabase-storage-data-plane' <<<"$attached_networks" || {
    storage_fail "proxy da data plane nao esta conectado a rede interna do Storage"
    return 1
  }
  ! grep -Fxq 'rede-supabase' <<<"$attached_networks" || {
    storage_fail "proxy da data plane nao pode estar conectado a rede geral dos projetos"
    return 1
  }
  ! grep -Fxq 'supabase-storage-control' <<<"$attached_networks" || {
    storage_fail "proxy da data plane nao pode estar conectado a rede administrativa"
    return 1
  }
}

storage_assert_project_gateway_container_contract() {
  local project_ref="$1" container attached_networks attached_count
  storage_validate_project_ref "$project_ref" || return 1
  container="supabase-nginx-$project_ref"
  attached_networks="$(docker inspect -f \
    '{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}' \
    "$container" 2>/dev/null)" || {
    storage_fail "container $container nao encontrado"
    return 1
  }
  attached_count="$(grep -c '[^[:space:]]' <<<"$attached_networks" || true)"
  [[ "$attached_count" == "2" ]] || {
    storage_fail "$container deve possuir somente as redes geral e de gateway Storage"
    return 1
  }
  grep -Fxq 'rede-supabase' <<<"$attached_networks" || {
    storage_fail "$container nao esta conectado a rede geral do projeto"
    return 1
  }
  grep -Fxq 'supabase-storage-gateways' <<<"$attached_networks" || {
    storage_fail "$container nao esta conectado a rede exclusiva dos gateways Storage"
    return 1
  }
}

# Vincula o ref mutavel ao UUID imutavel persistido pelo control plane. Isso
# impede que um .env adulterado ou divergente selecione o namespace de outro
# projeto durante backup, restore, rename, delete ou manutencao.
storage_assert_project_identity() {
  local project_ref="$1" tenant_id="$2" persisted_raw persisted_tenant
  storage_validate_project_ref "$project_ref" || return 1
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ -n "${POSTGRES_USER:-}" && -n "${POSTGRES_DB:-}" ]] || {
    storage_fail "POSTGRES_USER/POSTGRES_DB ausentes para validar identidade"
    return 1
  }
  docker inspect supabase-db >/dev/null 2>&1 || {
    storage_fail "container supabase-db ausente para validar identidade"
    return 1
  }
  persisted_raw="$(docker exec supabase-db psql -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc \
    "SELECT tenant_uuid::text FROM public.projects WHERE name = '$project_ref';")" || {
    storage_fail "nao foi possivel validar identidade de $project_ref"
    return 1
  }
  persisted_tenant="$(printf '%s' "$persisted_raw" | tr -d '[:space:]')" \
    || return 1
  [[ "$persisted_tenant" == "$tenant_id" ]] || {
    storage_fail "tenant UUID de $project_ref diverge do control plane"
    return 1
  }
}

storage_database_urls() {
  local project_ref="$1" encoded_password direct_url pool_url
  storage_validate_project_ref "$project_ref" || return 1
  for variable in POSTGRES_PORT POSTGRES_PASSWORD POOLER_PROXY_PORT_TRANSACTION \
    STORAGE_TENANT_DB_USER; do
    [[ -n "${!variable:-}" ]] || {
      storage_fail "$variable ausente para registrar tenant"
      return 1
    }
  done

  encoded_password="$(storage_percent_encode "$POSTGRES_PASSWORD")" || return 1
  direct_url="postgresql://${STORAGE_TENANT_DB_USER}:${encoded_password}@db:${POSTGRES_PORT}/_supabase_${project_ref}"
  pool_url="postgresql://${STORAGE_TENANT_DB_USER}.${project_ref}:${encoded_password}@supavisor:${POOLER_PROXY_PORT_TRANSACTION}/_supabase_${project_ref}"
  printf '%s\n%s\n' "$direct_url" "$pool_url"
}

# O body entra por stdin e a chave administrativa e lida somente dentro do
# container. Assim nenhum segredo administrativo aparece em argv ou nos logs.
storage_admin_request() {
  local method="$1" path="$2" accepted="$3" body="${4:-}"
  storage_assert_global_container_contract || return 1

  printf '%s' "$body" | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const [method, path, acceptedRaw] = process.argv.slice(1);
const accepted = new Set(acceptedRaw.split(",").map(Number));
const key = (process.env.SERVER_ADMIN_API_KEYS || "").split(",")[0];
if (!key) {
  console.error("Storage admin key ausente");
  process.exit(20);
}
let body = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { body += chunk; });
process.stdin.on("end", async () => {
  try {
    const response = await fetch(`http://127.0.0.1:5001${path}`, {
      method,
      headers: {
        apikey: key,
        "content-type": "application/json",
        "x-request-id": `lifecycle-${Date.now()}`,
      },
      body: body.length > 0 ? body : undefined,
      signal: AbortSignal.timeout(10000),
    });
    const responseBody = await response.text();
    if (!accepted.has(response.status)) {
      console.error(`Storage admin ${method} ${path}: HTTP ${response.status}`);
      process.exit(21);
    }
    process.stdout.write(responseBody);
  } catch (error) {
    console.error(`Storage admin ${method} ${path}: indisponivel`);
    process.exit(22);
  }
});
' "$method" "$path" "$accepted"
}

storage_wait_global() {
  local attempts="${1:-90}" status=""
  storage_validate_positive_integer attempts "$attempts" || return 1
  storage_require_canonical_global_config || return 1
  for _ in $(seq 1 "$attempts"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$STORAGE_GLOBAL_CONTAINER" 2>/dev/null || true)"
    case "$status" in
      healthy)
        storage_assert_global_container_contract || return 1
        storage_wait_data_plane "$attempts" || return 1
        return 0
        ;;
      unhealthy|exited|dead)
        docker logs --tail 200 "$STORAGE_GLOBAL_CONTAINER" >&2 || true
        storage_fail "$STORAGE_GLOBAL_CONTAINER terminou com status $status"
        return 1
        ;;
    esac
    sleep 2
  done
  docker logs --tail 200 "$STORAGE_GLOBAL_CONTAINER" >&2 || true
  storage_fail "$STORAGE_GLOBAL_CONTAINER nao ficou healthy dentro do prazo"
}

storage_wait_data_plane() {
  local attempts="${1:-90}" status=""
  storage_validate_positive_integer attempts "$attempts" || return 1
  for _ in $(seq 1 "$attempts"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$STORAGE_DATA_PLANE_CONTAINER" 2>/dev/null || true)"
    case "$status" in
      healthy)
        storage_assert_data_plane_container_contract || return 1
        return 0
        ;;
      unhealthy|exited|dead)
        docker logs --tail 200 "$STORAGE_DATA_PLANE_CONTAINER" >&2 || true
        storage_fail "$STORAGE_DATA_PLANE_CONTAINER terminou com status $status"
        return 1
        ;;
    esac
    sleep 2
  done
  docker logs --tail 200 "$STORAGE_DATA_PLANE_CONTAINER" >&2 || true
  storage_fail "$STORAGE_DATA_PLANE_CONTAINER nao ficou healthy dentro do prazo"
}

storage_build_tenant_payload() {
  local anon_key="$1" service_key="$2" jwt_secret="$3" database_url="$4"
  local pool_url="$5" file_size_limit="$6" image_enabled="$7"
  local s3_enabled="$8" vectors_enabled="$9" vector_max_buckets="${10}"
  local vector_max_indexes="${11}"

  [[ -n "$anon_key" && -n "$service_key" && -n "$jwt_secret" \
    && -n "$database_url" && -n "$pool_url" ]] || {
    storage_fail "payload do tenant possui segredo ou database URL ausente"
    return 1
  }
  storage_validate_positive_integer file_size_limit "$file_size_limit" || return 1
  storage_validate_bool image_enabled "$image_enabled" || return 1
  storage_validate_bool s3_enabled "$s3_enabled" || return 1
  storage_validate_bool vectors_enabled "$vectors_enabled" || return 1
  storage_validate_positive_integer vector_max_buckets "$vector_max_buckets" || return 1
  storage_validate_positive_integer vector_max_indexes "$vector_max_indexes" || return 1
  storage_validate_positive_integer STORAGE_TENANT_MAX_CONNECTIONS \
    "${STORAGE_TENANT_MAX_CONNECTIONS:-}" || return 1

  printf '%s\n' "$anon_key" "$service_key" "$jwt_secret" "$database_url" "$pool_url" \
    | jq -Rn \
      --argjson fileSizeLimit "$file_size_limit" \
      --argjson imageEnabled "$image_enabled" \
      --argjson s3Enabled "$s3_enabled" \
      --argjson vectorsEnabled "$vectors_enabled" \
      --argjson maxBuckets "$vector_max_buckets" \
      --argjson maxIndexes "$vector_max_indexes" \
      --argjson maxConnections "$STORAGE_TENANT_MAX_CONNECTIONS" \
      '[inputs] | {
        anonKey: .[0],
        serviceKey: .[1],
        jwtSecret: .[2],
        databaseUrl: .[3],
        databasePoolUrl: .[4],
        maxConnections: $maxConnections,
        fileSizeLimit: $fileSizeLimit,
        features: {
          imageTransformation: {enabled: $imageEnabled},
          s3Protocol: {enabled: $s3Enabled},
          vectorBuckets: {
            enabled: $vectorsEnabled,
            maxBuckets: $maxBuckets,
            maxIndexes: $maxIndexes
          }
        }
      }'
}

storage_provision_tenant() {
  local tenant_id="$1" project_ref="$2" jwt_secret="$3" anon_key="$4" service_key="$5"
  local file_size_limit="$6" image_enabled="$7" s3_enabled="$8" vectors_enabled="$9"
  local max_buckets="${10}" max_indexes="${11}" urls database_url pool_url payload
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_project_ref "$project_ref" || return 1
  storage_assert_project_identity "$project_ref" "$tenant_id" || return 1
  storage_wait_global || return 1
  urls="$(storage_database_urls "$project_ref")" || return 1
  database_url="$(sed -n '1p' <<<"$urls")"
  pool_url="$(sed -n '2p' <<<"$urls")"
  payload="$(storage_build_tenant_payload "$anon_key" "$service_key" "$jwt_secret" \
    "$database_url" "$pool_url" "$file_size_limit" "$image_enabled" \
    "$s3_enabled" "$vectors_enabled" "$max_buckets" "$max_indexes")" || return 1
  storage_admin_request POST "/tenants/$tenant_id" "201" "$payload" >/dev/null
}

storage_assert_tenant_absent() {
  local tenant_id="$1" payload
  storage_validate_tenant_id "$tenant_id" || return 1
  payload="$(storage_admin_request GET "/tenants/$tenant_id" "200,404")" || return 1
  [[ -z "$payload" ]] || storage_fail "tenant $tenant_id ja existe no Storage"
}

storage_patch_tenant_connection() {
  local tenant_id="$1" project_ref="$2" urls database_url pool_url payload
  storage_validate_tenant_id "$tenant_id" || return 1
  urls="$(storage_database_urls "$project_ref")" || return 1
  database_url="$(sed -n '1p' <<<"$urls")"
  pool_url="$(sed -n '2p' <<<"$urls")"
  payload="$(printf '%s\n%s\n' "$database_url" "$pool_url" \
    | jq -Rn '[inputs] | {databaseUrl: .[0], databasePoolUrl: .[1]}')" \
    || return 1
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_patch_tenant_keys() {
  local tenant_id="$1" anon_key="$2" service_key="$3" payload
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ -n "$anon_key" && -n "$service_key" ]] || {
    storage_fail "JWTs internos ausentes"
    return 1
  }
  payload="$(printf '%s\n%s\n' "$anon_key" "$service_key" \
    | jq -Rn '[inputs] | {anonKey: .[0], serviceKey: .[1]}')" || return 1
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_data_plane_status() {
  local tenant_id="$1" service_key="$2"
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ -n "$service_key" ]] || {
    storage_fail "service key ausente para sonda da data plane"
    return 1
  }
  printf '%s' "$service_key" | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const tenant = process.argv[1];
let key = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { key += chunk; });
process.stdin.on("end", async () => {
  try {
    const response = await fetch("http://127.0.0.1:5000/bucket", {
      headers: {
        authorization: `Bearer ${key}`,
        apikey: key,
        "x-forwarded-host": `${tenant}.storage.internal`,
        "x-request-id": `tenant-maintenance-${Date.now()}`,
      },
      signal: AbortSignal.timeout(5000),
    });
    await response.arrayBuffer();
    process.stdout.write(String(response.status));
  } catch {
    process.exit(38);
  }
});
' "$tenant_id"
}

# Bloqueia novas operacoes do tenant sem parar o Storage global. Um pool URL
# deliberadamente inalcançavel permanece truthy no upstream, portanto
# getDbSettings nao pode cair para databaseUrl. A sonda confirma o fail-closed
# antes de o lifecycle tocar no banco ou no namespace fisico.
storage_quiesce_tenant() {
  local tenant_id="$1" project_ref="$2" service_key="$3" payload status="" attempts
  local maintenance_url="postgresql://storage_maintenance:disabled@127.0.0.1:1/storage_maintenance"
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_project_ref "$project_ref" || return 1
  [[ -n "$service_key" ]] || {
    storage_fail "service key ausente para quiescencia"
    return 1
  }

  status="$(storage_data_plane_status "$tenant_id" "$service_key")" || {
    storage_fail "data plane do tenant indisponivel antes da quiescencia"
    return 1
  }
  [[ "$status" == 2?? ]] || {
    storage_fail "data plane do tenant retornou HTTP $status antes da quiescencia"
    return 1
  }

  payload="$(jq -cn --arg url "$maintenance_url" '{databasePoolUrl:$url}')" || return 1
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null \
    || return 1

  for attempts in $(seq 1 30); do
    status="$(storage_data_plane_status "$tenant_id" "$service_key")" || {
      storage_patch_tenant_connection "$tenant_id" "$project_ref" \
        || storage_fail "quiescencia falhou e a conexao canonica nao foi restaurada"
      storage_fail "data plane do tenant ficou indeterminada durante quiescencia"
      return 1
    }
    case "$status" in
      2??) sleep 1 ;;
      5??) return 0 ;;
      *)
        storage_patch_tenant_connection "$tenant_id" "$project_ref" \
          || storage_fail "quiescencia falhou e a conexao canonica nao foi restaurada"
        storage_fail "data plane retornou HTTP $status durante quiescencia"
        return 1
        ;;
    esac
  done

  storage_patch_tenant_connection "$tenant_id" "$project_ref" \
    || storage_fail "quiescencia expirou e a conexao canonica nao foi restaurada"
  storage_fail "tenant $tenant_id continuou aceitando requests durante quiescencia"
}

storage_patch_tenant_settings() {
  local tenant_id="$1" file_size_limit="$2" image_enabled="$3"
  local s3_enabled="$4" vectors_enabled="$5" max_buckets="$6" max_indexes="$7" payload
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_positive_integer file_size_limit "$file_size_limit" || return 1
  storage_validate_bool image_enabled "$image_enabled" || return 1
  storage_validate_bool s3_enabled "$s3_enabled" || return 1
  storage_validate_bool vectors_enabled "$vectors_enabled" || return 1
  storage_validate_positive_integer vector_max_buckets "$max_buckets" || return 1
  storage_validate_positive_integer vector_max_indexes "$max_indexes" || return 1
  payload="$(jq -cn \
    --argjson fileSizeLimit "$file_size_limit" \
    --argjson imageEnabled "$image_enabled" \
    --argjson s3Enabled "$s3_enabled" \
    --argjson vectorsEnabled "$vectors_enabled" \
    --argjson maxBuckets "$max_buckets" \
    --argjson maxIndexes "$max_indexes" \
    '{fileSizeLimit: $fileSizeLimit, features: {
      imageTransformation: {enabled: $imageEnabled},
      s3Protocol: {enabled: $s3Enabled},
      vectorBuckets: {enabled: $vectorsEnabled, maxBuckets: $maxBuckets, maxIndexes: $maxIndexes}
    }}')" || return 1
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_create_s3_credentials() {
  local tenant_id="$1" payload response
  storage_validate_tenant_id "$tenant_id" || return 1
  payload='{"description":"Project lifecycle credential","claims":{"role":"service_role"}}'
  response="$(storage_admin_request POST "/s3/$tenant_id/credentials" "201" "$payload")" \
    || return 1
  jq -er '
    select(.id | test("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")) |
    select(.access_key | test("^[0-9a-f]{32}$")) |
    select(.secret_key | test("^[0-9a-f]{64}$")) |
    [.id, .access_key, .secret_key] | @tsv
  ' <<<"$response" || storage_fail "Storage retornou credencial S3 invalida"
}

storage_delete_s3_credential() {
  local tenant_id="$1" credential_id="$2" payload
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ "$credential_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || {
      storage_fail "credential id S3 invalido"
      return 1
    }
  payload="$(jq -cn --arg id "$credential_id" '{id:$id}')" || return 1
  storage_admin_request DELETE "/s3/$tenant_id/credentials" "204,404" "$payload" >/dev/null
}

storage_delete_tenant_registry() {
  local tenant_id="$1" credentials credential_id
  storage_validate_tenant_id "$tenant_id" || return 1
  credentials="$(storage_admin_request GET "/s3/$tenant_id/credentials" "200,404")" \
    || return 1
  if [[ -n "$credentials" ]]; then
    jq -e '
      type == "array" and all(.[].id;
        type == "string" and
        test("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
      )
    ' >/dev/null <<<"$credentials" || {
      storage_fail "Storage retornou lista de credenciais S3 invalida"
      return 1
    }
    while IFS= read -r credential_id; do
      [[ -n "$credential_id" ]] || continue
      storage_delete_s3_credential "$tenant_id" "$credential_id" || return 1
    done < <(jq -r '.[].id' <<<"$credentials")
  fi
  storage_admin_request DELETE "/tenants/$tenant_id" "204,404" '{}' >/dev/null
}

storage_tenant_namespace() {
  local tenant_id="$1" root
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_require_canonical_global_config || return 1
  mkdir -p "$STORAGE_OBJECT_ROOT" || return 1
  root="$(cd "$STORAGE_OBJECT_ROOT" && pwd -P)" || return 1
  printf '%s/%s\n' "$root" "$tenant_id"
}

storage_assert_namespace_target() {
  local tenant_id="$1" target parent
  target="$(storage_tenant_namespace "$tenant_id")" || return 1
  parent="$(cd "$STORAGE_OBJECT_ROOT" && pwd -P)" || return 1
  [[ "$(dirname "$target")" == "$parent" ]] \
    || {
      storage_fail "namespace do tenant escapou da raiz de objetos"
      return 1
    }
  [[ ! -L "$target" ]] || {
    storage_fail "namespace do tenant nao pode ser symlink"
    return 1
  }
  if [[ -e "$target" ]]; then
    [[ -d "$target" ]] || {
      storage_fail "namespace do tenant nao e diretorio"
      return 1
    }
    [[ "$(cd "$target" && pwd -P)" == "$target" ]] \
      || {
        storage_fail "namespace do tenant resolve fora do caminho canonico"
        return 1
      }
  fi
  printf '%s\n' "$target"
}

storage_validate_file_tree() {
  local root="$1" description="$2" unexpected
  storage_require_command find || return 1
  [[ -d "$root" && ! -L "$root" ]] || {
    storage_fail "$description nao e um diretorio canonico"
    return 1
  }
  unexpected="$(find "$root" ! -type d ! -type f -print -quit)" || {
    storage_fail "nao foi possivel validar tipos de arquivo em $description"
    return 1
  }
  [[ -z "$unexpected" ]] || {
    storage_fail "$description contem symlink ou tipo de arquivo nao permitido"
    return 1
  }
}

storage_remove_tenant_namespace() {
  local tenant_id="$1" target
  target="$(storage_assert_namespace_target "$tenant_id")" || return 1
  [[ -e "$target" ]] || return 0
  rm -rf -- "$target" || return 1
  [[ ! -e "$target" ]] || storage_fail "nao foi possivel remover namespace $tenant_id"
}

storage_clone_tenant_namespace() {
  local source_tenant="$1" destination_tenant="$2" source_path destination_path staging
  storage_validate_tenant_id "$source_tenant" || return 1
  storage_validate_tenant_id "$destination_tenant" || return 1
  [[ "$source_tenant" != "$destination_tenant" ]] \
    || {
      storage_fail "origem e destino do namespace sao iguais"
      return 1
    }
  source_path="$(storage_assert_namespace_target "$source_tenant")" || return 1
  destination_path="$(storage_assert_namespace_target "$destination_tenant")" || return 1
  [[ -d "$source_path" ]] || {
    storage_fail "namespace de origem $source_tenant ausente"
    return 1
  }
  storage_validate_file_tree "$source_path" "namespace de origem" || return 1
  [[ ! -e "$destination_path" ]] \
    || {
      storage_fail "namespace de destino $destination_tenant ja existe"
      return 1
    }

  staging="${destination_path}.copy.$$"
  [[ ! -e "$staging" ]] || {
    storage_fail "staging de copia ja existe"
    return 1
  }
  mkdir -p "$staging" || return 1
  if ! (cd "$source_path" && tar --xattrs --xattrs-include='*' --acls -cpf - .) \
    | (cd "$staging" && tar --xattrs --xattrs-include='*' --acls -xpf -); then
    rm -rf -- "$staging"
    storage_fail "falha ao copiar namespace $source_tenant"
    return 1
  fi
  mv -- "$staging" "$destination_path"
}

storage_create_empty_tenant_namespace() {
  local tenant_id="$1" target
  target="$(storage_assert_namespace_target "$tenant_id")" || return 1
  [[ ! -e "$target" ]] || {
    storage_fail "namespace $tenant_id ja existe"
    return 1
  }
  mkdir "$target"
}

storage_validate_namespace_archive() {
  local archive="$1"
  [[ -s "$archive" ]] || {
    storage_fail "archive de objetos ausente ou vazio"
    return 1
  }
  command -v python3 >/dev/null 2>&1 || {
    storage_fail "python3 nao esta instalado"
    return 1
  }
  python3 - "$archive" <<'PY'
import pathlib
import sys
import tarfile

archive = pathlib.Path(sys.argv[1])
with tarfile.open(archive, mode="r:gz") as handle:
    for member in handle.getmembers():
        path = pathlib.PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"entrada fora do namespace: {member.name!r}")
        if not (member.isfile() or member.isdir()):
            raise SystemExit(f"tipo de entrada nao permitido: {member.name!r}")
PY
}

storage_extract_namespace_archive() {
  local tenant_id="$1" archive="$2" target staging
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_namespace_archive "$archive" || return 1
  target="$(storage_assert_namespace_target "$tenant_id")" || return 1
  [[ ! -e "$target" ]] || {
    storage_fail "namespace $tenant_id ja existe no restore"
    return 1
  }
  staging="${target}.restore.$$"
  [[ ! -e "$staging" ]] || {
    storage_fail "staging de restore ja existe"
    return 1
  }
  mkdir -p "$staging" || return 1
  if ! tar --xattrs --xattrs-include='*' --acls --numeric-owner \
    -xzpf "$archive" -C "$staging"; then
    rm -rf -- "$staging"
    storage_fail "falha ao extrair objetos do tenant $tenant_id"
    return 1
  fi
  mv -- "$staging" "$target"
}

storage_delete_tenant() {
  local tenant_id="$1"
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_delete_tenant_registry "$tenant_id" || return 1
  storage_remove_tenant_namespace "$tenant_id"
}

storage_run_and_assert_migrations() {
  local tenant_id="$1" attempts="${2:-60}" payload="" status
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_positive_integer attempts "$attempts" || return 1
  storage_admin_request POST "/tenants/$tenant_id/migrations" "200" '{}' >/dev/null \
    || return 1
  for _ in $(seq 1 "$attempts"); do
    payload="$(storage_admin_request GET "/tenants/$tenant_id/migrations" "200")" \
      || return 1
    if jq -e '.isLatest == true and .migrationsStatus == "COMPLETED"' \
      >/dev/null <<<"$payload"; then
      return 0
    fi
    status="$(jq -er '.migrationsStatus // "ausente"' <<<"$payload")" || return 1
    [[ "$status" != "FAILED" ]] || {
      storage_fail "migrations do tenant $tenant_id falharam"
      return 1
    }
    sleep 2
  done
  storage_fail "migrations do tenant $tenant_id nao concluiram dentro do prazo"
}

storage_assert_tenant_health() {
  local tenant_id="$1" payload
  storage_validate_tenant_id "$tenant_id" || return 1
  payload="$(storage_admin_request GET "/tenants/$tenant_id/health" "200")" \
    || return 1
  jq -e '.healthy == true' >/dev/null <<<"$payload" \
    || storage_fail "health do tenant $tenant_id falhou"
}

storage_assert_jwt_data_plane() {
  local tenant_id="$1" service_key="$2"
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ -n "$service_key" ]] || {
    storage_fail "service key ausente para validar data plane"
    return 1
  }
  printf '%s' "$service_key" | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const tenant = process.argv[1];
let key = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { key += chunk; });
process.stdin.on("end", async () => {
  try {
    const response = await fetch("http://127.0.0.1:5000/bucket", {
      headers: {
        authorization: `Bearer ${key}`,
        apikey: key,
        "x-forwarded-host": `${tenant}.storage.internal`,
        "x-request-id": `tenant-probe-${Date.now()}`,
      },
      signal: AbortSignal.timeout(10000),
    });
    const body = await response.text();
    if (!response.ok) {
      console.error(`Storage tenant data probe: HTTP ${response.status}`);
      process.exit(30);
    }
    const parsed = JSON.parse(body);
    if (!Array.isArray(parsed)) process.exit(31);
  } catch {
    console.error("Storage tenant data probe falhou");
    process.exit(32);
  }
});
' "$tenant_id"
}

storage_assert_project_gateway() {
  local tenant_id="$1" project_ref="$2" service_key="$3"
  storage_validate_tenant_id "$tenant_id" || return 1
  storage_validate_project_ref "$project_ref" || return 1
  [[ -n "$service_key" ]] || {
    storage_fail "service key ausente para validar gateway"
    return 1
  }
  storage_assert_data_plane_container_contract || return 1
  storage_assert_project_gateway_container_contract "$project_ref" || return 1
  printf '%s\n' "$service_key" \
    | docker exec -i "$STORAGE_DATA_PLANE_CONTAINER" sh -eu -c '
IFS= read -r key
body="$(wget -qO- -T 10 \
  --header="Authorization: Bearer $key" \
  --header="X-Forwarded-Host: 00000000-0000-0000-0000-000000000000.storage.internal" \
  --header="X-Request-Id: gateway-probe-$$" \
  "http://supabase-nginx-$1:8080/storage/v1/bucket")" || {
  echo "Storage gateway probe falhou" >&2
  exit 33
}
case "$body" in
  \[*\]) ;;
  *) echo "Storage gateway retornou body invalido" >&2; exit 34 ;;
esac
' sh "$project_ref"
}

storage_vector_request() {
  local tenant_id="$1" service_key="$2" operation="$3" json_body="$4"
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ -n "$service_key" ]] || {
    storage_fail "service key ausente para operacao Vector"
    return 1
  }
  [[ "$operation" =~ ^[A-Za-z]+$ ]] || {
    storage_fail "operacao Vector invalida"
    return 1
  }
  jq -e . >/dev/null <<<"$json_body" || {
    storage_fail "body Vector invalido"
    return 1
  }

  printf '%s\n%s' "$service_key" "$json_body" \
    | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const [tenant, operation] = process.argv.slice(1);
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", async () => {
  const separator = input.indexOf("\n");
  if (separator < 0) process.exit(35);
  const key = input.slice(0, separator);
  const body = input.slice(separator + 1);
  try {
    const response = await fetch(`http://127.0.0.1:5000/vector/${operation}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${key}`,
        apikey: key,
        "x-forwarded-host": `${tenant}.storage.internal`,
        "x-request-id": `vector-probe-${Date.now()}`,
      },
      body,
      signal: AbortSignal.timeout(10000),
    });
    const responseBody = await response.text();
    if (!response.ok) {
      console.error(`Storage Vector ${operation}: HTTP ${response.status}`);
      process.exit(36);
    }
    JSON.parse(responseBody);
    process.stdout.write(responseBody);
  } catch {
    console.error(`Storage Vector ${operation} falhou`);
    process.exit(37);
  }
});
' "$tenant_id" "$operation"
}

storage_list_vector_buckets() {
  local tenant_id="$1" service_key="$2" payload
  payload="$(storage_vector_request "$tenant_id" "$service_key" ListVectorBuckets '{}')" \
    || return 1
  jq -e '.vectorBuckets | type == "array"' >/dev/null <<<"$payload" || {
    storage_fail "Resposta de ListVectorBuckets invalida"
    return 1
  }
  jq -r '.vectorBuckets[].vectorBucketName' <<<"$payload"
}

storage_assert_vector_bucket() {
  local tenant_id="$1" service_key="$2" bucket_name="$3" payload request
  [[ -n "$bucket_name" && "$bucket_name" != *$'\n'* && "$bucket_name" != *$'\r'* ]] \
    || {
      storage_fail "nome de Vector Bucket invalido"
      return 1
    }
  request="$(jq -cn --arg name "$bucket_name" '{vectorBucketName:$name}')" || return 1
  payload="$(storage_vector_request "$tenant_id" "$service_key" GetVectorBucket "$request")" \
    || return 1
  jq -e --arg name "$bucket_name" '.vectorBucket.vectorBucketName == $name' \
    >/dev/null <<<"$payload" || storage_fail "Storage retornou Vector Bucket inesperado"
}

storage_sigv4_probe() {
  local tenant_id="$1" access_key="$2" secret_key="$3" service="$4"
  local method="$5" path="$6" body="${7:-}"
  storage_validate_tenant_id "$tenant_id" || return 1
  [[ "$access_key" =~ ^[0-9a-f]{32}$ ]] || {
    storage_fail "access key S3 invalida"
    return 1
  }
  [[ "$secret_key" =~ ^[0-9a-f]{64}$ ]] || {
    storage_fail "secret key S3 invalida"
    return 1
  }
  [[ "$service" == "s3" || "$service" == "s3vectors" ]] \
    || {
      storage_fail "servico SigV4 invalido"
      return 1
    }
  [[ "$path" == /* && "$path" != *".."* ]] || {
    storage_fail "path SigV4 invalido"
    return 1
  }

  printf '%s\n%s\n%s' "$access_key" "$secret_key" "$body" \
    | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const crypto = require("node:crypto");
const http = require("node:http");
const [tenant, service, method, path] = process.argv.slice(1);
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { input += chunk; });
process.stdin.on("end", () => {
  const first = input.indexOf("\n");
  const second = input.indexOf("\n", first + 1);
  if (first < 0 || second < 0) process.exit(40);
  const access = input.slice(0, first);
  const secret = input.slice(first + 1, second);
  const body = input.slice(second + 1);
  const region = process.env.STORAGE_S3_REGION;
  if (!region) process.exit(41);
  const host = `${tenant}.storage.internal`;
  const now = new Date();
  const amzDate = now.toISOString().replace(/[:-]|\.\d{3}/g, "");
  const shortDate = amzDate.slice(0, 8);
  const hash = value => crypto.createHash("sha256").update(value).digest("hex");
  const hmac = (key, value) => crypto.createHmac("sha256", key).update(value).digest();
  const payloadHash = hash(body);
  const hasBody = body.length > 0;
  const signedHeaders = hasBody
    ? "content-type;host;x-amz-content-sha256;x-amz-date"
    : "host;x-amz-content-sha256;x-amz-date";
  const canonicalHeaders = hasBody
    ? `content-type:application/json\nhost:${host}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`
    : `host:${host}\nx-amz-content-sha256:${payloadHash}\nx-amz-date:${amzDate}\n`;
  const canonicalRequest = [method, path, "", canonicalHeaders, signedHeaders, payloadHash].join("\n");
  const scope = `${shortDate}/${region}/${service}/aws4_request`;
  const stringToSign = ["AWS4-HMAC-SHA256", amzDate, scope, hash(canonicalRequest)].join("\n");
  const dateKey = hmac(Buffer.from(`AWS4${secret}`), shortDate);
  const regionKey = hmac(dateKey, region);
  const serviceKey = hmac(regionKey, service);
  const signingKey = hmac(serviceKey, "aws4_request");
  const signature = crypto.createHmac("sha256", signingKey).update(stringToSign).digest("hex");
  const headers = {
    host,
    "x-forwarded-host": host,
    "x-amz-content-sha256": payloadHash,
    "x-amz-date": amzDate,
    authorization: `AWS4-HMAC-SHA256 Credential=${access}/${scope}, SignedHeaders=${signedHeaders}, Signature=${signature}`,
    "content-length": Buffer.byteLength(body),
  };
  if (hasBody) headers["content-type"] = "application/json";
  const request = http.request({host: "127.0.0.1", port: 5000, method, path, headers}, response => {
    response.resume();
    response.on("end", () => {
      if (response.statusCode < 200 || response.statusCode >= 300) {
        console.error(`Storage ${service} probe: HTTP ${response.statusCode}`);
        process.exit(42);
      }
    });
  });
  request.on("error", () => {
    console.error(`Storage ${service} probe indisponivel`);
    process.exit(43);
  });
  request.setTimeout(10000, () => request.destroy(new Error("timeout")));
  request.end(body);
});
' "$tenant_id" "$service" "$method" "$path"
}

storage_validate_tenant() {
  local tenant_id="$1" service_key="$2" access_key="$3" secret_key="$4"
  local s3_enabled="$5" vectors_enabled="$6"
  storage_validate_bool s3_enabled "$s3_enabled" || return 1
  storage_validate_bool vectors_enabled "$vectors_enabled" || return 1
  storage_run_and_assert_migrations "$tenant_id" || return 1
  storage_assert_tenant_health "$tenant_id" || return 1
  storage_assert_jwt_data_plane "$tenant_id" "$service_key" || return 1
  if [[ "$s3_enabled" == "true" ]]; then
    storage_sigv4_probe "$tenant_id" "$access_key" "$secret_key" s3 GET /s3 '' \
      || return 1
  fi
  if [[ "$vectors_enabled" == "true" ]]; then
    storage_sigv4_probe "$tenant_id" "$access_key" "$secret_key" \
      s3vectors POST /vector/ListVectorBuckets '{}' || return 1
  fi
}
