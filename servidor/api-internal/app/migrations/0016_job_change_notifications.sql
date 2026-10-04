CREATE FUNCTION notify_project_jobs_changed() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('project_jobs_changed', '');
    RETURN NULL;
END;
$$;

CREATE TRIGGER jobs_changed
AFTER INSERT OR UPDATE OR DELETE ON jobs
FOR EACH STATEMENT EXECUTE FUNCTION notify_project_jobs_changed();

CREATE TRIGGER job_membership_changed
AFTER INSERT OR UPDATE OR DELETE ON project_members
FOR EACH STATEMENT EXECUTE FUNCTION notify_project_jobs_changed();

CREATE TRIGGER job_groups_changed
AFTER INSERT OR UPDATE OR DELETE ON user_groups
FOR EACH STATEMENT EXECUTE FUNCTION notify_project_jobs_changed();

CREATE TRIGGER job_directory_changed
AFTER INSERT OR UPDATE OR DELETE ON studio_directory_state
FOR EACH STATEMENT EXECUTE FUNCTION notify_project_jobs_changed();
