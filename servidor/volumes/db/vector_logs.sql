CREATE DATABASE logs_db;

\c logs_db

\set pgpass `echo "$POSTGRES_PASSWORD"`

\set ON_ERROR_STOP off
CREATE USER vector_writer WITH PASSWORD :'pgpass';
\set ON_ERROR_STOP on

ALTER USER vector_writer WITH PASSWORD :'pgpass';

GRANT ALL ON DATABASE logs_db TO vector_writer;
ALTER DATABASE logs_db OWNER TO supabase_admin;
GRANT USAGE, CREATE ON SCHEMA public TO vector_writer;

CREATE TABLE IF NOT EXISTS public.logs (
    timestamp TIMESTAMPTZ NOT NULL,
    container_id TEXT,
    container_name TEXT,
    image TEXT,
    stream TEXT,
    message TEXT,
    host TEXT,
    container_created_at TIMESTAMPTZ,
    label JSONB,
    source_type TEXT
) PARTITION BY RANGE (timestamp);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON public.logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_container_name ON public.logs(container_name);
CREATE INDEX IF NOT EXISTS idx_logs_stream ON public.logs(stream);

ALTER TABLE public.logs OWNER TO vector_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vector_writer;

CREATE TABLE IF NOT EXISTS public.logs_default PARTITION OF public.logs DEFAULT;
ALTER TABLE public.logs_default OWNER TO vector_writer;

DO $$
DECLARE
    curr_date date := date_trunc('month', now());
    next_date date := date_trunc('month', now() + interval '1 month');
    dates date[];
    d date;
    partition_name text;
    start_str text;
    end_str text;
BEGIN
    dates := ARRAY[curr_date, next_date];

    FOREACH d IN ARRAY dates
    LOOP
        partition_name := 'logs_' || to_char(d, 'YYYY_MM');
        start_str := to_char(d, 'YYYY-MM-DD');
        end_str := to_char(d + interval '1 month', 'YYYY-MM-DD');

        IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
            EXECUTE format('CREATE TABLE public.%I PARTITION OF public.logs FOR VALUES FROM (%L) TO (%L)', 
                            partition_name, start_str, end_str);
            EXECUTE format('ALTER TABLE public.%I OWNER TO vector_writer', partition_name);
            EXECUTE format('GRANT ALL ON TABLE public.%I TO vector_writer', partition_name);
            RAISE NOTICE 'Partição criada: %', partition_name;
        END IF;
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION maintain_log_partitions()
RETURNS void AS $$
DECLARE
    next_month_start date := date_trunc('month', now() + interval '2 months');
    old_month_end date := date_trunc('month', now() - interval '3 months');
    partition_name text;
    start_str text;
    end_str text;
BEGIN
    partition_name := 'logs_' || to_char(next_month_start, 'YYYY_MM');
    start_str := to_char(next_month_start, 'YYYY-MM-DD');
    end_str := to_char(next_month_start + interval '1 month', 'YYYY-MM-DD');
    
    IF NOT EXISTS (SELECT 1 FROM pg_class WHERE relname = partition_name) THEN
        EXECUTE format('CREATE TABLE public.%I PARTITION OF public.logs FOR VALUES FROM (%L) TO (%L)', 
                        partition_name, start_str, end_str);
        EXECUTE format('ALTER TABLE public.%I OWNER TO vector_writer', partition_name);
        EXECUTE format('GRANT ALL ON TABLE public.%I TO vector_writer', partition_name);
    END IF;

    FOR partition_name IN 
        SELECT relname FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'logs'
        AND c.relname ~ '^logs_\d{4}_\d{2}$'
        AND to_date(substring(c.relname from '\d{4}_\d{2}'), 'YYYY_MM') < old_month_end
    LOOP
        EXECUTE format('DROP TABLE public.%I', partition_name);
        RAISE NOTICE 'Partição antiga removida: %', partition_name;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

\c postgres

CREATE EXTENSION IF NOT EXISTS pg_cron;

SELECT cron.unschedule('maintain_logs_partitions_job') 
WHERE EXISTS (SELECT 1 FROM cron.job WHERE jobname = 'maintain_logs_partitions_job');

SELECT cron.schedule(
    'maintain_logs_partitions_job',
    '0 4 * * *', 
    $$SELECT maintain_log_partitions()$$
);

UPDATE cron.job 
SET database = 'logs_db' 
WHERE jobname = 'maintain_logs_partitions_job';