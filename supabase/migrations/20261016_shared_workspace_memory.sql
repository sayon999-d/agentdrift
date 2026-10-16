-- Cross-agent shared workspace memory and incremental audit checkpoints.
CREATE TABLE IF NOT EXISTS workspace_sessions (
    id TEXT PRIMARY KEY,
    repository_token TEXT,
    active_branch TEXT,
    architecture_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES workspace_sessions(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN ('create','edit','audit','refactor')),
    files_touched TEXT[] NOT NULL DEFAULT '{}',
    summary TEXT NOT NULL,
    diff_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workspace_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES workspace_sessions(id) ON DELETE CASCADE,
    artifact_key TEXT NOT NULL,
    producer_agent TEXT NOT NULL,
    schema_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','verified','deprecated')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(session_id, artifact_key)
);

-- session_id is included to keep identical repository-relative paths isolated.
CREATE TABLE IF NOT EXISTS audit_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES workspace_sessions(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    last_scanned_commit_or_hash TEXT NOT NULL,
    scan_status TEXT NOT NULL CHECK (scan_status IN ('passed','flagged')),
    auditor_agent TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(session_id, file_path)
);

-- Durable in-flight task claims let the novelty guard coordinate agents before
-- work is complete. Advisory locking in the repository serializes claim checks
-- within a workspace session.
CREATE TABLE IF NOT EXISTS workspace_task_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id TEXT NOT NULL REFERENCES workspace_sessions(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    task_description TEXT NOT NULL,
    normalized_task TEXT NOT NULL,
    target_files TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','released')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_files_touched ON agent_actions USING GIN(files_touched);
CREATE INDEX IF NOT EXISTS idx_agent_actions_created_at ON agent_actions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workspace_artifacts_session ON workspace_artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_checkpoints_session ON audit_checkpoints(session_id);
CREATE INDEX IF NOT EXISTS idx_workspace_task_claims_session ON workspace_task_claims(session_id, normalized_task);
CREATE INDEX IF NOT EXISTS idx_workspace_task_claims_files ON workspace_task_claims USING GIN(target_files);

CREATE OR REPLACE FUNCTION agentdrift_workspace_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS trg_workspace_artifacts_updated ON workspace_artifacts;
CREATE TRIGGER trg_workspace_artifacts_updated BEFORE UPDATE ON workspace_artifacts
FOR EACH ROW EXECUTE FUNCTION agentdrift_workspace_updated_at();
DROP TRIGGER IF EXISTS trg_audit_checkpoints_updated ON audit_checkpoints;
CREATE TRIGGER trg_audit_checkpoints_updated BEFORE UPDATE ON audit_checkpoints
FOR EACH ROW EXECUTE FUNCTION agentdrift_workspace_updated_at();
DROP TRIGGER IF EXISTS trg_workspace_task_claims_updated ON workspace_task_claims;
CREATE TRIGGER trg_workspace_task_claims_updated BEFORE UPDATE ON workspace_task_claims
FOR EACH ROW EXECUTE FUNCTION agentdrift_workspace_updated_at();
