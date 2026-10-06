-- Existing key timestamps are intentionally preserved.  NULL is introduced only
-- by an explicit slot policy transition or by issuing a key under that policy.
ALTER TABLE project_api_key_slots
    ALTER COLUMN rotation_interval_days DROP NOT NULL;

ALTER TABLE project_api_key_slots
    DROP CONSTRAINT IF EXISTS project_api_key_slots_rotation_interval;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'project_api_key_slots'::regclass
          AND conname = 'project_api_key_slots_lifecycle'
    ) THEN
        ALTER TABLE project_api_key_slots
            ADD CONSTRAINT project_api_key_slots_lifecycle CHECK (
                (
                    rotation_interval_days IS NULL
                    AND automatic_rotation_enabled = false
                )
                OR (
                    rotation_interval_days IS NOT NULL
                    AND rotation_interval_days BETWEEN 1 AND 3650
                )
            );
    END IF;
END
$migration$;

ALTER TABLE project_api_keys
    ALTER COLUMN expires_at DROP NOT NULL;

ALTER TABLE project_api_keys
    DROP CONSTRAINT IF EXISTS project_api_keys_lifetime;

DO $migration$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'project_api_keys'::regclass
          AND conname = 'project_api_keys_optional_lifetime'
    ) THEN
        ALTER TABLE project_api_keys
            ADD CONSTRAINT project_api_keys_optional_lifetime CHECK (
                expires_at IS NULL OR expires_at > created_at
            );
    END IF;
END
$migration$;

DROP INDEX IF EXISTS idx_project_api_keys_due;

CREATE INDEX IF NOT EXISTS idx_project_api_keys_expiring_due
    ON project_api_keys(expires_at)
    WHERE status = 'active' AND expires_at IS NOT NULL;
