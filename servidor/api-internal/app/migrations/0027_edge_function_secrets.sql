CREATE TABLE project_function_secrets (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (name ~ '^[A-Za-z_][A-Za-z0-9_]{0,127}$'),
    secret_ciphertext text NOT NULL,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, name)
);
REVOKE ALL ON project_function_secrets FROM PUBLIC;
ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN ('save_draft','publish','configure','unpublish','delete','set_secret','delete_secret'));
