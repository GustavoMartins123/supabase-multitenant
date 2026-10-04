-- Used by both privileged migrations and lifecycle scripts. Never executed by HTTP.
SELECT set_config('platform.meta_role', :'meta_role', false);
SELECT set_config('platform.meta_password', :'meta_password', false);
DO $tenant_meta$
DECLARE
    tenant_role text := current_setting('platform.meta_role');
    parent_role text;
    obj record;
BEGIN
    IF tenant_role !~ '^tenant_meta_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'invalid tenant SQL identity';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = tenant_role) THEN
        EXECUTE format('CREATE ROLE %I', tenant_role);
    END IF;
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION BYPASSRLS CONNECTION LIMIT 20 PASSWORD %L', tenant_role, current_setting('platform.meta_password'));
    -- NOINHERIT alone does not prevent SET ROLE: remove every membership.
    FOR parent_role IN
        SELECT parent.rolname FROM pg_auth_members m
        JOIN pg_roles parent ON parent.oid=m.roleid
        JOIN pg_roles member ON member.oid=m.member
        WHERE member.rolname=tenant_role
    LOOP
        EXECUTE format('REVOKE %I FROM %I', parent_role, tenant_role);
    END LOOP;
    EXECUTE format('ALTER ROLE %I SET statement_timeout = %L', tenant_role, '30s');
    EXECUTE format('ALTER ROLE %I SET lock_timeout = %L', tenant_role, '10s');
    EXECUTE format('GRANT CONNECT, CREATE, TEMPORARY ON DATABASE %I TO %I', current_database(), tenant_role);
    -- Ownership is local to public; shared Auth/Storage roles are never granted.
    EXECUTE format('ALTER SCHEMA public OWNER TO %I', tenant_role);
    FOR obj IN
        SELECT c.relname, c.relkind FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=c.oid AND d.deptype='e' AND d.classid='pg_class'::regclass)
    LOOP
        EXECUTE format('ALTER %s public.%I OWNER TO %I',
            CASE obj.relkind WHEN 'S' THEN 'SEQUENCE' WHEN 'v' THEN 'VIEW'
                WHEN 'm' THEN 'MATERIALIZED VIEW' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
            obj.relname, tenant_role);
    END LOOP;
    FOR obj IN
        SELECT p.oid::regprocedure AS signature, p.prokind FROM pg_proc p
        JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prokind IN ('f','p')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=p.oid AND d.deptype='e' AND d.classid='pg_proc'::regclass)
    LOOP
        -- SECURITY DEFINER functions no longer carry a shared privileged owner.
        EXECUTE format('ALTER %s %s OWNER TO %I',
            CASE obj.prokind WHEN 'p' THEN 'PROCEDURE' ELSE 'FUNCTION' END,
            obj.signature, tenant_role);
    END LOOP;
    FOR obj IN
        SELECT t.typname FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
        WHERE n.nspname='public' AND t.typtype IN ('e','d')
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.objid=t.oid AND d.deptype='e' AND d.classid='pg_type'::regclass)
    LOOP
        EXECUTE format('ALTER %s public.%I OWNER TO %I',
            CASE WHEN (SELECT typtype FROM pg_type WHERE oid=format('public.%I',obj.typname)::regtype)='d' THEN 'DOMAIN' ELSE 'TYPE' END,
            obj.typname, tenant_role);
    END LOOP;
    FOR obj IN SELECT nspname FROM pg_namespace WHERE nspname IN ('auth','storage','extensions') LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', obj.nspname, tenant_role);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I', obj.nspname, tenant_role);
        EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO %I', obj.nspname, tenant_role);
    END LOOP;
END
$tenant_meta$;
DO $assistant_reader$
DECLARE
    reader_role text := replace(current_setting('platform.meta_role'), 'tenant_meta_', 'tenant_ai_reader_');
    reader_password text := encode(sha256(convert_to('assistant-reader-v1:' || current_setting('platform.meta_password'), 'UTF8')), 'hex');
    parent_role text;
BEGIN
    IF reader_role !~ '^tenant_ai_reader_[0-9a-f]{32}$' THEN
        RAISE EXCEPTION 'invalid assistant SQL identity';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=reader_role) THEN
        EXECUTE format('CREATE ROLE %I', reader_role);
    END IF;
    EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 4 PASSWORD %L', reader_role, reader_password);
    FOR parent_role IN
        SELECT parent.rolname FROM pg_auth_members m
        JOIN pg_roles parent ON parent.oid=m.roleid
        JOIN pg_roles member ON member.oid=m.member
        WHERE member.rolname=reader_role
    LOOP
        EXECUTE format('REVOKE %I FROM %I', parent_role, reader_role);
    END LOOP;
    EXECUTE format('ALTER ROLE %I SET default_transaction_read_only=on', reader_role);
    EXECUTE format('ALTER ROLE %I SET statement_timeout=%L', reader_role, '10s');
    EXECUTE format('ALTER ROLE %I SET lock_timeout=%L', reader_role, '2s');
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), reader_role);
    EXECUTE format('GRANT USAGE ON SCHEMA public TO %I', reader_role);
    EXECUTE format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', reader_role);
    EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I', current_setting('platform.meta_role'), reader_role);
END
$assistant_reader$;
SELECT set_config('platform.meta_password', '', false);
