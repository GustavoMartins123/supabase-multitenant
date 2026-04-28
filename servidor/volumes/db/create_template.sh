#!/usr/bin/env bash
set -e

echo "Criando schema _analytics..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE SCHEMA IF NOT EXISTS _analytics AUTHORIZATION "$POSTGRES_USER";
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
  | psql -U "$POSTGRES_USER" -d _supabase_template

echo "Criando tabelas de identidade..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY,
  authelia_username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  authelia_groups TEXT[] NOT NULL DEFAULT '{}'::text[],
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
  name TEXT NOT NULL UNIQUE,
  owner_id TEXT NOT NULL,
  owner_uuid UUID REFERENCES users(id) ON DELETE SET NULL,
  anon_key TEXT,
  service_role TEXT,
  config_token TEXT
);

COMMENT ON COLUMN projects.owner_id IS
  'UUID canonico do usuario serializado em texto por compatibilidade.';

CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);
CREATE INDEX IF NOT EXISTS idx_projects_owner_uuid ON projects(owner_uuid);
EOSQL

echo "Criando tabela dos membros do projeto"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE IF NOT EXISTS project_members (
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  user_uuid UUID REFERENCES users(id) ON DELETE SET NULL,
  role TEXT DEFAULT 'member',
  PRIMARY KEY (project_id, user_id)
);

COMMENT ON COLUMN project_members.user_id IS
  'UUID canonico do usuario serializado em texto por compatibilidade.';

CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user_uuid ON project_members(user_uuid);
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
    owner_id   TEXT    NOT NULL,
    status     TEXT    NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT now()
  );

  COMMENT ON COLUMN jobs.owner_id IS
    'UUID canonico do usuario serializado em texto por compatibilidade.';
EOSQL

echo "Transformando _supabase_template em um template de fato..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER DATABASE _supabase_template WITH is_template = true;
  UPDATE pg_database SET datallowconn = false WHERE datname = '_supabase_template';
EOSQL

echo "Template _supabase_template criado com sucesso."
