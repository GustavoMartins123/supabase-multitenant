#!/usr/bin/env bash
set -euo pipefail

die() { echo "❌ $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

TRANSACTION_DIR="$PROJECT_ROOT/.rotate_transaction_$$"
MODIFIED_FILES=()

init_transaction() {
  mkdir -p "$TRANSACTION_DIR"
  echo "🔄 Sistema de transação inicializado"
}

backup_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
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

rollback_transaction() {
  trap - ERR
  set +e
  local runtime_restored=true
  echo "❌ Erro detectado! Revertendo alterações..."
  
  if [[ -d "$TRANSACTION_DIR" ]]; then
    for file in "${MODIFIED_FILES[@]}"; do
      local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
      if [[ -f "$backup_path" ]]; then
        cp "$backup_path" "$file"
        echo "   Restaurado: $(basename "$file")"
      fi
    done
    if [[ -n "${PROJECT_DIR:-}" && -d "$PROJECT_DIR" && -f "$PROJECT_DIR/docker-compose.yml" ]]; then
      if (
        cd "$PROJECT_DIR" &&
        docker compose -p "$PROJECT_ID" \
          --env-file ../../.env \
          --env-file .env \
          up --build -d nginx
      ); then
        echo "   Runtime do Nginx restaurado com a configuração anterior."
      else
        runtime_restored=false
        echo "❌ Arquivos restaurados, mas o runtime anterior do Nginx não pôde ser confirmado." >&2
      fi
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

PROJECT_ID="${1:-}"

[[ -z "$PROJECT_ID" ]] && die "Uso: $0 <project_id>"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || die "PROJECT_ID invalido"

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

CONFIG_TOKEN=$(get_env_value "CONFIG_TOKEN_PROJETO" "$PROJECT_DIR/.env")
JWT_SECRET_PROJETO=$(get_env_value "JWT_SECRET_PROJETO" "$PROJECT_DIR/.env")
PROJECT_UUID=$(get_env_value "PROJECT_UUID" "$PROJECT_DIR/.env")
API_GATEWAY_TOKEN_PROJETO=$(get_env_value "API_GATEWAY_TOKEN_PROJETO" "$PROJECT_DIR/.env")
CURRENT_ANON=$(get_env_value "ANON_KEY_PROJETO" "$PROJECT_DIR/.env")
CURRENT_SERVICE=$(get_env_value "SERVICE_ROLE_KEY_PROJETO" "$PROJECT_DIR/.env")

[[ "$CONFIG_TOKEN" =~ ^[a-f0-9]{64}$ ]] \
  || die "CONFIG_TOKEN_PROJETO invalido"
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

echo "🔄 Gerando novos tokens para projeto $PROJECT_ID..."
echo "   Usando issuer: $PROJECT_UUID"

NEW_ANON=$(generate_jwt    "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp,\"jti\":\"$anon_jti\"}"         "$JWT_SECRET_PROJETO")
NEW_SERVICE=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp,\"jti\":\"$service_jti\"}" "$JWT_SECRET_PROJETO")
PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL" "${SERVER_PROTO:-}")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$PROJECT_ID"
PROJECT_AUTH_EXTERNAL_URL="$PROJECT_PUBLIC_URL/auth/v1"

template_to_file() {
  local template="$1" outfile="$2"
  local anon_key service_role_key project_id project_uuid config_token jwt_secret
  local server_url public_base_url project_public_url project_auth_external_url project_root

  anon_key="$(escape_sed_replacement "$NEW_ANON")"
  service_role_key="$(escape_sed_replacement "$NEW_SERVICE")"
  project_id="$(escape_sed_replacement "$PROJECT_ID")"
  project_uuid="$(escape_sed_replacement "$PROJECT_UUID")"
  config_token="$(escape_sed_replacement "$CONFIG_TOKEN")"
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
    -e "s|{{config_token}}|$config_token|g" \
    -e "s|{{jwt_secret}}|$jwt_secret|g" \
    -e "s|{{api_gateway_token}}|$(escape_sed_replacement "$API_GATEWAY_TOKEN_PROJETO")|g" \
    -e "s|{{server_url}}|$server_url|g" \
    -e "s|{{public_base_url}}|$public_base_url|g" \
    -e "s|{{project_public_url}}|$project_public_url|g" \
    -e "s|{{project_auth_external_url}}|$project_auth_external_url|g" \
    -e "s|{{project_root}}|$project_root|g" \
    "$template" > "$outfile"
}

init_transaction

backup_file "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
backup_file "$PROJECT_DIR/Dockerfile"
backup_file "$PROJECT_DIR/docker-compose.yml"
backup_file "$PROJECT_DIR/.env"
backup_file "$PROJECT_DIR/.dockerignore"

template_to_file "$SCRIPT_DIR/nginxtemplate" "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
template_to_file "$SCRIPT_DIR/Dockerfile" "$PROJECT_DIR/Dockerfile"
template_to_file "$SCRIPT_DIR/dockercomposetemplate" "$PROJECT_DIR/docker-compose.yml"
template_to_file "$SCRIPT_DIR/.dockerignore" "$PROJECT_DIR/.dockerignore"
chmod 600 "$PROJECT_DIR/.env"
chmod 644 "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf" "$PROJECT_DIR/.dockerignore"

replace_env_value "ANON_KEY_PROJETO" "$NEW_ANON" "$PROJECT_DIR/.env"
replace_env_value "SERVICE_ROLE_KEY_PROJETO" "$NEW_SERVICE" "$PROJECT_DIR/.env"

cd "$PROJECT_DIR"
docker compose -p "$PROJECT_ID" \
  --env-file ../../.env \
  --env-file .env \
  up --build -d nginx

echo ""
echo "✅ Tokens rotacionados com sucesso para projeto $PROJECT_ID"
echo ""
echo "⚠️  NOTA: O JWT_SECRET_PROJETO não foi alterado"
echo "   Apenas os tokens foram regenerados com o mesmo secret."

commit_transaction
