CREATE TABLE IF NOT EXISTS public.mailer_template (
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('confirmation','invite','magic_link','recovery','email_change','reauthentication')),
    body TEXT CHECK (octet_length(body) BETWEEN 1 AND 1048576),
    version INTEGER NOT NULL CHECK (version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    PRIMARY KEY (project_id, kind)
);
CREATE TABLE IF NOT EXISTS public.mailer_template_version (
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    body TEXT,
    action TEXT NOT NULL CHECK (action IN ('save','reset','import','copy')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL,
    PRIMARY KEY (project_id, kind, version)
);
REVOKE ALL ON public.mailer_template, public.mailer_template_version FROM PUBLIC;
