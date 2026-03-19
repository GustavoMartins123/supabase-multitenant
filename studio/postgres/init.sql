CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS ai_chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  project_ref TEXT NOT NULL,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID REFERENCES ai_chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
  content TEXT NOT NULL,
  tokens_estimate INTEGER,
  model_used TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_user_project 
  ON ai_chat_sessions(user_id, project_ref, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session 
  ON ai_chat_messages(session_id, created_at ASC);

CREATE OR REPLACE FUNCTION update_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE ai_chat_sessions 
  SET updated_at = NOW() 
  WHERE id = NEW.session_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_session_on_message ON ai_chat_messages;
CREATE TRIGGER update_session_on_message
AFTER INSERT ON ai_chat_messages
FOR EACH ROW
EXECUTE FUNCTION update_session_timestamp();

CREATE OR REPLACE FUNCTION get_recent_messages(
  p_session_id UUID,
  p_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
  role TEXT,
  content TEXT,
  created_at TIMESTAMPTZ
) AS $$
BEGIN
  RETURN QUERY
  SELECT m.role, m.content, m.created_at
  FROM ai_chat_messages m
  WHERE m.session_id = p_session_id
  ORDER BY m.created_at DESC
  LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_or_create_session(
    p_user_id text,
    p_project_ref text,
    p_session_id text DEFAULT NULL
) RETURNS text AS $$
DECLARE
    v_session_id text;
BEGIN
    IF p_session_id IS NOT NULL THEN
        SELECT id INTO v_session_id FROM ai_chat_sessions WHERE id::text = p_session_id;
    END IF;
    
    IF v_session_id IS NULL THEN
        INSERT INTO ai_chat_sessions (id, user_id, project_ref)
        VALUES (COALESCE(p_session_id::uuid, gen_random_uuid()), p_user_id, p_project_ref)
        RETURNING id::text INTO v_session_id;
    END IF;
    
    RETURN v_session_id;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION save_message(
  p_session_id UUID,
  p_role TEXT,
  p_content TEXT,
  p_model_used TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
  v_tokens INTEGER;
  v_message_id UUID;
BEGIN
  v_tokens := length(p_content) / 4;
  
  INSERT INTO ai_chat_messages (session_id, role, content, tokens_estimate, model_used)
  VALUES (p_session_id, p_role, p_content, v_tokens, p_model_used)
  RETURNING id INTO v_message_id;
  
  RETURN v_message_id;
END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION check_slow_queries(threshold_ms INTEGER DEFAULT 1000)
RETURNS TABLE(
  query TEXT,
  calls BIGINT,
  mean_time_ms NUMERIC,
  total_time_ms NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    LEFT(query, 100) as query,
    calls,
    ROUND(mean_exec_time::NUMERIC, 2) as mean_time_ms,
    ROUND(total_exec_time::NUMERIC, 2) as total_time_ms
  FROM pg_stat_statements
  WHERE mean_exec_time > threshold_ms
  ORDER BY mean_exec_time DESC
  LIMIT 10;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION check_active_connections()
RETURNS JSON AS $$
BEGIN
  RETURN (
    SELECT json_build_object(
      'total', COUNT(*),
      'active', COUNT(*) FILTER (WHERE state = 'active'),
      'idle', COUNT(*) FILTER (WHERE state = 'idle'),
      'idle_in_transaction', COUNT(*) FILTER (WHERE state = 'idle in transaction'),
      'details', json_agg(
        json_build_object(
          'database', datname,
          'user', usename,
          'state', state,
          'query_start', query_start
        )
      ) FILTER (WHERE state = 'active')
    )
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


CREATE OR REPLACE FUNCTION check_database_locks()
RETURNS JSON AS $$
BEGIN
  RETURN (
    SELECT json_build_object(
      'waiting_locks', COUNT(*) FILTER (WHERE NOT granted),
      'granted_locks', COUNT(*) FILTER (WHERE granted),
      'blocking_queries', json_agg(
        json_build_object(
          'blocked_pid', blocked.pid,
          'blocked_query', blocked.query,
          'blocking_pid', blocking.pid,
          'blocking_query', blocking.query
        )
      ) FILTER (WHERE NOT blocked_locks.granted)
    )
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked ON blocked.pid = blocked_locks.pid
    LEFT JOIN pg_catalog.pg_locks blocking_locks 
      ON blocking_locks.locktype = blocked_locks.locktype
      AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
      AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
      AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
      AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
      AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
      AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
      AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
      AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
      AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
      AND blocking_locks.pid != blocked_locks.pid
    LEFT JOIN pg_catalog.pg_stat_activity blocking ON blocking.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION get_database_health()
RETURNS JSON AS $$
DECLARE
  db_size TEXT;
  uptime INTERVAL;
BEGIN
  SELECT pg_size_pretty(pg_database_size(current_database())) INTO db_size;
  SELECT NOW() - pg_postmaster_start_time() INTO uptime;
  
  RETURN json_build_object(
    'database_size', db_size,
    'uptime', uptime::TEXT,
    'connections', (SELECT check_active_connections()),
    'cache_hit_ratio', (
      SELECT ROUND(100.0 * sum(heap_blks_hit) / NULLIF(sum(heap_blks_hit) + sum(heap_blks_read), 0), 2)
      FROM pg_statio_user_tables
    )
  );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

COMMENT ON FUNCTION check_slow_queries(INTEGER) IS '[AI] Verifica queries lentas no banco. Parâmetro threshold_ms define tempo mínimo em ms (padrão 1000). Retorna tabela com query, calls, mean_time_ms, total_time_ms.';

COMMENT ON FUNCTION check_active_connections() IS '[AI] Retorna informações sobre conexões ativas no banco de dados. Sem parâmetros. Retorna JSON com total, active, idle, idle_in_transaction e detalhes das conexões ativas.';

COMMENT ON FUNCTION check_database_locks() IS '[AI] Verifica locks (bloqueios) no banco de dados. Sem parâmetros. Retorna JSON com waiting_locks, granted_locks e blocking_queries.';

COMMENT ON FUNCTION get_database_health() IS '[AI] Retorna saúde geral do banco de dados. Sem parâmetros. Retorna JSON com database_size, uptime, connections e cache_hit_ratio.';
