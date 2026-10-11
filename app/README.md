# FastAPI daemon (`app`)

`app` is AgentDrift's REST daemon and execution-ingestion engine. Start it
from the repository root with:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8901
```

It supports memory fallback, local SQLite + LanceDB persistence, or PostgreSQL
when `DATABASE_URL`/`SUPABASE_DB_URL` is configured. Runtime settings are in
`config.py` and `.env.example`.

## File map

| Path | Purpose |
|---|---|
| `main.py` | FastAPI app, lifespan, compatibility routes, sentinel, NLI utility, SSE stream |
| `routers/api.py` | Session, execution, detection, timeline, and stats API routes |
| `schemas.py` | Pydantic request/response models |
| `store.py` | Memory/SQLite/Postgres persistence facade and execution ingest |
| `hybrid_store.py` | SQLite relational + LanceDB vector implementation |
| `database.py` | Async SQLAlchemy engine and session factory |
| `models.py` | SQLAlchemy relational models |
| `drift.py` | Per-execution drift classification |
| `embeddings.py` | SentenceTransformers, hash fallback, optional NLI heuristic/model |
| `config.py` | Environment settings |

## Detection and execution flow

`POST /executions` persists an execution and compares it to its predecessor.
`POST /v1/sentinel/scan` scans adjacent executions for matching state hashes or
cosine similarity at the sentinel threshold (default 0.92). Drift
classification uses the separate configured drift threshold (default 0.85).
The NLI model is optional; it is not a stage in the sentinel ping-pong scan.
See [`../docs/architecture.md`](../docs/architecture.md) and
[`../docs/api_reference.md`](../docs/api_reference.md).

## Dependencies

The root project declares FastAPI/Uvicorn, Pydantic Settings, SQLAlchemy,
asyncpg, NumPy, SentenceTransformers, LanceDB, PyArrow, and MCP dependencies.
Heavy model components load lazily and have fallbacks. Apply schema migrations
before using PostgreSQL. Never expose an unauthenticated daemon to an untrusted
network.
