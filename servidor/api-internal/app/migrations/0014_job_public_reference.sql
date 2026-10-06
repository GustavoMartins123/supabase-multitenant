ALTER TABLE jobs ADD COLUMN public_ref TEXT
    CHECK (public_ref ~ '^[a-z]{20}$' AND octet_length(public_ref) = 20);

UPDATE jobs j SET public_ref = p.public_ref
FROM projects p WHERE p.id = j.project_uuid;

UPDATE jobs j SET public_ref = h.old_ref
FROM project_reference_history h WHERE h.job_id = j.job_id;

ALTER TABLE jobs ADD CONSTRAINT jobs_active_public_reference
    CHECK (status NOT IN ('queued', 'running') OR public_ref IS NOT NULL);
