CREATE TABLE public_client_configuration_keys (
    key_id UUID PRIMARY KEY REFERENCES project_api_keys(id) ON DELETE CASCADE,
    publishable_key TEXT NOT NULL CHECK (publishable_key ~ '^sb_publishable_[A-Za-z0-9_-]+$')
);

CREATE FUNCTION validate_public_client_configuration_key() RETURNS trigger
LANGUAGE plpgsql SET search_path = public, pg_catalog AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM project_api_keys k JOIN project_api_key_slots s ON s.id = k.slot_id
        WHERE k.id = NEW.key_id AND s.kind = 'publishable'
          AND k.secret_hash = sha256(convert_to(NEW.publishable_key, 'UTF8'))
    ) THEN
        RAISE EXCEPTION 'Publishable configuration identity does not match the registry';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION validate_public_client_configuration_key() FROM PUBLIC;
CREATE TRIGGER validate_public_client_configuration_key
    BEFORE INSERT OR UPDATE ON public_client_configuration_keys
    FOR EACH ROW EXECUTE FUNCTION validate_public_client_configuration_key();

CREATE VIEW public_client_configurations WITH (security_barrier = true) AS
SELECT s.application_ref, p.public_ref,
       (s.status = 'active' AND p.opaque_keys_activated_at IS NOT NULL
           AND p.opaque_gateway_ready_at IS NOT NULL) AS available,
       effective.id AS key_id, effective.expires_at, effective.publishable_key
FROM project_api_key_slots s JOIN projects p ON p.id = s.project_id
LEFT JOIN LATERAL (
    SELECT k.id, k.expires_at, material.publishable_key
    FROM project_api_keys k
    LEFT JOIN public_client_configuration_keys material ON material.key_id = k.id
        AND sha256(convert_to(material.publishable_key, 'UTF8')) = k.secret_hash
    WHERE k.slot_id = s.id AND (k.expires_at IS NULL OR k.expires_at > now())
      AND s.status = 'active' AND p.opaque_keys_activated_at IS NOT NULL
      AND p.opaque_gateway_ready_at IS NOT NULL
      AND (
          (k.status = 'pending' AND k.activate_at <= now() AND k.confirmed_at IS NOT NULL)
          OR (k.status = 'active' AND k.activated_at IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM project_api_keys due WHERE due.slot_id = k.slot_id
                AND due.status = 'pending' AND due.activate_at <= now()
                AND due.confirmed_at IS NOT NULL
          ))
      )
) effective ON true
WHERE s.kind = 'publishable';
REVOKE ALL ON public_client_configurations, public_client_configuration_keys FROM PUBLIC;
