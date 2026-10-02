-- Separate namespace: never exposed through external key slots/reveals.
CREATE TABLE project_studio_keys (
    project_id uuid PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    secret_hash bytea NOT NULL UNIQUE CHECK (octet_length(secret_hash) = 32),
    secret_ciphertext text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);
