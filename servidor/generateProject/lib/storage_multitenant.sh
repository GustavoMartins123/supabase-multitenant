#!/usr/bin/env bash

# Lifecycle do Storage API compartilhado. Todas as mutacoes de tenant passam
# pela API administrativa oficial; nenhuma tabela do registry e editada aqui.

STORAGE_LIFECYCLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORAGE_SERVER_ROOT="$(dirname "$(dirname "$STORAGE_LIFECYCLE_DIR")")"
STORAGE_GLOBAL_CONTAINER="supabase-storage-global"
STORAGE_OBJECT_ROOT="$STORAGE_SERVER_ROOT/volumes/storage/objects"

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
  storage_require_command jq
  printf '%s' "$1" | jq -sRr @uri
}

storage_database_urls() {
  local project_ref="$1" encoded_password direct_url pool_url
  storage_validate_project_ref "$project_ref"
  for variable in POSTGRES_HOST POSTGRES_PORT POSTGRES_PASSWORD POSTGRES_POOLER \
    POOLER_PROXY_PORT_TRANSACTION STORAGE_TENANT_DB_USER; do
    [[ -n "${!variable:-}" ]] || storage_fail "$variable ausente para registrar tenant"
  done

  encoded_password="$(storage_percent_encode "$POSTGRES_PASSWORD")"
  direct_url="postgresql://${STORAGE_TENANT_DB_USER}:${encoded_password}@${POSTGRES_HOST}:${POSTGRES_PORT}/_supabase_${project_ref}"
  pool_url="postgresql://${STORAGE_TENANT_DB_USER}.${project_ref}:${encoded_password}@${POSTGRES_POOLER}:${POOLER_PROXY_PORT_TRANSACTION}/_supabase_${project_ref}"
  printf '%s\n%s\n' "$direct_url" "$pool_url"
}

# O body entra por stdin e a chave administrativa e lida somente dentro do
# container. Assim nenhum segredo administrativo aparece em argv ou nos logs.
storage_admin_request() {
  local method="$1" path="$2" accepted="$3" body="${4:-}"
  docker inspect "$STORAGE_GLOBAL_CONTAINER" >/dev/null 2>&1 \
    || storage_fail "container $STORAGE_GLOBAL_CONTAINER nao encontrado"

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
  storage_validate_positive_integer attempts "$attempts"
  for _ in $(seq 1 "$attempts"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' \
      "$STORAGE_GLOBAL_CONTAINER" 2>/dev/null || true)"
    case "$status" in
      healthy) return 0 ;;
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

storage_build_tenant_payload() {
  local anon_key="$1" service_key="$2" jwt_secret="$3" database_url="$4"
  local pool_url="$5" file_size_limit="$6" image_enabled="$7"
  local s3_enabled="$8" vectors_enabled="$9" vector_max_buckets="${10}"
  local vector_max_indexes="${11}"

  storage_validate_positive_integer file_size_limit "$file_size_limit"
  storage_validate_bool image_enabled "$image_enabled"
  storage_validate_bool s3_enabled "$s3_enabled"
  storage_validate_bool vectors_enabled "$vectors_enabled"
  storage_validate_positive_integer vector_max_buckets "$vector_max_buckets"
  storage_validate_positive_integer vector_max_indexes "$vector_max_indexes"
  storage_validate_positive_integer STORAGE_TENANT_MAX_CONNECTIONS \
    "${STORAGE_TENANT_MAX_CONNECTIONS:-}"

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
  storage_validate_tenant_id "$tenant_id"
  storage_validate_project_ref "$project_ref"
  storage_wait_global
  urls="$(storage_database_urls "$project_ref")"
  database_url="$(sed -n '1p' <<<"$urls")"
  pool_url="$(sed -n '2p' <<<"$urls")"
  payload="$(storage_build_tenant_payload "$anon_key" "$service_key" "$jwt_secret" \
    "$database_url" "$pool_url" "$file_size_limit" "$image_enabled" \
    "$s3_enabled" "$vectors_enabled" "$max_buckets" "$max_indexes")"
  storage_admin_request POST "/tenants/$tenant_id" "201" "$payload" >/dev/null
}

storage_assert_tenant_absent() {
  local tenant_id="$1" payload
  storage_validate_tenant_id "$tenant_id"
  payload="$(storage_admin_request GET "/tenants/$tenant_id" "200,404")"
  [[ -z "$payload" ]] || storage_fail "tenant $tenant_id ja existe no Storage"
}

storage_patch_tenant_connection() {
  local tenant_id="$1" project_ref="$2" urls database_url pool_url payload
  storage_validate_tenant_id "$tenant_id"
  urls="$(storage_database_urls "$project_ref")"
  database_url="$(sed -n '1p' <<<"$urls")"
  pool_url="$(sed -n '2p' <<<"$urls")"
  payload="$(printf '%s\n%s\n' "$database_url" "$pool_url" \
    | jq -Rn '[inputs] | {databaseUrl: .[0], databasePoolUrl: .[1]}')"
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_patch_tenant_keys() {
  local tenant_id="$1" anon_key="$2" service_key="$3" payload
  storage_validate_tenant_id "$tenant_id"
  [[ -n "$anon_key" && -n "$service_key" ]] || storage_fail "JWTs internos ausentes"
  payload="$(printf '%s\n%s\n' "$anon_key" "$service_key" \
    | jq -Rn '[inputs] | {anonKey: .[0], serviceKey: .[1]}')"
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_disconnect_tenant_pool() {
  local tenant_id="$1"
  storage_validate_tenant_id "$tenant_id"
  storage_admin_request PATCH "/tenants/$tenant_id" "204" \
    '{"databasePoolUrl":null}' >/dev/null
}

storage_patch_tenant_settings() {
  local tenant_id="$1" file_size_limit="$2" image_enabled="$3"
  local s3_enabled="$4" vectors_enabled="$5" max_buckets="$6" max_indexes="$7" payload
  storage_validate_tenant_id "$tenant_id"
  storage_validate_positive_integer file_size_limit "$file_size_limit"
  storage_validate_bool image_enabled "$image_enabled"
  storage_validate_bool s3_enabled "$s3_enabled"
  storage_validate_bool vectors_enabled "$vectors_enabled"
  storage_validate_positive_integer vector_max_buckets "$max_buckets"
  storage_validate_positive_integer vector_max_indexes "$max_indexes"
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
    }}')"
  storage_admin_request PATCH "/tenants/$tenant_id" "204" "$payload" >/dev/null
}

storage_create_s3_credentials() {
  local tenant_id="$1" payload response
  storage_validate_tenant_id "$tenant_id"
  payload='{"description":"Project lifecycle credential","claims":{"role":"service_role"}}'
  response="$(storage_admin_request POST "/s3/$tenant_id/credentials" "201" "$payload")"
  jq -er '
    select(.id | test("^[0-9a-f-]{36}$")) |
    select(.access_key | test("^[0-9a-f]{32}$")) |
    select(.secret_key | test("^[0-9a-f]{64}$")) |
    [.id, .access_key, .secret_key] | @tsv
  ' <<<"$response" || storage_fail "Storage retornou credencial S3 invalida"
}

storage_delete_s3_credential() {
  local tenant_id="$1" credential_id="$2" payload
  storage_validate_tenant_id "$tenant_id"
  [[ "$credential_id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || storage_fail "credential id S3 invalido"
  payload="$(jq -cn --arg id "$credential_id" '{id:$id}')"
  storage_admin_request DELETE "/s3/$tenant_id/credentials" "204,404" "$payload" >/dev/null
}

storage_delete_tenant_registry() {
  local tenant_id="$1" credentials credential_id
  storage_validate_tenant_id "$tenant_id"
  credentials="$(storage_admin_request GET "/s3/$tenant_id/credentials" "200,404")"
  if [[ -n "$credentials" ]]; then
    while IFS= read -r credential_id; do
      [[ -n "$credential_id" ]] || continue
      storage_delete_s3_credential "$tenant_id" "$credential_id"
    done < <(jq -er '.[]?.id' <<<"$credentials")
  fi
  storage_admin_request DELETE "/tenants/$tenant_id" "204,404" '{}' >/dev/null
}

storage_tenant_namespace() {
  local tenant_id="$1" root
  storage_validate_tenant_id "$tenant_id"
  mkdir -p "$STORAGE_OBJECT_ROOT"
  root="$(cd "$STORAGE_OBJECT_ROOT" && pwd -P)"
  printf '%s/%s\n' "$root" "$tenant_id"
}

storage_assert_namespace_target() {
  local tenant_id="$1" target parent
  target="$(storage_tenant_namespace "$tenant_id")"
  parent="$(cd "$STORAGE_OBJECT_ROOT" && pwd -P)"
  [[ "$(dirname "$target")" == "$parent" ]] \
    || storage_fail "namespace do tenant escapou da raiz de objetos"
  [[ ! -L "$target" ]] || storage_fail "namespace do tenant nao pode ser symlink"
  if [[ -e "$target" ]]; then
    [[ -d "$target" ]] || storage_fail "namespace do tenant nao e diretorio"
    [[ "$(cd "$target" && pwd -P)" == "$target" ]] \
      || storage_fail "namespace do tenant resolve fora do caminho canonico"
  fi
  printf '%s\n' "$target"
}

storage_remove_tenant_namespace() {
  local tenant_id="$1" target
  target="$(storage_assert_namespace_target "$tenant_id")"
  [[ -e "$target" ]] || return 0
  rm -rf -- "$target"
  [[ ! -e "$target" ]] || storage_fail "nao foi possivel remover namespace $tenant_id"
}

storage_clone_tenant_namespace() {
  local source_tenant="$1" destination_tenant="$2" source_path destination_path staging
  storage_validate_tenant_id "$source_tenant"
  storage_validate_tenant_id "$destination_tenant"
  [[ "$source_tenant" != "$destination_tenant" ]] \
    || storage_fail "origem e destino do namespace sao iguais"
  source_path="$(storage_assert_namespace_target "$source_tenant")"
  destination_path="$(storage_assert_namespace_target "$destination_tenant")"
  [[ -d "$source_path" ]] || storage_fail "namespace de origem $source_tenant ausente"
  [[ ! -e "$destination_path" ]] \
    || storage_fail "namespace de destino $destination_tenant ja existe"

  staging="${destination_path}.copy.$$"
  [[ ! -e "$staging" ]] || storage_fail "staging de copia ja existe"
  mkdir -p "$staging"
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
  target="$(storage_assert_namespace_target "$tenant_id")"
  [[ ! -e "$target" ]] || storage_fail "namespace $tenant_id ja existe"
  mkdir "$target"
}

storage_validate_namespace_archive() {
  local archive="$1"
  [[ -s "$archive" ]] || storage_fail "archive de objetos ausente ou vazio"
  command -v python3 >/dev/null 2>&1 || storage_fail "python3 nao esta instalado"
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
  storage_validate_tenant_id "$tenant_id"
  storage_validate_namespace_archive "$archive"
  target="$(storage_assert_namespace_target "$tenant_id")"
  [[ ! -e "$target" ]] || storage_fail "namespace $tenant_id ja existe no restore"
  staging="${target}.restore.$$"
  [[ ! -e "$staging" ]] || storage_fail "staging de restore ja existe"
  mkdir -p "$staging"
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
  storage_validate_tenant_id "$tenant_id"
  storage_delete_tenant_registry "$tenant_id"
  storage_remove_tenant_namespace "$tenant_id"
}

storage_run_and_assert_migrations() {
  local tenant_id="$1" attempts="${2:-60}" payload="" status
  storage_validate_tenant_id "$tenant_id"
  storage_admin_request POST "/tenants/$tenant_id/migrations" "200" '{}' >/dev/null
  for _ in $(seq 1 "$attempts"); do
    payload="$(storage_admin_request GET "/tenants/$tenant_id/migrations" "200")"
    if jq -e '.isLatest == true and .migrationsStatus == "COMPLETED"' \
      >/dev/null <<<"$payload"; then
      return 0
    fi
    status="$(jq -r '.migrationsStatus // "ausente"' <<<"$payload")"
    [[ "$status" != "FAILED" ]] || storage_fail "migrations do tenant $tenant_id falharam"
    sleep 2
  done
  storage_fail "migrations do tenant $tenant_id nao concluiram dentro do prazo"
}

storage_assert_tenant_health() {
  local tenant_id="$1" payload
  storage_validate_tenant_id "$tenant_id"
  payload="$(storage_admin_request GET "/tenants/$tenant_id/health" "200")"
  jq -e '.healthy == true' >/dev/null <<<"$payload" \
    || storage_fail "health do tenant $tenant_id falhou"
}

storage_assert_jwt_data_plane() {
  local tenant_id="$1" service_key="$2"
  storage_validate_tenant_id "$tenant_id"
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
  storage_validate_tenant_id "$tenant_id"
  storage_validate_project_ref "$project_ref"
  printf '%s' "$service_key" | docker exec -i "$STORAGE_GLOBAL_CONTAINER" node -e '
const [tenant, project] = process.argv.slice(1);
let key = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", chunk => { key += chunk; });
process.stdin.on("end", async () => {
  try {
    const response = await fetch(`http://supabase-nginx-${project}:8080/storage/v1/bucket`, {
      headers: {
        authorization: `Bearer ${key}`,
        apikey: key,
        host: `gateway-probe-${project}.internal`,
        // Este valor hostil deve ser descartado pelo Nginx do projeto.
        "x-forwarded-host": "00000000-0000-0000-0000-000000000000.storage.internal",
        "x-request-id": `gateway-probe-${Date.now()}`,
      },
    });
    const body = await response.text();
    if (!response.ok || !Array.isArray(JSON.parse(body))) {
      console.error(`Storage gateway probe: HTTP ${response.status}`);
      process.exit(33);
    }
  } catch {
    console.error(`Storage gateway do tenant ${tenant} falhou`);
    process.exit(34);
  }
});
' "$tenant_id" "$project_ref"
}

storage_vector_request() {
  local tenant_id="$1" service_key="$2" operation="$3" json_body="$4"
  storage_validate_tenant_id "$tenant_id"
  [[ "$operation" =~ ^[A-Za-z]+$ ]] || storage_fail "operacao Vector invalida"
  jq -e . >/dev/null <<<"$json_body" || storage_fail "body Vector invalido"

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
  payload="$(storage_vector_request "$tenant_id" "$service_key" ListVectorBuckets '{}')"
  jq -e '.vectorBuckets | type == "array"' >/dev/null <<<"$payload" \
    || storage_fail "Resposta de ListVectorBuckets invalida"
  jq -r '.vectorBuckets[].vectorBucketName' <<<"$payload"
}

storage_assert_vector_bucket() {
  local tenant_id="$1" service_key="$2" bucket_name="$3" payload request
  [[ -n "$bucket_name" && "$bucket_name" != *$'\n'* && "$bucket_name" != *$'\r'* ]] \
    || storage_fail "nome de Vector Bucket invalido"
  request="$(jq -cn --arg name "$bucket_name" '{vectorBucketName:$name}')"
  payload="$(storage_vector_request "$tenant_id" "$service_key" GetVectorBucket "$request")"
  jq -e --arg name "$bucket_name" '.vectorBucket.vectorBucketName == $name' \
    >/dev/null <<<"$payload" || storage_fail "Storage retornou Vector Bucket inesperado"
}

storage_sigv4_probe() {
  local tenant_id="$1" access_key="$2" secret_key="$3" service="$4"
  local method="$5" path="$6" body="${7:-}"
  storage_validate_tenant_id "$tenant_id"
  [[ "$access_key" =~ ^[0-9a-f]{32}$ ]] || storage_fail "access key S3 invalida"
  [[ "$secret_key" =~ ^[0-9a-f]{64}$ ]] || storage_fail "secret key S3 invalida"
  [[ "$service" == "s3" || "$service" == "s3vectors" ]] \
    || storage_fail "servico SigV4 invalido"
  [[ "$path" == /* && "$path" != *".."* ]] || storage_fail "path SigV4 invalido"

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
  request.end(body);
});
' "$tenant_id" "$service" "$method" "$path"
}

storage_validate_tenant() {
  local tenant_id="$1" service_key="$2" access_key="$3" secret_key="$4"
  local s3_enabled="$5" vectors_enabled="$6"
  storage_validate_bool s3_enabled "$s3_enabled"
  storage_validate_bool vectors_enabled "$vectors_enabled"
  storage_run_and_assert_migrations "$tenant_id"
  storage_assert_tenant_health "$tenant_id"
  storage_assert_jwt_data_plane "$tenant_id" "$service_key"
  if [[ "$s3_enabled" == "true" ]]; then
    storage_sigv4_probe "$tenant_id" "$access_key" "$secret_key" s3 GET /s3 ''
  fi
  if [[ "$vectors_enabled" == "true" ]]; then
    storage_sigv4_probe "$tenant_id" "$access_key" "$secret_key" \
      s3vectors POST /vector/ListVectorBuckets '{}'
  fi
}
