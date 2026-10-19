# `agentdrift` Python package

This package contains the CLI, MCP server, shared storage interfaces, and the
production Cloud MCP server. Root `cli.py` and `mcp_server.py` remain
compatibility shims. Installed console scripts target package modules declared
in the repository-root `pyproject.toml`.

## Install and use

```bash
pip install -e .
agentdrift-mcp --help
```

Use `agentdrift.storage.get_store()` to select the configured backend:

```python
from agentdrift.storage import get_store

store = get_store()  # local SQLite + LanceDB unless cloud URL is configured
```

The store interface is asynchronous. Local mode writes below `./.agentdrift`
unless `AGENTDRIFT_DIR` or `AGENTDRIFT_DATA_DIR` is set. Use `--global` to
store local data under `~/.agentdrift`, or set `AGENTDRIFT_DB_PATH` to choose a
specific SQLite file. Set `SUPABASE_DATABASE_URL` or
`AGENTDRIFT_DATABASE_URL` to select the Supabase PostgreSQL/pgvector adapter.

## Internal map

| Path | Purpose |
|---|---|
| `cli.py` | Installed `agentdrift` command |
| `mcp/server.py` | Installed `agentdrift-mcp` command |
| `storage/base.py` | `BaseStore` contract and typed `DriftReport` |
| `storage/factory.py` | Backend selection and lazy construction |
| `storage/local.py` | Adapter over the app's SQLite/LanceDB hybrid engine |
| `storage/supabase.py` | Supabase Postgres + pgvector implementation |
| `mcp/cloud_server.py` | Authenticated cloud MCP server and HTTP/SSE app |
| `mcp/__init__.py` | MCP package marker |

## Dependencies and runtime notes

The package shares root dependencies including FastAPI, SQLAlchemy, asyncpg,
pgvector, LanceDB, PyArrow, FastMCP/MCP SDK, PyJWT, and the embedding
dependencies. Imports and database connections are deferred where possible.
Apply the matching SQL migration before selecting a cloud backend. Cloud
credentials belong only in the server environment, never a coding-agent
client's config.

See [`../docs/memory_and_storage.md`](../docs/memory_and_storage.md),
[`../docs/security_and_sandboxing.md`](../docs/security_and_sandboxing.md),
and [`../docs/MCP_INTEGRATION_MATRIX.md`](../docs/MCP_INTEGRATION_MATRIX.md).
