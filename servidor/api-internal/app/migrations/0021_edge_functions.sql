CREATE TABLE project_edge_functions (
    project_id uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    enabled boolean NOT NULL DEFAULT false,
    network_allowlist jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(network_allowlist) = 'array'),
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE project_function_keys (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('publishable', 'secret')),
    secret_hash bytea NOT NULL UNIQUE CHECK (octet_length(secret_hash) = 32),
    secret_ciphertext text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(project_id, kind)
);
CREATE TABLE studio_edge_audit (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    actor_id uuid REFERENCES users(id) ON DELETE SET NULL,
    action text NOT NULL CHECK (action IN ('save_draft','publish','configure')),
    function_name text,
    revision text CHECK (revision ~ '^[0-9a-f]{64}$'),
    outcome text NOT NULL CHECK (outcome IN ('requested','completed','failed')),
    created_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON project_edge_functions, project_function_keys, studio_edge_audit FROM PUBLIC;
