-- Run only in a tenant database, with the old worker stopped. Transactional,
-- additive migration; never creates tokens/notifications or changes their states.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
SELECT pg_advisory_xact_lock(-426557861);

DO $$
BEGIN
  IF to_regclass('public.notifications') IS NULL OR to_regclass('public.push_tokens') IS NULL THEN
    RAISE EXCEPTION 'push base tables missing: configure this tenant first';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='push_tokens' AND column_name='id' AND data_type='uuid')
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='notifications' AND column_name='id' AND data_type='uuid')
     OR NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public'
      AND table_name='notifications' AND column_name='status' AND data_type='text') THEN
    RAISE EXCEPTION 'unsupported push schema: inspect IDs and notification status contract';
  END IF;
  -- Existing contract is one row per FCM token within a tenant. Do not silently
  -- consolidate or delete duplicates in an incompatible installation.
  IF NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a
      ON a.attrelid=i.indrelid AND a.attnum=ANY(i.indkey)
      WHERE i.indrelid='public.push_tokens'::regclass AND i.indisunique
        AND i.indisvalid AND i.indnkeyatts=1 AND i.indpred IS NULL AND a.attname='token') THEN
    RAISE EXCEPTION 'push_tokens requires existing unique(token); review duplicate policy';
  END IF;
  -- Refuse unknown check constraints rather than modifying their semantics.
  IF EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.notifications'::regclass
      AND contype='c' AND pg_get_constraintdef(oid) ~ '\mstatus\M') THEN
    RAISE EXCEPTION 'notification status check requires consumer review before migration';
  END IF;
END $$;

ALTER TABLE public.notifications
  ADD COLUMN IF NOT EXISTS available_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS attempts integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS locked_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_error text,
  ADD COLUMN IF NOT EXISTS claim_id uuid,
  ADD COLUMN IF NOT EXISTS deliveries_initialized_at timestamptz;

-- A generation protects even an upsert of the SAME token during an in-flight
-- request. Clients do not need to supply it; every UPDATE advances it.
ALTER TABLE public.push_tokens ADD COLUMN IF NOT EXISTS push_generation uuid NOT NULL DEFAULT gen_random_uuid();
CREATE OR REPLACE FUNCTION public.push_advance_generation() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
BEGIN
  NEW.push_generation := gen_random_uuid();
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS push_generation_changed ON public.push_tokens;
CREATE TRIGGER push_generation_changed BEFORE UPDATE ON public.push_tokens
FOR EACH ROW EXECUTE FUNCTION public.push_advance_generation();

CREATE TABLE IF NOT EXISTS public.notification_deliveries (
  notification_id uuid NOT NULL REFERENCES public.notifications(id) ON DELETE CASCADE,
  token text NOT NULL,
  platform text,
  status text NOT NULL DEFAULT 'pendente',
  attempts integer NOT NULL DEFAULT 0,
  available_at timestamptz NOT NULL DEFAULT now(),
  locked_at timestamptz,
  last_error text,
  delivered_at timestamptz,
  PRIMARY KEY (notification_id, token)
);
ALTER TABLE public.notification_deliveries
  ADD COLUMN IF NOT EXISTS claim_id uuid,
  ADD COLUMN IF NOT EXISTS push_token_id uuid,
  ADD COLUMN IF NOT EXISTS push_generation uuid,
  ADD COLUMN IF NOT EXISTS result_category text,
  ADD COLUMN IF NOT EXISTS http_status integer,
  ADD COLUMN IF NOT EXISTS fcm_code text,
  ADD COLUMN IF NOT EXISTS retry_after_seconds double precision;
-- Do not backfill token generations for existing deliveries: no reliable
-- snapshot exists. Such deliveries can finish but cannot delete token rows.
UPDATE public.notifications n SET deliveries_initialized_at=now()
WHERE deliveries_initialized_at IS NULL AND EXISTS
  (SELECT 1 FROM public.notification_deliveries d WHERE d.notification_id=n.id);
CREATE INDEX IF NOT EXISTS idx_notifications_push_available
  ON public.notifications(status, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_deliveries_push_available
  ON public.notification_deliveries(notification_id, status, available_at);
CREATE INDEX IF NOT EXISTS idx_notifications_push_lease
  ON public.notifications(locked_at) WHERE status='processando';
ALTER TABLE public.notification_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.notification_deliveries FROM PUBLIC;
COMMIT;
