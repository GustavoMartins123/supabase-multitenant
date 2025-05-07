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

echo "Transformando _supabase_template em um template de fato..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  ALTER DATABASE _supabase_template WITH is_template = true;
  UPDATE pg_database SET datallowconn = false WHERE datname = '_supabase_template';
EOSQL

echo "Template _supabase_template criado com sucesso."
