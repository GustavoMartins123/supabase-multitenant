#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"

fail() {
  echo "❌ $*" >&2
  exit 1
}

PROJECT_ID="${1:-}"
[[ -n "$PROJECT_ID" ]] || fail "Uso: $0 <project_id>"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] || fail "project_id invalido"

PROJECT_DIR="$SERVER_ROOT/projects/$PROJECT_ID"
GLOBAL_ENV="$SERVER_ROOT/.env"
PROJECT_ENV="$PROJECT_DIR/.env"
STORAGE_CONTAINER="supabase-storage-$PROJECT_ID"

[[ -d "$PROJECT_DIR" ]] || fail "Projeto nao encontrado: $PROJECT_DIR"
[[ -f "$GLOBAL_ENV" ]] || fail "Arquivo ausente: $GLOBAL_ENV"
[[ -f "$PROJECT_ENV" ]] || fail "Arquivo ausente: $PROJECT_ENV"
[[ -f "$PROJECT_DIR/docker-compose.yml" ]] || fail "docker-compose.yml ausente no projeto"

set -a
# shellcheck disable=SC1090
source "$GLOBAL_ENV"
# shellcheck disable=SC1090
source "$PROJECT_ENV"
set +a

EXPECTED_DATABASE="_supabase_$PROJECT_ID"
POSTGRES_DATABASE="${POSTGRES_DATABASE:-$EXPECTED_DATABASE}"
[[ "$POSTGRES_DATABASE" == "$EXPECTED_DATABASE" ]] || fail "POSTGRES_DATABASE nao corresponde ao projeto"

POSTGRES_USER="${POSTGRES_USER:-supabase_admin}"
POSTGRES_HOST="${POSTGRES_HOST:?POSTGRES_HOST ausente}"
POSTGRES_PORT="${POSTGRES_PORT:?POSTGRES_PORT ausente}"
STORAGE_DB_USER="${STORAGE_DB_USER:-supabase_storage_admin}"

command -v docker >/dev/null 2>&1 || fail "docker nao esta instalado"
command -v python3 >/dev/null 2>&1 || fail "python3 nao esta instalado"
docker inspect supabase-db >/dev/null 2>&1 || fail "Container supabase-db nao encontrado"

# O Storage API executa as migrations de storage_vectors com o usuario restrito.
# A instalacao da extensao exige o administrador do Postgres e ocorre antes de
# recriar o container; as operacoes normais continuam como supabase_storage_admin.
echo "▶ Instalando/verificando pgvector em $POSTGRES_DATABASE..."
docker exec supabase-db psql \
  -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DATABASE" \
  -c 'CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;'

VECTOR_VERSION="$(
  docker exec supabase-db psql \
    -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DATABASE" \
    -tAc "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
)"
[[ -n "$VECTOR_VERSION" ]] || fail "A extensao vector nao foi instalada"

python3 - "$VECTOR_VERSION" <<'PY'
import sys

version = sys.argv[1].strip()
try:
    parts = tuple(int(part) for part in version.split(".")[:3])
except ValueError as exc:
    raise SystemExit(f"versao pgvector invalida: {version}") from exc

parts = parts + (0,) * (3 - len(parts))
if parts < (0, 7, 0):
    raise SystemExit(f"pgvector >= 0.7.0 obrigatorio; encontrado {version}")
PY

# Usa referencias Compose em vez de copiar a senha global para o arquivo do
# projeto. O comando padrao carrega ../../.env antes de .env, portanto essas
# referencias sao resolvidas pelo proprio Docker Compose.
python3 - "$PROJECT_ENV" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
updates = {
    "VECTOR_ENABLED": "true",
    "VECTOR_BUCKET_PROVIDER": "pgvector",
    "VECTOR_DATABASE_URL": "postgres://${STORAGE_DB_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DATABASE}",
    "VECTOR_DATABASE_CREATE": "false",
    "VECTOR_STORE_MIGRATIONS_ENABLED": "true",
}

lines = path.read_text(encoding="utf-8").splitlines()
positions = {}
for index, line in enumerate(lines):
    if not line or line.lstrip().startswith("#") or "=" not in line:
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        positions[key] = index

for key, value in updates.items():
    rendered = f"{key}={value}"
    if key in positions:
        lines[positions[key]] = rendered
    else:
        lines.append(rendered)

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY

echo "▶ Validando configuracao Compose..."
(
  cd "$PROJECT_DIR"
  docker compose -p "$PROJECT_ID" --env-file ../../.env --env-file .env config >/dev/null
)

echo "▶ Recriando o Storage API com backend pgvector..."
(
  cd "$PROJECT_DIR"
  docker compose -p "$PROJECT_ID" --env-file ../../.env --env-file .env \
    up -d --force-recreate storage
)

for _ in $(seq 1 60); do
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$STORAGE_CONTAINER" 2>/dev/null || true)"
  case "$STATUS" in
    healthy)
      break
      ;;
    unhealthy|exited|dead)
      docker logs --tail 200 "$STORAGE_CONTAINER" >&2 || true
      fail "Storage terminou com status $STATUS"
      ;;
  esac
  sleep 2
done

STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$STORAGE_CONTAINER")"
[[ "$STATUS" == "healthy" ]] || {
  docker logs --tail 200 "$STORAGE_CONTAINER" >&2 || true
  fail "Storage nao ficou healthy dentro do prazo"
}

# Consulta o endpoint real do Storage API. Nenhuma resposta vazia e fabricada
# pelo gateway e aceita: falhas de provider, migration ou banco encerram o script.
echo "▶ Consultando ListVectorBuckets no Storage API..."
docker exec "$STORAGE_CONTAINER" node -e '
const key = process.env.SERVICE_KEY;
if (!key) {
  console.error("SERVICE_KEY ausente no container");
  process.exit(2);
}
fetch("http://127.0.0.1:5000/vector/ListVectorBuckets", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${key}`,
    "apikey": key,
  },
  body: "{}",
}).then(async (response) => {
  const text = await response.text();
  console.log(`HTTP ${response.status} ${text}`);
  if (!response.ok) process.exit(3);
  const payload = JSON.parse(text);
  if (!Array.isArray(payload.vectorBuckets)) {
    console.error("Resposta sem vectorBuckets");
    process.exit(4);
  }
}).catch((error) => {
  console.error(error);
  process.exit(5);
});
'

echo "✅ Storage Vectors habilitado para $PROJECT_ID usando o banco $POSTGRES_DATABASE (pgvector $VECTOR_VERSION)."
