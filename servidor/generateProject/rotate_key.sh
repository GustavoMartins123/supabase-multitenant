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
  echo "❌ Erro detectado! Revertendo alterações..."
  
  if [[ -d "$TRANSACTION_DIR" ]]; then
    for file in "${MODIFIED_FILES[@]}"; do
      local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
      if [[ -f "$backup_path" ]]; then
        cp "$backup_path" "$file"
        echo "   Restaurado: $(basename "$file")"
      fi
    done
    rm -rf "$TRANSACTION_DIR"
    echo "⚠️  Todas as alterações foram revertidas."
  fi
  
  exit 1
}

trap rollback_transaction ERR

set -a
source "$PROJECT_ROOT/secrets/.env"
source "$PROJECT_ROOT/.env"
set +a

[[ -z "${SERVER_URL:-}" ]] && die "SERVER_URL ausente"
[[ -z "${HOST_PROJECT_ROOT:-}" ]] && die "HOST_PROJECT_ROOT ausente"

PROJECT_ID="${1:-}"

[[ -z "$PROJECT_ID" ]] && die "Uso: $0 <project_id>"

PROJECT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
[[ -d "$PROJECT_DIR" ]] || die "Projeto '$PROJECT_ID' não encontrado em $PROJECT_DIR"

get_env_value() {
  local key="$1"
  local file="$2"
  local value
  value=$(grep -m1 "^${key}=" "$file" | cut -d'=' -f2- || true)
  printf '%s' "$value"
}

upsert_env_value() {
  local key="$1"
  local value="$2"
  local file="$3"
  local escaped_value
  escaped_value=$(escape_sed_replacement "$value")

  if grep -q "^${key}=" "$file"; then
    sed -i "s|^${key}=.*|${key}=${escaped_value}|" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$file"
  fi
}

NGINX_PORT=$(get_env_value "NGINX_PORT" "$PROJECT_DIR/.env")
META_PORT=$(get_env_value "META_PORT" "$PROJECT_DIR/.env")
CONFIG_TOKEN=$(get_env_value "CONFIG_TOKEN_PROJETO" "$PROJECT_DIR/.env")
JWT_SECRET_PROJETO=$(get_env_value "JWT_SECRET_PROJETO" "$PROJECT_DIR/.env")
PROJECT_UUID=$(get_env_value "PROJECT_UUID" "$PROJECT_DIR/.env")

[[ -z "$NGINX_PORT" ]] && die "NGINX_PORT não encontrado no .env do projeto"
[[ -z "$META_PORT" ]]  && die "META_PORT não encontrado no .env do projeto"
[[ -z "$CONFIG_TOKEN" ]] && die "CONFIG_TOKEN_PROJETO não encontrado no .env do projeto"
[[ -z "$JWT_SECRET_PROJETO" ]]  && die "JWT_SECRET_PROJETO não encontrado no .env do projeto"

MIGRATE_PROJECT_UUID=false
if [[ -z "$PROJECT_UUID" ]]; then
    echo "⚠️  PROJECT_UUID não encontrado no .env - usando PROJECT_ID como fallback (projeto antigo)"
    PROJECT_UUID="$PROJECT_ID"
    MIGRATE_PROJECT_UUID=true
fi

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
  [[ "$url" =~ ^https?:// ]] || url="https://$url"
  echo "$url"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|\\]/\\&/g'
}

now=$(date +%s)
exp=$((now + (3 * 30 * 24 * 3600)))

echo "🔄 Gerando novos tokens para projeto $PROJECT_ID..."
echo "   Usando issuer: $PROJECT_UUID"

NEW_ANON=$(generate_jwt    "{\"role\":\"anon\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp}"         "$JWT_SECRET_PROJETO")
NEW_SERVICE=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_UUID\",\"iat\":$now,\"exp\":$exp}" "$JWT_SECRET_PROJETO")
PUBLIC_BASE_URL="$(normalize_public_base_url "$SERVER_URL")"
PROJECT_PUBLIC_URL="$PUBLIC_BASE_URL/$PROJECT_ID"

template_to_file() {
  local template="$1" outfile="$2"
  local anon_key service_role_key project_id project_uuid nginx_port meta_port config_token jwt_secret
  local server_url public_base_url project_public_url

  anon_key="$(escape_sed_replacement "$NEW_ANON")"
  service_role_key="$(escape_sed_replacement "$NEW_SERVICE")"
  project_id="$(escape_sed_replacement "$PROJECT_ID")"
  project_uuid="$(escape_sed_replacement "$PROJECT_UUID")"
  nginx_port="$(escape_sed_replacement "$NGINX_PORT")"
  meta_port="$(escape_sed_replacement "$META_PORT")"
  config_token="$(escape_sed_replacement "$CONFIG_TOKEN")"
  jwt_secret="$(escape_sed_replacement "$JWT_SECRET_PROJETO")"
  server_url="$(escape_sed_replacement "$SERVER_URL")"
  public_base_url="$(escape_sed_replacement "$PUBLIC_BASE_URL")"
  project_public_url="$(escape_sed_replacement "$PROJECT_PUBLIC_URL")"

  sed \
    -e "s|{{anon_key}}|$anon_key|g" \
    -e "s|{{service_role_key}}|$service_role_key|g" \
    -e "s|{{project_id}}|$project_id|g" \
    -e "s|{{project_uuid}}|$project_uuid|g" \
    -e "s|{{nginx_port}}|$nginx_port|g" \
    -e "s|{{meta_port}}|$meta_port|g" \
    -e "s|{{config_token}}|$config_token|g" \
    -e "s|{{jwt_secret}}|$jwt_secret|g" \
    -e "s|{{server_url}}|$server_url|g" \
    -e "s|{{public_base_url}}|$public_base_url|g" \
    -e "s|{{project_public_url}}|$project_public_url|g" \
    "$template" > "$outfile"
}

init_transaction

backup_file "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
backup_file "$PROJECT_DIR/.env"

template_to_file "$SCRIPT_DIR/nginxtemplate" "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"

upsert_env_value "ANON_KEY_PROJETO" "$NEW_ANON" "$PROJECT_DIR/.env"
upsert_env_value "SERVICE_ROLE_KEY_PROJETO" "$NEW_SERVICE" "$PROJECT_DIR/.env"

if [[ "$MIGRATE_PROJECT_UUID" == "true" ]]; then
  upsert_env_value "PROJECT_UUID" "$PROJECT_UUID" "$PROJECT_DIR/.env"
  echo "🛠️  Projeto legado migrado: PROJECT_UUID=$PROJECT_UUID gravado no .env"
fi

cd "$PROJECT_DIR"
docker compose -p "$PROJECT_ID" \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up --build -d nginx

echo ""
echo "✅ Tokens rotacionados com sucesso para projeto $PROJECT_ID"
echo ""
echo "ANON_KEY_PROJETO=$NEW_ANON"
echo "SERVICE_ROLE_KEY_PROJETO=$NEW_SERVICE"
echo ""
echo "⚠️  NOTA: O JWT_SECRET_PROJETO não foi alterado"
echo "   Apenas os tokens foram regenerados com o mesmo secret."

commit_transaction
