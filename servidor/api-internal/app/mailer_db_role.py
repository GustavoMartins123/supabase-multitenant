import re

def role_sql(password):
    if not re.fullmatch(r"[0-9a-f]{64}", password):
        raise ValueError("Senha inválida do mailer")
    return (
        """DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='mailer_template_service') THEN
        CREATE ROLE mailer_template_service; END IF; END $$;
    ALTER ROLE mailer_template_service WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
        NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 8 PASSWORD '%s';
    ALTER ROLE mailer_template_service SET search_path = public,pg_catalog;
    ALTER ROLE mailer_template_service SET statement_timeout = '5s';
    ALTER ROLE mailer_template_service SET lock_timeout = '2s';
    ALTER ROLE mailer_template_service SET idle_in_transaction_session_timeout = '10s';
    DO $$ DECLARE parent_role text; BEGIN
        FOR parent_role IN SELECT r.rolname FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.roleid
            WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='mailer_template_service') LOOP
            EXECUTE format('REVOKE %%I FROM mailer_template_service',parent_role);
        END LOOP;
    END $$;
    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mailer_template_service;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM mailer_template_service;
    REVOKE CREATE ON SCHEMA public FROM mailer_template_service;
    GRANT USAGE ON SCHEMA public TO mailer_template_service;
    GRANT SELECT(id,tenant_uuid,name) ON public.projects TO mailer_template_service;
    GRANT SELECT,INSERT,UPDATE ON public.mailer_template TO mailer_template_service;
    GRANT SELECT,INSERT ON public.mailer_template_version TO mailer_template_service;
    GRANT SELECT,INSERT ON public.mailer_template_default TO mailer_template_service;
    GRANT SELECT,INSERT,DELETE ON public.mailer_template_publication_grant TO mailer_template_service;
    DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %%I TO mailer_template_service',current_database()); END $$;
    """
        % password
    )

