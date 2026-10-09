-- AgentDrift Cloud MCP schema (Supabase SQL editor).
-- Phase 1: run once against the Supabase Postgres instance backing
-- SupabasePgVectorStore (agentdrift/storage/supabase.py).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_executions (
    execution_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    sequence INT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    thinking TEXT,
    state_hash TEXT NOT NULL,
    embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drift_detections (
    detection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    prior_execution_id TEXT,
    agent_id TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'ping_pong_loop',
    similarity DOUBLE PRECISION NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exec_session_seq ON agent_executions(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_exec_created ON agent_executions(created_at);
CREATE INDEX IF NOT EXISTS idx_drift_session ON drift_detections(session_id);
