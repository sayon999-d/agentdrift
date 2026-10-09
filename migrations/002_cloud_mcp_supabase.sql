-- ============================================================================
-- AgentDrift Cloud MCP schema — Supabase (PostgreSQL + pgvector + Auth).
-- File: migrations/002_cloud_mcp_supabase.sql
-- Run:  Supabase Dashboard -> SQL Editor -> paste & run (once per project).
--
-- What this does:
--   1. Enables `vector` (pgvector) and `uuid-ossp` extensions.
--   2. Creates multi-tenant tables `agent_sessions` / `agent_executions` /
--      `drift_detections`, each scoped by `user_id UUID REFERENCES
--      auth.users(id)` so traces are sandboxed per Supabase Auth user.
--   3. Enables Row-Level Security with `authenticated`-role policies
--      (`auth.uid() = user_id`). The `service_role` key bypasses RLS by
--      design — the cloud MCP server uses it server-side via
--      SUPABASE_DATABASE_URL, while end-user JWTs are sandboxed.
--   4. Creates (session_id, sequence) + HNSW cosine indexes for fast
--      trajectory + similarity queries.
--
-- Compatibility: safe to run AFTER migrations/002_supabase_mcp.sql (Phase 1).
-- The `ADD COLUMN IF NOT EXISTS` guards backfill `user_id` /
-- `payload_embedding` onto Phase-1 tables instead of failing.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extensions
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ----------------------------------------------------------------------------
-- 1. Tables (multi-tenant via user_id -> auth.users)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_sessions (
    session_id TEXT PRIMARY KEY,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_executions (
    execution_id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    session_id TEXT NOT NULL REFERENCES agent_sessions(session_id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT 'unknown',
    node_id TEXT NOT NULL DEFAULT 'default',
    sequence INT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    thinking TEXT,
    state_hash TEXT,
    payload_embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drift_detections (
    detection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT,
    execution_id TEXT,
    prior_execution_id TEXT,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL DEFAULT 'unknown',
    kind TEXT NOT NULL DEFAULT 'ping_pong_loop',
    similarity FLOAT8 NOT NULL,
    threshold FLOAT8 NOT NULL,
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Back-compat guards for databases migrated with Phase-1 (002_supabase_mcp.sql),
-- whose tables lack user_id / payload_embedding (it used `embedding`).
ALTER TABLE agent_sessions   ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE agent_sessions   ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE agent_sessions   ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS node_id TEXT NOT NULL DEFAULT 'default';
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS payload JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS thinking TEXT;
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS state_hash TEXT;
ALTER TABLE agent_executions ADD COLUMN IF NOT EXISTS payload_embedding vector(384);
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE;
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS prior_execution_id TEXT;
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS agent_id TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'ping_pong_loop';
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS similarity FLOAT8;
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS threshold FLOAT8;
ALTER TABLE drift_detections ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ----------------------------------------------------------------------------
-- 2. Row-Level Security (per-user sandbox; service_role bypasses RLS)
-- ----------------------------------------------------------------------------
ALTER TABLE agent_sessions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE drift_detections ENABLE ROW LEVEL SECURITY;

-- Drop-then-create so the migration is re-runnable from the SQL editor.
DROP POLICY IF EXISTS "users_full_access_sessions"   ON agent_sessions;
DROP POLICY IF EXISTS "users_full_access_executions" ON agent_executions;
DROP POLICY IF EXISTS "users_full_access_detections" ON drift_detections;

-- `authenticated` role (end-user JWTs): full access to OWN rows only.
-- Server-side `service_role` connections bypass RLS entirely (no policy needed).
CREATE POLICY "users_full_access_sessions"
    ON agent_sessions FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_full_access_executions"
    ON agent_executions FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_full_access_detections"
    ON drift_detections FOR ALL
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- ----------------------------------------------------------------------------
-- 3. Indexes (trajectory ordering + pgvector cosine search)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_exec_session_seq
    ON agent_executions(session_id, sequence);

CREATE INDEX IF NOT EXISTS idx_exec_user_session
    ON agent_executions(user_id, session_id);

-- HNSW cosine index for `1 - (payload_embedding <=> $1)` loop queries.
-- Requires pgvector >= 0.7 (preinstalled on Supabase).
CREATE INDEX IF NOT EXISTS idx_exec_embedding_hnsw
    ON agent_executions USING hnsw (payload_embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_drift_user_session
    ON drift_detections(user_id, session_id);
