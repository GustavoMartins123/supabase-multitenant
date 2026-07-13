#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_ROOT="$(dirname "$SCRIPT_DIR")"

fail() {
  echo "❌ $*" >&2
  exit 1
}

PROJECT_ID="${1:-}"
BUCKET_NAME="${2:-}"

[[ -n "$PROJECT_ID" && -n "$BUCKET_NAME" ]] \
  || fail "Uso: $0 <project_id> <vector_bucket_name>"
[[ "$PROJECT_ID" =~ ^[a-z_][a-z0-9_]{2,39}$ ]] \
  || fail "project_id invalido"
[[ "$BUCKET_NAME" != *$'\n'* && "$BUCKET_NAME" != *$'\r'* && "$BUCKET_NAME" != */* ]] \
  || fail "vector_bucket_name invalido"

PROJECT_DIR="$SERVER_ROOT/projects/$PROJECT_ID"
GLOBAL_ENV="$SERVER_ROOT/.env"
PROJECT_ENV="$PROJECT_DIR/.env"
STORAGE_CONTAINER="supabase-storage-$PROJECT_ID"
POSTGRES_DATABASE="_supabase_$PROJECT_ID"

[[ -d "$PROJECT_DIR" ]] || fail "Projeto nao encontrado: $PROJECT_DIR"
[[ -f "$GLOBAL_ENV" ]] || fail "Arquivo ausente: $GLOBAL_ENV"
[[ -f "$PROJECT_ENV" ]] || fail "Arquivo ausente: $PROJECT_ENV"

command -v docker >/dev/null 2>&1 || fail "docker nao esta instalado"
command -v python3 >/dev/null 2>&1 || fail "python3 nao esta instalado"

# Garante o provider pgvector, as migrations oficiais e um par SigV4 exclusivo
# do projeto antes de criar o FDW que consulta o endpoint vetorial.
"$SCRIPT_DIR/enable_vector_storage.sh" "$PROJECT_ID"

set -a
# shellcheck disable=SC1090
source "$GLOBAL_ENV"
# shellcheck disable=SC1090
source "$PROJECT_ENV"
set +a

POSTGRES_USER="${POSTGRES_USER:-supabase_admin}"
STORAGE_REGION="${STORAGE_REGION:-us-east-1}"
S3_PROTOCOL_ACCESS_KEY_ID="${S3_PROTOCOL_ACCESS_KEY_ID:-}"
S3_PROTOCOL_ACCESS_KEY_SECRET="${S3_PROTOCOL_ACCESS_KEY_SECRET:-}"

[[ "$S3_PROTOCOL_ACCESS_KEY_ID" =~ ^[0-9a-fA-F]{32}$ ]] \
  || fail "S3_PROTOCOL_ACCESS_KEY_ID ausente ou invalido"
[[ "$S3_PROTOCOL_ACCESS_KEY_SECRET" =~ ^[0-9a-fA-F]{64}$ ]] \
  || fail "S3_PROTOCOL_ACCESS_KEY_SECRET ausente ou invalido"

docker inspect supabase-db >/dev/null 2>&1 || fail "Container supabase-db nao encontrado"
docker inspect "$STORAGE_CONTAINER" >/dev/null 2>&1 \
  || fail "Container $STORAGE_CONTAINER nao encontrado"

mapfile -t VECTOR_NAMES < <(python3 - "$BUCKET_NAME" <<'PY'
import re
import sys

name = sys.argv[1]
# Equivalente para os nomes aceitos pelo Storage ao lodash snakeCase usado pelo
# Studio: separa camelCase, troca pontuacao por '_' e normaliza para minusculas.
value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
if not value:
    raise SystemExit("o nome do bucket nao produz um identificador SQL valido")
print(f"{value}_fdw")
print(f"{value}_fdw_server")
PY
)

WRAPPER_NAME="${VECTOR_NAMES[0]:-}"
SERVER_NAME="${VECTOR_NAMES[1]:-}"
[[ -n "$WRAPPER_NAME" && -n "$SERVER_NAME" ]] || fail "Falha ao gerar nomes do wrapper"
[[ ${#WRAPPER_NAME} -le 63 && ${#SERVER_NAME} -le 63 ]] \
  || fail "Nome do bucket gera identificador maior que o limite de 63 bytes do Postgres"

ACCESS_SECRET_NAME="${WRAPPER_NAME}_vault_access_key_id"
SECRET_SECRET_NAME="${WRAPPER_NAME}_vault_secret_access_key"
VECTOR_ENDPOINT="http://${STORAGE_CONTAINER}:5000/vector"

# Confirma que o bucket existe no backend real antes de alterar o catalogo do
# Postgres. A chamada usa a service_role apenas dentro do container do Storage.
echo "▶ Validando o vector bucket '$BUCKET_NAME' no Storage API..."
docker exec \
  -e VECTOR_BUCKET_NAME="$BUCKET_NAME" \
  "$STORAGE_CONTAINER" \
  node -e '
const key = process.env.SERVICE_KEY;
const bucket = process.env.VECTOR_BUCKET_NAME;
if (!key || !bucket) process.exit(2);
fetch("http://127.0.0.1:5000/vector/GetVectorBucket", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${key}`,
    "apikey": key,
  },
  body: JSON.stringify({ vectorBucketName: bucket }),
}).then(async (response) => {
  const text = await response.text();
  if (!response.ok) {
    console.error(`GetVectorBucket HTTP ${response.status}: ${text}`);
    process.exit(3);
  }
  const payload = JSON.parse(text);
  if (payload?.vectorBucket?.vectorBucketName !== bucket) {
    console.error("GetVectorBucket retornou um bucket inesperado");
    process.exit(4);
  }
}).catch((error) => {
  console.error(error);
  process.exit(5);
});
'

# A imagem Supabase Postgres fornece Vault e Wrappers. O Studio exige Wrappers
# >= 0.5.6 para reconhecer a integracao S3 Vectors.
echo "▶ Instalando/verificando Vault e Wrappers em $POSTGRES_DATABASE..."
docker exec -i supabase-db psql \
  -X -q -v ON_ERROR_STOP=1 \
  -U "$POSTGRES_USER" \
  -d "$POSTGRES_DATABASE" <<'SQL'
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS supabase_vault CASCADE;
CREATE EXTENSION IF NOT EXISTS wrappers WITH SCHEMA extensions;
SQL

WRAPPERS_VERSION="$(
  docker exec supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DATABASE" \
    -tAc "SELECT extversion FROM pg_extension WHERE extname = 'wrappers'"
)"
[[ -n "$WRAPPERS_VERSION" ]] || fail "A extensao wrappers nao foi instalada"

python3 - "$WRAPPERS_VERSION" <<'PY'
import re
import sys

version = sys.argv[1].strip()
match = re.match(r"^(\d+)\.(\d+)\.(\d+)", version)
if not match:
    raise SystemExit(f"versao Wrappers invalida: {version}")
parts = tuple(map(int, match.groups()))
if parts < (0, 5, 6):
    raise SystemExit(
        f"Wrappers >= 0.5.6 obrigatorio para S3 Vectors; encontrado {version}"
    )
PY

# Os segredos ficam criptografados no Vault. O servidor FDW referencia apenas os
# UUIDs do Vault, exatamente como o gerador SQL do Studio oficial.
echo "▶ Configurando o S3 Vectors Wrapper '$WRAPPER_NAME'..."
docker exec -i \
  -e SETUP_WRAPPER_NAME="$WRAPPER_NAME" \
  -e SETUP_SERVER_NAME="$SERVER_NAME" \
  -e SETUP_ACCESS_SECRET_NAME="$ACCESS_SECRET_NAME" \
  -e SETUP_SECRET_SECRET_NAME="$SECRET_SECRET_NAME" \
  -e SETUP_S3_ACCESS_KEY="$S3_PROTOCOL_ACCESS_KEY_ID" \
  -e SETUP_S3_SECRET_KEY="$S3_PROTOCOL_ACCESS_KEY_SECRET" \
  -e SETUP_REGION="$STORAGE_REGION" \
  -e SETUP_ENDPOINT="$VECTOR_ENDPOINT" \
  supabase-db psql \
    -X -q -v ON_ERROR_STOP=1 \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DATABASE" <<'SQL'
\getenv wrapper_name SETUP_WRAPPER_NAME
\getenv server_name SETUP_SERVER_NAME
\getenv access_secret_name SETUP_ACCESS_SECRET_NAME
\getenv secret_secret_name SETUP_SECRET_SECRET_NAME
\getenv s3_access_key SETUP_S3_ACCESS_KEY
\getenv s3_secret_key SETUP_S3_SECRET_KEY
\getenv aws_region SETUP_REGION
\getenv endpoint_url SETUP_ENDPOINT

BEGIN;
SET LOCAL log_statement = 'none';

CREATE TEMP TABLE vector_wrapper_setup_params (
  wrapper_name text NOT NULL,
  server_name text NOT NULL,
  access_secret_name text NOT NULL,
  secret_secret_name text NOT NULL,
  s3_access_key text NOT NULL,
  s3_secret_key text NOT NULL,
  aws_region text NOT NULL,
  endpoint_url text NOT NULL
) ON COMMIT DROP;

INSERT INTO vector_wrapper_setup_params VALUES (
  :'wrapper_name', :'server_name',
  :'access_secret_name', :'secret_secret_name',
  :'s3_access_key', :'s3_secret_key',
  :'aws_region', :'endpoint_url'
);

DO $setup$
DECLARE
  cfg record;
  access_secret_id uuid;
  secret_secret_id uuid;
  handler_schema text;
  validator_schema text;
  existing_handler text;
  existing_server_fdw text;
  option_name text;
  option_value text;
BEGIN
  SELECT * INTO STRICT cfg FROM vector_wrapper_setup_params;

  SELECT id INTO access_secret_id
  FROM vault.secrets
  WHERE name = cfg.access_secret_name;

  IF access_secret_id IS NULL THEN
    access_secret_id := vault.create_secret(
      cfg.s3_access_key,
      cfg.access_secret_name,
      'S3 Vectors access key for ' || cfg.wrapper_name
    );
  ELSE
    PERFORM vault.update_secret(
      access_secret_id,
      cfg.s3_access_key,
      cfg.access_secret_name,
      'S3 Vectors access key for ' || cfg.wrapper_name
    );
  END IF;

  SELECT id INTO secret_secret_id
  FROM vault.secrets
  WHERE name = cfg.secret_secret_name;

  IF secret_secret_id IS NULL THEN
    secret_secret_id := vault.create_secret(
      cfg.s3_secret_key,
      cfg.secret_secret_name,
      'S3 Vectors secret key for ' || cfg.wrapper_name
    );
  ELSE
    PERFORM vault.update_secret(
      secret_secret_id,
      cfg.s3_secret_key,
      cfg.secret_secret_name,
      'S3 Vectors secret key for ' || cfg.wrapper_name
    );
  END IF;

  SELECT n.nspname INTO handler_schema
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE p.proname = 's3_vectors_fdw_handler'
  ORDER BY (n.nspname = 'extensions') DESC, n.nspname
  LIMIT 1;

  SELECT n.nspname INTO validator_schema
  FROM pg_proc p
  JOIN pg_namespace n ON n.oid = p.pronamespace
  WHERE p.proname = 's3_vectors_fdw_validator'
  ORDER BY (n.nspname = 'extensions') DESC, n.nspname
  LIMIT 1;

  IF handler_schema IS NULL OR validator_schema IS NULL THEN
    RAISE EXCEPTION
      'Wrappers % nao fornece s3_vectors_fdw_handler/validator',
      (SELECT extversion FROM pg_extension WHERE extname = 'wrappers');
  END IF;

  SELECT p.proname INTO existing_handler
  FROM pg_foreign_data_wrapper w
  LEFT JOIN pg_proc p ON p.oid = w.fdwhandler
  WHERE w.fdwname = cfg.wrapper_name;

  IF existing_handler IS NULL THEN
    EXECUTE format(
      'CREATE FOREIGN DATA WRAPPER %I HANDLER %I.%I VALIDATOR %I.%I',
      cfg.wrapper_name,
      handler_schema,
      's3_vectors_fdw_handler',
      validator_schema,
      's3_vectors_fdw_validator'
    );
  ELSIF existing_handler <> 's3_vectors_fdw_handler' THEN
    RAISE EXCEPTION
      'FDW % ja existe com handler inesperado %',
      cfg.wrapper_name,
      existing_handler;
  END IF;

  SELECT w.fdwname INTO existing_server_fdw
  FROM pg_foreign_server s
  JOIN pg_foreign_data_wrapper w ON w.oid = s.srvfdw
  WHERE s.srvname = cfg.server_name;

  IF existing_server_fdw IS NULL THEN
    EXECUTE format(
      'CREATE SERVER %I FOREIGN DATA WRAPPER %I OPTIONS (' ||
      'vault_access_key_id %L, vault_secret_access_key %L, ' ||
      'aws_region %L, endpoint_url %L)',
      cfg.server_name,
      cfg.wrapper_name,
      access_secret_id::text,
      secret_secret_id::text,
      cfg.aws_region,
      cfg.endpoint_url
    );
  ELSIF existing_server_fdw <> cfg.wrapper_name THEN
    RAISE EXCEPTION
      'Servidor % pertence ao FDW %, esperado %',
      cfg.server_name,
      existing_server_fdw,
      cfg.wrapper_name;
  ELSE
    FOREACH option_name IN ARRAY ARRAY[
      'vault_access_key_id',
      'vault_secret_access_key',
      'aws_region',
      'endpoint_url'
    ]
    LOOP
      option_value := CASE option_name
        WHEN 'vault_access_key_id' THEN access_secret_id::text
        WHEN 'vault_secret_access_key' THEN secret_secret_id::text
        WHEN 'aws_region' THEN cfg.aws_region
        WHEN 'endpoint_url' THEN cfg.endpoint_url
      END;

      IF EXISTS (
        SELECT 1
        FROM pg_foreign_server s,
             LATERAL unnest(COALESCE(s.srvoptions, ARRAY[]::text[])) opt
        WHERE s.srvname = cfg.server_name
          AND split_part(opt, '=', 1) = option_name
      ) THEN
        EXECUTE format(
          'ALTER SERVER %I OPTIONS (SET %I %L)',
          cfg.server_name,
          option_name,
          option_value
        );
      ELSE
        EXECUTE format(
          'ALTER SERVER %I OPTIONS (ADD %I %L)',
          cfg.server_name,
          option_name,
          option_value
        );
      END IF;
    END LOOP;
  END IF;
END
$setup$;

COMMIT;
SQL

# IMPORT FOREIGN SCHEMA e a operacao real usada pelo Studio para expor os
# indexes como tabelas. A sonda cria um schema temporario, consulta o Storage
# usando SigV4 e o remove logo depois; nenhuma tabela do usuario e alterada.
PROBE_SCHEMA="vector_wrapper_probe_${PROJECT_ID}_$$"
PROBE_SCHEMA="${PROBE_SCHEMA:0:63}"

echo "▶ Testando o wrapper contra $VECTOR_ENDPOINT..."
if python3 - "$WRAPPERS_VERSION" <<'PY'
import re
import sys
m = re.match(r"^(\d+)\.(\d+)\.(\d+)", sys.argv[1])
raise SystemExit(0 if m and tuple(map(int, m.groups())) >= (0, 5, 7) else 1)
PY
then
  docker exec -i \
    -e PROBE_SCHEMA="$PROBE_SCHEMA" \
    -e PROBE_SERVER="$SERVER_NAME" \
    -e PROBE_BUCKET="$BUCKET_NAME" \
    supabase-db psql \
      -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" \
      -d "$POSTGRES_DATABASE" <<'SQL'
\getenv probe_schema PROBE_SCHEMA
\getenv probe_server PROBE_SERVER
\getenv probe_bucket PROBE_BUCKET
CREATE SCHEMA :"probe_schema";
IMPORT FOREIGN SCHEMA :"probe_bucket"
  FROM SERVER :"probe_server"
  INTO :"probe_schema"
  OPTIONS (strict 'true');
DROP SCHEMA :"probe_schema" CASCADE;
SQL
else
  docker exec -i \
    -e PROBE_SCHEMA="$PROBE_SCHEMA" \
    -e PROBE_SERVER="$SERVER_NAME" \
    -e PROBE_BUCKET="$BUCKET_NAME" \
    supabase-db psql \
      -X -q -v ON_ERROR_STOP=1 \
      -U "$POSTGRES_USER" \
      -d "$POSTGRES_DATABASE" <<'SQL'
\getenv probe_schema PROBE_SCHEMA
\getenv probe_server PROBE_SERVER
\getenv probe_bucket PROBE_BUCKET
CREATE SCHEMA :"probe_schema";
IMPORT FOREIGN SCHEMA :"probe_schema"
  FROM SERVER :"probe_server"
  INTO :"probe_schema"
  OPTIONS (bucket_name :'probe_bucket', strict 'true');
DROP SCHEMA :"probe_schema" CASCADE;
SQL
fi

echo "✅ Integracao S3 Vectors Wrapper configurada para '$BUCKET_NAME'."
echo "   FDW:      $WRAPPER_NAME"
echo "   Servidor: $SERVER_NAME"
echo "   Endpoint: $VECTOR_ENDPOINT"
