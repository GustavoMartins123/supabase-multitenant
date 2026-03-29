#!/usr/bin/env bash
set -euo pipefail

die() { echo "❌ $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Diretório temporário para transações
TRANSACTION_DIR="$PROJECT_ROOT/.rotate_transaction_$$"
MODIFIED_FILES=()

# Inicializa o sistema de transação
init_transaction() {
  mkdir -p "$TRANSACTION_DIR"
  echo "🔄 Sistema de transação inicializado"
}

# Faz backup de um arquivo antes de modificá-lo
backup_file() {
  local file="$1"
  if [[ -f "$file" ]]; then
    local backup_path="$TRANSACTION_DIR/$(echo "$file" | tr '/' '_')"
    cp "$file" "$backup_path"
    MODIFIED_FILES+=("$file")
    echo "   Backup criado: $(basename "$file")"
  fi
}

# Commit: remove backups após sucesso
commit_transaction() {
  if [[ -d "$TRANSACTION_DIR" ]]; then
    rm -rf "$TRANSACTION_DIR"
    echo "✅ Transação confirmada. Backups removidos."
  fi
}

# Rollback: restaura todos os arquivos modificados
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

# Trap para capturar erros e fazer rollback
trap rollback_transaction ERR

set -a
source "$PROJECT_ROOT/secrets/.env"
source "$PROJECT_ROOT/.env"
set +a

PROJECT_ID="${1:-}"
[[ -z "$PROJECT_ID" ]] && die "Uso: $0 <project_id>"

PROJECT_DIR="$PROJECT_ROOT/projects/$PROJECT_ID"
[[ -d "$PROJECT_DIR" ]] || die "Projeto '$PROJECT_ID' não encontrado"

source "$PROJECT_DIR/.env"
NGINX_PORT="${NGINX_PORT:-}"
META_PORT="${META_PORT:-}"
CONFIG_TOKEN="${CONFIG_TOKEN_PROJETO:-}"
[[ -z "$NGINX_PORT" ]] && die "NGINX_PORT não encontrado no .env do projeto"
[[ -z "$META_PORT" ]]  && die "META_PORT não encontrado no .env do projeto"

generate_jwt() {
  local payload="$1" secret="$2"
  local header='{"alg":"HS256","typ":"JWT"}'
  b64() { printf '%s' "$1" | openssl base64 -A | tr '+/' '-_' | tr -d '='; }
  local h p sig
  h=$(b64 "$header"); p=$(b64 "$payload")
  sig=$(printf '%s' "$h.$p" | openssl dgst -binary -sha256 -hmac "$secret" | openssl base64 -A | tr '+/' '-_' | tr -d '=')
  echo "$h.$p.$sig"
}

now=$(date +%s)
exp=$((now + (8 * 365 * 24 * 3600)))

NEW_ANON=$(generate_jwt    "{\"role\":\"anon\",\"iss\":\"$PROJECT_ID\",\"iat\":$now,\"exp\":$exp}"         "$JWT_SECRET_PROJETO")
NEW_SERVICE=$(generate_jwt "{\"role\":\"service_role\",\"iss\":\"$PROJECT_ID\",\"iat\":$now,\"exp\":$exp}" "$JWT_SECRET_PROJETO")

# Inicializa transação
init_transaction

# Backup dos arquivos que serão modificados
backup_file "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"
backup_file "$PROJECT_DIR/.env"

sed \
  -e "s|{{anon_key}}|$NEW_ANON|g" \
  -e "s|{{service_role_key}}|$NEW_SERVICE|g" \
  -e "s|{{project_id}}|$PROJECT_ID|g" \
  -e "s|{{nginx_port}}|$NGINX_PORT|g" \
  -e "s|{{meta_port}}|$META_PORT|g" \
  -e "s|{{config_token}}|$CONFIG_TOKEN|g" \
  -e "s|{{server_url}}|$SERVER_URL|g" \
  "$SCRIPT_DIR/nginxtemplate" > "$PROJECT_DIR/nginx/nginx_${PROJECT_ID}.conf"

sed -i "s|^ANON_KEY_PROJETO=.*|ANON_KEY_PROJETO=$NEW_ANON|"             "$PROJECT_DIR/.env"
sed -i "s|^SERVICE_ROLE_KEY_PROJETO=.*|SERVICE_ROLE_KEY_PROJETO=$NEW_SERVICE|" "$PROJECT_DIR/.env"

cd "$PROJECT_DIR"
docker compose -p "$PROJECT_ID" \
  --env-file ../../secrets/.env \
  --env-file ../../.env \
  --env-file .env \
  up --build -d nginx

echo "ANON_KEY_PROJETO=$NEW_ANON"
echo "SERVICE_ROLE_KEY_PROJETO=$NEW_SERVICE"

# Commit da transação - tudo deu certo
commit_transaction