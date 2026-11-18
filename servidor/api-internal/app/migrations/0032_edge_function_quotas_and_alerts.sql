ALTER TABLE project_edge_functions
    ADD COLUMN quotas jsonb NOT NULL DEFAULT '{}'
        CHECK (jsonb_typeof(quotas) = 'object');

CREATE TABLE studio_edge_quota_events (
    id bigserial PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    function_name text,
    kind text NOT NULL CHECK (kind IN ('concurrency_429', 'quota_updated', 'near_limit')),
    severity text NOT NULL CHECK (severity IN ('info', 'warn', 'critical')),
    message text NOT NULL DEFAULT '',
    detail jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(detail) = 'object'),
    acknowledged_by uuid REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX studio_edge_quota_events_project_idx
    ON studio_edge_quota_events(project_id, created_at DESC, id DESC);
REVOKE ALL ON studio_edge_quota_events FROM PUBLIC;

ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN (
        'save_draft', 'publish', 'configure', 'unpublish', 'delete',
        'set_secret', 'delete_secret', 'configure_function', 'test_invoke', 'rollback', 'configure_quotas'
    ));
