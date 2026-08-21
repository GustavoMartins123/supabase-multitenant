-- API key plaintext is no longer single-use.  A publishable key is readable by
-- any project member and a secret key requires step-up on every read, so the
-- reveal row lives exactly as long as the key version it belongs to.
ALTER TABLE project_api_key_reveals
    DROP CONSTRAINT IF EXISTS project_api_key_reveals_lifetime;

ALTER TABLE project_api_key_reveals
    DROP COLUMN IF EXISTS expires_at;

-- Material of keys that can no longer authenticate is deleted instead of being
-- carried over by the rule above.
DELETE FROM project_api_key_reveals r
USING project_api_keys k
WHERE r.key_id = k.id
  AND k.status IN ('revoked', 'expired');
