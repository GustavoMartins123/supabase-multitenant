CREATE TABLE project_edge_function_revisions (
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    function_name text NOT NULL CHECK (function_name ~ '^[A-Za-z][A-Za-z0-9_-]{0,63}$' AND function_name <> 'main'),
    revision text NOT NULL CHECK (revision ~ '^[0-9a-f]{64}$'),
    author_id uuid REFERENCES users(id) ON DELETE SET NULL,
    author_label text NOT NULL DEFAULT '',
    action text NOT NULL CHECK (action IN ('save_draft', 'rollback')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, function_name, revision)
);
REVOKE ALL ON project_edge_function_revisions FROM PUBLIC;
