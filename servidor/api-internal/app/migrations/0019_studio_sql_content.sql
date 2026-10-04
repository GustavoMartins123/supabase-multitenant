CREATE TABLE studio_sql_folders (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 500),
    UNIQUE (project_id, owner_id, id),
    UNIQUE (project_id, owner_id, name)
);

CREATE TABLE studio_sql_snippets (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    owner_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    folder_id uuid,
    name text NOT NULL CHECK (length(name) BETWEEN 1 AND 500),
    description text NOT NULL DEFAULT '',
    favorite boolean NOT NULL DEFAULT false,
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object' AND content ? 'content_id' AND content ? 'sql'
        AND content->>'content_id' = id::text AND jsonb_typeof(content->'sql') = 'string'),
    inserted_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (project_id, owner_id, folder_id)
        REFERENCES studio_sql_folders(project_id, owner_id, id) ON DELETE CASCADE
);

CREATE INDEX studio_sql_snippets_scope_date
    ON studio_sql_snippets(project_id, owner_id, folder_id, inserted_at, id);
CREATE INDEX studio_sql_snippets_scope_name
    ON studio_sql_snippets(project_id, owner_id, lower(name), id);
REVOKE ALL ON studio_sql_folders, studio_sql_snippets FROM PUBLIC;
