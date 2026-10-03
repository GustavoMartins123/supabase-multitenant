CREATE TABLE project_reference_history (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id UUID NOT NULL UNIQUE REFERENCES jobs(job_id),
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    old_ref TEXT NOT NULL CHECK (old_ref ~ '^[a-z]{20}$' AND octet_length(old_ref) = 20),
    new_ref TEXT NOT NULL UNIQUE CHECK (new_ref ~ '^[a-z]{20}$' AND octet_length(new_ref) = 20),
    CHECK (old_ref <> new_ref),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'rolled_back')),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);
CREATE UNIQUE INDEX project_reference_history_active_project
    ON project_reference_history(project_id) WHERE status IN ('queued', 'running');
CREATE INDEX project_reference_history_project_created
    ON project_reference_history(project_id, created_at DESC);
