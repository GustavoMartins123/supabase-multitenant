ALTER TABLE project_api_key_slots ADD COLUMN application_ref TEXT;

DO $backfill$
DECLARE
    crypto_schema text;
    slot record;
    entropy bytea;
    candidate text;
    byte_value integer;
    position integer;
BEGIN
    SELECT n.nspname INTO STRICT crypto_schema
    FROM pg_extension e JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'pgcrypto';
    FOR slot IN SELECT id FROM project_api_key_slots WHERE kind = 'publishable' ORDER BY id LOOP
        candidate := '';
        WHILE length(candidate) < 20 LOOP
            EXECUTE format('SELECT %I.gen_random_bytes(64)', crypto_schema) INTO entropy;
            FOR position IN 0..63 LOOP
                byte_value := get_byte(entropy, position);
                IF byte_value < 234 THEN
                    candidate := candidate || chr(97 + byte_value % 26);
                    EXIT WHEN length(candidate) = 20;
                END IF;
            END LOOP;
        END LOOP;
        UPDATE project_api_key_slots SET application_ref = candidate WHERE id = slot.id;
    END LOOP;
END
$backfill$;

ALTER TABLE project_api_key_slots ADD CONSTRAINT project_api_key_slots_application_ref_format
    CHECK (
        (kind = 'publishable' AND application_ref IS NOT NULL
            AND application_ref ~ '^[a-z]{20}$' AND octet_length(application_ref) = 20)
        OR (kind = 'secret' AND application_ref IS NULL)
    );
ALTER TABLE project_api_key_slots ADD CONSTRAINT project_api_key_slots_application_ref_key
    UNIQUE (application_ref);

ALTER TABLE projects DROP COLUMN config_token;
