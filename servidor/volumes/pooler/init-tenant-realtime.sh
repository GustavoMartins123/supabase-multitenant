#!/usr/bin/env sh
set -e

TENANT_URL="http://realtime-dev.supabase-realtime-${PROJECT_ID}:4000/api/tenants/${PROJECT_ID}"

echo "⏳ Aguardando Realtime responder (tenant health)..."
until curl -sSL --head -o /dev/null \
  -H "Authorization: Bearer ${ANON_KEY_PROJETO}" \
  "${TENANT_URL}/health"
do
  sleep 1
done

STATUS=$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer ${ANON_KEY_PROJETO}" \
  "${TENANT_URL}/health")

# Se não existir, injeta
if [ "$STATUS" -ge 400 ]; then
  echo "🚀 Injetando tenant ${PROJECT_ID} (status=$STATUS)…"

  PAYLOAD=$(cat <<EOF
{
  "tenant": {
    "name": "${PROJECT_ID}",
    "external_id": "${PROJECT_ID}",
    "jwt_secret": "${API_JWT_SECRET}",
    "extensions": [{
      "type": "postgres_cdc_rls",
      "settings": {
        "db_name": "${POSTGRES_DATABASE}",
        "db_host": "${POSTGRES_HOST}",
        "db_user": "${POSTGRES_USER}",
        "db_password": "${POSTGRES_PASSWORD}",
        "db_port": "${POSTGRES_PORT}",
        "region": "us-west-1",
        "poll_interval_ms": 100,
        "poll_max_record_bytes": 1048576,
        "ssl_enforced": false
      }
    }]
  }
}
EOF
)
  curl -s -X POST \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ANON_KEY_PROJETO}" \
    -d "$PAYLOAD" \
    "http://realtime-dev.supabase-realtime-${PROJECT_ID}:4000/api/tenants"

  echo "✅ Tenant ${PROJECT_ID} criado!"
else
  echo "✅ Tenant ${PROJECT_ID} já existe (status=$STATUS). Nada a fazer."
fi