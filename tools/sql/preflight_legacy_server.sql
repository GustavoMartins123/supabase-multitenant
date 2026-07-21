\set ON_ERROR_STOP on
\pset pager off

BEGIN TRANSACTION READ ONLY;

SELECT
  current_database() AS database_name,
  current_setting('server_version') AS postgres_version,
  pg_is_in_recovery() AS is_replica;

SELECT
  table_schema,
  table_name,
  column_name,
  data_type,
  udt_name,
  is_nullable
FROM information_schema.columns
WHERE table_schema IN ('public', '_realtime', '_supavisor', '_analytics')
  AND table_name IN (
    'users',
    'projects',
    'project_members',
    'jobs',
    'project_key_envelopes',
    'tenants',
    'extensions'
  )
ORDER BY table_schema, table_name, ordinal_position;

SELECT
  tc.table_schema,
  tc.table_name,
  tc.constraint_name,
  tc.constraint_type,
  kcu.column_name,
  ccu.table_schema AS referenced_schema,
  ccu.table_name AS referenced_table,
  ccu.column_name AS referenced_column
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_schema = tc.constraint_schema
 AND kcu.constraint_name = tc.constraint_name
LEFT JOIN information_schema.constraint_column_usage ccu
  ON ccu.constraint_schema = tc.constraint_schema
 AND ccu.constraint_name = tc.constraint_name
WHERE tc.table_schema = 'public'
  AND tc.table_name IN ('users', 'projects', 'project_members', 'jobs')
ORDER BY tc.table_name, tc.constraint_type, tc.constraint_name, kcu.ordinal_position;

SELECT
  to_regclass('public.users') IS NOT NULL AS users_exists,
  to_regclass('public.projects') IS NOT NULL AS projects_exists,
  to_regclass('public.project_members') IS NOT NULL AS project_members_exists,
  to_regclass('public.jobs') IS NOT NULL AS jobs_exists,
  to_regclass('public.project_key_envelopes') IS NOT NULL AS envelopes_exist,
  to_regclass('_realtime.tenants') IS NOT NULL AS realtime_tenants_exist,
  to_regclass('_supavisor.tenants') IS NOT NULL AS supavisor_tenants_exist;

SELECT format(
  'SELECT count(*) AS projects_total, '
  'count(*) FILTER (WHERE anon_key LIKE %L) AS legacy_anon_keys, '
  'count(*) FILTER (WHERE service_role LIKE %L) AS legacy_service_keys, '
  'count(*) FILTER (WHERE config_token LIKE %L) AS legacy_config_tokens, '
  'count(*) FILTER (WHERE anon_key LIKE %L) AS v2_anon_keys '
  'FROM public.projects',
  'gAAAA%', 'gAAAA%', 'gAAAA%', 'v2:%'
)
WHERE to_regclass('public.projects') IS NOT NULL
\gexec

SELECT
  rolname,
  rolcanlogin,
  rolsuper,
  rolcreaterole,
  rolcreatedb
FROM pg_roles
WHERE rolname IN ('supabase_admin', 'meta_guest', 'pgbouncer')
ORDER BY rolname;

SELECT extname, extversion
FROM pg_extension
WHERE extname IN (
  'uuid-ossp', 'pgcrypto', 'vector', 'pg_net', 'pg_cron', 'vault', 'wrappers'
)
ORDER BY extname;

SELECT
  datname,
  datallowconn,
  datistemplate
FROM pg_database
WHERE datname = 'postgres'
   OR datname = '_supabase'
   OR datname = '_supabase_template'
   OR datname LIKE '\_supabase\_%' ESCAPE '\'
ORDER BY datname;

SELECT
  slot_name,
  slot_type,
  database,
  active
FROM pg_replication_slots
ORDER BY slot_name;

COMMIT;
