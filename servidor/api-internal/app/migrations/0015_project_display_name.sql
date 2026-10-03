UPDATE projects SET display_name = name
WHERE display_name IS NULL OR btrim(display_name) = '';

ALTER TABLE projects ALTER COLUMN display_name SET NOT NULL;
ALTER TABLE projects ADD CONSTRAINT projects_display_name_format
    CHECK (char_length(display_name) BETWEEN 1 AND 80 AND btrim(display_name) <> '');

COMMENT ON COLUMN projects.display_name IS
    'Editable project title; independent of its public URL and technical infrastructure name.';
