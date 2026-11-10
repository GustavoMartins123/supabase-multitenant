CREATE TABLE IF NOT EXISTS public.mailer_template_default (
    kind TEXT PRIMARY KEY CHECK (kind IN ('confirmation','invite','magic_link','recovery','email_change','reauthentication')),
    body TEXT NOT NULL CHECK (octet_length(body) BETWEEN 1 AND 1048576),
    version INTEGER NOT NULL CHECK (version > 0),
    migration_signature TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL
);
REVOKE ALL ON public.mailer_template_default FROM PUBLIC;
ALTER TABLE public.mailer_template ADD COLUMN IF NOT EXISTS migration_signature TEXT;
ALTER TABLE public.mailer_template_version DROP CONSTRAINT IF EXISTS mailer_template_version_action_check;
ALTER TABLE public.mailer_template_version ADD CONSTRAINT mailer_template_version_action_check
    CHECK (action IN ('save','reset','import','import_active','import_default','copy','draft','draft_default','publish','publish_default','quarantine'));
