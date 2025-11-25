-- Criar database para logs
CREATE DATABASE logs_db;

-- Conectar ao database logs_db
\c logs_db

-- Criar a tabela de logs (sem NOT NULL no id)
CREATE TABLE IF NOT EXISTS public.logs (
    timestamp TIMESTAMPTZ,
    container_id TEXT,
    container_name TEXT,
    image TEXT,
    stream TEXT,
    message TEXT,
    host TEXT,
    container_created_at TIMESTAMPTZ,
    label JSONB,
    source_type TEXT
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON public.logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_container_name ON public.logs(container_name);
CREATE INDEX IF NOT EXISTS idx_logs_stream ON public.logs(stream);


\set pgpass `echo "$POSTGRES_PASSWORD"`

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'vector_writer') THEN
        CREATE USER vector_writer WITH PASSWORD :'pgpass';
    END IF;
END $$;

ALTER TABLE public.logs OWNER TO vector_writer;

-- Permissões para tabelas futuras
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO vector_writer;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO vector_writer;