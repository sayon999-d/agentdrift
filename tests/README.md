# Test suite

The tests exercise FastAPI contracts, storage backend selection, MCP tool
contracts, sentinel behavior, and SSE stream snapshots. Run from the repository
root after installing the project and development dependencies:

```bash
python -m pytest tests/ -q
```

## Test isolation

`conftest.py` sets `AGENTDRIFT_DATA_DIR` to a temporary directory so the local
hybrid store does not touch the project or user data directories. API tests use FastAPI's test client
and in-process state; storage tests use local objects and monkeypatch backend
selection where needed. Keep tests independent of real Supabase credentials
and network services.

## File map

| File | Coverage |
|---|---|
| `test_api.py` | Health, session/execution/drift flow, state-hash signals |
| `test_storage_abstraction.py` | Factory defaults, cloud backend selection, local store, MCP contracts |
| `test_watch_endpoints.py` | Execution ordering, detections, scan results, aliases, SSE snapshot |
| `conftest.py` | Temporary data directory fixture/setup |

The current tests are API/contract and regression tests, not a statistically
controlled latency benchmark. The product target of p99 < 25 ms for local
checks requires a separate representative benchmark harness and should not be
claimed from this suite alone.

## Adding coverage

- For route changes, assert status, response shape, and relevant error cases.
- For sentinel regressions, cover identical hashes, similarity threshold
  boundaries, and idempotent detections.
- For storage changes, test both selected backend and persisted/retrieved
  values; isolate filesystem paths.
- For SSE changes, validate the first snapshot, later deltas, and `once=true`
  behavior without leaving open streams.
- Avoid logging credentials or real payload data in assertion failures.
