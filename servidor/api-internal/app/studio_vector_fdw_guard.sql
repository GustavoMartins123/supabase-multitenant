-- Narrow superuser-owned delegation guard for S3 Vectors FDW wrappers.
-- Keeps studio_storage_guard non-superuser and tenant Studio logins free of
-- superuser attributes or role memberships, while allowing HMAC-signed
-- creation/cleanup strictly for extensions.s3_vectors_fdw_handler wrappers
-- and enforcing pinned endpoint_url/aws_region via a superuser EVENT TRIGGER.
DO $fdw_guard_schema$
DECLARE
    tenant_role TEXT := current_setting('platform.meta_role');
    pinned_endpoint TEXT := current_setting('platform.vector_fdw_endpoint_url');
    pinned_region TEXT := current_setting('platform.vector_fdw_aws_region');
    tenant_hex TEXT;
    expected_endpoint TEXT;
    previous_tenant TEXT;
    handler_oid OID;
    obj RECORD;
BEGIN
    IF tenant_role !~ '^tenant_meta_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'Invalid tenant FDW identity';
    END IF;
    IF pinned_endpoint !~ '^http://storage-vector-proxy:8081/fdw/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/vector$' THEN
        RAISE EXCEPTION 'Invalid S3 Vectors FDW pinned endpoint URL';
    END IF;
    tenant_hex := substr(tenant_role, length('tenant_meta_') + 1);
    expected_endpoint := 'http://storage-vector-proxy:8081/fdw/'
        || substr(tenant_hex, 1, 8) || '-'
        || substr(tenant_hex, 9, 4) || '-'
        || substr(tenant_hex, 13, 4) || '-'
        || substr(tenant_hex, 17, 4) || '-'
        || substr(tenant_hex, 21, 12) || '/vector';
    IF pinned_endpoint <> expected_endpoint THEN
        RAISE EXCEPTION 'S3 Vectors FDW pinned endpoint URL does not match tenant identity';
    END IF;
    IF pinned_region !~ '^[a-z0-9][a-z0-9-]{0,62}$' THEN
        RAISE EXCEPTION 'Invalid S3 Vectors FDW pinned AWS region';
    END IF;
    IF NOT (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user) THEN
        RAISE EXCEPTION 'Vector FDW guard must be provisioned by a superuser';
    END IF;
    IF EXISTS (
        SELECT FROM pg_catalog.pg_namespace n
        JOIN pg_catalog.pg_roles r ON r.oid = n.nspowner
        WHERE n.nspname = 'studio_vector_fdw_guard' AND NOT r.rolsuper
    ) OR EXISTS (
        SELECT FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
        WHERE n.nspname = 'studio_vector_fdw_guard' AND NOT r.rolsuper
    ) OR EXISTS (
        SELECT FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
        WHERE n.nspname = 'studio_vector_fdw_guard' AND NOT r.rolsuper
    ) THEN
        RAISE EXCEPTION 'Untrusted Vector FDW delegation schema';
    END IF;
    SELECT p.oid INTO handler_oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'extensions'
       AND p.proname = 's3_vectors_fdw_handler'
       AND p.pronargs = 0
     LIMIT 1;
    IF to_regclass('studio_vector_fdw_guard.authorities') IS NOT NULL THEN
        FOR previous_tenant IN
            SELECT role_name FROM studio_vector_fdw_guard.authorities
            WHERE role_name <> tenant_role
        LOOP
            IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = previous_tenant) THEN
                EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA studio_vector_fdw_guard FROM %I', previous_tenant);
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA studio_vector_fdw_guard FROM %I', previous_tenant);
                EXECUTE format('REVOKE ALL ON SCHEMA studio_vector_fdw_guard FROM %I', previous_tenant);
                IF handler_oid IS NOT NULL THEN
                    FOR obj IN
                        SELECT s.srvname
                          FROM pg_catalog.pg_foreign_server s
                          JOIN pg_catalog.pg_foreign_data_wrapper w ON w.oid = s.srvfdw
                         WHERE w.fdwhandler = handler_oid
                    LOOP
                        EXECUTE format('REVOKE ALL ON FOREIGN SERVER %I FROM %I', obj.srvname, previous_tenant);
                    END LOOP;
                    FOR obj IN
                        SELECT w.fdwname
                          FROM pg_catalog.pg_foreign_data_wrapper w
                         WHERE w.fdwhandler = handler_oid
                    LOOP
                        EXECUTE format('REVOKE ALL ON FOREIGN DATA WRAPPER %I FROM %I', obj.fdwname, previous_tenant);
                    END LOOP;
                END IF;
            END IF;
        END LOOP;
    END IF;
END
$fdw_guard_schema$;

CREATE SCHEMA IF NOT EXISTS studio_vector_fdw_guard;
REVOKE ALL ON SCHEMA studio_vector_fdw_guard FROM PUBLIC;

CREATE TABLE IF NOT EXISTS studio_vector_fdw_guard.authorities (
    role_name TEXT PRIMARY KEY,
    signing_key BYTEA NOT NULL CHECK (octet_length(signing_key) = 32)
);
REVOKE ALL ON studio_vector_fdw_guard.authorities FROM PUBLIC;

CREATE TABLE IF NOT EXISTS studio_vector_fdw_guard.server_policy (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    endpoint_url TEXT NOT NULL,
    aws_region TEXT NOT NULL
);
REVOKE ALL ON studio_vector_fdw_guard.server_policy FROM PUBLIC;

DELETE FROM studio_vector_fdw_guard.authorities WHERE role_name <> current_setting('platform.meta_role');
INSERT INTO studio_vector_fdw_guard.authorities(role_name, signing_key)
VALUES (
    current_setting('platform.meta_role'),
    decode(current_setting('platform.vector_fdw_key'), 'hex')
)
ON CONFLICT (role_name) DO UPDATE SET signing_key = EXCLUDED.signing_key;

INSERT INTO studio_vector_fdw_guard.server_policy(singleton, endpoint_url, aws_region)
VALUES (
    TRUE,
    current_setting('platform.vector_fdw_endpoint_url'),
    current_setting('platform.vector_fdw_aws_region')
)
ON CONFLICT (singleton) DO UPDATE
   SET endpoint_url = EXCLUDED.endpoint_url,
       aws_region = EXCLUDED.aws_region;

-- Pure built-in SHA-256 HMAC helper (not SECURITY DEFINER, not granted to tenants).
CREATE OR REPLACE FUNCTION studio_vector_fdw_guard.signature(key BYTEA, message BYTEA)
RETURNS BYTEA LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = pg_catalog AS $fdw_signature$
DECLARE
    inner_pad BYTEA := decode(repeat('36', 64), 'hex');
    outer_pad BYTEA := decode(repeat('5c', 64), 'hex');
    i INTEGER;
BEGIN
    IF octet_length(key) <> 32 THEN
        RAISE EXCEPTION 'Invalid signing key';
    END IF;
    FOR i IN 0..31 LOOP
        inner_pad := set_byte(inner_pad, i, get_byte(key, i) # 54);
        outer_pad := set_byte(outer_pad, i, get_byte(key, i) # 92);
    END LOOP;
    RETURN sha256(outer_pad || sha256(inner_pad || message));
END
$fdw_signature$;

CREATE OR REPLACE FUNCTION studio_vector_fdw_guard.ensure_s3_vectors_fdw(
    fdw_name TEXT,
    expires BIGINT,
    proof TEXT
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, extensions AS $ensure_fdw$
DECLARE
    key BYTEA;
    expected TEXT;
    now_seconds BIGINT := floor(extract(epoch FROM clock_timestamp()));
    handler_oid OID;
    validator_oid OID;
    existing_fdw RECORD;
BEGIN
    IF fdw_name IS NULL OR fdw_name !~ '^[a-z0-9_]{1,63}$' THEN
        RAISE EXCEPTION 'Invalid S3 Vectors FDW name' USING ERRCODE = '42501';
    END IF;
    SELECT signing_key INTO key
      FROM studio_vector_fdw_guard.authorities
     WHERE role_name = session_user;
    IF key IS NULL OR proof IS NULL OR proof !~ '^[0-9a-f]{64}$'
       OR expires IS NULL OR expires < now_seconds OR expires > now_seconds + 65 THEN
        RAISE EXCEPTION 'Vector FDW delegation is not authorized' USING ERRCODE = '42501';
    END IF;
    expected := encode(
        studio_vector_fdw_guard.signature(
            key,
            convert_to(
                'ensure_s3_vectors_fdw' || E'\n' || session_user || E'\n' || expires::TEXT || E'\n' || fdw_name,
                'UTF8'
            )
        ),
        'hex'
    );
    IF proof <> expected THEN
        RAISE EXCEPTION 'Vector FDW delegation is not authorized' USING ERRCODE = '42501';
    END IF;

    SELECT p.oid INTO handler_oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'extensions'
       AND p.proname = 's3_vectors_fdw_handler'
       AND p.pronargs = 0
     LIMIT 1;
    SELECT p.oid INTO validator_oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'extensions'
       AND p.proname = 's3_vectors_fdw_validator'
       AND p.pronargs = 2
     LIMIT 1;
    IF handler_oid IS NULL OR validator_oid IS NULL THEN
        RAISE EXCEPTION 's3_vectors_fdw handler/validator not installed in schema extensions' USING ERRCODE = '42883';
    END IF;

    SELECT w.fdwhandler, w.fdwvalidator
      INTO existing_fdw
      FROM pg_catalog.pg_foreign_data_wrapper w
     WHERE w.fdwname = ensure_s3_vectors_fdw.fdw_name;
    IF FOUND THEN
        IF existing_fdw.fdwhandler IS DISTINCT FROM handler_oid
           OR existing_fdw.fdwvalidator IS DISTINCT FROM validator_oid THEN
            RAISE EXCEPTION 'Foreign data wrapper % is not an s3_vectors_fdw wrapper', fdw_name USING ERRCODE = '42501';
        END IF;
    ELSE
        EXECUTE format(
            'CREATE FOREIGN DATA WRAPPER %I HANDLER extensions.s3_vectors_fdw_handler VALIDATOR extensions.s3_vectors_fdw_validator',
            fdw_name
        );
    END IF;
    EXECUTE format('GRANT USAGE ON FOREIGN DATA WRAPPER %I TO %I', fdw_name, session_user);
END
$ensure_fdw$;

CREATE OR REPLACE FUNCTION studio_vector_fdw_guard.drop_s3_vectors_fdw(
    fdw_name TEXT,
    expires BIGINT,
    proof TEXT
)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, extensions AS $drop_fdw$
DECLARE
    key BYTEA;
    expected TEXT;
    now_seconds BIGINT := floor(extract(epoch FROM clock_timestamp()));
    handler_oid OID;
    existing_handler OID;
BEGIN
    IF fdw_name IS NULL OR fdw_name !~ '^[a-z0-9_]{1,63}$' THEN
        RAISE EXCEPTION 'Invalid S3 Vectors FDW name' USING ERRCODE = '42501';
    END IF;
    SELECT signing_key INTO key
      FROM studio_vector_fdw_guard.authorities
     WHERE role_name = session_user;
    IF key IS NULL OR proof IS NULL OR proof !~ '^[0-9a-f]{64}$'
       OR expires IS NULL OR expires < now_seconds OR expires > now_seconds + 65 THEN
        RAISE EXCEPTION 'Vector FDW delegation is not authorized' USING ERRCODE = '42501';
    END IF;
    expected := encode(
        studio_vector_fdw_guard.signature(
            key,
            convert_to(
                'drop_s3_vectors_fdw' || E'\n' || session_user || E'\n' || expires::TEXT || E'\n' || fdw_name,
                'UTF8'
            )
        ),
        'hex'
    );
    IF proof <> expected THEN
        RAISE EXCEPTION 'Vector FDW delegation is not authorized' USING ERRCODE = '42501';
    END IF;

    SELECT w.fdwhandler INTO existing_handler
      FROM pg_catalog.pg_foreign_data_wrapper w
     WHERE w.fdwname = drop_s3_vectors_fdw.fdw_name;
    IF FOUND THEN
        SELECT p.oid INTO handler_oid
          FROM pg_catalog.pg_proc p
          JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = 'extensions'
           AND p.proname = 's3_vectors_fdw_handler'
           AND p.pronargs = 0
         LIMIT 1;
        IF handler_oid IS NULL OR existing_handler IS DISTINCT FROM handler_oid THEN
            RAISE EXCEPTION 'Cannot drop non-vector foreign data wrapper %', fdw_name USING ERRCODE = '42501';
        END IF;
        EXECUTE format('DROP FOREIGN DATA WRAPPER IF EXISTS %I CASCADE', fdw_name);
    END IF;
END
$drop_fdw$;

-- Superuser-owned EVENT TRIGGER enforcing pinned endpoint_url & aws_region on
-- all non-superuser CREATE SERVER / ALTER SERVER DDL targeting s3_vectors_fdw,
-- closing dynamic SQL string-concatenation SSRF bypasses inside DO/functions.
CREATE OR REPLACE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint()
RETURNS event_trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, extensions AS $enforce_server$
DECLARE
    pinned RECORD;
    handler_oid OID;
    srv RECORD;
    endpoint_vals TEXT[];
    region_vals TEXT[];
BEGIN
    IF (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = session_user) THEN
        RETURN;
    END IF;
    SELECT p.oid INTO handler_oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'extensions'
       AND p.proname = 's3_vectors_fdw_handler'
       AND p.pronargs = 0
     LIMIT 1;
    IF handler_oid IS NULL THEN
        RETURN;
    END IF;
    SELECT endpoint_url, aws_region
      INTO pinned
      FROM studio_vector_fdw_guard.server_policy
     WHERE singleton = TRUE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'S3 Vectors FDW endpoint policy is not configured' USING ERRCODE = '42501';
    END IF;
    FOR srv IN
        SELECT s.srvname, coalesce(s.srvoptions, ARRAY[]::TEXT[]) AS srvoptions
          FROM pg_catalog.pg_foreign_server s
          JOIN pg_catalog.pg_foreign_data_wrapper w ON w.oid = s.srvfdw
         WHERE w.fdwhandler = handler_oid
    LOOP
        SELECT array_agg(substr(opt, strpos(opt, '=') + 1))
          INTO endpoint_vals
          FROM unnest(srv.srvoptions) AS opt
         WHERE lower(split_part(opt, '=', 1)) = 'endpoint_url';
        SELECT array_agg(substr(opt, strpos(opt, '=') + 1))
          INTO region_vals
          FROM unnest(srv.srvoptions) AS opt
         WHERE lower(split_part(opt, '=', 1)) = 'aws_region';
        IF coalesce(array_length(endpoint_vals, 1), 0) <> 1
           OR endpoint_vals[1] IS DISTINCT FROM pinned.endpoint_url
           OR coalesce(array_length(region_vals, 1), 0) <> 1
           OR region_vals[1] IS DISTINCT FROM pinned.aws_region THEN
            RAISE EXCEPTION 'S3 Vectors foreign server % must use pinned endpoint_url and aws_region', srv.srvname
                USING ERRCODE = '42501';
        END IF;
    END LOOP;
END
$enforce_server$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA studio_vector_fdw_guard FROM PUBLIC;

DO $fdw_server_event$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_event_trigger
         WHERE evtname = 'studio_vector_fdw_enforce_server_endpoint'
    ) THEN
        CREATE EVENT TRIGGER studio_vector_fdw_enforce_server_endpoint
            ON ddl_command_end
            WHEN TAG IN ('CREATE SERVER', 'ALTER SERVER')
            EXECUTE FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint();
    END IF;
END
$fdw_server_event$;

DO $fdw_guard_access$
DECLARE
    tenant_role TEXT := current_setting('platform.meta_role');
    handler_oid OID;
    obj RECORD;
BEGIN
    IF tenant_role !~ '^tenant_meta_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'Invalid tenant FDW identity';
    END IF;
    EXECUTE format('REVOKE ALL ON studio_vector_fdw_guard.authorities FROM %I', tenant_role);
    EXECUTE format('REVOKE ALL ON studio_vector_fdw_guard.server_policy FROM %I', tenant_role);
    EXECUTE format('REVOKE ALL ON FUNCTION studio_vector_fdw_guard.signature(BYTEA, BYTEA) FROM %I', tenant_role);
    EXECUTE format('REVOKE ALL ON FUNCTION studio_vector_fdw_guard.enforce_vector_server_endpoint() FROM %I', tenant_role);
    EXECUTE format('GRANT USAGE ON SCHEMA studio_vector_fdw_guard TO %I', tenant_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_vector_fdw_guard.ensure_s3_vectors_fdw(TEXT, BIGINT, TEXT) TO %I', tenant_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_vector_fdw_guard.drop_s3_vectors_fdw(TEXT, BIGINT, TEXT) TO %I', tenant_role);
    SELECT p.oid INTO handler_oid
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
     WHERE n.nspname = 'extensions'
       AND p.proname = 's3_vectors_fdw_handler'
       AND p.pronargs = 0
     LIMIT 1;
    IF handler_oid IS NOT NULL THEN
        FOR obj IN
            SELECT w.fdwname
              FROM pg_catalog.pg_foreign_data_wrapper w
             WHERE w.fdwhandler = handler_oid
        LOOP
            EXECUTE format('GRANT USAGE ON FOREIGN DATA WRAPPER %I TO %I', obj.fdwname, tenant_role);
        END LOOP;
        FOR obj IN
            SELECT s.srvname
              FROM pg_catalog.pg_foreign_server s
              JOIN pg_catalog.pg_foreign_data_wrapper w ON w.oid = s.srvfdw
             WHERE w.fdwhandler = handler_oid
        LOOP
            EXECUTE format('GRANT USAGE ON FOREIGN SERVER %I TO %I', obj.srvname, tenant_role);
        END LOOP;
    END IF;
END
$fdw_guard_access$;

SELECT
    set_config('platform.vector_fdw_key', '', false),
    set_config('platform.vector_fdw_endpoint_url', '', false),
    set_config('platform.vector_fdw_aws_region', '', false);
