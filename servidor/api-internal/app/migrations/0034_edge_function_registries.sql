CREATE TABLE IF NOT EXISTS project_edge_function_registries (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 80 AND name ~ '^[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}$'),
    kind text NOT NULL CHECK (kind IN ('npm', 'jsr')),
    scope text NOT NULL DEFAULT '' CHECK (
        (kind = 'jsr' AND scope = '') OR
        (kind = 'npm' AND (scope = '' OR scope ~ '^@[a-z0-9][a-z0-9._-]{0,127}$'))
    ),
    registry_url text NOT NULL CHECK (registry_url LIKE 'https://%' AND length(registry_url) BETWEEN 10 AND 512),
    auth_type text NOT NULL DEFAULT 'bearer' CHECK (auth_type IN ('none', 'bearer', 'basic')),
    token_ciphertext text NOT NULL DEFAULT '',
    allow_private_network boolean NOT NULL DEFAULT false,
    ca_pem text NOT NULL DEFAULT '' CHECK (length(ca_pem) <= 32768),
    enabled boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_by uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, name)
);
CREATE UNIQUE INDEX IF NOT EXISTS project_edge_function_registries_active_slot_idx
    ON project_edge_function_registries(project_id, kind, scope) WHERE enabled = true;
CREATE INDEX IF NOT EXISTS project_edge_function_registries_project_idx
    ON project_edge_function_registries(project_id, name);
REVOKE ALL ON project_edge_function_registries FROM PUBLIC;

ALTER TABLE studio_edge_audit DROP CONSTRAINT studio_edge_audit_action_check;
ALTER TABLE studio_edge_audit ADD CONSTRAINT studio_edge_audit_action_check
    CHECK (action IN (
        'save_draft', 'publish', 'configure', 'unpublish', 'delete',
        'set_secret', 'delete_secret', 'configure_function', 'test_invoke',
        'rollback', 'configure_quotas', 'configure_schedule', 'delete_schedule',
        'configure_registry', 'delete_registry'
    ));
