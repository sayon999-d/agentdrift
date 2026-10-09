CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    parent_session_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_executions (
    execution_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    parent_execution_id TEXT,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    sequence INT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ok',
    input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    thinking_trace JSONB,
    state_hash TEXT,
    payload_embedding vector(384),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    frozen_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drift_detections (
    detection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    prior_execution_id TEXT,
    kind TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    similarity DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_executions_session_seq ON agent_executions(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_agent_executions_created ON agent_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_drift_session ON drift_detections(session_id);
CREATE INDEX IF NOT EXISTS idx_drift_execution ON drift_detections(execution_id);

-- Keep updated_at fresh
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_sessions_updated ON agent_sessions;
CREATE TRIGGER trg_agent_sessions_updated
  BEFORE UPDATE ON agent_sessions
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Optional: ivfflat index for cosine search (needs data to be useful; uses lists=100)
-- CREATE INDEX IF NOT EXISTS idx_exec_embedding_cosine
--   ON agent_executions USING ivfflat (payload_embedding vector_cosine_ops) WITH (lists = 100);
