-- Index expires_at on mailer template grant and step-up replay tables so
-- periodic expiration sweeps use an index scan instead of sequential scans.
CREATE INDEX IF NOT EXISTS idx_mailer_publication_grant_expires_at
    ON public.mailer_template_publication_grant(expires_at);

CREATE INDEX IF NOT EXISTS idx_mailer_step_up_used_expires_at
    ON public.mailer_template_step_up_used(expires_at);
