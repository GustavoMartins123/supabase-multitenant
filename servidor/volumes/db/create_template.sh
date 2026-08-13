#!/usr/bin/env bash
set -euo pipefail

: "${KEY_AUTHORIZER_DB_PASSWORD:?KEY_AUTHORIZER_DB_PASSWORD ausente}"
if [[ ! "$KEY_AUTHORIZER_DB_PASSWORD" =~ ^[A-Za-z0-9_-]{32,128}$ ]]; then
  echo "KEY_AUTHORIZER_DB_PASSWORD deve ter 32-128 caracteres URL-safe" >&2
  exit 1
fi

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
# cada banco de projeto. Como os projetos nascem de _supabase_template, a
# extensao precisa existir no banco base antes do pg_dump que forma o template.
# Isso evita que cada projeto dependa de um bootstrap manual posterior.
echo "Habilitando pgvector no banco base antes de criar _supabase_template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;

DO $vector_check$
DECLARE
  installed_version text;
BEGIN
  SELECT extversion
    INTO installed_version
    FROM pg_extension
   WHERE extname = 'vector';

  IF installed_version IS NULL THEN
    RAISE EXCEPTION 'pgvector extension is not installed';
  END IF;

  IF string_to_array(installed_version, '.')::int[] < ARRAY[0, 7, 0]::int[] THEN
    RAISE EXCEPTION
      'pgvector >= 0.7.0 required for Storage Vectors, found %',
      installed_version;
  END IF;
END
$vector_check$;
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

# Falha durante a inicializacao do Postgres caso o dump deixe de transportar a
# extensao. Assim nenhum projeto pode ser criado a partir de um template sem
# suporte ao backend vetorial.
echo "Validando pgvector dentro de _supabase_template..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname _supabase_template <<-'EOSQL'
DO $template_vector_check$
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

  IF string_to_array(installed_version, '.')::int[] < ARRAY[0, 7, 0]::int[] THEN
    RAISE EXCEPTION
      '_supabase_template requires pgvector >= 0.7.0, found %',
      installed_version;
  END IF;
END
$template_vector_check$;
EOSQL

echo "Criando tabelas de identidade..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY,
  authelia_username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  is_active BOOLEAN NOT NULL DEFAULT true,
  source TEXT NOT NULL DEFAULT 'authelia',
  last_login_at TIMESTAMPTZ,
  last_sync_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN users.id IS
  'Opaque identifier do usuario no Authelia/OpenID quando disponivel.';
COMMENT ON COLUMN users.authelia_username IS
  'Nome de usuario vindo do Authelia. Serve como atributo, nao como identidade canonica.';

CREATE TABLE IF NOT EXISTS user_groups (
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  group_name TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'authelia',
  synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, group_name)
);

CREATE TABLE IF NOT EXISTS user_group_audit (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  group_name TEXT NOT NULL,
  action TEXT NOT NULL,
  old_value JSONB,
  new_value JSONB,
  actor_type TEXT NOT NULL DEFAULT 'system',
  actor_user_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);
CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);
EOSQL

echo "Criando tabela Projetos..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  tenant_uuid UUID,
  name TEXT NOT NULL UNIQUE,
  display_name TEXT,
  owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  anon_key TEXT,
  service_role TEXT,
  config_token TEXT,
  automatic_key_rotation_enabled BOOLEAN NOT NULL DEFAULT true,
  key_expires_at TIMESTAMPTZ,
  last_key_rotation_at TIMESTAMPTZ,
  automatic_key_rotation_blocked_at TIMESTAMPTZ,
  automatic_key_rotation_last_error TEXT,
  api_keyset_version BIGINT NOT NULL DEFAULT 1,
  api_gateway_token_hash BYTEA,
  opaque_keys_prepared_at TIMESTAMPTZ,
  opaque_keys_activated_at TIMESTAMPTZ,
  opaque_gateway_cutover_started_at TIMESTAMPTZ,
  opaque_gateway_ready_at TIMESTAMPTZ
);

ALTER TABLE projects ADD COLUMN IF NOT EXISTS display_name TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS tenant_uuid UUID;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS automatic_key_rotation_enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS key_expires_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS last_key_rotation_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS automatic_key_rotation_blocked_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS automatic_key_rotation_last_error TEXT;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS api_keyset_version BIGINT NOT NULL DEFAULT 1;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS api_gateway_token_hash BYTEA;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS opaque_keys_prepared_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS opaque_keys_activated_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS opaque_gateway_cutover_started_at TIMESTAMPTZ;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS opaque_gateway_ready_at TIMESTAMPTZ;
UPDATE projects SET automatic_key_rotation_enabled = true
WHERE automatic_key_rotation_enabled IS NULL;
ALTER TABLE projects
  ALTER COLUMN automatic_key_rotation_enabled SET DEFAULT true,
  ALTER COLUMN automatic_key_rotation_enabled SET NOT NULL;

COMMENT ON COLUMN projects.owner_id IS
  'UUID canonico do usuario dono do projeto.';

COMMENT ON COLUMN projects.display_name IS
  'Nome exibicao humano do projeto. O slug/path continua sendo a coluna name.';

COMMENT ON COLUMN projects.tenant_uuid IS
  'Tenant externo persistido (Realtime/JWT/backups). Em projetos novos equivale a projects.id.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_tenant_uuid_unique
  ON projects(tenant_uuid)
  WHERE tenant_uuid IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_projects_automatic_key_rotation_due
  ON projects(key_expires_at)
  WHERE automatic_key_rotation_enabled
    AND automatic_key_rotation_blocked_at IS NULL
    AND anon_key IS NOT NULL;

CREATE OR REPLACE FUNCTION set_project_tenant_uuid_from_id()
RETURNS trigger
LANGUAGE plpgsql
AS \$\$
BEGIN
  IF NEW.tenant_uuid IS NULL THEN
    NEW.tenant_uuid := NEW.id;
  END IF;
  RETURN NEW;
END;
\$\$;

DROP TRIGGER IF EXISTS projects_default_tenant_uuid ON projects;
CREATE TRIGGER projects_default_tenant_uuid
BEFORE INSERT ON projects
FOR EACH ROW
EXECUTE FUNCTION set_project_tenant_uuid_from_id();

CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);
EOSQL

echo "Criando registro normalizado de API keys opacas..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
CREATE TABLE IF NOT EXISTS project_api_key_slots (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  allowed_services TEXT[] NOT NULL,
  automatic_rotation_enabled BOOLEAN NOT NULL,
  rotation_interval_days INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  automatic_rotation_blocked_at TIMESTAMPTZ,
  automatic_rotation_last_error TEXT,
  created_by UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT project_api_key_slots_name_format CHECK (
    name ~ '^[a-z][a-z0-9_-]{2,39}$'
  ),
  CONSTRAINT project_api_key_slots_kind CHECK (
    kind IN ('publishable', 'secret')
  ),
  CONSTRAINT project_api_key_slots_services CHECK (
    cardinality(allowed_services) > 0
    AND allowed_services <@ ARRAY[
      'auth', 'rest', 'graphql', 'realtime', 'storage', 'functions'
    ]::text[]
  ),
  CONSTRAINT project_api_key_slots_lifecycle CHECK (
    (
      rotation_interval_days IS NULL
      AND automatic_rotation_enabled = false
    )
    OR (
      rotation_interval_days IS NOT NULL
      AND rotation_interval_days BETWEEN 1 AND 3650
    )
  ),
  CONSTRAINT project_api_key_slots_status CHECK (
    status IN ('active', 'disabled')
  ),
  CONSTRAINT project_api_key_slots_project_name_unique
    UNIQUE(project_id, name)
);

ALTER TABLE project_api_key_slots
  ADD COLUMN IF NOT EXISTS automatic_rotation_blocked_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS automatic_rotation_last_error TEXT;

CREATE TABLE IF NOT EXISTS project_api_keys (
  id UUID PRIMARY KEY,
  slot_id UUID NOT NULL REFERENCES project_api_key_slots(id) ON DELETE CASCADE,
  secret_hash BYTEA NOT NULL UNIQUE,
  token_hint TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  activate_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ,
  activated_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  last_used_at TIMESTAMPTZ,
  revealed_at TIMESTAMPTZ,
  confirmed_at TIMESTAMPTZ,
  replaces_key_id UUID REFERENCES project_api_keys(id) ON DELETE SET NULL,
  rotation_trigger TEXT NOT NULL DEFAULT 'manual',
  CONSTRAINT project_api_keys_status CHECK (
    status IN ('pending', 'active', 'revoked', 'expired')
  ),
  CONSTRAINT project_api_keys_optional_lifetime CHECK (
    expires_at IS NULL OR expires_at > created_at
  ),
  CONSTRAINT project_api_keys_rotation_trigger CHECK (
    rotation_trigger IN ('initial', 'manual', 'automatic')
  ),
  CONSTRAINT project_api_keys_state_timestamps CHECK (
    (status = 'pending' AND activated_at IS NULL AND revoked_at IS NULL)
    OR (status = 'active' AND activated_at IS NOT NULL AND revoked_at IS NULL)
    OR (status IN ('revoked', 'expired') AND revoked_at IS NOT NULL)
  )
);

ALTER TABLE project_api_keys
  ADD COLUMN IF NOT EXISTS rotation_trigger TEXT NOT NULL DEFAULT 'manual',
  ADD COLUMN IF NOT EXISTS revealed_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_api_keys_one_active
  ON project_api_keys(slot_id) WHERE status = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_api_keys_one_pending
  ON project_api_keys(slot_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_project_api_keys_lookup
  ON project_api_keys(secret_hash) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_project_api_keys_expiring_due
  ON project_api_keys(expires_at)
  WHERE status = 'active' AND expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_project_api_key_slots_project
  ON project_api_key_slots(project_id, status);

CREATE TABLE IF NOT EXISTS project_api_key_reveals (
  key_id UUID PRIMARY KEY REFERENCES project_api_keys(id) ON DELETE CASCADE,
  ciphertext TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  CONSTRAINT project_api_key_reveals_lifetime CHECK (expires_at > created_at)
);
EOSQL

echo "Criando tabela dos membros do projeto"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE IF NOT EXISTS project_members (
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member'
    CONSTRAINT project_members_role_check CHECK (role IN ('admin', 'member')),
  PRIMARY KEY (project_id, user_id)
);

COMMENT ON COLUMN project_members.user_id IS
  'UUID canonico do usuario membro do projeto.';

CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
EOSQL

echo "Criando tabelas de auditoria..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL

CREATE TABLE IF NOT EXISTS project_members_audit (
  id BIGSERIAL PRIMARY KEY,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  target_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  old_role TEXT,
  new_role TEXT,
  action TEXT NOT NULL,
  actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_project_members_audit_project_id ON project_members_audit(project_id);
EOSQL

echo "Criando tabela jobs..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE TABLE jobs (
    job_id     UUID PRIMARY KEY,
    project    TEXT    NOT NULL,
    owner_id   UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status     TEXT    NOT NULL,
    message    TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
  );

  COMMENT ON COLUMN jobs.owner_id IS
    'UUID canonico do usuario que iniciou o job.';
EOSQL

echo "Criando identidade de banco restrita para o autorizador de API keys..."
psql -v ON_ERROR_STOP=1 \
  --set=key_authorizer_password="$KEY_AUTHORIZER_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-'EOSQL'
SELECT format(
  'CREATE ROLE key_authorizer WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 40 PASSWORD %L',
  :'key_authorizer_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'key_authorizer')
\gexec

SELECT format(
  'ALTER ROLE key_authorizer PASSWORD %L',
  :'key_authorizer_password'
)
\gexec

ALTER ROLE key_authorizer WITH
  LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT
  NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 40;
ALTER ROLE key_authorizer SET search_path = public, pg_catalog;
ALTER ROLE key_authorizer SET statement_timeout = '3s';
ALTER ROLE key_authorizer SET lock_timeout = '1s';
ALTER ROLE key_authorizer SET idle_in_transaction_session_timeout = '3s';

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM key_authorizer;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM key_authorizer;
REVOKE CREATE ON SCHEMA public FROM key_authorizer;
GRANT USAGE ON SCHEMA public TO key_authorizer;
GRANT SELECT (
  id, name, api_gateway_token_hash, api_keyset_version,
  opaque_keys_activated_at
) ON projects TO key_authorizer;
GRANT SELECT (
  id, project_id, kind, allowed_services, status
) ON project_api_key_slots TO key_authorizer;
GRANT SELECT (
  id, slot_id, secret_hash, status, activated_at, activate_at, expires_at, last_used_at, confirmed_at
) ON project_api_keys TO key_authorizer;
GRANT UPDATE (last_used_at) ON project_api_keys TO key_authorizer;

SELECT format(
  'GRANT CONNECT ON DATABASE %I TO key_authorizer',
  current_database()
)
\gexec
EOSQL

echo "Transformando _supabase_template em um template de fato..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER DATABASE _supabase_template WITH is_template = true;
  UPDATE pg_database SET datallowconn = false WHERE datname = '_supabase_template';
EOSQL

echo "Template _supabase_template criado com pgvector e validado com sucesso."

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
