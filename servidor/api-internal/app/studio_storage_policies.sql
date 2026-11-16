-- Policy DDL is delegated inside the caller's transaction. Storage ownership
-- and its migration role stay unchanged; tenant SQL logins gain no memberships.
DO $guard_schema$
DECLARE
    tenant_role TEXT := current_setting('platform.meta_role');
    helper_role TEXT := replace(tenant_role,'tenant_meta_','tenant_storage_policy_');
    inherited RECORD;
    previous_tenant TEXT;
    grantee TEXT;
BEGIN
    IF tenant_role !~ '^tenant_meta_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'Invalid tenant policy identity';
    END IF;
    IF EXISTS (
        SELECT FROM pg_namespace n JOIN pg_roles r ON r.oid=n.nspowner
        WHERE n.nspname='studio_storage_guard' AND NOT r.rolsuper
    ) OR EXISTS (
        SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_roles r ON r.oid=c.relowner
        WHERE n.nspname='studio_storage_guard' AND NOT r.rolsuper
    ) THEN
        RAISE EXCEPTION 'Untrusted Storage policy delegation schema';
    END IF;
    FOR inherited IN
        SELECT p.oid, r.rolname, r.rolcanlogin, r.rolcreatedb, r.rolcreaterole,
               r.rolreplication, r.rolbypassrls
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_roles r ON r.oid=p.proowner
        WHERE n.nspname='studio_storage_guard' AND NOT r.rolsuper
    LOOP
        IF inherited.oid IS DISTINCT FROM to_regprocedure('studio_storage_guard.execute_policy(text,bigint,text)') THEN
            RAISE EXCEPTION 'Untrusted Storage policy delegation schema';
        END IF;
        IF inherited.rolname<>helper_role THEN
            IF inherited.rolname !~ '^tenant_storage_policy_[0-9a-f]{32}$'
               OR inherited.rolcanlogin OR inherited.rolcreatedb OR inherited.rolcreaterole
               OR inherited.rolreplication OR inherited.rolbypassrls
               OR to_regclass('studio_storage_guard.authorities') IS NULL THEN
                RAISE EXCEPTION 'Untrusted Storage policy delegation schema';
            END IF;
            previous_tenant := replace(inherited.rolname,'tenant_storage_policy_','tenant_meta_');
            IF NOT EXISTS(SELECT FROM studio_storage_guard.authorities WHERE role_name=previous_tenant) THEN
                RAISE EXCEPTION 'Untrusted Storage policy delegation schema';
            END IF;
            EXECUTE format('ALTER FUNCTION studio_storage_guard.execute_policy(TEXT,BIGINT,TEXT) OWNER TO %I',current_user);
            FOR grantee IN SELECT rolname FROM pg_roles WHERE rolname IN (previous_tenant,inherited.rolname)
            LOOP
                EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA studio_storage_guard FROM %I',grantee);
                EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA studio_storage_guard FROM %I',grantee);
                EXECUTE format('REVOKE ALL ON SCHEMA studio_storage_guard FROM %I',grantee);
            END LOOP;
        END IF;
    END LOOP;
END
$guard_schema$;
CREATE SCHEMA IF NOT EXISTS studio_storage_guard;
REVOKE ALL ON SCHEMA studio_storage_guard FROM PUBLIC;
CREATE TABLE IF NOT EXISTS studio_storage_guard.authorities (
    role_name TEXT PRIMARY KEY,
    signing_key BYTEA NOT NULL CHECK (octet_length(signing_key)=32)
);
REVOKE ALL ON studio_storage_guard.authorities FROM PUBLIC;
DELETE FROM studio_storage_guard.authorities WHERE role_name<>current_setting('platform.meta_role');
INSERT INTO studio_storage_guard.authorities(role_name,signing_key)
VALUES(current_setting('platform.meta_role'),decode(current_setting('platform.storage_policy_key'),'hex'))
ON CONFLICT(role_name) DO UPDATE SET signing_key=EXCLUDED.signing_key;

-- Use PostgreSQL's built-in SHA-256, without adding an extension dependency.
CREATE OR REPLACE FUNCTION studio_storage_guard.signature(key BYTEA, message BYTEA)
RETURNS BYTEA LANGUAGE plpgsql IMMUTABLE STRICT SET search_path=pg_catalog AS $signature$
DECLARE
    inner_pad BYTEA := decode(repeat('36',64),'hex');
    outer_pad BYTEA := decode(repeat('5c',64),'hex');
    i INTEGER;
BEGIN
    IF octet_length(key)<>32 THEN RAISE EXCEPTION 'Invalid signing key'; END IF;
    FOR i IN 0..31 LOOP
        inner_pad := set_byte(inner_pad,i,get_byte(key,i) # 54);
        outer_pad := set_byte(outer_pad,i,get_byte(key,i) # 92);
    END LOOP;
    RETURN sha256(outer_pad || sha256(inner_pad || message));
END
$signature$;

CREATE OR REPLACE FUNCTION studio_storage_guard.execute_policy(statement TEXT, expires BIGINT, proof TEXT)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $policy$
DECLARE
    key BYTEA;
    expected TEXT;
    now_seconds BIGINT := floor(extract(epoch FROM clock_timestamp()));
BEGIN
    SELECT signing_key INTO key FROM studio_storage_guard.authorities WHERE role_name=session_user;
    IF key IS NULL OR proof IS NULL OR proof !~ '^[0-9a-f]{64}$'
       OR expires IS NULL OR expires<now_seconds OR expires>now_seconds+65
       OR statement IS NULL OR octet_length(statement)>1048576 THEN
        RAISE EXCEPTION 'Storage policy delegation is not authorized' USING ERRCODE='42501';
    END IF;
    expected := encode(studio_storage_guard.signature(key,
        convert_to(session_user || E'\n' || expires::TEXT || E'\n' || statement,'UTF8')),'hex');
    IF proof<>expected THEN
        RAISE EXCEPTION 'Storage policy delegation is not authorized' USING ERRCODE='42501';
    END IF;
    -- The API signs only parsed CREATE/ALTER/DROP POLICY statements for the
    -- project's storage.objects/buckets. Other SQL keeps the tenant identity.
    EXECUTE statement;
END
$policy$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA studio_storage_guard FROM PUBLIC;
DO $policy_access$
DECLARE
    tenant_role TEXT := current_setting('platform.meta_role');
    helper_role TEXT := replace(tenant_role,'tenant_meta_','tenant_storage_policy_');
    parent_role TEXT;
    target RECORD;
BEGIN
    IF tenant_role !~ '^tenant_meta_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'Invalid tenant policy identity';
    END IF;
    IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname=helper_role) THEN
        EXECUTE format('CREATE ROLE %I',helper_role);
    END IF;
    EXECUTE format('ALTER ROLE %I NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',helper_role);
    FOR parent_role IN
        SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
        WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname=helper_role)
    LOOP
        EXECUTE format('REVOKE %I FROM %I',parent_role,helper_role);
    END LOOP;
    -- Only the signed function uses the owner's table rights. Tenant logins
    -- gain no membership, and the helper inherits no global role attributes.
    EXECUTE format('GRANT supabase_storage_admin TO %I',helper_role);
    EXECUTE format('GRANT USAGE ON SCHEMA public,auth,storage TO %I',helper_role);
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA studio_storage_guard TO %I',helper_role);
    EXECUTE format('GRANT SELECT ON studio_storage_guard.authorities TO %I',helper_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_storage_guard.signature(BYTEA,BYTEA) TO %I',helper_role);
    EXECUTE format('ALTER FUNCTION studio_storage_guard.execute_policy(TEXT,BIGINT,TEXT) OWNER TO %I',helper_role);
    EXECUTE format('REVOKE CREATE ON SCHEMA studio_storage_guard FROM %I',helper_role);
    FOR target IN
        SELECT c.relname, r.rolname AS owner FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner
        WHERE n.nspname='storage' AND c.relname IN ('objects','buckets') AND c.relkind='r'
    LOOP
        IF target.owner<>'supabase_storage_admin' THEN
            RAISE EXCEPTION 'Storage table % has unexpected owner %',target.relname,target.owner;
        END IF;
    END LOOP;
    EXECUTE format('REVOKE ALL ON studio_storage_guard.authorities FROM %I',tenant_role);
    EXECUTE format('GRANT USAGE ON SCHEMA studio_storage_guard TO %I',tenant_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_storage_guard.execute_policy(TEXT,BIGINT,TEXT) TO %I',tenant_role);
END
$policy_access$;
SELECT set_config('platform.storage_policy_key','',false);
