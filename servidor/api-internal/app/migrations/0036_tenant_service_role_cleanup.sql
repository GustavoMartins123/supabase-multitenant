-- Keep platform_meta_admin NOCREATEROLE. Expose only tenant-scoped service role cleanup.
CREATE OR REPLACE FUNCTION public.drop_tenant_service_roles(target_tenant_uuid uuid)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $cleanup$
DECLARE
  hex_id text;
  role_name text;
  proj_db text;
BEGIN
  IF target_tenant_uuid IS NULL THEN
    RAISE EXCEPTION 'Invalid tenant role cleanup scope' USING ERRCODE = '42501';
  END IF;
  SELECT '_supabase_' || name INTO proj_db
  FROM public.projects
  WHERE tenant_uuid = target_tenant_uuid
  LIMIT 1;
  IF proj_db IS NULL THEN
    RAISE EXCEPTION 'Invalid tenant role cleanup scope' USING ERRCODE = '42501';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_database WHERE datname = proj_db) THEN
    RAISE EXCEPTION 'Refusing to drop tenant service roles while database % still exists', proj_db
      USING ERRCODE = '55006';
  END IF;
  hex_id := replace(lower(target_tenant_uuid::text), '-', '');
  IF hex_id !~ '^[0-9a-f]{32}$' THEN
    RAISE EXCEPTION 'Invalid tenant role cleanup scope' USING ERRCODE = '42501';
  END IF;
  FOREACH role_name IN ARRAY ARRAY['tenant_auth_' || hex_id, 'tenant_rest_' || hex_id] LOOP
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('DROP ROLE %I', role_name);
    END IF;
  END LOOP;
END;
$cleanup$;
REVOKE ALL ON FUNCTION public.drop_tenant_service_roles(uuid) FROM PUBLIC;
