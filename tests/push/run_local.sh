#!/usr/bin/env bash
# Fully local integration: ephemeral DBs, four nginx workers, real TLS/JWT;
# Google HTTP is mocked. Internal Docker network blocks external connectivity.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
PUSH_TEST_ROOT=$(mktemp -d /tmp/supabase-push-test.XXXXXX)
PUSH_TEST_SUFFIX="$$"
PUSH_TEST_NETWORK="supabase-push-test-$PUSH_TEST_SUFFIX"
PUSH_TEST_PG="supabase-push-pg-$PUSH_TEST_SUFFIX"
PUSH_TEST_NGINX="supabase-push-nginx-$PUSH_TEST_SUFFIX"
PUSH_PG_IMAGE=${PUSH_PG_IMAGE:-postgres:15}
PUSH_NGINX_IMAGE=${PUSH_NGINX_IMAGE:-supabase-studio-nginx}
PUSH_PYTHON_IMAGE=${PUSH_PYTHON_IMAGE:-servidor-projects-api}
cleanup() {
  docker rm -f "$PUSH_TEST_NGINX" "$PUSH_TEST_PG" >/dev/null 2>&1 || true
  docker network rm "$PUSH_TEST_NETWORK" >/dev/null 2>&1 || true
  rm -rf -- "$PUSH_TEST_ROOT"
}
trap cleanup EXIT
for image in "$PUSH_PG_IMAGE" "$PUSH_NGINX_IMAGE" "$PUSH_PYTHON_IMAGE"; do
  docker image inspect "$image" >/dev/null
 done
mkdir -p "$PUSH_TEST_ROOT/config"
git -C "$ROOT" show dc02ebb:studio/nginx/lua/send_push.lua > "$PUSH_TEST_ROOT/send_push_before.lua"
docker network create --internal "$PUSH_TEST_NETWORK" >/dev/null
docker run -d --name "$PUSH_TEST_PG" --network "$PUSH_TEST_NETWORK" \
  -e POSTGRES_HOST_AUTH_METHOD=trust "$PUSH_PG_IMAGE" >/dev/null
docker run -d --name "$PUSH_TEST_NGINX" --network "$PUSH_TEST_NETWORK" \
  -e INTERNAL_HMAC_SECRET=internal-test-secret -v "$ROOT:/workspace:ro" \
  -v "$PUSH_TEST_ROOT/send_push_before.lua:/baseline/send_push.lua:ro" \
  -v "$PUSH_TEST_ROOT/config:/config" --entrypoint sh "$PUSH_NGINX_IMAGE" \
  /workspace/tests/push/openresty/start.sh >/dev/null
ready=false
for _ in {1..30}; do
  if docker exec "$PUSH_TEST_PG" pg_isready -U postgres >/dev/null 2>&1 && \
     docker exec "$PUSH_TEST_NGINX" test -f /tmp/push-nginx.pid; then ready=true; break; fi
  sleep 1
 done
if [[ "$ready" != true ]]; then docker logs "$PUSH_TEST_NGINX"; exit 1; fi
docker logs "$PUSH_TEST_NGINX"
# Validate the actual repository nginx.conf with synthetic config and local
# placeholders for unchanged upstream names. Never reloads an existing nginx.
docker exec "$PUSH_TEST_NGINX" sh -c 'mkdir -p /config/ssl; chmod 777 /config/ssl; cp /config/test.crt /config/ssl/server.pem; cp /config/test.key /config/ssl/server.key; cp /config/test.crt /config/ssl/ca.pem; cp /config/test.key /config/ssl/ca.key; printf "users: {}\n" > /config/users_database.yml'
docker run --rm --network none \
  --add-host studio:127.0.0.1 \
  --add-host studio-assistant:127.0.0.1 \
  -e STUDIO_SERVICE_KEY_ENCRYPTION_KEY=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
  -v "$PUSH_TEST_ROOT/config:/config:ro" \
  -v "$PUSH_TEST_ROOT/config/test.crt:/var/run/studio-ca-bundle.pem:ro" \
  -v "$ROOT/studio/nginx/lua/init/init.lua:/usr/local/openresty/lualib/init/init.lua:ro" \
  -v "$ROOT/studio/nginx/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro" \
  -v "$ROOT/studio/nginx/lua/send_push.lua:/usr/local/openresty/lualib/send_push.lua:ro" \
  -v "$ROOT/studio/nginx/lua/push:/usr/local/openresty/lualib/push:ro" \
  --entrypoint openresty "$PUSH_NGINX_IMAGE" -t -c /usr/local/openresty/nginx/conf/nginx.conf
# Actual lua-resty-http handshakes are tested through HTTP content handlers.
docker run --rm -i --network "container:$PUSH_TEST_NGINX" \
  -e "PUSH_TEST_DSN=postgres://postgres@$PUSH_TEST_PG/postgres" \
  -e PUSH_TEST_GATEWAY=https://localhost:8443 -e PUSH_TEST_CA=/config/test.crt \
  -v "$ROOT:/workspace:ro" -v "$PUSH_TEST_ROOT/config:/config:ro" -w /workspace \
  --entrypoint python "$PUSH_PYTHON_IMAGE" - <<'PY'
import unittest

suite = unittest.defaultTestLoader.discover("tests/push", pattern="test_push*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
success = result.wasSuccessful() and result.testsRun > 0 and not result.skipped
raise SystemExit(0 if success else 1)
PY
# Explicitly inspect the resulting nginx logs for mock credentials.
if docker exec "$PUSH_TEST_NGINX" sh -c "grep -E 'secret-oauth-access|secret-fcm-token|internal-test-secret|BEGIN PRIVATE KEY' /tmp/push-error.log"; then
  echo 'FAIL: sensitive data in nginx logs' >&2; exit 1
fi
