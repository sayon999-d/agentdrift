-- Structured, append-only history for completed or audited agent tasks.
CREATE TABLE IF NOT EXISTS commit_history (
    commit_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES workspace_sessions(id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    task_intent TEXT NOT NULL,
    execution_summary TEXT NOT NULL,
    files_touched JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(files_touched) = 'array'),
    exported_contracts JSONB,
    status TEXT NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed','reverted','audited')),
    diff_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_commit_history_session_created
    ON commit_history(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_commit_history_files_touched
    ON commit_history USING GIN(files_touched);

-- This table is backend-managed; do not expose workspace history to browser roles.
ALTER TABLE commit_history ENABLE ROW LEVEL SECURITY;

-- Preserve existing action history in the structured format.
INSERT INTO commit_history
    (commit_id,session_id,agent_id,task_intent,execution_summary,files_touched,
     exported_contracts,status,diff_hash,created_at)
SELECT a.id::text, a.session_id, a.agent_name, a.summary, a.summary,
       COALESCE((
           SELECT jsonb_agg(jsonb_build_object(
               'path', f.path,
               'change_type', CASE WHEN a.action_type='audit' THEN 'audited'
                                   WHEN a.action_type='create' THEN 'added' ELSE 'modified' END
           )) FROM unnest(a.files_touched) AS f(path)
       ), '[]'::jsonb),
       NULL,
       CASE WHEN a.action_type='audit' THEN 'audited' ELSE 'completed' END,
       a.diff_hash,
       a.created_at
FROM agent_actions AS a
ON CONFLICT (commit_id) DO NOTHING;
