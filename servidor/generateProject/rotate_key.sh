#!/usr/bin/env bash
set -euo pipefail

die() { echo "❌ $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/functions_config.sh"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/vector_lifecycle.sh"
source "$SCRIPT_DIR/lib/resource_profiles.sh"
source "$SCRIPT_DIR/lib/project_public_ref.sh"

TRANSACTION_DIR="$PROJECT_ROOT/.rotate_transaction_$$"
MODIFIED_FILES=()
STORAGE_KEYS_UPDATED=false
REALTIME_JWT_UPDATED=false
ROTATE_JWT_SECRET="${ROTATE_JWT_SECRET:-false}"
SERVICES_TO_RECREATE=(nginx)

init_transaction() {
  mkdir -p "$TRANSACTION_DIR"
  echo "🔄 Sistema de transação inicializado"
}

backup_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local backup_path
    backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
    cp "$file" "$backup_path"
    MODIFIED_FILES+=("$file")
    echo "   Backup criado: $(basename "$file")"
  fi
}

commit_transaction() {
  if [[ -d "$TRANSACTION_DIR" ]]; then
    rm -rf "$TRANSACTION_DIR"
    echo "✅ Transação confirmada. Backups removidos."
  fi
}

realtime_patch_tenant_jwt_secret() {
  local tenant_uuid="$1" secret="$2" api_token="$3" payload response http_code
  payload="$(jq -cn --arg secret "$secret" '{tenant:{jwt_secret:$secret}}')" || return 1
  response="$(docker exec realtime-dev.supabase-realtime curl -sS -w '\n%{http_code}' \
    -X PUT "http://localhost:4000/api/tenants/${tenant_uuid}" \
    -H 'Content-Type: application/json' \
    -H "Authorization: Bearer ${api_token}" \
    -d "$payload")" || return 1
  http_code="$(printf '%s\n' "$response" | tail -n1)"
  [[ "$http_code" == "200" || "$http_code" == "201" || "$http_code" == "204" ]]
}

rollback_transaction() {
  trap - ERR
  set +e
  local runtime_restored=true
  if [[ "$FUNCTIONS_CONFIG_LOCKED" == 1 ]] && [[ "${FUNCTIONS_WITHDRAWN[$PROJECT_ID]:-0}" == 1 ]]; then
    functions_config_withdraw "$PROJECT_ID" || runtime_restored=false
  fi
  echo "❌ Erro detectado! Revertendo alterações..."

  if [[ "$REALTIME_JWT_UPDATED" == "true" ]]; then
    if ! realtime_patch_tenant_jwt_secret "$PROJECT_UUID" "$PREVIOUS_JWT_SECRET" "$GLOBAL_API_TOKEN"; then
      runtime_restored=false
      echo "❌ Configuracao anterior do tenant Realtime nao foi restaurada." >&2
    fi
  fi

  if [[ "$STORAGE_KEYS_UPDATED" == "true" ]]; then
    local rollback_jwt=""
    if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
      rollback_jwt="$PREVIOUS_JWT_SECRET"
    fi
    if ! storage_patch_tenant_keys "$PROJECT_UUID" "$CURRENT_ANON" "$CURRENT_SERVICE" "$rollback_jwt"; then
      runtime_restored=false
      echo "❌ Configuracao anterior do tenant Storage nao foi restaurada." >&2
    fi
  fi
  
  if [[ -d "$TRANSACTION_DIR" ]]; then
    for file in "${MODIFIED_FILES[@]}"; do
      local backup_path
      backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
      if [[ -f "$backup_path" ]]; then
        cp "$backup_path" "$file" || runtime_restored=false
        echo "   Restaurado: $(basename "$file")"
      fi
    done
    if [[ -n "${PROJECT_DIR:-}" && -d "$PROJECT_DIR" && -f "$PROJECT_DIR/docker-compose.yml" ]]; then
      if (
        cd "$PROJECT_DIR" &&
        docker compose -p "$PROJECT_ID" \
          --env-file ../../.env \
          --env-file .env \
          up --build -d "${SERVICES_TO_RECREATE[@]}"
      ); then
        echo "   Runtime dos servicos restaurado com a configuração anterior."
      else
        runtime_restored=false
        echo "❌ Arquivos restaurados, mas o runtime anterior nao pôde ser confirmado." >&2
      fi
    fi
    if [[ "$runtime_restored" == "true" ]]; then
      functions_config_publish "$PROJECT_ID" || runtime_restored=false
    fi
    if [[ "$runtime_restored" == "true" ]]; then
      rm -rf "$TRANSACTION_DIR"
      echo "⚠️  Todas as alterações foram revertidas."
    else
      echo "⚠️  Backups preservados em $TRANSACTION_DIR para recuperação manual." >&2
    fi
  fi
  
  exit 1
}

trap rollback_transaction ERR

set -a
source "$PROJECT_ROOT/.env"
set +a

[[ -z "${SERVER_URL:-}" ]] && die "SERVER_URL ausente"
[[ -z "${HOST_PROJECT_ROOT:-}" ]] && die "HOST_PROJECT_ROOT ausente"

PROJECT_ID=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rotate-jwt-secret)
      ROTATE_JWT_SECRET="true"
      shift
      ;;
    --keep-jwt-secret)
      ROTATE_JWT_SECRET="false"
      shift
      ;;
    -*)
      die "Flag nao reconhecida: $1"
      ;;
    *)
      if [[ -z "$PROJECT_ID" ]]; then
        PROJECT_ID="$1"
      else
        die "Uso: $0 <project_id> [--rotate-jwt-secret]"
      fi
      shift
      ;;
  esac
done

[[ "$ROTATE_JWT_SECRET" == "true" || "$ROTATE_JWT_SECRET" == "false" ]] \
  || die "ROTATE_JWT_SECRET deve ser true ou false"

[[ -z "$PROJECT_ID" ]] && die "Uso: $0 <project_id> [--rotate-jwt-secret]"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "PROJECT_ID invalido"

functions_config_lock "$PROJECT_ID"
PROJECT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
[[ -d "$PROJECT_DIR" ]] || die "Projeto '$PROJECT_ID' não encontrado em $PROJECT_DIR"
for command in docker openssl sed grep; do
  command -v "$command" >/dev/null || die "Comando obrigatorio ausente: $command"
done
for template in nginxtemplate Dockerfile dockercomposetemplate .dockerignore; do
  [[ -f "$SCRIPT_DIR/$template" ]] || die "Template ausente: $template"
done
for file in .env "nginx/nginx_${PROJECT_ID}.conf" Dockerfile docker-compose.yml .dockerignore; do
  [[ -f "$PROJECT_DIR/$file" ]] || die "Arquivo do projeto ausente: $file"
done

get_env_value() {
  local key="$1"
  local file="$2"
  local assignment_count canonical_count value
  assignment_count="$(grep -Ec "^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*=" "$file" || true)"
  canonical_count="$(grep -c "^${key}=" "$file" || true)"
  [[ "$assignment_count" == "1" && "$canonical_count" == "1" ]] \
    || die "$key deve ter exatamente uma atribuicao canonica em $file"
  value="$(sed -n "s/^${key}=//p" "$file")"
  [[ "$value" != *$'\r'* && -n "$value" && "$value" == "${value# }" && "$value" == "${value% }" ]] \
    || die "$key possui valor nao canonico em $file"
  printf '%s' "$value"
}

replace_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  local escaped_value
  escaped_value=$(escape_sed_replacement "$value")
  get_env_value "$key" "$file" >/dev/null
  sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
}

JWT_SECRET_PROJETO=$(get_env_value "JWT_SECRET_PROJETO" "$PROJECT_DIR/.env")
PROJECT_UUID=$(get_env_value "PROJECT_UUID" "$PROJECT_DIR/.env")
PROJECT_PUBLIC_REF="$(project_public_ref_read "$PROJECT_DIR/.env")" \
  || die "Referencia publica ausente ou invalida"
API_GATEWAY_TOKEN_PROJETO=$(get_env_value "API_GATEWAY_TOKEN_PROJETO" "$PROJECT_DIR/.env")
CURRENT_ANON=$(get_env_value "ANON_KEY_PROJETO" "$PROJECT_DIR/.env")
CURRENT_SERVICE=$(get_env_value "SERVICE_ROLE_KEY_PROJETO" "$PROJECT_DIR/.env")
S3_PROTOCOL_CREDENTIAL_ID=$(get_env_value "S3_PROTOCOL_CREDENTIAL_ID" "$PROJECT_DIR/.env")
S3_PROTOCOL_ACCESS_KEY_ID=$(get_env_value "S3_PROTOCOL_ACCESS_KEY_ID" "$PROJECT_DIR/.env")
S3_PROTOCOL_ACCESS_KEY_SECRET=$(get_env_value "S3_PROTOCOL_ACCESS_KEY_SECRET" "$PROJECT_DIR/.env")
S3_PROTOCOL_ENABLED=$(get_env_value "S3_PROTOCOL_ENABLED" "$PROJECT_DIR/.env")
VECTOR_BUCKETS_ENABLED=$(get_env_value "VECTOR_BUCKETS_ENABLED" "$PROJECT_DIR/.env")
PROJECT_UUID="$(tr '[:upper:]' '[:lower:]' <<<"$PROJECT_UUID")"
project_public_ref_assert "$PROJECT_ID" "$PROJECT_UUID" "$PROJECT_PUBLIC_REF" \
  || die "Referencia publica diverge do control plane"

[[ "$JWT_SECRET_PROJETO" =~ ^[A-Za-z0-9_-]{43}=?$ ]] \
  || die "JWT_SECRET_PROJETO invalido"
[[ "$PROJECT_UUID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] \
  || die "PROJECT_UUID invalido"
[[ "$API_GATEWAY_TOKEN_PROJETO" =~ ^[a-f0-9]{64}$ ]] \
  || die "API_GATEWAY_TOKEN_PROJETO ausente ou invalido"
[[ "$CURRENT_ANON" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]] \
  || die "ANON_KEY_PROJETO atual invalida"
[[ "$CURRENT_SERVICE" =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]] \
  || die "SERVICE_ROLE_KEY_PROJETO atual invalida"
export PROJECT_UUID S3_PROTOCOL_CREDENTIAL_ID S3_PROTOCOL_ACCESS_KEY_ID \
  S3_PROTOCOL_ACCESS_KEY_SECRET VECTOR_BUCKETS_ENABLED
storage_validate_bool VECTOR_BUCKETS_ENABLED "$VECTOR_BUCKETS_ENABLED" \
  || die "VECTOR_BUCKETS_ENABLED invalido"
storage_validate_bool S3_PROTOCOL_ENABLED "$S3_PROTOCOL_ENABLED" \
  || die "S3_PROTOCOL_ENABLED invalido"
vector_validate_s3_credentials || die "Credenciais SigV4 do projeto invalidas"
storage_assert_project_identity "$PROJECT_ID" "$PROJECT_UUID" \
  || die "Identidade Storage diverge do control plane"
storage_wait_global || die "Storage compartilhado indisponivel"

generate_jwt() {
  local payload="$1" secret="$2"
  local header='{"alg":"HS256","typ":"JWT"}'
  b64() { printf '%s' "$1" | openssl base64 -A | tr '+/' '-_' | tr -d '='; }
  local h p sig
  h=$(b64 "$header"); p=$(b64 "$payload")
  sig=$(printf '%s' "$h.$p" | openssl dgst -binary -sha256 -hmac "$secret" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  echo "$h.$p.$sig"
}

normalize_public_base_url() {
  local url="${1%/}"
  local proto="${2:-}"
  if [[ "$url" =~ ^https?:// ]]; then
    echo "$url"
    return
  fi
  [[ "$proto" == "http" || "$proto" == "https" ]] || \
    die "SERVER_PROTO deve ser http ou https quando SERVER_URL nao inclui esquema"
  url="${proto}://$url"
  echo "$url"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

now=$(date +%s)
exp=$((now + (3 * 30 * 24 * 3600)))
anon_jti=$(openssl rand -hex 16)
service_jti=$(openssl rand -hex 16)
PREVIOUS_JWT_SECRET="$JWT_SECRET_PROJETO"
GLOBAL_API_TOKEN=""

if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
  [[ -n "${JWT_SECRET:-}" ]] || die "JWT_SECRET global ausente para atualizar o Realtime"
  JWT_SECRET_PROJETO="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
  SERVICES_TO_RECREATE=(auth rest nginx)
  GLOBAL_API_TOKEN="$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"supabase\",\"iat\":$now,\"exp\":$((now + 300))}" "$JWT_SECRET")"
  echo "🔄 Gerando novo JWT_SECRET_PROJETO e novos tokens para projeto $PROJECT_ID..."
else
  echo "🔄 Gerando novos tokens para projeto $PROJECT_ID..."
fi
echo "   Usando issuer: $PROJECT_UUID"

echo "HOST_AGENT_PROGRESS=rotate:generate_tokens"
NEW_ANON=$(generate_jwt    "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp,\"jti\":\"$anon_jti\"}"         "$JWT_SECRET_PROJETO")
NEW_SERVICE=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp,\"jti\":\"$service_jti\"}" "$JWT_SECRET_PROJETO")
PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$PROJECT_PUBLIC_REF"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"

template_to_file() {
  local template="$1" outfile="$2"
  local anon_key service_role_key project_id project_uuid jwt_secret
  local server_url public_base_url project_public_url project_auth_external_url project_root

  anon_key="$(escape_sed_replacement "$NEW_ANON")"
  service_role_key="$(escape_sed_replacement "$NEW_SERVICE")"
  project_id="$(escape_sed_replacement "$PROJECT_ID")"
  project_uuid="$(escape_sed_replacement "$PROJECT_UUID")"
  jwt_secret="$(escape_sed_replacement "$JWT_SECRET_PROJETO")"
  server_url="$(escape_sed_replacement "$SERVER_URL")"
  public_base_url="$(escape_sed_replacement "$PUBLIC_BASE_URL")"
  project_public_url="$(escape_sed_replacement "$PROJECT_PUBLIC_URL")"
  project_auth_external_url="$(escape_sed_replacement "$PROJECT_AUTH_EXTERNAL_URL")"
  project_root="$(escape_sed_replacement "$HOST_PROJECT_ROOT")"

  sed \
    -e "s|{{anon_key}}|$anon_key|g" \
    -e "s|{{service_role_key}}|$service_role_key|g" \
    -e "s|{{project_id}}|$project_id|g" \
    -e "s|{{project_uuid}}|$project_uuid|g" \
    -e "s|{{project_public_ref}}|$PROJECT_PUBLIC_REF|g" \
    -e "s|{{jwt_secret}}|$jwt_secret|g" \
    -e "s|{{api_gateway_token}}|$(escape_sed_replacement "$API_GATEWAY_TOKEN_PROJETO")|g" \
    -e "s|{{server_url}}|$server_url|g" \
    -e "s|{{public_base_url}}|$public_base_url|g" \
    -e "s|{{project_public_url}}|$project_public_url|g" \
    -e "s|{{project_auth_external_url}}|$project_auth_external_url|g" \
    -e "s|{{project_root}}|$project_root|g" \
    "$template" > "$outfile"
}

functions_config_withdraw "$PROJECT_ID"
init_transaction

echo "HOST_AGENT_PROGRESS=rotate:configure_storage"
if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
  storage_patch_tenant_keys "$PROJECT_UUID" "$NEW_ANON" "$NEW_SERVICE" "$JWT_SECRET_PROJETO" \
    || die "Storage nao aceitou o novo JWT_SECRET e os novos JWTs internos"
else
  storage_patch_tenant_keys "$PROJECT_UUID" "$NEW_ANON" "$NEW_SERVICE" \
    || die "Storage nao aceitou os novos JWTs internos"
fi
STORAGE_KEYS_UPDATED=true

if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
  realtime_patch_tenant_jwt_secret "$PROJECT_UUID" "$JWT_SECRET_PROJETO" "$GLOBAL_API_TOKEN" \
    || die "Realtime nao aceitou o novo JWT_SECRET_PROJETO"
  REALTIME_JWT_UPDATED=true
fi

backup_file "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
backup_file "$PROJECT_DIR/Dockerfile"
backup_file "$PROJECT_DIR/docker-compose.yml"
backup_file "$PROJECT_DIR/.env"
backup_file "$PROJECT_DIR/.dockerignore"

echo "HOST_AGENT_PROGRESS=rotate:render_files"
template_to_file "$SCRIPT_DIR/nginxtemplate" "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
template_to_file "$SCRIPT_DIR/Dockerfile" "$PROJECT_DIR/Dockerfile"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$PROJECT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/.dockerignore" "$PROJECT_DIR/.dockerignore"
chmod 600 "$PROJECT_DIR/.env"
apply_project_resource_limits "$PROJECT_ROOT/.env" "$PROJECT_DIR/.env" "${PROJECT_RESOURCE_PROFILE_OVERRIDE:-}"
chmod 644 "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf" "$PROJECT_DIR/.dockerignore"

if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
  replace_env_value "JWT_SECRET_PROJETO" "$JWT_SECRET_PROJETO" "$PROJECT_DIR/.env"
fi
if ! grep -q '^PROJECT_INTERNAL_SUBNET=' "$PROJECT_DIR/.env"; then
  PROJECT_INTERNAL_SUBNET="$(python3 "$SCRIPT_DIR/allocate_project_subnet.py" "$PROJECT_ID" "$PROJECT_ROOT/projects")" \
    || die "Falha ao alocar subnet interna do projeto"
  printf '\nPROJECT_INTERNAL_SUBNET=%s\n' "$PROJECT_INTERNAL_SUBNET" >> "$PROJECT_DIR/.env"
fi
replace_env_value "ANON_KEY_PROJETO" "$NEW_ANON" "$PROJECT_DIR/.env"
replace_env_value "SERVICE_ROLE_KEY_PROJETO" "$NEW_SERVICE" "$PROJECT_DIR/.env"

echo "HOST_AGENT_PROGRESS=rotate:restart_services"
cd "$PROJECT_DIR"
docker compose -p "$PROJECT_ID" \
  --env-file ../../.env \
  --env-file .env \
  up --build -d "${SERVICES_TO_RECREATE[@]}"

echo "HOST_AGENT_PROGRESS=rotate:verify_storage"
storage_validate_tenant "$PROJECT_UUID" "$NEW_SERVICE" \
  "$S3_PROTOCOL_ACCESS_KEY_ID" "$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  "$S3_PROTOCOL_ENABLED" "$VECTOR_BUCKETS_ENABLED" \
  || die "Tenant Storage falhou apos rotacao de JWTs"
storage_assert_project_gateway "$PROJECT_UUID" "$PROJECT_ID" "$NEW_SERVICE" \
  || die "Nginx nao encaminhou os novos JWTs ao tenant Storage"

echo ""
echo "✅ Tokens rotacionados com sucesso para projeto $PROJECT_ID"
echo ""
if [[ "$ROTATE_JWT_SECRET" == "true" ]]; then
  echo "🔐 JWT_SECRET_PROJETO rotacionado; sessoes e JWTs anteriores foram invalidados."
else
  echo "⚠️  NOTA: O JWT_SECRET_PROJETO não foi alterado"
  echo "   Apenas os tokens foram regenerados com o mesmo secret."
fi

echo "HOST_AGENT_PROGRESS=rotate:publish_configuration"
functions_config_publish "$PROJECT_ID"
commit_transaction
