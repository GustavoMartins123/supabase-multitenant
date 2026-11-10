ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS draft_body TEXT;
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS draft_exists BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS published_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS allowed_origins JSONB NOT NULL DEFAULT '[]';
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS draft_origins JSONB NOT NULL DEFAULT '[]';
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS policy_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.mailer_template DROP CONSTRAINT IF EXISTS mailer_template_draft_size;
ALTER TABLE public.mailer_template ADD CONSTRAINT mailer_template_draft_size CHECK (draft_body IS NULL OR octet_length(draft_body) BETWEEN 1 AND 1048576);
ALTER TABLE public.mailer_template_version DROP CONSTRAINT IF EXISTS mailer_template_version_action_check;
ALTER TABLE public.mailer_template_version ADD CONSTRAINT mailer_template_version_action_check
    CHECK (action IN ('save','reset','import','copy','draft','draft_default','publish','publish_default','quarantine'));
-- Legacy content has not passed the new policy or a publication confirmation.
-- Preserve it as an editable draft and serve the embedded default until reviewed.
WITH changed AS (
    UPDATE public.mailer_template SET draft_body=body, draft_exists=(body IS NOT NULL),
        body=NULL, published_version=0, policy_version=1, version=version+1,
        updated_by='security-migration', updated_at=now()
    WHERE policy_version=0 RETURNING *
)
INSERT INTO public.mailer_template_version(project_id,kind,body,version,updated_by,action)
SELECT project_id,kind,draft_body,version,updated_by,'quarantine' FROM changed;
CREATE TABLE IF NOT EXISTS public.mailer_template_publication_grant (
    jti TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS public.mailer_template_step_up_used (
    jti TEXT PRIMARY KEY,
    expires_at TIMESTAMPTZ NOT NULL
);
REVOKE ALL ON public.mailer_template_publication_grant, public.mailer_template_step_up_used FROM PUBLIC;
DO $$ BEGIN
    IF to_regclass('public.studio_step_up_grant_consumptions') IS NOT NULL THEN
        ALTER TABLE public.studio_step_up_grant_consumptions DROP CONSTRAINT IF EXISTS studio_step_up_grant_consumptions_action_check;
        ALTER TABLE public.studio_step_up_grant_consumptions ADD CONSTRAINT studio_step_up_grant_consumptions_action_check
            CHECK (action IN ('delete_project','reveal_secret_key','create_secret_key','rotate_secret_key',
                'activate_secret_key','update_secret_key_policy','cancel_secret_key_rotation','revoke_secret_key',
                'update_access_policy','publish_mailer_template'));
    END IF;
END $$;
