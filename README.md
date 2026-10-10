# agentdrift — runtime supervisor for autonomous coding agents

AgentDrift is the runtime supervisor and circuit breaker for autonomous coding
agents. It detects repetitive tool calls and execution spirals, then reports an
intervention diagnostic before endless retries consume a token budget. The
Python package includes a CLI, local and cloud Model Context Protocol (MCP)
servers, and a web telemetry interface.

**Python 3.12+** · [PyPI](https://pypi.org/project/agentdrift/) ·
[Documentation](https://github.com/sayon999-d/agentdrift#readme) ·
[Issues](https://github.com/sayon999-d/agentdrift/issues)

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in DATABASE_URL
python scripts/migrate.py  # Phase 1: apply migrations/001_init.sql to Supabase
uvicorn app.main:app --host 127.0.0.1 --port 8901
```

No `DATABASE_URL`? The daemon runs in **memory mode** (hash embeddings,
same API) so dashboard development works with zero config.

## Phase 1 — Supabase migration

`migrations/001_init.sql` creates `vector` + `uuid-ossp`, tables
`agent_sessions`, `agent_executions` (with `payload_embedding vector(384)`),
`drift_detections`, and indexes. Applied via `scripts/migrate.py`
(psycopg or asyncpg).

## API (dashboard-facing)

| Method | Path | Notes |
|---|---|---|
| GET | `/health`, `/ready`, `/api/health` | db mode, embeddings backend, uptime |
| POST/GET | `/sessions`, `/api/sessions`, `/v1/sessions` | create/list |
| GET/PATCH | `/sessions/{id}` | fetch/update |
| POST | `/executions`, `/ingest`, `/api/executions` | ingest + auto drift-detect → `{execution, detection, drifted, kind}` |
| GET | `/executions`, `/sessions/{id}/executions` | list |
| GET | `/sessions/{id}/timeline` | executions interleaved with detections |
| GET | `/detections`, `/sessions/{id}/detections` | list |
| POST | `/detect` | read-only re-check vs predecessor |
| GET | `/stats` | counts for dashboard cards |

CORS allows `http://localhost:3000` + `http://127.0.0.1:3000` by default.

## Drift engine (`app/drift.py`)

Compares each ingested execution to the prior `sequence` in its session:

1. **state_drift** — `state_hash` changed (hard signal, wins)
2. **schema_drift** — output key-set changed without semantic break
3. **logical_drift** — NLI contradiction ≥ 0.7 (cross-encoder/deberta-v3-small when `NLI_ENABLED=true`, else negation-flip heuristic)
4. **semantic_drift** — cosine similarity of 384-d payload embeddings < threshold (default 0.85)
5. else **no_drift**

Embeddings: `sentence-transformers/all-MiniLM-L6-v2` when available,
otherwise a deterministic hashing-trick fallback (works offline).

## Tests

```bash
python -m pytest tests/ -q
```

## Storage: two runtimes

`agentdrift/storage/` defines one interface (`BaseStore`: `record_execution`,
`check_drift`, `list_recent_executions`) with two backends, selected
automatically — Supabase when `SUPABASE_DATABASE_URL` (or
`AGENTDRIFT_DATABASE_URL`) is set, otherwise local:

| Mode | Backend | Data | Entry |
|---|---|---|---|
| Local (CLI / stdio) | SQLite + LanceDB | `~/.agentdrift/` (offline) | `agentdrift …`, `mcp_server.py --transport stdio` |
| Cloud MCP (remote) | Supabase Postgres + pgvector | Supabase project | `mcp_server.py --transport http --token …` |

### Phase 1 — Supabase migration (Cloud MCP)

Run `migrations/002_supabase_mcp.sql` once in the Supabase SQL editor
(`vector` + `uuid-ossp` extensions, `agent_sessions` / `agent_executions`
with `embedding vector(384)` / `drift_detections`, plus indices).

### MCP server (Claude Code, Cline, OpenCode, Codex)

Tools: `record_execution`, `check_drift`, `list_recent_executions`, `get_health`.

```bash
# Local stdio (add to the client's MCP config)
python mcp_server.py --transport stdio

# Cloud Streamable HTTP with token auth (refuses to serve remote without one)
AGENTDRIFT_MCP_TOKEN=secret SUPABASE_DATABASE_URL=... \
  python mcp_server.py --transport http --host 0.0.0.0 --port 8931
# Legacy SSE (connect clients to /mcp)
python mcp_server.py --transport sse --port 8931 --token secret
```

After `pip install -e .` the same server is available as `agentdrift-mcp`.
Remote transports require `--token` (or `AGENTDRIFT_MCP_TOKEN`) unless
`--allow-unauthenticated` is passed for local dev; `/health` is always open.

## Terminal CLI (`agentdrift`)

The `cli.py` entrypoint replaces the web dashboard. Install it as a real
command (project layout stays as-is: `app/` is the daemon package,
`cli.py` is the console entrypoint):

```bash
pip install -e .
agentdrift health
agentdrift scan --threshold 0.92
agentdrift ingest --agent-id demo --session-id s1 --payload '{"key": "val"}'
agentdrift evaluate --premise "the cat sits" --hypothesis "the cat sits"
agentdrift test-all
```

`python cli.py <cmd>` keeps working without installing.

### Live tail (`watch`)

```bash
agentdrift watch --session-id s1 --interval 1.0 --threshold 0.92 --no-bell
```

Polls `GET /v1/executions` + `POST /v1/sentinel/scan` (falls back to
`GET /v1/detections`) and renders a live header / execution-stream / alerts
layout. New steps appear as `[HH:MM:SS] [seq N] agent:node -> summary`;
ping-pong loops raise a red alert banner plus terminal bell (disable with
`--no-bell`). A raw SSE feed is also available for custom tailers:

```bash
curl -N http://127.0.0.1:8901/v1/events/stream
```

## Production Cloud MCP server

The Supabase-backed remote MCP server is available at `/mcp` with Streamable
HTTP, or `/sse` with legacy SSE. Apply
[`migrations/002_cloud_mcp_supabase.sql`](migrations/002_cloud_mcp_supabase.sql)
in the Supabase SQL Editor first. Set `SUPABASE_DATABASE_URL` to the direct
Postgres URL (port 5432), `SUPABASE_JWT_SECRET` to the Supabase Auth JWT
signing secret, and `AGENTDRIFT_REQUIRE_AUTH=1` in production. With Render,
also set these values in the service's Environment page: its deploy hook
triggers a deployment but does not transfer GitHub secrets into Render.
`render.yaml` declares the keys as `sync: false`.

```bash
python -m agentdrift.mcp.cloud_server --transport streamable-http --port 8000
```

The server accepts a Supabase user JWT or an explicitly configured server
token (`AGENTDRIFT_MCP_TOKEN` / `MCP_TOKEN`). User JWTs are verified and their
`sub` claim scopes session and execution queries. Never put a service-role key
in a client configuration.

Claude Code (`.mcp.json`):

```json
{
  "mcpServers": {
    "agentdrift-cloud": {
      "type": "http",
      "url": "https://mcp.your-domain.com/mcp",
      "headers": { "Authorization": "Bearer <SUPABASE_USER_TOKEN>" }
    }
  }
}
```

Cline (`cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "agentdrift-cloud": {
      "type": "streamableHttp",
      "url": "https://mcp.your-domain.com/mcp",
      "headers": { "Authorization": "Bearer <SUPABASE_USER_TOKEN>" },
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

OpenCode (`opencode.json`):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "agentdrift-cloud": {
      "type": "remote",
      "url": "https://mcp.your-domain.com/mcp",
      "oauth": false,
      "headers": { "Authorization": "Bearer <SUPABASE_USER_TOKEN>" }
    }
  }
}
```

For legacy SSE, run the server with `--transport sse` and use
`https://mcp.your-domain.com/sse` as the client URL.
