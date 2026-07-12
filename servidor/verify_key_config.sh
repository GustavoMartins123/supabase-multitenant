#!/usr/bin/env bash
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SERVER_DIR")"
SERVER_ENV="$SERVER_DIR/.env"
ANALYTICS_ENV="$SERVER_DIR/.analytics.env"
STUDIO_ENV="$ROOT_DIR/studio/.env"
STUDIO_ANALYTICS_ENV="$ROOT_DIR/studio/.analytics.env"

fail() { echo "ERRO: $*" >&2; exit 1; }
ok() { echo "OK: $*"; }

env_value() {
  local file="$1" key="$2"
  sed -n "s/^${key}=//p" "$file" | head -n1
}

[[ -f "$SERVER_ENV" ]] || fail "servidor/.env não encontrado"
[[ -f "$ANALYTICS_ENV" ]] || fail "servidor/.analytics.env não encontrado"
[[ -f "$STUDIO_ENV" ]] || fail "studio/.env não encontrado"
[[ -f "$STUDIO_ANALYTICS_ENV" ]] || fail "studio/.analytics.env não encontrado"

server_transport_key="$(env_value "$SERVER_ENV" STUDIO_SERVICE_KEY_ENCRYPTION_KEY)"
studio_transport_key="$(env_value "$STUDIO_ENV" STUDIO_SERVICE_KEY_ENCRYPTION_KEY)"
[[ "$server_transport_key" =~ ^[A-Za-z0-9_-]{43}=$ ]] \
  || fail "STUDIO_SERVICE_KEY_ENCRYPTION_KEY inválida no servidor"
[[ "$studio_transport_key" =~ ^[A-Za-z0-9_-]{43}=$ ]] \
  || fail "STUDIO_SERVICE_KEY_ENCRYPTION_KEY inválida no Studio"
[[ "$server_transport_key" == "$studio_transport_key" ]] \
  || fail "STUDIO_SERVICE_KEY_ENCRYPTION_KEY diverge entre servidor e Studio"

for key in NGINX_SHARED_TOKEN NGINX_HMAC_SECRET INTERNAL_HMAC_SECRET; do
  server_value="$(env_value "$SERVER_ENV" "$key")"
  studio_value="$(env_value "$STUDIO_ENV" "$key")"
  [[ -n "$server_value" && "$server_value" == "$studio_value" ]] \
    || fail "$key ausente ou divergente entre servidor e Studio"
done
ok "segredos compartilhados estão presentes e consistentes"

logflare_public="$(env_value "$ANALYTICS_ENV" LOGFLARE_PUBLIC_ACCESS_TOKEN)"
logflare_private="$(env_value "$ANALYTICS_ENV" LOGFLARE_PRIVATE_ACCESS_TOKEN)"
logflare_encryption="$(env_value "$ANALYTICS_ENV" LOGFLARE_DB_ENCRYPTION_KEY)"
studio_logflare_private="$(env_value "$STUDIO_ANALYTICS_ENV" LOGFLARE_PRIVATE_ACCESS_TOKEN)"
[[ ${#logflare_public} -ge 32 ]] \
  || fail "LOGFLARE_PUBLIC_ACCESS_TOKEN ausente ou curto"
[[ ${#logflare_private} -ge 32 ]] \
  || fail "LOGFLARE_PRIVATE_ACCESS_TOKEN ausente ou curto"
[[ "$logflare_public" != "$logflare_private" ]] \
  || fail "tokens publico e privado do Logflare devem ser distintos"
[[ "$logflare_private" == "$studio_logflare_private" ]] \
  || fail "LOGFLARE_PRIVATE_ACCESS_TOKEN diverge entre servidor e Studio"
[[ "$logflare_encryption" =~ ^[A-Za-z0-9+/]{43}=$ ]] \
  || fail "LOGFLARE_DB_ENCRYPTION_KEY deve ser uma chave Base64 de 32 bytes"
ok "tokens do Supabase Analytics estao presentes, distintos e consistentes"

shopt -s nullglob
for project_env in "$SERVER_DIR"/projects/*/.env; do
  project_dir="$(dirname "$project_env")"
  project_name="$(basename "$project_dir")"
  for key in PROJECT_UUID ANON_KEY_PROJETO SERVICE_ROLE_KEY_PROJETO \
    CONFIG_TOKEN_PROJETO JWT_SECRET_PROJETO; do
    [[ -n "$(env_value "$project_env" "$key")" ]] \
      || fail "$project_name: $key ausente"
  done

  config_token="$(env_value "$project_env" CONFIG_TOKEN_PROJETO)"
  [[ "$config_token" =~ ^[0-9a-f]{64}$ ]] \
    || fail "$project_name: CONFIG_TOKEN_PROJETO fora do formato esperado"

  anon_key="$(env_value "$project_env" ANON_KEY_PROJETO)"
  service_key="$(env_value "$project_env" SERVICE_ROLE_KEY_PROJETO)"
  [[ "$anon_key" == *.*.* ]] || fail "$project_name: anon key não é JWT"
  [[ "$service_key" == *.*.* ]] || fail "$project_name: service role não é JWT"

  nginx_config="$project_dir/nginx/nginx_${project_name}.conf"
  [[ -f "$nginx_config" ]] || fail "$project_name: configuração Nginx ausente"
  grep -Fq "$config_token" "$nginx_config" \
    || fail "$project_name: config token não foi renderizado no Nginx"
  grep -Fq "$service_key" "$nginx_config" \
    || fail "$project_name: service role não foi renderizada no Nginx"
  ok "$project_name: chaves e templates consistentes"
done

ok "verificação concluída sem expor valores secretos"
