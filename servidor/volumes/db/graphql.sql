-- Canonical GraphQL contract after extension creation or pg_dump restoration.
-- Normalize the upstream extension-owned wrapper to a project-owned function
-- so pg_dump preserves its definition before restoring its explicit ACLs.
BEGIN;
CREATE EXTENSION IF NOT EXISTS pg_graphql;
CREATE SCHEMA IF NOT EXISTS graphql_public;
CREATE OR REPLACE FUNCTION graphql_public.graphql(
  "operationName" text DEFAULT NULL,
  query text DEFAULT NULL,
  variables jsonb DEFAULT NULL,
  extensions jsonb DEFAULT NULL
) RETURNS jsonb LANGUAGE sql AS $graphql$
  SELECT graphql.resolve(
    query := query,
    variables := coalesce(variables, '{}'),
    "operationName" := "operationName",
    extensions := extensions
  );
$graphql$;
DO $membership$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_depend
    WHERE classid = 'pg_proc'::regclass
      AND objid = 'graphql_public.graphql(text,text,jsonb,jsonb)'::regprocedure
      AND refclassid = 'pg_extension'::regclass
      AND refobjid = (SELECT oid FROM pg_extension WHERE extname = 'pg_graphql')
      AND deptype = 'e'
  ) THEN
    ALTER EXTENSION pg_graphql DROP FUNCTION graphql_public.graphql(text,text,jsonb,jsonb);
  END IF;
END;
$membership$;
GRANT USAGE ON SCHEMA graphql, graphql_public TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION graphql.resolve TO anon, authenticated, service_role;
REVOKE EXECUTE ON FUNCTION graphql_public.graphql(text,text,jsonb,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION graphql_public.graphql(text,text,jsonb,jsonb)
  TO anon, authenticated, service_role;
COMMIT;
