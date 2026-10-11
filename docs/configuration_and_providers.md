# Configuration and providers

The daemon's canonical settings are in `app/config.py` and are loaded by
`pydantic-settings` from process environment variables and `.env`. Unknown
variables are ignored by that settings class. MCP server settings are partly
read directly from `os.environ` in `mcp_server.py` and
`agentdrift/mcp/cloud_server.py`, so they are not all represented in
`app/config.py`.

## Daemon settings

| Variable | Default | Purpose |
|---|---|---|
| `HOST` | `127.0.0.1` | Uvicorn bind address; use a private interface/reverse proxy for deployment |
| `PORT` | `8901` | Daemon HTTP port |
| `LOG_LEVEL` | `info` | Application logging level |
| `ENV` | `dev` | Environment label |
| `DATABASE_URL` | empty | Async SQL database URL; when set, the daemon uses PostgreSQL persistence |
| `SUPABASE_DB_URL` | empty | Alternate daemon DB URL used if `DATABASE_URL` is empty |
| `SUPABASE_DATABASE_URL` | empty | Render/cloud alias used after the two daemon URL names |
| `SYNC_DATABASE_URL` | empty | Synchronous migration-runner URL; also accepted after Supabase alias |
| `CORS_ORIGINS` | localhost:3000 and 127.0.0.1:3000 | Comma-separated allowed origins |
| `DRIFT_SIMILARITY_THRESHOLD` | `0.85` | Ingest-time drift classification threshold |
| `DRIFT_AUTO_DETECT` | `true` | Declared setting for automatic detection; inspect current call sites before relying on disabling it |

PostgreSQL URLs are normalized to `postgresql+asyncpg://` for the async SQLAlchemy
engine. Keep credentials in environment/secret management, not committed `.env`
files. See `.env.example` for a starting template.

## Storage modes that exist today

| Mode | Selection | Persistence | Notes |
|---|---|---|---|
| Process memory | Fallback when persistence is unavailable | None; lost on restart | Useful for isolated tests/demo, not production retention |
| Local hybrid | Default when local persistence dependencies are available | SQLite + LanceDB under `~/.agentdrift` | `AGENTDRIFT_DATA_DIR` overrides the directory |
| PostgreSQL | Daemon `DATABASE_URL` or `SUPABASE_DB_URL` | PostgreSQL via SQLAlchemy/asyncpg | Apply schema migration before use |
| Supabase MCP backend | MCP factory selects when `SUPABASE_DATABASE_URL` or `AGENTDRIFT_DATABASE_URL` is set | Postgres + pgvector | Separate MCP storage adapter and schema from daemon settings |

There is no explicit `STORAGE_MODE=in-memory|hybrid|postgres+pgvector|supabase`
setting in `app/config.py`; backend choice follows URL presence and dependency
availability. “Supabase” is PostgreSQL with Supabase-specific auth/schema
features, not a distinct database engine.

## Embedding and NLI settings

| Variable | Default | Behavior |
|---|---|---|
| `EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | SentenceTransformer model name |
| `EMBEDDING_DIM` | `384` | Vector dimension expected by local/Postgres schemas |
| `EMBEDDING_FALLBACK_HASH` | `true` | Declared fallback setting; current embedding service falls back to hashing when loading/inference fails |
| `NLI_MODEL` | `cross-encoder/nli-deberta-v3-small` | Optional NLI cross-encoder identifier |
| `NLI_ENABLED` | `false` | Enables NLI model path; otherwise contradiction heuristic is used |

Current embedding providers are SentenceTransformers and deterministic
token-hash fallback. FastEmbed is not implemented. Changing the embedding
dimension requires coordinated schema and index migration; do not change
`EMBEDDING_DIM` alone. The local LanceDB table has a fixed Arrow vector schema
of 384 dimensions. The pgvector schemas likewise declare `vector(384)`.

## MCP server environment

### `mcp_server.py` standalone server

| Variable/flag | Purpose |
|---|---|
| `AGENTDRIFT_MCP_TOKEN` / `MCP_TOKEN` | Bearer token for remote standalone MCP transport |
| `SUPABASE_DATABASE_URL` / `AGENTDRIFT_DATABASE_URL` | Select remote Postgres store |
| `AGENTDRIFT_EMBED_MODE` | Set `hash` to skip model load; default is hash in this server |
| `AGENTDRIFT_EMBED_MODEL` | SentenceTransformer model name for model mode |
| `--transport` | `stdio`, `http`, or legacy `sse` |
| `--host`, `--port` | HTTP/SSE bind settings |
| `--allow-unauthenticated` | Development-only override for remote transport auth |

Remote transport refuses to start without a token unless explicitly allowed.

### Cloud MCP server

`agentdrift.mcp.cloud_server` reads `SUPABASE_DATABASE_URL` (or
`AGENTDRIFT_DATABASE_URL`), `SUPABASE_JWT_SECRET`, `SUPABASE_URL`,
`SUPABASE_ANON_KEY`, `AGENTDRIFT_MCP_TOKEN`/`MCP_TOKEN`, and
`AGENTDRIFT_REQUIRE_AUTH`. It accepts Streamable HTTP or SSE; check the
cloud-server module and deployment environment template for exact auth policy.
Never distribute `SUPABASE_SERVICE_ROLE_KEY` to an agent client.

## Run locally

```bash
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8901
```

No database URL selects the local fallback behavior. Production deployment
should bind behind a trusted reverse proxy, configure an explicit database,
and set exact CORS origins.
