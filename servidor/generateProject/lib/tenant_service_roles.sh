#!/usr/bin/env bash
# Per-tenant PostgreSQL service roles (T5): tenant_auth_<uuid32> and tenant_rest_<uuid32>.
# Keyed on immutable lowercase 32-hex PROJECT_UUID so roles survive project renames.

tenant_service_role_hex() {
  local tenant_uuid="${1,,}" hex
  [[ "$tenant_uuid" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] \
    || return 1
  hex="${tenant_uuid//-/}"
  [[ "$hex" =~ ^[0-9a-f]{32}$ ]] || return 1
  printf '%s' "$hex"
}

tenant_auth_role_name() {
  local hex
  hex="$(tenant_service_role_hex "$1")" || return 1
  printf 'tenant_auth_%s' "$hex"
}

tenant_rest_role_name() {
  local hex
  hex="$(tenant_service_role_hex "$1")" || return 1
  printf 'tenant_rest_%s' "$hex"
}

validate_tenant_service_password() {
  local password="${1:-}"
  [[ "$password" =~ ^[A-Za-z0-9_-]{32,128}$ ]]
}

generate_tenant_service_password() {
  local password
  password="$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '=\n\r')" || return 1
  validate_tenant_service_password "$password" || return 1
  printf '%s' "$password"
}

provision_tenant_service_roles() {
  local db="$1" tenant_uuid="${2,,}" auth_password="$3" rest_password="$4"
  local auth_role rest_role db_container db_admin_user

  [[ "$db" =~ ^_supabase_[a-z_][a-z0-9_]{2,39}$ ]] || return 1
  auth_role="$(tenant_auth_role_name "$tenant_uuid")" || return 1
  rest_role="$(tenant_rest_role_name "$tenant_uuid")" || return 1
  validate_tenant_service_password "$auth_password" || return 1
  validate_tenant_service_password "$rest_password" || return 1
  [[ "$auth_password" != "$rest_password" ]] || return 1

  db_container="${SUPABASE_DB_CONTAINER:-supabase-db}"
  db_admin_user="${SUPABASE_DB_ADMIN_USER:-supabase_admin}"

  # Pass secrets strictly through inherited environment variables (-e VAR without =value)
  # and \getenv + SET LOCAL log_statement = 'none' so passwords never appear in argv or PG logs.
  TENANT_AUTH_DB_USER="$auth_role" \
  TENANT_REST_DB_USER="$rest_role" \
  TENANT_AUTH_DB_PASSWORD="$auth_password" \
  TENANT_REST_DB_PASSWORD="$rest_password" \
    docker exec -i \
      -e TENANT_AUTH_DB_USER \
      -e TENANT_REST_DB_USER \
      -e TENANT_AUTH_DB_PASSWORD \
      -e TENANT_REST_DB_PASSWORD \
      "$db_container" psql -X -q -v ON_ERROR_STOP=1 -1 -U "$db_admin_user" -d "$db" <<'SQL' >/dev/null
SET LOCAL log_statement = 'none';
\getenv auth_role TENANT_AUTH_DB_USER
\getenv rest_role TENANT_REST_DB_USER
\getenv auth_pwd TENANT_AUTH_DB_PASSWORD
\getenv rest_pwd TENANT_REST_DB_PASSWORD
SELECT set_config('platform.tenant_auth_role', :'auth_role', true),
       set_config('platform.tenant_rest_role', :'rest_role', true),
       set_config('platform.tenant_auth_pwd', :'auth_pwd', true),
       set_config('platform.tenant_rest_pwd', :'rest_pwd', true);
DO $tenant_service_roles$
DECLARE
  auth_role text := current_setting('platform.tenant_auth_role');
  rest_role text := current_setting('platform.tenant_rest_role');
  auth_pwd text := current_setting('platform.tenant_auth_pwd');
  rest_pwd text := current_setting('platform.tenant_rest_pwd');
  parent_role text;
  preload_sql text;
  meta_role text;
  db_name text := current_database();
BEGIN
  IF auth_role !~ '^tenant_auth_[0-9a-f]{32}$' OR rest_role !~ '^tenant_rest_[0-9a-f]{32}$' THEN
    RAISE EXCEPTION 'invalid tenant service role identity';
  END IF;
  IF auth_pwd !~ '^[A-Za-z0-9_-]{32,128}$' OR rest_pwd !~ '^[A-Za-z0-9_-]{32,128}$' THEN
    RAISE EXCEPTION 'invalid tenant service role password';
  END IF;
  IF auth_pwd = rest_pwd THEN
    RAISE EXCEPTION 'tenant auth and rest passwords must be distinct';
  END IF;

  -- 1. PostgREST role: LOGIN NOINHERIT, member of anon/authenticated/service_role ONLY (never authenticator).
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = rest_role) THEN
    EXECUTE format('CREATE ROLE %I', rest_role);
  END IF;
  EXECUTE format(
    'ALTER ROLE %I WITH LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    rest_role, rest_pwd
  );
  FOR parent_role IN
    SELECT parent.rolname
    FROM pg_auth_members m
    JOIN pg_roles parent ON parent.oid = m.roleid
    JOIN pg_roles member ON member.oid = m.member
    WHERE member.rolname = rest_role
  LOOP
    EXECUTE format('REVOKE %I FROM %I', parent_role, rest_role);
  END LOOP;
  FOREACH parent_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = parent_role) THEN
      EXECUTE format('GRANT %I TO %I', parent_role, rest_role);
    END IF;
  END LOOP;
  EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', rest_role, '8s');
  EXECUTE format('ALTER ROLE %I SET lock_timeout = %L', rest_role, '8s');
  -- session_preload_libraries is GUC_LIST_INPUT | GUC_LIST_QUOTE; quote each item separately.
  SELECT string_agg(quote_literal(item), ', ' ORDER BY ord)
    INTO preload_sql
  FROM (
    SELECT trim(both '"' FROM btrim(part)) AS item, ord
    FROM (
      SELECT substr(cfg, length('session_preload_libraries=') + 1) AS raw_libs
      FROM pg_roles r,
           unnest(coalesce(r.rolconfig, ARRAY[]::text[])) cfg
      WHERE r.rolname = 'authenticator'
        AND cfg LIKE 'session_preload_libraries=%'
      LIMIT 1
    ) src,
    LATERAL regexp_split_to_table(src.raw_libs, ',') WITH ORDINALITY AS t(part, ord)
  ) libs
  WHERE item <> '';
  IF preload_sql IS NOT NULL AND preload_sql <> '' THEN
    EXECUTE format('ALTER ROLE %I SET session_preload_libraries = %s', rest_role, preload_sql);
  ELSE
    EXECUTE format('ALTER ROLE %I RESET session_preload_libraries', rest_role);
  END IF;

  -- 2. GoTrue role: LOGIN INHERIT member of supabase_auth_admin (CREATEROLE is never inherited in PG).
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = auth_role) THEN
    EXECUTE format('CREATE ROLE %I', auth_role);
  END IF;
  EXECUTE format(
    'ALTER ROLE %I WITH LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
    auth_role, auth_pwd
  );
  FOR parent_role IN
    SELECT parent.rolname
    FROM pg_auth_members m
    JOIN pg_roles parent ON parent.oid = m.roleid
    JOIN pg_roles member ON member.oid = m.member
    WHERE member.rolname = auth_role
  LOOP
    EXECUTE format('REVOKE %I FROM %I', parent_role, auth_role);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    EXECUTE format('GRANT supabase_auth_admin TO %I', auth_role);
  END IF;
  EXECUTE format('ALTER ROLE %I SET search_path = %I', auth_role, 'auth');
  EXECUTE format('ALTER ROLE %I SET idle_in_transaction_session_timeout = 60000', auth_role);
  EXECUTE format('ALTER ROLE %I SET log_statement = %L', auth_role, 'none');

  -- 3. Cross-tenant database lock: revoke PUBLIC, authenticator, supabase_auth_admin.
  EXECUTE format('REVOKE CONNECT, TEMPORARY, CREATE ON DATABASE %I FROM PUBLIC', db_name);
  FOREACH parent_role IN ARRAY ARRAY['authenticator', 'supabase_auth_admin'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = parent_role) THEN
      EXECUTE format('REVOKE CONNECT, TEMPORARY, CREATE ON DATABASE %I FROM %I', db_name, parent_role);
    END IF;
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pgbouncer') THEN
    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO pgbouncer', db_name);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
    EXECUTE format('GRANT CONNECT, TEMPORARY, CREATE ON DATABASE %I TO supabase_storage_admin', db_name);
  END IF;
  EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO %I', db_name, rest_role);
  EXECUTE format('GRANT CONNECT, TEMPORARY, CREATE ON DATABASE %I TO %I', db_name, auth_role);

  -- Cover future GoTrue migrations immediately when tenant_meta_<uuid32> already exists
  -- (e.g. during sync_existing_projects_security.py or migrate_shared_storage.sh).
  meta_role := replace(auth_role, 'tenant_auth_', 'tenant_meta_');
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'auth')
     AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = meta_role) THEN
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA auth GRANT SELECT, INSERT, UPDATE, DELETE, REFERENCES ON TABLES TO %I',
      auth_role, meta_role
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA auth GRANT USAGE, SELECT ON SEQUENCES TO %I',
      auth_role, meta_role
    );
  END IF;
END
$tenant_service_roles$;
SELECT set_config('platform.tenant_auth_pwd', '', true),
       set_config('platform.tenant_rest_pwd', '', true);
SQL
}

reassign_tenant_auth_objects_to_auth_admin() {
  local db="$1" db_container db_admin_user
  [[ "$db" =~ ^_supabase_[a-z_][a-z0-9_]{2,39}$ ]] || return 1

  db_container="${SUPABASE_DB_CONTAINER:-supabase-db}"
  db_admin_user="${SUPABASE_DB_ADMIN_USER:-supabase_admin}"

  docker exec -i "$db_container" psql -X -q -v ON_ERROR_STOP=1 -1 -U "$db_admin_user" -d "$db" <<'SQL' >/dev/null
DO $reassign_tenant_auth$
DECLARE
  stale_role text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    RETURN;
  END IF;
  FOR stale_role IN
    SELECT DISTINCT r.rolname
    FROM pg_roles r
    WHERE r.rolname ~ '^tenant_auth_[0-9a-f]{32}$'
      AND (
        EXISTS (SELECT 1 FROM pg_class c WHERE c.relowner = r.oid)
        OR EXISTS (SELECT 1 FROM pg_proc p WHERE p.proowner = r.oid)
        OR EXISTS (SELECT 1 FROM pg_type t WHERE t.typowner = r.oid)
        OR EXISTS (SELECT 1 FROM pg_namespace n WHERE n.nspowner = r.oid)
      )
  LOOP
    EXECUTE format('REASSIGN OWNED BY %I TO supabase_auth_admin', stale_role);
  END LOOP;
END
$reassign_tenant_auth$;
SQL
}

drop_tenant_service_roles() {
  local tenant_uuid="${1,,}" auth_role rest_role db_container db_admin_user
  auth_role="$(tenant_auth_role_name "$tenant_uuid")" || return 1
  rest_role="$(tenant_rest_role_name "$tenant_uuid")" || return 1

  db_container="${SUPABASE_DB_CONTAINER:-supabase-db}"
  db_admin_user="${SUPABASE_DB_ADMIN_USER:-supabase_admin}"

  TENANT_AUTH_DB_USER="$auth_role" \
  TENANT_REST_DB_USER="$rest_role" \
    docker exec -i \
      -e TENANT_AUTH_DB_USER \
      -e TENANT_REST_DB_USER \
      "$db_container" psql -X -q -v ON_ERROR_STOP=1 -1 -U "$db_admin_user" -d postgres <<'SQL' >/dev/null
\getenv auth_role TENANT_AUTH_DB_USER
\getenv rest_role TENANT_REST_DB_USER
SELECT set_config('platform.drop_auth_role', :'auth_role', true),
       set_config('platform.drop_rest_role', :'rest_role', true);
DO $drop_tenant_service_roles$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    current_setting('platform.drop_auth_role'),
    current_setting('platform.drop_rest_role')
  ] LOOP
    IF role_name !~ '^tenant_(auth|rest)_[0-9a-f]{32}$' THEN
      RAISE EXCEPTION 'invalid tenant service role for drop';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('DROP ROLE %I', role_name);
    END IF;
  END LOOP;
END
$drop_tenant_service_roles$;
SQL
}

rollback_tenant_service_roles_to_legacy_db_access() {
  local db="$1" tenant_uuid="${2,,}" auth_role rest_role db_container db_admin_user
  [[ "$db" =~ ^_supabase_[a-z_][a-z0-9_]{2,39}$ ]] || return 1
  auth_role="$(tenant_auth_role_name "$tenant_uuid")" || return 1
  rest_role="$(tenant_rest_role_name "$tenant_uuid")" || return 1

  db_container="${SUPABASE_DB_CONTAINER:-supabase-db}"
  db_admin_user="${SUPABASE_DB_ADMIN_USER:-supabase_admin}"

  reassign_tenant_auth_objects_to_auth_admin "$db" || return 1

  TENANT_AUTH_DB_USER="$auth_role" \
  TENANT_REST_DB_USER="$rest_role" \
    docker exec -i \
      -e TENANT_AUTH_DB_USER \
      -e TENANT_REST_DB_USER \
      "$db_container" psql -X -q -v ON_ERROR_STOP=1 -1 -U "$db_admin_user" -d "$db" <<'SQL' >/dev/null
\getenv auth_role TENANT_AUTH_DB_USER
\getenv rest_role TENANT_REST_DB_USER
SELECT set_config('platform.rollback_auth_role', :'auth_role', true),
       set_config('platform.rollback_rest_role', :'rest_role', true);
DO $rollback_tenant_service_roles$
DECLARE
  db_name text := current_database();
  role_name text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticator') THEN
    EXECUTE format('GRANT CONNECT, TEMPORARY ON DATABASE %I TO authenticator', db_name);
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supabase_auth_admin') THEN
    EXECUTE format('GRANT CONNECT, TEMPORARY, CREATE ON DATABASE %I TO supabase_auth_admin', db_name);
  END IF;
  FOREACH role_name IN ARRAY ARRAY[
    current_setting('platform.rollback_auth_role'),
    current_setting('platform.rollback_rest_role')
  ] LOOP
    IF role_name !~ '^tenant_(auth|rest)_[0-9a-f]{32}$' THEN
      RAISE EXCEPTION 'invalid tenant service role for rollback';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL ON DATABASE %I FROM %I', db_name, role_name);
      EXECUTE format('DROP OWNED BY %I', role_name);
    END IF;
  END LOOP;
END
$rollback_tenant_service_roles$;
SQL

  drop_tenant_service_roles "$tenant_uuid"
}
