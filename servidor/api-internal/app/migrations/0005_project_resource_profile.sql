-- Perfil de recursos escolhido por projeto (small|medium|large).
-- O valor alimenta a resolucao de PROJECT_MEM_LIMIT/PROJECT_CPUS/
-- PROJECT_PIDS_LIMIT gravada no .env do projeto (ver
-- docs/architecture/project-lifecycle.md, secao Resource limits).

ALTER TABLE projects
    ADD COLUMN resource_profile TEXT NOT NULL DEFAULT 'medium';

ALTER TABLE projects
    ADD CONSTRAINT projects_resource_profile_check
    CHECK (resource_profile IN ('small', 'medium', 'large'));
