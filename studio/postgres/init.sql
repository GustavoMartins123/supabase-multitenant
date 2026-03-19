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