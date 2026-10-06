CREATE EXTENSION IF NOT EXISTS pgcrypto;

ALTER TABLE projects ADD COLUMN public_ref TEXT;
ALTER TABLE projects ADD CONSTRAINT projects_public_ref_format
    CHECK (public_ref ~ '^[a-z]{20}$' AND octet_length(public_ref) = 20);
ALTER TABLE projects ADD CONSTRAINT projects_public_ref_key UNIQUE (public_ref);

DO $backfill$
DECLARE
    crypto_schema text;
    project record;
    entropy bytea;
    candidate text;
    byte_value integer;
    position integer;
BEGIN
    SELECT n.nspname INTO STRICT crypto_schema
    FROM pg_extension e
    JOIN pg_namespace n ON n.oid = e.extnamespace
    WHERE e.extname = 'pgcrypto';

    FOR project IN SELECT id FROM projects ORDER BY id LOOP
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
        UPDATE projects SET public_ref = candidate WHERE id = project.id;
    END LOOP;
END
$backfill$;

ALTER TABLE projects ALTER COLUMN public_ref SET NOT NULL;

COMMENT ON COLUMN projects.public_ref IS
    'Random public URL identifier, independent of internal UUID and infrastructure name; not an authentication credential.';
