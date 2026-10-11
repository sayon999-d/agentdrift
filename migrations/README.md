# Database migrations

This directory contains schemas for separate AgentDrift persistence paths.
Read each migration header and match it to the server/backend before applying;
the numbered files are not one universal linear migration chain.

## Files and intended consumers

| File | Consumer | Schema details |
|---|---|---|
| `001_init.sql` | FastAPI daemon via SQLAlchemy/Postgres | Sessions, executions, detections, JSONB, `payload_embedding vector(384)`, timestamps and indexes |
| `002_supabase_mcp.sql` | Standalone `agentdrift.storage.supabase` adapter | Supabase MCP session/execution/detection tables and `embedding vector(384)` |
| `002_cloud_mcp_supabase.sql` | Multi-tenant Cloud MCP server | `user_id`, Supabase Auth references, RLS policies, `payload_embedding vector(384)`, HNSW cosine index |

The two `002` scripts target different implementations and column conventions.
Do not run both based only on their numeric prefix. The cloud schema header
describes compatibility with Phase 1, but validate an existing database's
columns and constraints before applying it.

## Tables and lifecycle

- `agent_sessions` stores an agent/session identity, status, metadata, and
  creation/update times where defined.
- `agent_executions` stores sequence-ordered input/output payloads, state hash,
  optional trace, and embedding. Its session foreign key generally cascades on
  session deletion.
- `drift_detections` stores the reported kind, compared execution IDs,
  similarity, threshold, evidence, and timestamp.

Retention/deletion policy is not automated by these migrations. Review foreign
keys and detection cleanup behavior for the exact schema before deleting
sessions or setting retention jobs.

## Vector indexes

- `001_init.sql` includes a commented optional IVFFlat cosine index example;
  it is not created by default.
- `002_cloud_mcp_supabase.sql` creates an HNSW cosine index and requires a
  compatible pgvector release.
- The local LanceDB vector table is created by application code, not SQL.

Index type/parameters affect performance and should be chosen after examining
data volume, query shape, and pgvector version. Do not change vector dimensions
without coordinated backfill/reindexing.

## Apply

For the daemon's initial schema:

```bash
SYNC_DATABASE_URL='postgresql://…' python scripts/migrate.py
```

The MCP migrations include Supabase-specific SQL and may be applied through the
Supabase SQL editor as described by their headers. Back up first, use least-
privilege administrative access, and verify table/index state after execution.
Migration scripts are DDL, not an application-level rollback mechanism.
