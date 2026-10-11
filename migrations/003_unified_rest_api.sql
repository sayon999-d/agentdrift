-- Compatibility layer for running the FastAPI REST daemon and Cloud MCP
-- server against the same tables created by 002_cloud_mcp_supabase.sql.
-- Apply after 002_cloud_mcp_supabase.sql. Safe to re-run.

ALTER TABLE agent_sessions
    ADD COLUMN IF NOT EXISTS parent_session_id TEXT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE agent_executions
    ADD COLUMN IF NOT EXISTS parent_execution_id TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ok',
    ADD COLUMN IF NOT EXISTS input_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS output_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS thinking_trace JSONB,
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS frozen_at TIMESTAMPTZ;

-- Make existing Cloud MCP records visible through REST fields before enabling
-- the shared-write trigger. Payloads with explicit input/output keys retain
-- those values; other payloads are represented as output.
UPDATE agent_executions
SET input_payload = COALESCE(payload -> 'input_payload', '{}'::jsonb),
    output_payload = COALESCE(payload -> 'output_payload', payload, '{}'::jsonb),
    thinking_trace = CASE
        WHEN thinking IS NULL THEN NULL
        ELSE to_jsonb(thinking)
    END
WHERE input_payload = '{}'::jsonb
  AND output_payload = '{}'::jsonb;

-- Keep the legacy MCP JSON/text columns and REST-specific columns in sync.
-- MCP records store their complete payload in `payload`; REST records use
-- separate input/output columns. Both writers can therefore read the record.
CREATE OR REPLACE FUNCTION agentdrift_sync_rest_mcp_execution()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.payload IS NULL THEN
        NEW.payload := '{}'::jsonb;
    END IF;
    IF NEW.input_payload IS NULL THEN
        NEW.input_payload := '{}'::jsonb;
    END IF;
    IF NEW.output_payload IS NULL THEN
        NEW.output_payload := '{}'::jsonb;
    END IF;

    IF NEW.payload = '{}'::jsonb
       AND (NEW.input_payload <> '{}'::jsonb OR NEW.output_payload <> '{}'::jsonb) THEN
        NEW.payload := jsonb_build_object(
            'input_payload', NEW.input_payload,
            'output_payload', NEW.output_payload
        );
    ELSIF NEW.input_payload = '{}'::jsonb
       AND NEW.output_payload = '{}'::jsonb
       AND NEW.payload <> '{}'::jsonb THEN
        NEW.input_payload := COALESCE(NEW.payload -> 'input_payload', '{}'::jsonb);
        NEW.output_payload := COALESCE(NEW.payload -> 'output_payload', NEW.payload);
    END IF;

    IF NEW.thinking IS NULL AND NEW.thinking_trace IS NOT NULL THEN
        NEW.thinking := NEW.thinking_trace::text;
    ELSIF NEW.thinking_trace IS NULL AND NEW.thinking IS NOT NULL THEN
        NEW.thinking_trace := to_jsonb(NEW.thinking);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agentdrift_sync_execution ON agent_executions;
CREATE TRIGGER trg_agentdrift_sync_execution
    BEFORE INSERT OR UPDATE ON agent_executions
    FOR EACH ROW EXECUTE FUNCTION agentdrift_sync_rest_mcp_execution();

CREATE OR REPLACE FUNCTION agentdrift_set_session_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agentdrift_session_updated ON agent_sessions;
CREATE TRIGGER trg_agentdrift_session_updated
    BEFORE UPDATE ON agent_sessions
    FOR EACH ROW EXECUTE FUNCTION agentdrift_set_session_updated_at();

CREATE INDEX IF NOT EXISTS idx_agent_executions_session_sequence
    ON agent_executions(session_id, sequence);
CREATE INDEX IF NOT EXISTS idx_agent_detections_session_created
    ON drift_detections(session_id, created_at DESC);
