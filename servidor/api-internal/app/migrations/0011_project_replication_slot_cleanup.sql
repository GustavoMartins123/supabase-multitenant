-- Keep platform_meta_admin NOREPLICATION. Expose only tenant-scoped slot cleanup.
CREATE OR REPLACE FUNCTION public.drop_project_replication_slot(project_ref text, slot text)
RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $cleanup$
DECLARE target_database text;
BEGIN
  IF project_ref IS NULL OR slot IS NULL
     OR project_ref !~ '^[a-z_][a-z0-9_]{2,39}$'
     OR slot NOT IN (
       left('supabase_realtime_messages_replication_slot_' || project_ref, 63),
       left('supabase_realtime_replication_slot_' || project_ref, 63)
     )
     OR NOT EXISTS (SELECT 1 FROM public.projects WHERE name = project_ref)
  THEN
    RAISE EXCEPTION 'Invalid project replication slot cleanup scope' USING ERRCODE = '42501';
  END IF;
  SELECT database INTO target_database FROM pg_catalog.pg_replication_slots WHERE slot_name = slot;
  IF NOT FOUND THEN
    RETURN false;
  END IF;
  IF target_database IS DISTINCT FROM '_supabase_' || project_ref THEN
    RAISE EXCEPTION 'Replication slot belongs to another database' USING ERRCODE = '42501';
  END IF;
  PERFORM pg_catalog.pg_drop_replication_slot(slot);
  RETURN true;
END;
$cleanup$;
REVOKE ALL ON FUNCTION public.drop_project_replication_slot(text,text) FROM PUBLIC;
