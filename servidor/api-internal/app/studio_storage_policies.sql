-- Delegated DDL for Storage/Auth runs inside the caller's transaction while
-- keeping Storage/Auth ownership unchanged and tenant logins free of memberships.
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
        WHERE n.nspname IN ('studio_storage_guard','studio_trigger_guard') AND NOT r.rolsuper
    ) OR EXISTS (
        SELECT FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_roles r ON r.oid=c.relowner
        WHERE n.nspname IN ('studio_storage_guard','studio_trigger_guard') AND NOT r.rolsuper
    ) OR EXISTS (
        SELECT FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        JOIN pg_roles r ON r.oid=p.proowner
        WHERE n.nspname='studio_trigger_guard' AND NOT r.rolsuper
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
CREATE TABLE IF NOT EXISTS studio_storage_guard.managed_indexes (
    schema_name TEXT NOT NULL,
    index_name TEXT NOT NULL,
    PRIMARY KEY (schema_name, index_name)
);
REVOKE ALL ON studio_storage_guard.managed_indexes FROM PUBLIC;
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

CREATE OR REPLACE FUNCTION studio_storage_guard.unquote_ident(raw TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE STRICT SET search_path=pg_catalog AS $ident$
SELECT CASE
    WHEN left(raw,1)='"' AND right(raw,1)='"' AND length(raw)>=2
        THEN replace(substr(raw,2,length(raw)-2),'""','"')
    ELSE lower(raw)
END;
$ident$;

CREATE OR REPLACE FUNCTION studio_storage_guard.execute_policy(statement TEXT, expires BIGINT, proof TEXT)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $policy$
DECLARE
    key BYTEA;
    expected TEXT;
    now_seconds BIGINT := floor(extract(epoch FROM clock_timestamp()));
    trimmed TEXT;
    ident CONSTANT TEXT := '(?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_$]*)';
    m TEXT[];
    ddl_kind TEXT;
    target_schema TEXT;
    target_table TEXT;
    obj_name TEXT;
    idx_existed BOOLEAN := FALSE;
    trig_rec RECORD;
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

    trimmed := btrim(statement);
    m := pg_catalog.regexp_match(
        trimmed,
        '^(CREATE|ALTER)\s+POLICY\s+' || ident || '\s+ON\s+(storage|"storage")\.(objects|"objects"|buckets|"buckets")(?:\s|$)',
        'i'
    );
    IF m IS NOT NULL THEN
        ddl_kind := 'policy_write';
    ELSE
        m := pg_catalog.regexp_match(
            trimmed,
            '^DROP\s+POLICY\s+(?:IF\s+EXISTS\s+)?' || ident || '\s+ON\s+(storage|"storage")\.(objects|"objects"|buckets|"buckets")\s*$',
            'i'
        );
        IF m IS NOT NULL THEN
            ddl_kind := 'policy_drop';
        ELSE
            m := pg_catalog.regexp_match(
                trimmed,
                '^CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+(' || ident || ')\s+(?:BEFORE|AFTER|INSTEAD\s+OF)\s+.+?\s+ON\s+(storage|"storage"|auth|"auth")\.(objects|"objects"|buckets|"buckets"|users|"users"|identities|"identities")\s+',
                'i'
            );
            IF m IS NOT NULL THEN
                ddl_kind := 'trigger_create';
                obj_name := studio_storage_guard.unquote_ident(m[1]);
                target_schema := studio_storage_guard.unquote_ident(m[2]);
                target_table := studio_storage_guard.unquote_ident(m[3]);
            ELSE
                m := pg_catalog.regexp_match(
                    trimmed,
                    '^DROP\s+TRIGGER\s+(?:IF\s+EXISTS\s+)?(' || ident || ')\s+ON\s+(storage|"storage"|auth|"auth")\.(objects|"objects"|buckets|"buckets"|users|"users"|identities|"identities")\s*$',
                    'i'
                );
                IF m IS NOT NULL THEN
                    ddl_kind := 'trigger_drop';
                    obj_name := studio_storage_guard.unquote_ident(m[1]);
                    target_schema := studio_storage_guard.unquote_ident(m[2]);
                    target_table := studio_storage_guard.unquote_ident(m[3]);
                ELSE
                    m := pg_catalog.regexp_match(
                        trimmed,
                        '^ALTER\s+TABLE\s+(?:ONLY\s+)?(storage|"storage"|auth|"auth")\.(objects|"objects"|buckets|"buckets"|users|"users"|identities|"identities")\s+(?:ENABLE|DISABLE)\s+TRIGGER\s+(' || ident || ')\s*$',
                        'i'
                    );
                    IF m IS NOT NULL THEN
                        ddl_kind := 'trigger_toggle';
                        target_schema := studio_storage_guard.unquote_ident(m[1]);
                        target_table := studio_storage_guard.unquote_ident(m[2]);
                        obj_name := studio_storage_guard.unquote_ident(m[3]);
                        IF lower(obj_name) IN ('all','user') THEN
                            RAISE EXCEPTION 'Bulk trigger modification on %.% is not allowed', target_schema, target_table USING ERRCODE='42501';
                        END IF;
                    ELSE
                        m := pg_catalog.regexp_match(
                            trimmed,
                            '^CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(' || ident || ')\s+ON\s+(?:ONLY\s+)?(storage|"storage"|auth|"auth")\.(objects|"objects"|buckets|"buckets"|users|"users"|identities|"identities")(?:\s+USING\s+(?:btree|hash|gin|gist|brin))?\s*\(',
                            'i'
                        );
                        IF m IS NOT NULL THEN
                            ddl_kind := 'index_create';
                            obj_name := studio_storage_guard.unquote_ident(m[1]);
                            target_schema := studio_storage_guard.unquote_ident(m[2]);
                            target_table := studio_storage_guard.unquote_ident(m[3]);
                        ELSE
                            m := pg_catalog.regexp_match(
                                trimmed,
                                '^DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?(storage|"storage"|auth|"auth")\.(' || ident || ')\s*$',
                                'i'
                            );
                            IF m IS NOT NULL THEN
                                ddl_kind := 'index_drop';
                                target_schema := studio_storage_guard.unquote_ident(m[1]);
                                obj_name := studio_storage_guard.unquote_ident(m[2]);
                            ELSE
                                RAISE EXCEPTION 'Delegated Storage/Auth DDL statement is not allowed' USING ERRCODE='42501';
                            END IF;
                        END IF;
                    END IF;
                END IF;
            END IF;
        END IF;
    END IF;

    IF ddl_kind IN ('trigger_create','trigger_drop','trigger_toggle') THEN
        SELECT t.tgisinternal, pn.nspname AS fn_schema
          INTO trig_rec
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
          JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
         WHERE n.nspname=target_schema AND c.relname=target_table AND t.tgname=obj_name
         LIMIT 1;
        IF FOUND AND (trig_rec.tgisinternal OR trig_rec.fn_schema IN ('storage','auth')) THEN
            RAISE EXCEPTION 'Cannot modify internal trigger % on %.%', obj_name, target_schema, target_table USING ERRCODE='42501';
        END IF;
    ELSIF ddl_kind='index_create' THEN
        idx_existed := (to_regclass(format('%I.%I',target_schema,obj_name)) IS NOT NULL);
    ELSIF ddl_kind='index_drop' THEN
        IF NOT EXISTS (
            SELECT 1 FROM studio_storage_guard.managed_indexes
             WHERE schema_name=target_schema AND index_name=obj_name
        ) AND to_regclass(format('%I.%I',target_schema,obj_name)) IS NOT NULL THEN
            RAISE EXCEPTION 'Cannot drop internal index %.%', target_schema, obj_name USING ERRCODE='42501';
        END IF;
    END IF;

    -- The API signs only parsed Storage/Auth DDL for allowed tables.
    -- Other SQL keeps the isolated tenant identity.
    EXECUTE statement;

    IF ddl_kind='trigger_create' THEN
        SELECT t.tgisinternal, p.prosecdef, pn.nspname AS fn_schema, r.rolname AS fn_owner,
               EXISTS (
                   SELECT 1 FROM unnest(coalesce(p.proconfig,ARRAY[]::text[])) cfg
                    WHERE lower(cfg) LIKE 'role=%' OR lower(cfg) LIKE 'session_authorization=%'
               ) AS has_role_cfg
          INTO trig_rec
          FROM pg_catalog.pg_trigger t
          JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
          JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
          JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
          JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
          JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
         WHERE n.nspname=target_schema AND c.relname=target_table AND t.tgname=obj_name
         LIMIT 1;
        IF NOT FOUND OR trig_rec.tgisinternal
           OR trig_rec.fn_schema IN ('storage','auth','pg_catalog','studio_storage_guard','studio_trigger_guard')
           OR NOT trig_rec.prosecdef
           OR trig_rec.fn_owner IS DISTINCT FROM session_user
           OR trig_rec.has_role_cfg THEN
            RAISE EXCEPTION 'Trigger % on %.% requires a SECURITY DEFINER function owned by the project role',
                obj_name, target_schema, target_table USING ERRCODE='42501';
        END IF;
    ELSIF ddl_kind='policy_write' THEN
        IF EXISTS (
            SELECT 1 FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
             WHERE n.nspname='storage' AND c.relname IN ('objects','buckets') AND c.relforcerowsecurity
        ) THEN
            RAISE EXCEPTION 'FORCE ROW LEVEL SECURITY is not permitted on storage tables' USING ERRCODE='42501';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM pg_catalog.pg_policy pol
              JOIN pg_catalog.pg_class c ON c.oid=pol.polrelid
              JOIN pg_catalog.pg_namespace cn ON cn.oid=c.relnamespace
              JOIN pg_catalog.pg_depend d ON d.classid='pg_catalog.pg_policy'::regclass
                                         AND d.objid=pol.oid
                                         AND d.refclassid='pg_catalog.pg_proc'::regclass
              JOIN pg_catalog.pg_proc p ON p.oid=d.refobjid
              JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
              JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
             WHERE cn.nspname='storage'
               AND c.relname IN ('objects','buckets')
               AND p.prosecdef
               AND pn.nspname NOT IN ('auth','storage','pg_catalog')
               AND (
                   r.rolsuper
                   OR r.rolcreaterole
                   OR r.rolname IN (
                       'supabase_storage_admin','supabase_auth_admin',
                       'supabase_functions_admin','postgres','supabase_admin'
                   )
               )
        ) THEN
            RAISE EXCEPTION 'Storage policy cannot reference a privileged SECURITY DEFINER function' USING ERRCODE='42501';
        END IF;
    ELSIF ddl_kind='index_create' AND NOT idx_existed THEN
        INSERT INTO studio_storage_guard.managed_indexes(schema_name,index_name)
        VALUES(target_schema,obj_name)
        ON CONFLICT DO NOTHING;
    ELSIF ddl_kind='index_drop' THEN
        DELETE FROM studio_storage_guard.managed_indexes
         WHERE schema_name=target_schema AND index_name=obj_name;
    END IF;
END
$policy$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA studio_storage_guard FROM PUBLIC;

-- Superuser-owned schema (dumped cleanly with clones, no secrets) preventing
-- post-creation downgrade of Storage/Auth trigger functions to SECURITY INVOKER.
CREATE SCHEMA IF NOT EXISTS studio_trigger_guard;
REVOKE ALL ON SCHEMA studio_trigger_guard FROM PUBLIC;
CREATE OR REPLACE FUNCTION studio_trigger_guard.enforce_system_trigger_security()
RETURNS event_trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $trigger_guard$
DECLARE
    bad RECORD;
BEGIN
    IF (SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname=session_user) THEN
        RETURN;
    END IF;
    SELECT n.nspname, c.relname, t.tgname, p.oid::regprocedure AS fn
      INTO bad
      FROM pg_catalog.pg_trigger t
      JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
      JOIN pg_catalog.pg_namespace pn ON pn.oid=p.pronamespace
      JOIN pg_catalog.pg_roles r ON r.oid=p.proowner
     WHERE n.nspname IN ('storage','auth')
       AND NOT t.tgisinternal
       AND pn.nspname NOT IN ('storage','auth')
       AND (
           NOT p.prosecdef
           OR r.rolsuper
           OR r.rolcreaterole
           OR r.rolname IN (
               'supabase_storage_admin','supabase_auth_admin',
               'supabase_functions_admin','postgres','supabase_admin'
           )
           OR EXISTS (
               SELECT 1 FROM unnest(coalesce(p.proconfig,ARRAY[]::text[])) cfg
                WHERE lower(cfg) LIKE 'role=%' OR lower(cfg) LIKE 'session_authorization=%'
           )
       )
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'Trigger % on %.% requires a SECURITY DEFINER function (%) owned by the project role',
            bad.tgname, bad.nspname, bad.relname, bad.fn USING ERRCODE='42501';
    END IF;
END
$trigger_guard$;
REVOKE ALL ON FUNCTION studio_trigger_guard.enforce_system_trigger_security() FROM PUBLIC;
DO $trigger_event$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_event_trigger
         WHERE evtname='studio_guard_system_trigger_security'
    ) THEN
        CREATE EVENT TRIGGER studio_guard_system_trigger_security
            ON ddl_command_end
            WHEN TAG IN ('CREATE FUNCTION','ALTER FUNCTION','CREATE TRIGGER')
            EXECUTE FUNCTION studio_trigger_guard.enforce_system_trigger_security();
    END IF;
END
$trigger_event$;

DO $policy_access$
DECLARE
    tenant_role TEXT := current_setting('platform.meta_role');
    helper_role TEXT := replace(tenant_role,'tenant_meta_','tenant_storage_policy_');
    parent_role TEXT;
    ns RECORD;
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
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='supabase_storage_admin') THEN
        EXECUTE format('GRANT supabase_storage_admin TO %I',helper_role);
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='supabase_auth_admin') THEN
        EXECUTE format('GRANT supabase_auth_admin TO %I',helper_role);
    END IF;
    FOR ns IN
        SELECT nspname FROM pg_namespace WHERE nspname IN ('public','auth','storage','extensions')
    LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I',ns.nspname,helper_role);
    END LOOP;
    EXECUTE format('GRANT USAGE, CREATE ON SCHEMA studio_storage_guard TO %I',helper_role);
    EXECUTE format('GRANT SELECT ON studio_storage_guard.authorities TO %I',helper_role);
    EXECUTE format('GRANT SELECT, INSERT, DELETE ON studio_storage_guard.managed_indexes TO %I',helper_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_storage_guard.signature(BYTEA,BYTEA) TO %I',helper_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_storage_guard.unquote_ident(TEXT) TO %I',helper_role);
    EXECUTE format('ALTER FUNCTION studio_storage_guard.execute_policy(TEXT,BIGINT,TEXT) OWNER TO %I',helper_role);
    EXECUTE format('REVOKE CREATE ON SCHEMA studio_storage_guard FROM %I',helper_role);
    FOR target IN
        SELECT n.nspname, c.relname, r.rolname AS owner, r.rolsuper
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner
        WHERE (n.nspname='storage' AND c.relname IN ('objects','buckets') AND c.relkind='r')
           OR (n.nspname='auth' AND c.relname IN ('users','identities') AND c.relkind='r')
    LOOP
        IF target.nspname='storage' AND target.owner<>'supabase_storage_admin' THEN
            RAISE EXCEPTION 'Storage table % has unexpected owner %',target.relname,target.owner;
        END IF;
        IF target.nspname='auth' AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname='supabase_auth_admin')
           AND target.owner<>'supabase_auth_admin' AND NOT target.rolsuper THEN
            RAISE EXCEPTION 'Auth table % has unexpected owner %',target.relname,target.owner;
        END IF;
    END LOOP;
    EXECUTE format('REVOKE ALL ON studio_storage_guard.authorities FROM %I',tenant_role);
    EXECUTE format('REVOKE ALL ON studio_storage_guard.managed_indexes FROM %I',tenant_role);
    EXECUTE format('GRANT USAGE ON SCHEMA studio_storage_guard TO %I',tenant_role);
    EXECUTE format('GRANT EXECUTE ON FUNCTION studio_storage_guard.execute_policy(TEXT,BIGINT,TEXT) TO %I',tenant_role);
END
$policy_access$;
SELECT set_config('platform.storage_policy_key','',false);
