CREATE TABLE project_edge_function_schedules (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    function_name text NOT NULL CHECK (function_name ~ '^[A-Za-z][A-Za-z0-9_-]{0,63}$' AND function_name <> 'main'),
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80 AND name ~ '^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$'),
    cron text NOT NULL CHECK (length(cron) BETWEEN 9 AND 100),
    timezone text NOT NULL DEFAULT 'UTC' CHECK (timezone = 'UTC'),
    method text NOT NULL DEFAULT 'POST' CHECK (method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')),
    path text NOT NULL DEFAULT '/' CHECK (path LIKE '/%' AND length(path) <= 256),
    headers_json jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(headers_json) = 'object'),
    body text NOT NULL DEFAULT '' CHECK (length(body) <= 65536),
    auth_mode text NOT NULL DEFAULT 'service_role' CHECK (auth_mode IN ('anon', 'service_role', 'none')),
    enabled boolean NOT NULL DEFAULT true,
    next_run_at timestamptz,
    last_run_at timestamptz,
    last_status integer,
    last_duration_ms integer,
    last_request_id text,
    last_error text NOT NULL DEFAULT '',
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, function_name, name)
);
CREATE INDEX project_edge_function_schedules_due_idx
    ON project_edge_function_schedules(enabled, next_run_at) WHERE enabled = true;
CREATE INDEX project_edge_function_schedules_fn_idx
    ON project_edge_function_schedules(project_id, function_name);
REVOKE ALL ON project_edge_function_schedules FROM PUBLIC;

ALTER TABLE studio_edge_invocation_logs DROP CONSTRAINT IF EXISTS studio_edge_invocation_logs_source_check;
ALTER TABLE studio_edge_invocation_logs ADD CONSTRAINT studio_edge_invocation_logs_source_check
    CHECK (source IN ('studio_test', 'runtime', 'boot', 'console', 'cron'));

ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN (
        'save_draft', 'publish', 'configure', 'unpublish', 'delete',
        'set_secret', 'delete_secret', 'configure_function', 'test_invoke',
        'rollback', 'configure_quotas', 'configure_schedule', 'delete_schedule'
    ));
