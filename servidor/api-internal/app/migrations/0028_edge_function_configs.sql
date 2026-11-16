CREATE TABLE project_edge_function_configs (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    function_name text NOT NULL CHECK (function_name ~ '^[A-Za-z][A-Za-z0-9_-]{0,63}$' AND function_name <> 'main'),
    verify_jwt boolean NOT NULL DEFAULT true,
    published boolean NOT NULL DEFAULT false,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, function_name)
);
REVOKE ALL ON project_edge_function_configs FROM PUBLIC;
ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN ('save_draft','publish','configure','unpublish','delete','set_secret','delete_secret','configure_function'));
