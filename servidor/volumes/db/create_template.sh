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
pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" | psql -U "$POSTGRES_USER" -d _supabase_template

echo "Criando tabela Projetos..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
  CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    anon_key TEXT,
    service_role TEXT
  );
EOSQL

echo "Criando tabela dos membros do projeto"
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
CREATE TABLE IF NOT EXISTS project_members (
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  role TEXT DEFAULT 'member',
  PRIMARY KEY (project_id, user_id)
);
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
EOSQL

echo "Transformando _supabase_template em um template de fato..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER DATABASE _supabase_template WITH is_template = true;
  UPDATE pg_database SET datallowconn = false WHERE datname = '_supabase_template';
EOSQL

echo "Template _supabase_template criado com sucesso."

