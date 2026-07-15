"""Bootstrap e migracoes incrementais do schema do control plane."""

import asyncpg

async def ensure_identity_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                authelia_username TEXT UNIQUE NOT NULL,
                display_name TEXT,
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

            CREATE INDEX IF NOT EXISTS idx_users_last_sync_at ON users(last_sync_at);
            CREATE INDEX IF NOT EXISTS idx_users_last_seen_at ON users(last_seen_at);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
                ON users(lower(email))
                WHERE email IS NOT NULL AND email <> '';
            CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);
            CREATE INDEX IF NOT EXISTS idx_projects_owner_id ON projects(owner_id);
            CREATE INDEX IF NOT EXISTS idx_project_members_user_id ON project_members(user_id);
            CREATE INDEX IF NOT EXISTS idx_project_members_audit_project_id ON project_members_audit(project_id);
            """
        )
        await conn.execute(
            """
            UPDATE project_members
            SET role = 'member'
            WHERE role IS NULL OR role NOT IN ('admin', 'member');

            ALTER TABLE project_members
                ALTER COLUMN role SET DEFAULT 'member';
            ALTER TABLE project_members
                ALTER COLUMN role SET NOT NULL;

            DO $$
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
            $$;
            """
        )
        await conn.execute(
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS display_name TEXT"
        )
        await conn.execute(
            """
            ALTER TABLE projects
                ADD COLUMN IF NOT EXISTS project_key_version BIGINT NOT NULL DEFAULT 1;
            UPDATE projects SET project_key_version = 1
            WHERE project_key_version IS NULL OR project_key_version < 1;
            """
        )


async def ensure_collaboration_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
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
            """
        )
