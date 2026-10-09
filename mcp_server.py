"""AgentDrift MCP server — expose drift detection to external agents.

Two runtimes:
  Local Mode  (stdio)            embedded SQLite + LanceDB at ~/.agentdrift/
  Cloud Mode  (HTTP/SSE remote)  Supabase Postgres + pgvector (needs
                                 SUPABASE_DATABASE_URL) with Bearer-token auth.

Usage:
  Local (Claude Code / Cline / OpenCode / Codex stdio):
    python mcp_server.py --transport stdio
  Cloud (remote Streamable HTTP + Bearer token):
    AGENTDRIFT_MCP_TOKEN=secret SUPABASE_DATABASE_URL=... \\
      python mcp_server.py --transport http --host 0.0.0.0 --port 8931
  Legacy SSE transport:
    python mcp_server.py --transport sse --port 8931 --token secret

Backend selection is automatic (see agentdrift.storage.factory): Supabase
when SUPABASE_DATABASE_URL/AGENTDRIFT_DATABASE_URL is set, else local.

Performance design (sub-50ms tool latency):
  * NOTHING heavy is imported at module top-level — no torch,
    sentence_transformers, numpy, lancedb, or uvicorn. Those are imported
    lazily inside functions / background threads only.
  * ``embed_hashed`` (SHA-256 hashing-trick, pure stdlib) is the default fast
    path for loop detection (<10ms, no model). Dense transformer inference
    only runs when explicitly requested, via ``asyncio.to_thread`` so the
    stdio event loop is never blocked.
  * The store handle (SQLite + LanceDB) is resolved once and cached per
    server instance — never re-opened per request. SQLite WAL mode is applied
    once (``journal_mode=WAL; synchronous=NORMAL``) for sub-ms writes.
  * ``check_drift_status`` / ``check_loop_circuit_breaker`` implement a
    fast-path circuit breaker: Step 1 compares the last two ``state_hash``
    values straight from SQLite (0 vector work); Step 2 (cosine similarity)
    runs only when hashes differ but repetition is suspected.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import re
import secrets
import threading
import time
from typing import Any

log = logging.getLogger("agentdrift.mcp")


try:
    # Official MCP Python SDK v2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    try:
        # Standalone fastmcp package or official MCP v1.x fallback
        from fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server.fastmcp import FastMCP

# Backwards-compat alias: older code imported MCPServer directly.
MCPServer = FastMCP


# ---------------------------------------------------------------------------
# Fast-path embedding: pure-stdlib hashing trick (no torch / numpy at import)
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384
_WORD_RE = re.compile(r"[a-z0-9]+")

# NOTE: torch / sentence_transformers must NEVER be imported at module scope.
# They cost 4-8s of boot time on every stdio spawn. See _get_dense_model().
_FORBIDDEN_TOP_LEVEL = ("torch", "sentence_transformers")


def embed_hashed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Lightweight SHA-256 hash embedding, L2-normalized.

    Deterministic, dependency-free fast path for initial loop detection:
    identical texts -> cosine 1.0, unrelated -> ~0. Completes in <10ms.
    """
    vec = [0.0] * dim
    for token in _WORD_RE.findall((text or "").lower()):
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h >> 16) % dim] += 0.5
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-12:
        return vec
    return [v / norm for v in vec]


def cosine_fast(a: list[float], b: list[float]) -> float:
    """Pure-python cosine similarity (no numpy import cost on hot path)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    denom = na * nb
    if denom < 1e-12:
        return 1.0 if all(abs(x - y) < 1e-12 for x, y in zip(a, b)) else 0.0
    return dot / denom


def _payload_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload[:8000]
    try:
        return json.dumps(payload, sort_keys=True, default=str)[:8000]
    except Exception:
        return str(payload)[:8000]


# ---------------------------------------------------------------------------
# Lazy + async dense model loading (opt-in only, never on boot)
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_dense_model: Any = None
_dense_model_tried = False


def _get_dense_model() -> Any | None:
    """Import and load the transformer model on first explicit use only.

    Called exclusively from worker threads (via ``asyncio.to_thread``), never
    on the event loop and never at import/startup. Returns None offline.
    Honors AGENTDRIFT_EMBED_MODE=hash (default) to skip loading entirely.
    """
    global _dense_model, _dense_model_tried
    if os.getenv("AGENTDRIFT_EMBED_MODE", "hash").strip().lower() == "hash":
        return None
    with _model_lock:
        if _dense_model_tried:
            return _dense_model
        _dense_model_tried = True
    try:
        from sentence_transformers import SentenceTransformer  # lazy!

        model_name = os.getenv("AGENTDRIFT_EMBED_MODEL", "all-MiniLM-L6-v2")
        model = SentenceTransformer(model_name)
        with _model_lock:
            _dense_model = model
        log.info("Loaded dense embedding model %s (background)", model_name)
        return model
    except Exception as exc:  # offline / no torch -> hash fallback
        log.warning("Dense model unavailable, hash fallback: %s", exc)
        return None


async def embed_text_async(text: str) -> list[float]:
    """Non-blocking embedding: dense model in a worker thread, else hash."""
    text = (text or "")[:8000]

    def _encode() -> list[float] | None:
        model = _get_dense_model()
        if model is None:
            return None
        try:
            vec = model.encode([text], normalize_embeddings=True)[0]
            return [float(x) for x in vec]
        except Exception as exc:
            log.warning("dense encode failed, hash fallback: %s", exc)
            return None

    vec = await asyncio.to_thread(_encode)
    if vec is not None:
        return vec
    return await asyncio.to_thread(embed_hashed, text)


# ---------------------------------------------------------------------------
# Persistent store handles + SQLite WAL (applied once, never per-request)
# ---------------------------------------------------------------------------

_wal_lock = threading.Lock()
_wal_applied_for: set[str] = set()


def _ensure_wal_sync(store: Any) -> None:
    """Apply SQLite WAL pragmas once per database path (sync, thread-safe)."""
    hybrid = getattr(store, "_hybrid", None)
    sql = getattr(hybrid, "_sql", None)
    db_path = str(getattr(hybrid, "db_path", "") or "")
    if sql is None or not db_path:
        return  # cloud backend or unknown layout: nothing to tune
    with _wal_lock:
        if db_path in _wal_applied_for:
            return
        try:
            lock = getattr(hybrid, "_lock", None)
            if lock is not None:
                with lock:
                    sql.execute("PRAGMA journal_mode=WAL;")
                    sql.execute("PRAGMA synchronous=NORMAL;")
                    sql.execute("PRAGMA temp_store=MEMORY;")
                    sql.commit()
            else:
                sql.execute("PRAGMA journal_mode=WAL;")
                sql.execute("PRAGMA synchronous=NORMAL;")
                sql.commit()
            _wal_applied_for.add(db_path)
            log.info("SQLite WAL mode enabled at %s", db_path)
        except Exception as exc:
            log.debug("WAL pragma failed (non-fatal): %s", exc)


def _prewarm_in_background(store_factory) -> None:
    """Resolve the store + WAL off the hot path (daemon thread, boot only)."""

    def _run() -> None:
        try:
            store = store_factory()
            _ensure_wal_sync(store)
            if os.getenv("AGENTDRIFT_PREWARM_MODEL", "").strip() == "1":
                _get_dense_model()  # explicit opt-in; default OFF (slow)
        except Exception as exc:
            log.debug("store prewarm failed (lazy fallback): %s", exc)

    thread = threading.Thread(target=_run, name="agentdrift-prewarm", daemon=True)
    thread.start()


def resolve_token(explicit: str | None = None) -> str | None:
    return (
        explicit
        or os.getenv("AGENTDRIFT_MCP_TOKEN", "").strip()
        or os.getenv("MCP_TOKEN", "").strip()
        or None
    )


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _normalize_list_output_schemas(mcp: Any) -> None:
    """Let list-returning tools unwrap ``.data`` on any MCP client.

    Standalone fastmcp tags ``{"result": [...]}`` output schemas with
    ``x-fastmcp-wrap-result``, and its Client then collapses ``.data`` to the
    raw list. The MCP SDK v2 server emits the same shape without the marker,
    leaving ``.data`` as a wrapper model. Stamp the marker onto wrapped
    single-key ``result`` schemas so both server classes behave identically.
    No-op for native fastmcp servers (marker already present) and for
    dict-returning tools (never wrapped).
    """
    manager = getattr(mcp, "_tool_manager", None)
    tools = getattr(manager, "_tools", None) or {}
    for tool in tools.values():
        schema = getattr(tool, "output_schema", None)
        if schema is None:
            schema = getattr(tool, "outputSchema", None)
        if not isinstance(schema, dict) or schema.get("x-fastmcp-wrap-result"):
            continue
        props = schema.get("properties", {})
        if list(schema.get("required", [])) == ["result"] and set(props) == {"result"}:
            try:
                schema["x-fastmcp-wrap-result"] = True
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Fast-path circuit breaker: state_hash compare BEFORE any vector math
# ---------------------------------------------------------------------------

async def _last_two_hashes(
    store: Any, session_id: str
) -> tuple[dict | None, dict | None]:
    """Fetch the last two executions' (state_hash, payload) cheaply.

    Prefers a direct SQLite query (no vector I/O); falls back to
    ``list_recent_executions(limit=2)`` for cloud backends. Runs blocking
    SQLite work in a worker thread so the event loop stays responsive.
    """
    hybrid = getattr(store, "_hybrid", None)
    sql = getattr(hybrid, "_sql", None)
    if sql is not None and session_id:
        def _op():
            lock = getattr(hybrid, "_lock", None)
            query = (
                "SELECT execution_id, sequence, state_hash,"
                " input_payload, output_payload FROM executions"
                " WHERE session_id=? ORDER BY sequence DESC LIMIT 2"
            )
            if lock is not None:
                with lock:
                    rows = sql.execute(query, (session_id,)).fetchall()
            else:
                rows = sql.execute(query, (session_id,)).fetchall()
            out = []
            for r in rows:
                try:
                    d = dict(r)
                except Exception:
                    d = {
                        "execution_id": r[0], "sequence": r[1], "state_hash": r[2],
                        "input_payload": r[3], "output_payload": r[4],
                    }
                out.append(d)
            return out

        try:
            rows = await asyncio.to_thread(_op)
            if len(rows) >= 2:
                # rows are newest-first; return oldest-first (prev, cur)
                return rows[1], rows[0]
            if len(rows) == 1:
                return None, rows[0]
            return None, None
        except Exception as exc:
            log.debug("fast SQLite lane failed, list fallback: %s", exc)
    # Cloud / fallback lane: limit=2 keeps this a single cheap query.
    try:
        recent = await store.list_recent_executions(session_id, limit=2)
    except Exception:
        return None, None
    if not recent:
        return None, None
    if len(recent) == 1:
        return None, recent[0]
    # list_recent_executions is newest-first -> (prev, cur)
    return recent[1], recent[0]


def _payload_of(row: dict | None) -> Any:
    if not row:
        return ""
    if isinstance(row.get("output_payload"), dict) and row["output_payload"]:
        return row["output_payload"]
    if isinstance(row.get("input_payload"), dict) and row["input_payload"]:
        return row["input_payload"]
    return (
        row.get("output_payload")
        or row.get("input_payload")
        or row.get("payload")
        or ""
    )


async def _circuit_breaker_check(
    store: Any, session_id: str | None, threshold: float = 0.92
) -> dict[str, Any]:
    """Fast-path loop check.

    Step 1: compare last-2 ``state_hash`` directly from SQLite — identical
      hashes return a ping-pong alert immediately (0 vector work).
    Step 2: only when hashes differ, compute hash-embedding cosine
      (pure stdlib, <10ms); if below threshold, delegate to the full
      ``store.check_drift`` scan (LanceDB / pgvector).
    """
    started = _now_ms()
    if not session_id:
        report = await store.check_drift(None, threshold)
        data = report.model_dump() if hasattr(report, "model_dump") else dict(report)
        data.setdefault("fast_path", False)
        data["elapsed_ms"] = round(_now_ms() - started, 2)
        return data

    prev, cur = await _last_two_hashes(store, session_id)
    if prev and cur:
        ph, ch = prev.get("state_hash"), cur.get("state_hash")
        if ph and ch and str(ph) == str(ch):
            return {
                "ok": True,
                "session_id": session_id,
                "detections": 1,
                "threshold": threshold,
                "fast_path": "state_hash",
                "elapsed_ms": round(_now_ms() - started, 2),
                "loops": [{
                    "session_id": session_id,
                    "execution_id": cur.get("execution_id"),
                    "prior_execution_id": prev.get("execution_id"),
                    "kind": "ping_pong_loop",
                    "similarity": 1.0,
                    "threshold": threshold,
                    "evidence": {
                        "reason": "matching state_hash",
                        "state_hash": ch,
                        "prev_sequence": prev.get("sequence"),
                        "sequence": cur.get("sequence"),
                    },
                }],
            }
        # Step 2: cheap hash-embedding cosine over payload text only.
        def _sim() -> float:
            va = embed_hashed(_payload_text(_payload_of(prev)))
            vb = embed_hashed(_payload_text(_payload_of(cur)))
            return round(cosine_fast(va, vb), 4)

        try:
            sim = await asyncio.to_thread(_sim)
        except Exception:
            sim = 0.0
        if sim >= threshold:
            return {
                "ok": True,
                "session_id": session_id,
                "detections": 1,
                "threshold": threshold,
                "fast_path": "hash_cosine",
                "elapsed_ms": round(_now_ms() - started, 2),
                "loops": [{
                    "session_id": session_id,
                    "execution_id": cur.get("execution_id"),
                    "prior_execution_id": prev.get("execution_id"),
                    "kind": "ping_pong_loop",
                    "similarity": sim,
                    "threshold": threshold,
                    "evidence": {
                        "reason": f"hash cosine {sim:.4f} >= {threshold}",
                        "prev_sequence": prev.get("sequence"),
                        "sequence": cur.get("sequence"),
                    },
                }],
            }
    # Step 3: no fast signal — full scan (vector search lives here).
    report = await store.check_drift(session_id, threshold)
    data = report.model_dump() if hasattr(report, "model_dump") else dict(report)
    data.setdefault("fast_path", False)
    data["elapsed_ms"] = round(_now_ms() - started, 2)
    return data


def create_mcp(store=None):
    """Build the FastMCP server bound to ``store`` (resolved lazily if omitted).

    The store handle is opened once and cached for the life of the server —
    never per-request. Heavy imports (torch / sentence_transformers / lancedb
    / uvicorn) are never touched here; they load lazily inside workers.
    """
    from agentdrift.storage.base import BaseStore
    from agentdrift.storage.factory import backend_name, get_store

    active: dict[str, BaseStore | None] = {"store": store}
    active_lock = threading.Lock()
    wal_done = {"applied": False}

    def _store() -> BaseStore:
        # Fast path: already resolved (no lock, no I/O).
        if active["store"] is not None:
            return active["store"]
        with active_lock:
            if active["store"] is None:
                resolved = get_store()
                active["store"] = resolved
                if not wal_done["applied"]:
                    wal_done["applied"] = True
                    try:
                        _ensure_wal_sync(resolved)
                    except Exception as exc:
                        log.debug("WAL setup failed (non-fatal): %s", exc)
        return active["store"]

    mcp = FastMCP("agentdrift")

    @mcp.tool()
    async def record_execution(
        session_id: str,
        agent_id: str,
        node_id: str = "default",
        payload: dict[str, Any] | None = None,
        thinking: str | None = None,
        embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Persist one agent step (payload + thinking + optional embedding)."""
        started = _now_ms()
        result = await _store().record_execution(
            session_id, agent_id, node_id, payload or {}, thinking, embedding
        )
        result["elapsed_ms"] = round(_now_ms() - started, 2)
        return result

    @mcp.tool()
    async def check_drift(
        session_id: str | None = None,
        threshold: float = 0.92,
    ) -> dict[str, Any]:
        """Flag ping-pong loops among consecutive steps; returns a DriftReport.

        Fast lane first (state_hash compare, 0 vector work); falls back to the
        full vector scan only when hashes differ.
        """
        return await _circuit_breaker_check(_store(), session_id, threshold)

    @mcp.tool()
    async def check_drift_status(
        session_id: str | None = None,
        threshold: float = 0.92,
    ) -> dict[str, Any]:
        """Lightweight drift status: hash fast-path first, vectors only if needed."""
        return await _circuit_breaker_check(_store(), session_id, threshold)

    @mcp.tool()
    async def check_loop_circuit_breaker(
        session_id: str,
        threshold: float = 0.92,
    ) -> dict[str, Any]:
        """Circuit breaker: immediate loop alert on repeated state_hash.

        Step 1 — compare last-2 state_hash from SQLite (0ms vectors).
        Step 2 — hash-embedding cosine only if hashes differ.
        """
        data = await _circuit_breaker_check(_store(), session_id, threshold)
        loops = data.get("loops", [])
        return {
            "loop_detected": bool(loops),
            "session_id": session_id,
            "threshold": threshold,
            "fast_path": data.get("fast_path", False),
            "elapsed_ms": data.get("elapsed_ms", 0.0),
            "loops": loops,
            "detections": data.get("detections", 0),
        }

    @mcp.tool()
    async def list_recent_executions(
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Newest-first execution records, optionally filtered by session."""
        return await _store().list_recent_executions(session_id, limit)

    @mcp.tool()
    async def get_health() -> dict[str, Any]:
        """Daemon/store health: backend name and selection source."""
        url_set = bool(
            os.getenv("SUPABASE_DATABASE_URL", "").strip()
            or os.getenv("AGENTDRIFT_DATABASE_URL", "").strip()
        )
        return {
            "status": "ok",
            "backend": backend_name(),
            "supabase_configured": url_set,
            "embed_mode": os.getenv("AGENTDRIFT_EMBED_MODE", "hash"),
        }

    _normalize_list_output_schemas(mcp)
    return mcp


mcp = create_mcp()


# ---------------------------------------------------------------------------
# HTTP/SSE serving with Bearer-token auth
# ---------------------------------------------------------------------------


class _BearerAuthMiddleware:
    """Pure-ASGI Bearer check (exempts /health)."""

    def __init__(self, app, token: str) -> None:
        self.app = app
        self._token = token.encode()

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        presented = headers.get("authorization", "")
        ok = presented.startswith("Bearer ") and secrets.compare_digest(
            presented[len("Bearer ") :].encode(), self._token
        )
        if not ok:
            body = b'{"detail":"missing or invalid bearer token"}'
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _http_app(mcp, transport: str, token: str | None):
    from starlette.applications import Starlette  # lazy: keeps stdio boot fast
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    async def _health(_request):
        return JSONResponse({"status": "ok", "service": "agentdrift-mcp"})

    # Version-safe inner app construction:
    # - MCP SDK v2.x (MCPServer): sse_app() / streamable_http_app()
    # - standalone fastmcp / SDK v1.x: http_app(path=..., transport=...)
    if hasattr(mcp, "http_app"):
        inner = mcp.http_app(path="/mcp", transport=transport)
    elif transport == "sse" and hasattr(mcp, "sse_app"):
        inner = mcp.sse_app()
    elif hasattr(mcp, "streamable_http_app"):
        inner = mcp.streamable_http_app()
    elif hasattr(mcp, "sse_app"):
        inner = mcp.sse_app()
    else:
        raise RuntimeError(
            f"Unsupported MCP server object {type(mcp)!r}: no http_app/sse_app builder"
        )
    routes = [Route("/health", _health), Mount("/", app=inner)]
    # The inner StreamableHTTP app owns its lifespan (session manager task
    # group); the parent must forward it or every request 500s.
    lifespan = getattr(inner, "lifespan", None)
    if token:
        from starlette.middleware import Middleware

        return Starlette(
            middleware=[Middleware(_BearerAuthMiddleware, token=token)],
            routes=routes,
            lifespan=lifespan,
        )
    return Starlette(routes=routes, lifespan=lifespan)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AgentDrift MCP server")
    parser.add_argument(
        "--transport", choices=["stdio", "http", "sse"], default="stdio"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8931)
    parser.add_argument(
        "--token", default=None, help="Bearer token (or AGENTDRIFT_MCP_TOKEN)"
    )
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Serve HTTP/SSE without a token (local dev only)",
    )
    args = parser.parse_args(argv)

    if args.transport == "stdio":
        # Warm the store handle in the background so the first tool call is
        # already fast — without delaying stdio startup by a millisecond.
        from agentdrift.storage.factory import get_store as _get_store

        _prewarm_in_background(_get_store)
        mcp.run(transport="stdio")
        return

    token = resolve_token(args.token)
    if not token and not args.allow_unauthenticated:
        parser.error(
            "remote transports need --token (or AGENTDRIFT_MCP_TOKEN), "
            "or pass --allow-unauthenticated for local dev"
        )
    if not token:
        log.warning(
            "serving %s WITHOUT authentication (local dev only)", args.transport
        )
    import uvicorn  # lazy: stdio clients never pay this import

    from agentdrift.storage.factory import get_store as _get_store

    _prewarm_in_background(_get_store)
    app = _http_app(mcp, args.transport, token)
    log.info(
        "agentdrift-mcp serving %s on %s:%d (auth=%s)",
        args.transport,
        args.host,
        args.port,
        "token" if token else "none",
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
