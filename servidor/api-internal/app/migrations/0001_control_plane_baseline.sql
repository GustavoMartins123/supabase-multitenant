-- Baseline do schema do control plane no database `postgres`.
--
-- Esta migration converge tanto uma instalacao limpa quanto uma instalacao
-- existente que ja recebeu o schema pelo boot da Projects API. Cada objeto e
-- criado com guarda propria, e as colunas/constraints adicionadas depois da
-- forma original aparecem como ALTER idempotente logo abaixo da tabela.
--
-- Objetos de cluster (databases, extensoes, `_supabase_template`, `meta_trap`,
-- `meta_guest`) continuam no bootstrap historico
-- `servidor/volumes/db/create_template.sh`, executado uma unica vez pelo initdb
-- do Postgres. Tabelas do control plane pertencem exclusivamente a este
-- diretorio de migrations.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Identidade e acesso
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    authelia_username TEXT UNIQUE NOT NULL,
    display_name TEXT,
    email TEXT,
    picture_url TEXT,
    profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    profile_version BIGINT NOT NULL DEFAULT 1,
    profile_updated_at TIMESTAMPTZ,
    last_seen_at TIMESTAMPTZ,
    last_login_session_hash TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    source TEXT NOT NULL DEFAULT 'authelia',
    last_login_at TIMESTAMPTZ,
    last_sync_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS picture_url TEXT,
    ADD COLUMN IF NOT EXISTS profile_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS profile_version BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS profile_updated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_login_session_hash TEXT;

COMMENT ON COLUMN users.id IS
    'Opaque identifier do usuario no Authelia/OpenID quando disponivel.';
COMMENT ON COLUMN users.authelia_username IS
    'Nome de usuario vindo do Authelia. Serve como atributo, nao como identidade canonica.';

CREATE TABLE IF NOT EXISTS user_groups (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_name TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'authelia',
    synced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, group_name)
);

CREATE TABLE IF NOT EXISTS user_group_audit (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_name TEXT NOT NULL,
    action TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    actor_type TEXT NOT NULL DEFAULT 'system',
    actor_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);
CREATE INDEX IF NOT EXISTS idx_users_last_seen_at ON users(last_seen_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
    ON users(lower(email))
    WHERE email IS NOT NULL AND email <> '';
CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);

-- ---------------------------------------------------------------------------
-- Projetos
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_uuid UUID,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    owner_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    anon_key TEXT,
    service_role TEXT,
    config_token TEXT,
    project_key_version BIGINT NOT NULL DEFAULT 1,
    automatic_key_rotation_enabled BOOLEAN NOT NULL DEFAULT true,
    key_expires_at TIMESTAMPTZ,
    last_key_rotation_at TIMESTAMPTZ,
    automatic_key_rotation_blocked_at TIMESTAMPTZ,
    automatic_key_rotation_last_error TEXT,
    api_keyset_version BIGINT NOT NULL DEFAULT 1,
    api_gateway_token_hash BYTEA,
    opaque_keys_prepared_at TIMESTAMPTZ,
    opaque_keys_activated_at TIMESTAMPTZ,
    opaque_gateway_cutover_started_at TIMESTAMPTZ,
    opaque_gateway_ready_at TIMESTAMPTZ
);

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS project_key_version BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS tenant_uuid UUID,
    ADD COLUMN IF NOT EXISTS automatic_key_rotation_enabled BOOLEAN NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS key_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS last_key_rotation_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS automatic_key_rotation_blocked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS automatic_key_rotation_last_error TEXT,
    ADD COLUMN IF NOT EXISTS api_keyset_version BIGINT NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS api_gateway_token_hash BYTEA,
    ADD COLUMN IF NOT EXISTS opaque_keys_prepared_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS opaque_keys_activated_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS opaque_gateway_cutover_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS opaque_gateway_ready_at TIMESTAMPTZ;

UPDATE projects SET project_key_version = 1
WHERE project_key_version IS NULL OR project_key_version < 1;
UPDATE projects SET api_keyset_version = 1
WHERE api_keyset_version IS NULL OR api_keyset_version < 1;
UPDATE projects SET automatic_key_rotation_enabled = true
WHERE automatic_key_rotation_enabled IS NULL;

ALTER TABLE projects
    ALTER COLUMN automatic_key_rotation_enabled SET DEFAULT true,
    ALTER COLUMN automatic_key_rotation_enabled SET NOT NULL;

COMMENT ON COLUMN projects.owner_id IS
    'UUID canonico do usuario dono do projeto.';
COMMENT ON COLUMN projects.display_name IS
    'Nome exibicao humano do projeto. O slug/path continua sendo a coluna name.';
COMMENT ON COLUMN projects.tenant_uuid IS
    'Tenant externo persistido (Realtime/JWT/backups). Em projetos novos equivale a projects.id.';

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_tenant_uuid_unique
    ON projects(tenant_uuid)
    WHERE tenant_uuid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_automatic_key_rotation_due
    ON projects(key_expires_at)
    WHERE automatic_key_rotation_enabled
      AND automatic_key_rotation_blocked_at IS NULL
      AND anon_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);

CREATE OR REPLACE FUNCTION set_project_tenant_uuid_from_id()
RETURNS trigger
LANGUAGE plpgsql
AS $tenant_uuid_default$
BEGIN
    IF NEW.tenant_uuid IS NULL THEN
        NEW.tenant_uuid := NEW.id;
    END IF;
    RETURN NEW;
END;
$tenant_uuid_default$;

DO $baseline$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_trigger
        WHERE tgrelid = 'projects'::regclass
          AND tgname = 'projects_default_tenant_uuid'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER projects_default_tenant_uuid
        BEFORE INSERT ON projects
        FOR EACH ROW
        EXECUTE FUNCTION set_project_tenant_uuid_from_id();
    END IF;
END
$baseline$;

CREATE TABLE IF NOT EXISTS project_members (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    PRIMARY KEY (project_id, user_id)
);

COMMENT ON COLUMN project_members.user_id IS
    'UUID canonico do usuario membro do projeto.';

UPDATE project_members
SET role = 'member'
WHERE role IS NULL OR role NOT IN ('admin', 'member');

ALTER TABLE project_members
    ALTER COLUMN role SET DEFAULT 'member';
ALTER TABLE project_members
    ALTER COLUMN role SET NOT NULL;

DO $baseline$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'project_members'::regclass
          AND conname = 'project_members_role_check'
    ) THEN
        ALTER TABLE project_members
            ADD CONSTRAINT project_members_role_check
            CHECK (role IN ('admin', 'member'));
    END IF;
END
$baseline$;

CREATE TABLE IF NOT EXISTS project_members_audit (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    old_role TEXT,
    new_role TEXT,
    action TEXT NOT NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_audit_project_id ON project_members_audit(project_id);

-- ---------------------------------------------------------------------------
-- Segredos por projeto
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_key_envelopes (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    key_id UUID NOT NULL UNIQUE,
    wrapped_dek TEXT NOT NULL,
    wrapping_key_id TEXT NOT NULL,
    algorithm TEXT NOT NULL DEFAULT 'aes-256-gcm',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_key_envelopes_wrapping_key
    ON project_key_envelopes(wrapping_key_id);

-- ---------------------------------------------------------------------------
-- Registro de API keys opacas
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_api_key_slots (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    allowed_services TEXT[] NOT NULL,
    automatic_rotation_enabled BOOLEAN NOT NULL,
    rotation_interval_days INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    automatic_rotation_blocked_at TIMESTAMPTZ,
    automatic_rotation_last_error TEXT,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT project_api_key_slots_name_format CHECK (
        name ~ '^[a-z][a-z0-9_-]{2,39}$'
    ),
    CONSTRAINT project_api_key_slots_kind CHECK (
        kind IN ('publishable', 'secret')
    ),
    CONSTRAINT project_api_key_slots_services CHECK (
        cardinality(allowed_services) > 0
        AND allowed_services <@ ARRAY[
            'auth', 'rest', 'graphql', 'realtime', 'storage', 'functions'
        ]::text[]
    ),
    CONSTRAINT project_api_key_slots_lifecycle CHECK (
        (
            rotation_interval_days IS NULL
            AND automatic_rotation_enabled = false
        )
        OR (
            rotation_interval_days IS NOT NULL
            AND rotation_interval_days BETWEEN 1 AND 3650
        )
    ),
    CONSTRAINT project_api_key_slots_status CHECK (
        status IN ('active', 'disabled')
    ),
    CONSTRAINT project_api_key_slots_project_name_unique
        UNIQUE(project_id, name)
);

ALTER TABLE project_api_key_slots
    ADD COLUMN IF NOT EXISTS automatic_rotation_blocked_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS automatic_rotation_last_error TEXT;

CREATE TABLE IF NOT EXISTS project_api_keys (
    id UUID PRIMARY KEY,
    slot_id UUID NOT NULL
        REFERENCES project_api_key_slots(id) ON DELETE CASCADE,
    secret_hash BYTEA NOT NULL UNIQUE,
    token_hint TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activate_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    revealed_at TIMESTAMPTZ,
    confirmed_at TIMESTAMPTZ,
    replaces_key_id UUID REFERENCES project_api_keys(id) ON DELETE SET NULL,
    rotation_trigger TEXT NOT NULL DEFAULT 'manual',
    CONSTRAINT project_api_keys_status CHECK (
        status IN ('pending', 'active', 'revoked', 'expired')
    ),
    CONSTRAINT project_api_keys_optional_lifetime CHECK (
        expires_at IS NULL OR expires_at > created_at
    ),
    CONSTRAINT project_api_keys_rotation_trigger CHECK (
        rotation_trigger IN ('initial', 'manual', 'automatic')
    ),
    CONSTRAINT project_api_keys_state_timestamps CHECK (
        (status = 'pending' AND activated_at IS NULL AND revoked_at IS NULL)
        OR (status = 'active' AND activated_at IS NOT NULL AND revoked_at IS NULL)
        OR (status IN ('revoked', 'expired') AND revoked_at IS NOT NULL)
    )
);

ALTER TABLE project_api_keys
    ADD COLUMN IF NOT EXISTS rotation_trigger TEXT NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS revealed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ;

DO $baseline$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'project_api_keys'::regclass
          AND conname = 'project_api_keys_rotation_trigger'
    ) THEN
        ALTER TABLE project_api_keys
            ADD CONSTRAINT project_api_keys_rotation_trigger
            CHECK (
                rotation_trigger IN ('initial', 'manual', 'automatic')
            );
    END IF;
END
$baseline$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_project_api_keys_one_active
    ON project_api_keys(slot_id) WHERE status = 'active';
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_api_keys_one_pending
    ON project_api_keys(slot_id) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_project_api_keys_lookup
    ON project_api_keys(secret_hash) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_project_api_keys_expiring_due
    ON project_api_keys(expires_at)
    WHERE status = 'active' AND expires_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_project_api_key_slots_project
    ON project_api_key_slots(project_id, status);

CREATE TABLE IF NOT EXISTS project_api_key_reveals (
    key_id UUID PRIMARY KEY
        REFERENCES project_api_keys(id) ON DELETE CASCADE,
    ciphertext TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT project_api_key_reveals_lifetime CHECK (
        expires_at > created_at
    )
);

-- ---------------------------------------------------------------------------
-- Jobs administrativos
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS jobs (
    job_id UUID PRIMARY KEY,
    project TEXT NOT NULL,
    project_uuid UUID,
    owner_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    message TEXT,
    action TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    progress SMALLINT NOT NULL DEFAULT 0
        CHECK (progress BETWEEN 0 AND 100),
    current_step TEXT,
    total_steps INTEGER NOT NULL DEFAULT 1 CHECK (total_steps > 0),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    stdout_tail TEXT,
    stderr_tail TEXT,
    error_code TEXT,
    is_idempotent BOOLEAN NOT NULL DEFAULT false,
    retryable BOOLEAN NOT NULL DEFAULT false,
    retry_of UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    attempt INTEGER NOT NULL DEFAULT 1 CHECK (attempt > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN jobs.owner_id IS
    'UUID canonico do usuario que iniciou o job.';

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS project_uuid UUID;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_by UUID;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS message TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS action TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS current_step TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS total_steps INTEGER NOT NULL DEFAULT 1;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stdout_tail TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS stderr_tail TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error_code TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_idempotent BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retryable BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS retry_of UUID;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS attempt INTEGER NOT NULL DEFAULT 1;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE jobs ALTER COLUMN owner_id DROP NOT NULL;

UPDATE jobs j
SET project_uuid = p.id
FROM projects p
WHERE j.project_uuid IS NULL AND p.name = j.project;

UPDATE jobs SET created_by = owner_id WHERE created_by IS NULL;

-- Instalacoes que receberam `action` e `updated_at` por ALTER ficaram sem os
-- CHECK e sem o NOT NULL da definicao canonica. Jobs anteriores a coluna
-- `action` nao registraram a operacao e recebem o marcador 'unknown', que nao
-- pertence a nenhuma acao executavel nem a lista de acoes idempotentes. O
-- preenchimento vem antes do recalculo abaixo porque `NULL IN (...)` devolve
-- NULL e violaria o NOT NULL de `is_idempotent`.
UPDATE jobs SET updated_at = COALESCE(created_at, now())
WHERE updated_at IS NULL;
UPDATE jobs SET action = 'unknown' WHERE action IS NULL;

ALTER TABLE jobs ALTER COLUMN action SET NOT NULL;
ALTER TABLE jobs ALTER COLUMN updated_at SET DEFAULT now();
ALTER TABLE jobs ALTER COLUMN updated_at SET NOT NULL;

UPDATE jobs
SET is_idempotent = action IN ('start', 'stop', 'restart', 'recreate_services'),
    retryable = action IN ('start', 'stop', 'restart', 'recreate_services')
WHERE is_idempotent IS DISTINCT FROM
        (action IN ('start', 'stop', 'restart', 'recreate_services'))
   OR retryable IS DISTINCT FROM
        (action IN ('start', 'stop', 'restart', 'recreate_services'));

DO $baseline$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'jobs'::regclass AND conname = 'jobs_progress_check'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_progress_check
            CHECK (progress BETWEEN 0 AND 100);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'jobs'::regclass AND conname = 'jobs_total_steps_check'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_total_steps_check
            CHECK (total_steps > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'jobs'::regclass AND conname = 'jobs_attempt_check'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_attempt_check
            CHECK (attempt > 0);
    END IF;
END
$baseline$;

CREATE INDEX IF NOT EXISTS idx_jobs_status_updated
    ON jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_jobs_project_status
    ON jobs(project, status, updated_at);
CREATE INDEX IF NOT EXISTS idx_jobs_project_uuid_created
    ON jobs(project_uuid, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_created_by_created
    ON jobs(created_by, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_retry_of
    ON jobs(retry_of);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_active_retry
    ON jobs(retry_of)
    WHERE retry_of IS NOT NULL AND status IN ('queued', 'running');

-- As constraints ficam separadas da criacao porque instalacoes antigas
-- possuem a tabela `jobs` sem estas colunas e com FKs mais restritivas.
DO $baseline$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_project_uuid_fkey'
    ) THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_project_uuid_fkey;
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'jobs_owner_id_fkey' AND confdeltype <> 'n'
    ) THEN
        ALTER TABLE jobs DROP CONSTRAINT jobs_owner_id_fkey;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_owner_id_fkey'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_owner_id_fkey
            FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_created_by_fkey'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_created_by_fkey
            FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'jobs_retry_of_fkey'
    ) THEN
        ALTER TABLE jobs ADD CONSTRAINT jobs_retry_of_fkey
            FOREIGN KEY (retry_of) REFERENCES jobs(job_id) ON DELETE SET NULL;
    END IF;
END
$baseline$;

-- ---------------------------------------------------------------------------
-- Intencoes fisicas do host-agent
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS host_agent_workers (
    worker_id TEXT PRIMARY KEY,
    hostname TEXT,
    pid INTEGER,
    version TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS host_agent_commands (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(job_id) ON DELETE SET NULL,
    project TEXT NOT NULL,
    project_uuid UUID,
    command TEXT NOT NULL,
    args JSONB NOT NULL DEFAULT '{}'::jsonb,
    requested_by UUID,
    issued_at BIGINT NOT NULL,
    signature TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL CHECK (timeout_seconds > 0),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','done','failed','cancelled')),
    progress SMALLINT NOT NULL DEFAULT 0
        CHECK (progress BETWEEN 0 AND 100),
    current_step TEXT,
    message TEXT,
    worker_id TEXT,
    lease_seconds INTEGER NOT NULL DEFAULT 60,
    lease_expires_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,
    exit_code INTEGER,
    error_code TEXT,
    stdout_tail TEXT,
    stderr_tail TEXT,
    result JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_host_agent_commands_status_created
    ON host_agent_commands(status, created_at);
CREATE INDEX IF NOT EXISTS idx_host_agent_commands_job
    ON host_agent_commands(job_id, command, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_host_agent_commands_project_active
    ON host_agent_commands(project)
    WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS project_container_state (
    container_name TEXT PRIMARY KEY,
    project TEXT NOT NULL,
    state TEXT,
    status TEXT,
    image TEXT,
    ports TEXT,
    created_at_text TEXT,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_project_container_state_project
    ON project_container_state(project);

-- ---------------------------------------------------------------------------
-- Colaboracao administrativa no Studio
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS studio_project_tags (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    color TEXT NOT NULL DEFAULT '#3ECF8E',
    category TEXT NOT NULL DEFAULT 'custom',
    is_system BOOLEAN NOT NULL DEFAULT false,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS studio_project_tag_assignments (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES studio_project_tags(id) ON DELETE CASCADE,
    assigned_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, tag_id)
);

CREATE TABLE IF NOT EXISTS studio_project_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
    body TEXT NOT NULL,
    is_encrypted BOOLEAN NOT NULL DEFAULT false,
    encryption_key_id UUID,
    encryption_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS studio_project_hints (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    target_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    is_encrypted BOOLEAN NOT NULL DEFAULT false,
    encryption_key_id UUID,
    encryption_version TEXT,
    resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS studio_project_thread_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    body TEXT NOT NULL,
    is_encrypted BOOLEAN NOT NULL DEFAULT false,
    encryption_key_id UUID,
    encryption_version TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS studio_audit_log (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    old_value JSONB,
    new_value JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS project_name_history (
    id BIGSERIAL PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    job_id UUID NOT NULL UNIQUE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    old_name TEXT NOT NULL,
    new_name TEXT NOT NULL,
    old_path TEXT NOT NULL,
    new_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'rolled_back')),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS studio_project_notifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    target_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_studio_project_notes_project_id
    ON studio_project_notes(project_id);
CREATE INDEX IF NOT EXISTS idx_studio_project_notes_author_visibility
    ON studio_project_notes(author_user_id, visibility);
CREATE INDEX IF NOT EXISTS idx_studio_project_hints_project_status
    ON studio_project_hints(project_id, status);
CREATE INDEX IF NOT EXISTS idx_studio_project_hints_target_status
    ON studio_project_hints(target_user_id, status);
CREATE INDEX IF NOT EXISTS idx_studio_project_thread_project_created
    ON studio_project_thread_messages(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_studio_project_tag_assignments_project_id
    ON studio_project_tag_assignments(project_id);
CREATE INDEX IF NOT EXISTS idx_studio_audit_log_project_id
    ON studio_audit_log(project_id);
CREATE INDEX IF NOT EXISTS idx_project_name_history_project_created
    ON project_name_history(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_studio_notifications_target_unread
    ON studio_project_notifications(target_user_id, read_at, created_at DESC);

DELETE FROM studio_project_tags
WHERE name = 'Cliente crítico'
  AND is_system = true;

INSERT INTO studio_project_tags(name, color, category, is_system)
VALUES
    ('Produção', '#3ECF8E', 'ambiente', true),
    ('Desenvolvimento', '#A78BFA', 'ambiente', true),
    ('Teste 1', '#3B82F6', 'ambiente', true),
    ('Teste 2', '#06B6D4', 'ambiente', true),
    ('Homologação', '#22C55E', 'ambiente', true),
    ('Staging', '#8B5CF6', 'ambiente', true),
    ('Demo', '#EC4899', 'ambiente', true),
    ('Sandbox', '#64748B', 'ambiente', true),
    ('Manutenção', '#F97316', 'status', true),
    ('Pausado', '#94A3B8', 'status', true),
    ('Pendente', '#EF4444', 'status', true),
    ('Revisar', '#F59E0B', 'status', true),
    ('Monitorar', '#0EA5E9', 'operacao', true),
    ('Migração', '#EAB308', 'operacao', true),
    ('Backup', '#14B8A6', 'operacao', true),
    ('Auth', '#10B981', 'area', true),
    ('Storage', '#6366F1', 'area', true),
    ('Database', '#84CC16', 'area', true),
    ('Realtime', '#F43F5E', 'area', true),
    ('Gateway', '#F97316', 'area', true)
ON CONFLICT (name) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Restore points
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS project_restore_points (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'creating'
        CHECK (status IN ('creating', 'ready', 'restoring', 'deleting', 'failed')),
    is_automatic BOOLEAN NOT NULL DEFAULT false,
    job_id UUID,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    project_ref_at_creation TEXT,
    size_bytes BIGINT,
    last_restored_at TIMESTAMPTZ,
    restore_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_project_restore_points_project_created
    ON project_restore_points(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_project_restore_points_job
    ON project_restore_points(job_id);
