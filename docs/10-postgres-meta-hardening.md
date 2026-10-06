# Postgres-Meta hardening

This installation uses a `postgres-meta-global` shared across projects. When the dynamic encrypted connection fails, the service must fall back to the empty `meta_trap` database using the restricted `meta_guest` user.

## Objective

If someone obtains only the `meta_guest` password, the expected impact is:

- being able to connect only to the `meta_trap` database;
- being unable to connect to `postgres`, `_supabase`, `_supabase_template`, `template0`, `template1`, or `_supabase_*` databases;
- being unable to create tables, temporary tables, schemas, functions, or extensions;
- being unable to assume administrative roles;
- being unable to read server files or execute commands through `COPY PROGRAM`.

## Threat model

This hardening does not attempt to protect against root access to the machine or direct control of the PostgreSQL container. Its goal is to contain a failure chain in the `postgres-meta-global` flow:

- an authenticated Studio user;
- a valid user token and valid project `service_role`;
- a `pg-meta` route receiving unexpected input;
- the Python API or `postgres-meta-global` failing to resolve/decrypt the dynamic connection;
- the fallback attempting to connect to the default database.

In this scenario, the fallback must always land in `meta_trap` with `meta_guest`, without being able to pivot to real databases, extensions, server files, or administrative roles.

## Applied controls

In the `servidor/volumes/db/create_template.sh` script, `meta_guest` must be created with:

- `LOGIN`, but without `SUPERUSER`, `CREATEDB`, `CREATEROLE`, `REPLICATION`, or `BYPASSRLS`;
- `NOINHERIT`;
- `CONNECTION LIMIT 5`;
- `search_path = 'pg_catalog'`;
- `statement_timeout = '5s'`;
- `idle_in_transaction_session_timeout = '5s'`;
- only `CONNECT` on the `meta_trap` database;
- no `CREATE` or `TEMPORARY` on `meta_trap`;
- no permissions on the `public` schema;
- no sensitive predefined roles, such as `pg_monitor`, `pg_read_all_data`, `pg_write_all_data`, `pg_read_server_files`, `pg_write_server_files`, `pg_execute_server_program`, and `pg_signal_backend`.

The `meta_trap` database also has an `EVENT TRIGGER` named `block_meta_guest_extension_ddl`, used to block `CREATE EXTENSION`, `ALTER EXTENSION`, and `DROP EXTENSION` when the session user is `meta_guest`. This is necessary because the Supabase Postgres image uses `supautils.privileged_extensions`, which can delegate extension creation to `supabase_admin`.

The Python API endpoint `/api/projects/{ref}/meta...` also applies controls before calling `postgres-meta-global`:

- `ref` passes through `validate_project_id`, accepting only the internal project-id pattern;
- the project connection is always built internally as `_supabase_{ref}`;
- the `DB_DSN` query string, parameters, and fragment are discarded when building the pg-meta connection;
- `PG_META_INTERNAL_URL` is validated at startup and must point to a host allowed by `PG_META_ALLOWED_HOSTS`, with no path, query string, fragment, or userinfo;
- the API does not forward connection headers from the client; it generates only `x-connection-encrypted`;
- the proxy requires an authenticated user, project membership, and a valid project `service_role`.

## Validation checklist

Run these tests after updating the `supabase/postgres` image, recreating the database, or changing permissions:

```sql
SELECT current_user, session_user, current_database();

SELECT rolname, rolsuper, rolcreatedb, rolcreaterole,
       rolreplication, rolbypassrls, rolinherit, rolconnlimit
FROM pg_roles
WHERE rolname = 'meta_guest';

SELECT datname,
       has_database_privilege('meta_guest', datname, 'CONNECT') AS connect,
       has_database_privilege('meta_guest', datname, 'CREATE') AS create_db,
       has_database_privilege('meta_guest', datname, 'TEMPORARY') AS temp
FROM pg_database
ORDER BY datname;

SHOW search_path;
SHOW statement_timeout;
SHOW idle_in_transaction_session_timeout;
SHOW supautils.privileged_extensions;

SET ROLE supabase_admin;
CREATE TEMP TABLE meta_guest_temp_check(id int);
CREATE TABLE public.meta_guest_table_check(id int);
CREATE EXTENSION hstore;
CREATE EXTENSION dblink;
CREATE EXTENSION http;
CREATE EXTENSION pg_net;
SELECT pg_read_file('/etc/passwd', 0, 100);
SELECT pg_ls_dir('/');
COPY (SELECT 1) TO PROGRAM 'id';
DROP SCHEMA meta_guard CASCADE;
DROP EVENT TRIGGER block_meta_guest_extension_ddl;
```

Expected result:

- `meta_guest` must have `CONNECT = true` only on `meta_trap`;
- `CREATE` and `TEMPORARY` must be `false` for `meta_guest` in every database;
- all creation, extension, file-reading, program-execution, role-switching, and protection-removal commands must fail;
- `pg_extension` in `meta_trap` must contain only expected essential extensions, usually `plpgsql`.

## Known limitation

The user can still query global catalogs such as `pg_database` and therefore list database names with commands such as `\l`. This is not equivalent to connection permission. The applied mitigation is to prevent `CONNECT`, `CREATE`, `TEMPORARY`, extension operations, and privilege escalation.
