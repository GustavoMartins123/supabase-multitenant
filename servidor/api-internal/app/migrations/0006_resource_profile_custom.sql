-- Perfil personalizado: projetos com capacidade propria editada pelo
-- Studio ficam marcados como 'custom'; os limites vigentes continuam no
-- .env do projeto (PROJECT_RES_CUSTOM_* e rateio por servico).

ALTER TABLE projects DROP CONSTRAINT projects_resource_profile_check;

ALTER TABLE projects
    ADD CONSTRAINT projects_resource_profile_check
    CHECK (resource_profile IN ('small', 'medium', 'large', 'custom'));
