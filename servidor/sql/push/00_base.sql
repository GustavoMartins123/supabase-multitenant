-- Fresh tenant setup only. Supabase auth.users/auth.uid() must already exist.
-- For an existing push installation, use the versioned delivery migration.
BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE TABLE public.push_tokens (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NULL,
  token text NOT NULL,
  platform text NULL,
  created_at timestamptz NULL DEFAULT now(),
  CONSTRAINT push_tokens_pkey PRIMARY KEY (id),
  CONSTRAINT push_tokens_token_key UNIQUE (token),
  CONSTRAINT push_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE,
  CONSTRAINT push_tokens_platform_check CHECK (platform = ANY(ARRAY['ios'::text,'android'::text]))
);
ALTER TABLE public.push_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuários gerenciam seus próprios tokens" ON public.push_tokens
FOR ALL USING (auth.uid() = user_id);

CREATE TABLE public.notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NULL,
  body text NOT NULL,
  created_at timestamptz NULL DEFAULT now(),
  status text NULL DEFAULT 'pendente'::text,
  CONSTRAINT notifications_pkey PRIMARY KEY (id),
  CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE
);
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Usuários leem apenas suas notificações" ON public.notifications
FOR SELECT USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.notify_new_push() RETURNS trigger
LANGUAGE plpgsql SET search_path TO pg_catalog, public AS $$
BEGIN
  PERFORM pg_notify('new_push','');
  RETURN NEW;
END;
$$;
CREATE TRIGGER trigger_new_push AFTER INSERT ON public.notifications
FOR EACH STATEMENT EXECUTE FUNCTION public.notify_new_push();
COMMIT;
