-- Step-up grants are short-lived bearer proofs issued by Studio Nginx after
-- Authelia validates the currently authenticated user's credential. Only the
-- grant identifier and its security binding are persisted; submitted
-- credentials and bearer values are never stored.
CREATE TABLE IF NOT EXISTS studio_step_up_grant_consumptions (
    jti TEXT PRIMARY KEY
        CHECK (jti ~ '^[A-Za-z0-9_-]{22}$'),
    user_id UUID NOT NULL,
    login_session_hash TEXT NOT NULL
        CHECK (login_session_hash ~ '^[A-Za-z0-9_-]{43}$'),
    action TEXT NOT NULL
        CHECK (action IN (
            'delete_project',
            'reveal_secret_key',
            'create_secret_key',
            'rotate_secret_key'
        )),
    project_id UUID NOT NULL,
    project_ref TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    issued_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (expires_at > issued_at)
);

CREATE INDEX IF NOT EXISTS idx_step_up_grants_consumed_at
    ON studio_step_up_grant_consumptions(consumed_at);

CREATE INDEX IF NOT EXISTS idx_step_up_grants_actor
    ON studio_step_up_grant_consumptions(user_id, consumed_at DESC);
