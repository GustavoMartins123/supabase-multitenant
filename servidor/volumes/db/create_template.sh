#!/usr/bin/env bash
set -euo pipefail

echo "Criando schema _analytics..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE SCHEMA IF NOT EXISTS _analytics AUTHORIZATION "$POSTGRES_USER";
EOSQL

# Registry oficial do Storage multi-tenant. Ele nao pertence a nenhum projeto e
# recebe somente configuracao cifrada pelas migrations do proprio Storage API.
echo "Criando database isolado do registry do Storage..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
SELECT 'CREATE DATABASE "_supabase_storage"'
WHERE NOT EXISTS (
  SELECT 1 FROM pg_database WHERE datname = '_supabase_storage'
)\gexec

REVOKE ALL ON DATABASE "_supabase_storage" FROM PUBLIC;
GRANT ALL PRIVILEGES ON DATABASE "_supabase_storage" TO supabase_admin;
EOSQL

# O Storage API com VECTOR_BUCKET_PROVIDER=pgvector executa suas migrations em
# cada banco de projeto e o Studio usa Wrappers (s3_vectors_fdw) em extensions.
# Como os projetos nascem de _supabase_template, vector >= 0.7.0 em public e
# wrappers >= 0.5.7 em extensions precisam existir no banco base antes do pg_dump.
echo "Habilitando pgvector e wrappers no banco base antes de criar _supabase_template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
CREATE EXTENSION IF NOT EXISTS wrappers SCHEMA extensions;

DO $vector_and_wrappers_check$
DECLARE
  installed_version text;
  installed_schema text;
BEGIN
  SELECT e.extversion, n.nspname
    INTO installed_version, installed_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
   WHERE e.extname = 'vector';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION 'pgvector extension is not installed';
  END IF;

  IF installed_schema <> 'public' THEN
    RAISE EXCEPTION
      'pgvector must be installed in public for Storage Vectors, found schema %',
      installed_schema;
  END IF;

  IF string_to_array(split_part(installed_version, '-', 1), '.')::int[] < ARRAY[0, 7, 0]::int[] THEN
    RAISE EXCEPTION
      'pgvector >= 0.7.0 required for Storage Vectors, found %',
      installed_version;
  END IF;

  SELECT e.extversion, n.nspname
    INTO installed_version, installed_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
   WHERE e.extname = 'wrappers';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION 'wrappers extension is not installed';
  END IF;

  IF installed_schema <> 'extensions' THEN
    RAISE EXCEPTION
      'wrappers must be installed in extensions for s3_vectors_fdw, found schema %',
      installed_schema;
  END IF;

  IF string_to_array(split_part(installed_version, '-', 1), '.')::int[] < ARRAY[0, 5, 7]::int[] THEN
    RAISE EXCEPTION
      'wrappers >= 0.5.7 required for s3_vectors_fdw, found %',
      installed_version;
  END IF;
END
$vector_and_wrappers_check$;
EOSQL

echo "Criando database _supabase_template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE DATABASE _supabase_template;
EOSQL

echo "Fazendo pg_dump do DB principal e restaurando em _supabase_template..."
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --exclude-schema=cron \
  | grep -v "CREATE EXTENSION.*pg_cron" \
  | grep -v "COMMENT ON EXTENSION pg_cron" \
  | psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d _supabase_template

# Extension-owned GraphQL schemas/wrappers can lose their API-role ACLs across
# pg_dump/restore. Provision the canonical GraphQL contract in the template,
# never grant access to unrelated schemas or replace the resolver with a stub.
echo "Validando GraphQL e seus grants no template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname _supabase_template \
  -f /etc/supabase/graphql.sql

# Falha durante a inicializacao do Postgres caso o dump deixe de transportar as
# extensoes. Assim nenhum projeto pode ser criado a partir de um template sem
# suporte ao backend vetorial e ao s3_vectors_fdw.
echo "Validando pgvector e wrappers dentro de _supabase_template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname _supabase_template <<-'EOSQL'
DO $template_vector_and_wrappers_check$
DECLARE
  installed_version text;
  installed_schema text;
BEGIN
  SELECT e.extversion, n.nspname
    INTO installed_version, installed_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
   WHERE e.extname = 'vector';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION '_supabase_template was created without pgvector';
  END IF;

  IF installed_schema <> 'public' THEN
    RAISE EXCEPTION
      'pgvector must be installed in public for Storage Vectors, found schema %',
      installed_schema;
  END IF;

  IF string_to_array(split_part(installed_version, '-', 1), '.')::int[] < ARRAY[0, 7, 0]::int[] THEN
    RAISE EXCEPTION
      '_supabase_template requires pgvector >= 0.7.0, found %',
      installed_version;
  END IF;

  SELECT e.extversion, n.nspname
    INTO installed_version, installed_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
   WHERE e.extname = 'wrappers';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION '_supabase_template was created without wrappers';
  END IF;

  IF installed_schema <> 'extensions' THEN
    RAISE EXCEPTION
      'wrappers must be installed in extensions for s3_vectors_fdw, found schema %',
      installed_schema;
  END IF;

  IF string_to_array(split_part(installed_version, '-', 1), '.')::int[] < ARRAY[0, 5, 7]::int[] THEN
    RAISE EXCEPTION
      '_supabase_template requires wrappers >= 0.5.7, found %',
      installed_version;
  END IF;
END
$template_vector_and_wrappers_check$;
EOSQL

echo "Configurando search_path de supabase_storage_admin para resolver tipos pgvector..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v target_db="$POSTGRES_DB" <<-'EOSQL'
  ALTER ROLE supabase_storage_admin IN DATABASE _supabase_template SET search_path = storage, public;
  ALTER ROLE supabase_storage_admin IN DATABASE :"target_db" SET search_path = storage, public;
EOSQL

echo "Transformando _supabase_template em um template de fato..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER DATABASE _supabase_template WITH is_template = true;
  UPDATE pg_database SET datallowconn = false WHERE datname = '_supabase_template';
EOSQL

echo "Template _supabase_template criado com pgvector e wrappers e validado com sucesso."

echo "Criando banco e usuário restrito para fallback do pg-meta..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE meta_trap;
    CREATE USER meta_guest WITH
        LOGIN
        NOSUPERUSER
        NOCREATEDB
        NOCREATEROLE
        NOINHERIT
        NOREPLICATION
        NOBYPASSRLS
        CONNECTION LIMIT 5
        PASSWORD '$META_GUEST_PASSWORD';
    ALTER ROLE meta_guest SET search_path = 'pg_catalog';
    ALTER ROLE meta_guest SET statement_timeout = '5s';
    ALTER ROLE meta_guest SET idle_in_transaction_session_timeout = '5s';

    REVOKE pg_monitor FROM meta_guest;
    REVOKE pg_read_all_data FROM meta_guest;
    REVOKE pg_write_all_data FROM meta_guest;
    REVOKE pg_read_all_settings FROM meta_guest;
    REVOKE pg_read_all_stats FROM meta_guest;
    REVOKE pg_stat_scan_tables FROM meta_guest;
    REVOKE pg_read_server_files FROM meta_guest;
    REVOKE pg_write_server_files FROM meta_guest;
    REVOKE pg_execute_server_program FROM meta_guest;
    REVOKE pg_signal_backend FROM meta_guest;

    REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
    REVOKE TEMPORARY ON DATABASE postgres FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE _supabase FROM PUBLIC;
    REVOKE CONNECT ON DATABASE _supabase_template FROM PUBLIC;
    REVOKE TEMPORARY ON DATABASE _supabase_template FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE template0 FROM PUBLIC;
    REVOKE CONNECT, TEMPORARY ON DATABASE template1 FROM PUBLIC;
    GRANT CONNECT, TEMPORARY ON DATABASE _supabase TO supabase_admin;
    REVOKE ALL ON DATABASE meta_trap FROM PUBLIC;
    REVOKE ALL ON DATABASE meta_trap FROM meta_guest;
    REVOKE CREATE, TEMPORARY ON DATABASE meta_trap FROM PUBLIC;
    REVOKE CREATE, TEMPORARY ON DATABASE meta_trap FROM meta_guest;
    GRANT CONNECT ON DATABASE meta_trap TO meta_guest;

    \c meta_trap
    REVOKE ALL ON SCHEMA public FROM PUBLIC;
    REVOKE ALL ON SCHEMA public FROM meta_guest;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM meta_guest;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM meta_guest;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM meta_guest;
    CREATE SCHEMA meta_guard AUTHORIZATION supabase_admin;
    REVOKE ALL ON SCHEMA meta_guard FROM PUBLIC;
    CREATE OR REPLACE FUNCTION meta_guard.block_meta_guest_extension_ddl()
    RETURNS event_trigger
    LANGUAGE plpgsql
    SECURITY DEFINER
    SET search_path = pg_catalog
    AS \$\$
    BEGIN
        IF session_user = 'meta_guest' OR current_user = 'meta_guest' THEN
            RAISE EXCEPTION 'extension DDL is disabled for meta_guest';
        END IF;
    END;
    \$\$;
    REVOKE ALL ON FUNCTION meta_guard.block_meta_guest_extension_ddl() FROM PUBLIC;
    CREATE EVENT TRIGGER block_meta_guest_extension_ddl
        ON ddl_command_start
        WHEN TAG IN ('CREATE EXTENSION', 'ALTER EXTENSION', 'DROP EXTENSION')
        EXECUTE FUNCTION meta_guard.block_meta_guest_extension_ddl();

    \c postgres
    REVOKE ALL ON TABLE pg_database FROM PUBLIC;
EOSQL
