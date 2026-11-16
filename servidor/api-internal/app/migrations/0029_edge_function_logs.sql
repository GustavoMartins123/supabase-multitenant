CREATE TABLE studio_edge_invocation_logs (
    id bigserial PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    function_name text NOT NULL CHECK (function_name ~ '^[A-Za-z][A-Za-z0-9_-]{0,63}$'),
    request_id text NOT NULL,
    method text NOT NULL,
    path text NOT NULL,
    status integer NOT NULL,
    duration_ms integer NOT NULL,
    source text NOT NULL CHECK (source IN ('studio_test', 'runtime', 'boot', 'console')),
    level text NOT NULL CHECK (level IN ('info', 'warn', 'error')),
    published boolean NOT NULL DEFAULT true,
    message text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX studio_edge_invocation_logs_project_idx
    ON studio_edge_invocation_logs(project_id, created_at DESC, id DESC);
CREATE INDEX studio_edge_invocation_logs_fn_idx
    ON studio_edge_invocation_logs(project_id, function_name, created_at DESC, id DESC);
REVOKE ALL ON studio_edge_invocation_logs FROM PUBLIC;
ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN ('save_draft','publish','configure','unpublish','delete','set_secret','delete_secret','configure_function','test_invoke'));
