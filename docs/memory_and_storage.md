# Memory and storage

AgentDrift stores ordered sessions and executions plus drift detections. Vector
representations support semantic similarity checks; they complement rather
than replace the relational execution history.

## Local hybrid engine

The local engine in `app/hybrid_store.py` creates this layout under
`~/.agentdrift` by default. Set `AGENTDRIFT_DATA_DIR` to change the base path.

```text
<data_dir>/
├── agentdrift.db       SQLite sessions, executions, detections
└── vectors.lance/      LanceDB execution_vectors table (384-D vectors)
```

The SQLite database has session, execution, and detection tables plus indexes
for session/sequence and creation time. LanceDB stores execution ID, session
ID, and a fixed 384-element vector. Async public methods send synchronous
SQLite/LanceDB work to a worker thread under a lock to avoid blocking the
FastAPI event loop.

In-memory fallback is available when persistence cannot be initialized. It is
ephemeral and should not be selected for durable production history.

## PostgreSQL and Supabase

`migrations/001_init.sql` creates the daemon relational schema with JSONB
payloads, `vector(384)` embeddings, timestamps, foreign keys, indexes, and an
`updated_at` trigger. Its IVFFlat vector index is commented out by default and
must be deliberately enabled/tuned when suitable data volume exists.

`migrations/002_supabase_mcp.sql` supports the first Supabase MCP schema using
`embedding vector(384)`. `migrations/002_cloud_mcp_supabase.sql` adds the
multi-tenant cloud schema, `user_id` references, RLS policies, and an HNSW
cosine index over `payload_embedding`. These files represent different
application paths and should not be applied blindly in arbitrary order; see
[the migration guide](../migrations/README.md).

The ORM daemon uses SQLAlchemy/asyncpg when `DATABASE_URL` or `SUPABASE_DB_URL`
is configured. The MCP store factory uses `SUPABASE_DATABASE_URL` or
`AGENTDRIFT_DATABASE_URL` to select its Supabase adapter. Use direct database
credentials only in server environments.

Shared workspace memory stores work history in `commit_history`. Apply
`supabase/migrations/20261017_task_execution_commits.sql` after
`20261016_shared_workspace_memory.sql`; it backfills legacy actions and enables
RLS on the backend-managed history table. The MCP uses validated
`TaskExecutionCommit` records rather than open-ended action blobs.

## Retention and lifecycle

There is no built-in TTL, retention scheduler, or automatic archive policy in
the current repository. Session deletion cascades to executions in the SQL
schema where foreign keys are defined; detection relationships differ between
migrations. Define retention, backup, and deletion requirements operationally
before production use. Include both relational and vector stores in backups;
orphaned/missing vectors can change similarity results.

## Indexing and backfill

- Local LanceDB creates/opens the `execution_vectors` table with a fixed
  384-D schema. The current code does not configure a user-facing index
  parameter matrix; use LanceDB's defaults unless a reviewed implementation
  change introduces explicit index creation.
- PostgreSQL local schema includes an optional commented IVFFlat example.
- Cloud schema creates HNSW with cosine ops (requires a compatible pgvector).
- Backfill is not an automatic migration feature. A backfill must read stored
  input/output payloads, compute vectors using the same model and dimension,
  and upsert vectors keyed by execution ID. Track progress, handle retries
  idempotently, and validate vector counts/dimensions before switching reads.
- Changing the model can change vector geometry even when dimensions remain
  384. Re-embed historical and new records consistently, or version vectors
  and keep model metadata alongside them before comparing.

## Operational checks

1. Check `/ready` and backend mode.
2. Confirm SQLite/Postgres session and execution counts.
3. Confirm vector table/column dimension and count.
4. Run a known repeated-state pair through sentinel scan and verify evidence.
5. Back up relational and vector data and test restoration together.
