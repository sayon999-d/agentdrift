"""AgentDrift Cloud MCP server — Supabase Postgres + pgvector backend.

Production remote MCP server (Streamable HTTP / SSE) with per-user sandboxing
via Supabase Auth. Every trace and drift scan is scoped to the ``user_id``
extracted from the caller's Supabase JWT (``sub`` claim).

Run:
  python -m agentdrift.mcp.cloud_server --transport sse --port 8000
  python -m agentdrift.mcp.cloud_server --transport streamable-http --port 8000
Serve behind uvicorn:
  uvicorn agentdrift.mcp.cloud_server:app --host 0.0.0.0 --port 8000

Required env:
  SUPABASE_DATABASE_URL (or AGENTDRIFT_DATABASE_URL)  direct Postgres URL (5432)
  SUPABASE_JWT_SECRET      Auth JWT signing secret (HS256 verification)
Optional env:
  AGENTDRIFT_MCP_TOKEN / MCP_TOKEN / SUPABASE_SERVICE_ROLE_KEY
      server-to-server API tokens (service identity, unscoped server override)
  AGENTDRIFT_REQUIRE_AUTH=1  reject unauthenticated requests with 401 (default
      when a JWT secret or API token is configured, else off for local dev)
  AGENTDRIFT_EMBED_MODEL (default: all-MiniLM-L6-v2), AGENTDRIFT_EMBED_DIM (384)

Latency design mirrors ``mcp_server.py``: NOTHING heavy (torch /
sentence_transformers / asyncpg pool / model weights) is touched at import.
Embeddings load lazily and always encode inside ``asyncio.to_thread`` so the
MCP event loop is never blocked; a pure-stdlib hash fallback keeps the server
functional offline.
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
import uuid
from contextvars import ContextVar
from typing import Any

log = logging.getLogger("agentdrift.cloud_mcp")


try:
    # Official MCP Python SDK v2.x
    from mcp.server.mcpserver import MCPServer as FastMCP
except (ImportError, ModuleNotFoundError):
    try:
        # Standalone fastmcp package or official MCP v1.x fallback
        from fastmcp import FastMCP
    except (ImportError, ModuleNotFoundError):
        from mcp.server.fastmcp import FastMCP

# NOTE: torch / sentence_transformers / asyncpg must NEVER be imported here.
# They are imported lazily inside worker functions only.

EMBEDDING_DIM = int(os.getenv("AGENTDRIFT_EMBED_DIM", "384") or 384)
EMBED_MODEL = os.getenv("AGENTDRIFT_EMBED_MODEL", "all-MiniLM-L6-v2")
_WORD_RE = re.compile(r"[a-z0-9]+")

# Request-scoped identity set by the auth middleware, read by tools.
# (service identity, unscoped) vs (user uuid, strictly sandboxed).
current_identity: ContextVar[dict[str, Any]] = ContextVar(
    "agentdrift_cloud_identity", default={"user_id": None, "service": False}
)


# ---------------------------------------------------------------------------
# Auth: Supabase JWT (HS256) or server API token
# ---------------------------------------------------------------------------

def _jwt_secret() -> str | None:
    return os.getenv("SUPABASE_JWT_SECRET", "").strip() or None


def _api_tokens() -> set[str]:
    toks = set()
    for env in ("AGENTDRIFT_MCP_TOKEN", "MCP_TOKEN", "SUPABASE_SERVICE_ROLE_KEY"):
        val = os.getenv(env, "").strip()
        if val:
            toks.add(val)
    return toks


def _verify_supabase_jwt(token: str) -> str | None:
    """Return the ``sub`` user id when ``token`` is a valid Supabase JWT."""
    secret = _jwt_secret()
    if not secret:
        return None
    try:
        import jwt  # PyJWT; lazy so cloud boot never depends on it
    except ImportError:
        log.warning("PyJWT unavailable: cannot verify Supabase JWTs")
        return None
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"],
            audience="authenticated", leeway=30,
            options={"require": ["exp", "sub"]},
        )
    except Exception:
        # Some projects issue tokens without an `aud` claim — retry aud-less
        # rather than locking legitimate users out.
        try:
            claims = jwt.decode(
                token, secret, algorithms=["HS256"], leeway=30,
                options={"require": ["exp", "sub"]},
            )
        except Exception as exc:
            log.debug("JWT verification failed: %s", exc)
            return None
    sub = claims.get("sub")
    if not sub:
        return None
    try:
        return str(uuid.UUID(str(sub)))
    except (ValueError, TypeError, AttributeError):
        return None


def resolve_identity(authorization: str = "") -> dict[str, Any]:
    """Map an ``Authorization`` header to ``{user_id, service}``.

    - ``Bearer <supabase jwt>`` -> {"user_id": <sub>, "service": False}
    - ``Bearer <api token>``     -> {"user_id": None, "service": True}
    - missing/invalid            -> {"user_id": None, "service": False}
    """
    presented = (authorization or "").strip()
    if presented.lower().startswith("bearer "):
        presented = presented[len("Bearer "):].strip()
    if not presented:
        return {"user_id": None, "service": False}
    user_id = _verify_supabase_jwt(presented)
    if user_id:
        return {"user_id": user_id, "service": False}
    for candidate in _api_tokens():
        if secrets.compare_digest(presented, candidate):
            return {"user_id": None, "service": True}
    return {"user_id": None, "service": False}


def _require_auth() -> bool:
    explicit = os.getenv("AGENTDRIFT_REQUIRE_AUTH", "").strip().lower()
    if explicit in ("1", "true", "yes"):
        return True
    if explicit in ("0", "false", "no"):
        return False
    return bool(_jwt_secret() or _api_tokens())  # secure by default in cloud


class _CloudAuthMiddleware:
    """Starlette middleware: verify Bearer, stash identity, enforce /health."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode().lower(): v.decode()
            for k, v in scope.get("headers", [])
        }
        identity = resolve_identity(headers.get("authorization", ""))
        if not identity["service"] and identity["user_id"] is None:
            if _require_auth():
                body = b'{"detail":"missing or invalid bearer token"}'
                await send({
                    "type": "http.response.start", "status": 401,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                    ],
                })
                await send({"type": "http.response.body", "body": body})
                return
        token = current_identity.set(identity)
        try:
            await self.app(scope, receive, send)
        finally:
            current_identity.reset(token)


# ---------------------------------------------------------------------------
# Supabase connection pool (asyncpg, direct 5432, lazy singleton)
# ---------------------------------------------------------------------------

_pool = None
_pool_lock: asyncio.Lock | None = None
# Probed once per process so the server works against BOTH the Phase-1 schema
# (002_supabase_mcp.sql: `embedding`, no user_id) and the cloud schema
# (002_cloud_mcp_supabase.sql: `payload_embedding` + user_id).
_schema = {"emb_col": "payload_embedding", "has_user_id": True}


def resolve_database_url(url: str | None = None) -> str | None:
    raw = (
        url
        or os.getenv("SUPABASE_DATABASE_URL", "").strip()
        or os.getenv("AGENTDRIFT_DATABASE_URL", "").strip()
        or None
    )
    if raw and raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw[len("postgresql+asyncpg://"):]
    return raw


async def get_pool():
    """Return the shared asyncpg pool (created on first tool call)."""
    global _pool, _pool_lock
    if _pool is not None:
        return _pool
    if _pool_lock is None:
        _pool_lock = asyncio.Lock()
    async with _pool_lock:
        if _pool is not None:
            return _pool
        try:
            import asyncpg
            from pgvector.asyncpg import register_vector
        except ImportError as exc:
            raise RuntimeError(
                "cloud server needs the 'asyncpg' and 'pgvector' packages"
            ) from exc
        dsn = resolve_database_url()
        if not dsn:
            raise RuntimeError(
                "cloud server needs SUPABASE_DATABASE_URL "
                "(or AGENTDRIFT_DATABASE_URL)"
            )

        async def _init(conn):
            await register_vector(conn)

        _pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10, init=_init)
        await _probe_schema(_pool)
        if _require_auth() and not _schema["has_user_id"]:
            await _pool.close()
            _pool = None
            raise RuntimeError(
                "authenticated cloud MCP requires the multi-tenant schema; "
                "apply migrations/002_cloud_mcp_supabase.sql"
            )
        return _pool


async def _probe_schema(pool) -> None:
    """Detect embedding column + user_id support (Phase-1 vs cloud schema)."""
    try:
        async with pool.acquire() as conn:
            cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'agent_executions'"
                )
            }
            if "payload_embedding" in cols:
                _schema["emb_col"] = "payload_embedding"
            elif "embedding" in cols:
                _schema["emb_col"] = "embedding"
            session_cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'agent_sessions'"
                )
            }
            detection_cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'drift_detections'"
                )
            }
            _schema["has_user_id"] = all(
                "user_id" in table_cols
                for table_cols in (session_cols, cols, detection_cols)
            )
    except Exception as exc:
        _schema["has_user_id"] = False
        log.warning("schema probe failed; tenant-safe schema is unverified: %s", exc)


def _emb_col() -> str:
    col = _schema["emb_col"]
    if col not in ("payload_embedding", "embedding"):  # never inject unchecked SQL
        return "payload_embedding"
    return col


# ---------------------------------------------------------------------------
# Embeddings: lazy transformer in worker thread, hash fallback
# ---------------------------------------------------------------------------

_model_lock = threading.Lock()
_dense_model: Any = None
_dense_model_tried = False


def _get_dense_model() -> Any | None:
    global _dense_model, _dense_model_tried
    with _model_lock:
        if _dense_model_tried:
            return _dense_model
        _dense_model_tried = True
    try:
        from sentence_transformers import SentenceTransformer  # lazy!

        model = SentenceTransformer(EMBED_MODEL)
        with _model_lock:
            _dense_model = model
        log.info("Loaded cloud embedding model %s", EMBED_MODEL)
        return model
    except Exception as exc:
        log.warning("Dense model unavailable, hash fallback: %s", exc)
        return None


def hash_embed(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Pure-stdlib SHA-256 hashing-trick embedding (<10ms, offline-safe)."""
    vec = [0.0] * dim
    for token in _WORD_RE.findall((text or "").lower()):
        h = int(hashlib.sha256(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        vec[(h >> 16) % dim] += 0.5
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-12:
        return vec
    return [v / norm for v in vec]


async def embed_text_async(text: str) -> list[float]:
    """384-d embedding without blocking the MCP event loop."""
    text = (text or "")[:8000]

    def _encode() -> list[float]:
        model = _get_dense_model()
        if model is not None:
            try:
                vec = model.encode([text], normalize_embeddings=True)[0]
                return [float(x) for x in vec[:EMBEDDING_DIM]]
            except Exception as exc:
                log.warning("dense encode failed, hash fallback: %s", exc)
        return hash_embed(text)

    return await asyncio.to_thread(_encode)


def state_hash_of(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload or {}, sort_keys=True, default=str).encode()
    ).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Multi-tenant DB helpers (every query scoped to the caller's user_id)
# ---------------------------------------------------------------------------

def _identity() -> dict[str, Any]:
    return current_identity.get()


def _user_where(user_id: str | None, start: int = 1) -> tuple[str, list]:
    """SQL fragment + params scoping a query to one user (or no-op)."""
    if user_id and _schema["has_user_id"]:
        return f" AND user_id = ${start}", [uuid.UUID(user_id)]
    return "", []


async def _ensure_session(conn, session_id: str, agent_id: str, user_id: str | None):
    if _schema["has_user_id"]:
        await conn.execute(
            "INSERT INTO agent_sessions(session_id, user_id, agent_id)"
            " VALUES($1, $2, $3) ON CONFLICT(session_id) DO NOTHING",
            session_id, uuid.UUID(user_id) if user_id else None,
            agent_id or "unknown",
        )
        # session_id is globally unique. Do not let a second tenant attach
        # executions to a session created by another user.
        owner = await conn.fetchval(
            "SELECT user_id FROM agent_sessions WHERE session_id = $1",
            session_id,
        )
        if str(owner) != str(user_id):
            raise PermissionError("session belongs to a different user")
    else:  # Phase-1 schema without user_id
        await conn.execute(
            "INSERT INTO agent_sessions(session_id, agent_id)"
            " VALUES($1, $2) ON CONFLICT(session_id) DO NOTHING",
            session_id, agent_id or "unknown",
        )


def _row_turn(row) -> dict[str, Any]:
    payload = row["payload"] if isinstance(row.get("payload"), dict) else {}
    if isinstance(row.get("payload"), str):
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            payload = {}
    return {
        "execution_id": str(row["execution_id"]),
        "session_id": row["session_id"],
        "agent_id": row["agent_id"],
        "node_id": row.get("node_id"),
        "sequence": row["sequence"],
        "payload": payload,
        "thinking": row.get("thinking"),
        "state_hash": row.get("state_hash"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


# ---------------------------------------------------------------------------
# FastMCP cloud server + the 3 core tools
# ---------------------------------------------------------------------------

def _normalize_list_output_schemas(mcp: Any) -> None:
    """Stamp ``x-fastmcp-wrap-result`` on wrapped list schemas (see mcp_server)."""
    tools = getattr(getattr(mcp, "_tool_manager", None), "_tools", None) or {}
    for tool in tools.values():
        schema = getattr(tool, "output_schema", None)
        if schema is None:
            schema = getattr(tool, "outputSchema", None)
        if not isinstance(schema, dict) or schema.get("x-fastmcp-wrap-result"):
            continue
        if list(schema.get("required", [])) == ["result"] and set(
            schema.get("properties", {})
        ) == {"result"}:
            try:
                schema["x-fastmcp-wrap-result"] = True
            except Exception:
                pass


def create_cloud_mcp():
    """Build the production Supabase-backed FastMCP server."""
    mcp = FastMCP("agentdrift-cloud")

    @mcp.tool()
    async def log_agent_turn(
        session_id: str,
        agent_id: str,
        node_id: str,
        payload: dict[str, Any],
        thinking: str = "",
    ) -> dict[str, Any]:
        """Log one agent turn: hash state, embed, persist, hash-match check."""
        ident = _identity()
        user_id = ident.get("user_id")
        if not ident["service"] and user_id is None and _require_auth():
            raise ValueError("unauthenticated: provide a Supabase JWT Bearer token")
        payload = dict(payload or {})
        state_hash = payload.pop("state_hash", None) or state_hash_of(payload)
        emb_text = json.dumps(payload, sort_keys=True, default=str)
        if thinking:
            emb_text += "\n" + thinking[:4000]
        vector = await embed_text_async(emb_text)
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await _ensure_session(conn, session_id, agent_id, user_id)
                user_frag, user_params = _user_where(user_id, start=2)
                seq = await conn.fetchval(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM agent_executions"
                    f" WHERE session_id = $1{user_frag}",
                    session_id, *user_params,
                )
                cols = ["session_id", "agent_id", "node_id", "sequence"]
                vals: list[Any] = [
                    session_id, agent_id or "unknown",
                    node_id or "default", seq,
                ]
                if _schema["has_user_id"] and user_id:
                    cols.append("user_id")
                    vals.append(user_id)
                cols += ["payload", "thinking", "state_hash", _emb_col()]
                vals += [
                    json.dumps(payload, default=str), thinking or None,
                    state_hash, vector,
                ]
                placeholders = ", ".join(f"${i}" for i in range(1, len(vals) + 1))
                row = await conn.fetchrow(
                    "INSERT INTO agent_executions(" + ", ".join(cols) + ")"
                    f" VALUES({placeholders})"
                    " RETURNING execution_id, session_id, agent_id, node_id,"
                    " sequence, payload, thinking, state_hash, created_at",
                    *vals,
                )
                prev_frag, prev_params = _user_where(user_id, start=3)
                prev = await conn.fetchrow(
                    "SELECT execution_id, state_hash, sequence FROM agent_executions"
                    f" WHERE session_id = $1{prev_frag}"
                    " AND sequence < $2 ORDER BY sequence DESC LIMIT 1",
                    session_id, seq, *prev_params,
                )
        turn = _row_turn(dict(row))
        loop = bool(
            prev and prev["state_hash"] and state_hash
            and str(prev["state_hash"]) == str(state_hash)
        )
        turn["loop_detected"] = loop
        turn["prior_execution_id"] = (
            str(prev["execution_id"]) if prev else None
        )
        if loop:
            turn["warning"] = (
                "Consecutive state hashes match: the agent is repeating the"
                " same state — stop and try a different action."
            )
        return turn

    @mcp.tool()
    async def check_drift_status(
        session_id: str, threshold: float = 0.92
    ) -> str:
        """Circuit breaker: pgvector cosine over consecutive turns.

        Returns a critical STOP warning string when similarity >= threshold
        or state hashes match; otherwise an OK summary string.
        """
        ident = _identity()
        user_id = ident.get("user_id")
        if not ident["service"] and user_id is None and _require_auth():
            return "ERROR: unauthenticated — provide a Supabase JWT Bearer token."
        pool = await get_pool()
        emb = _emb_col()
        async with pool.acquire() as conn:
            user_frag, user_params = _user_where(user_id)
            rows = await conn.fetch(
                "SELECT execution_id, agent_id, sequence, state_hash,"
                f" {emb} AS vec FROM agent_executions"
                f" WHERE session_id = $1{user_frag} ORDER BY sequence",
                session_id, *user_params,
            )
        if len(rows) < 2:
            return (
                f"OK: session '{session_id}' has {len(rows)} recorded turn(s); "
                "need at least 2 consecutive turns to assess drift."
            )
        for prev, cur in zip(rows, rows[1:]):
            ph, ch = prev["state_hash"], cur["state_hash"]
            same_hash = bool(ph and ch and str(ph) == str(ch))
            sim: float | None = None
            if cur["vec"] is not None and prev["vec"] is not None:
                pool2 = await get_pool()
                async with pool2.acquire() as conn:
                    try:
                        sim = await conn.fetchval(
                            f"SELECT 1.0 - ({emb} <=> $1) FROM agent_executions"
                            " WHERE execution_id = $2",
                            list(cur["vec"]), str(prev["execution_id"]),
                        )
                        sim = round(float(sim), 4) if sim is not None else None
                    except Exception as exc:
                        log.debug("pgvector cosine failed: %s", exc)
            if sim is None:
                sim = 1.0 if same_hash else 0.0
            if same_hash or sim >= threshold:
                reason = (
                    "matching state_hash" if same_hash
                    else f"cosine {sim:.4f} >= {threshold}"
                )
                pool3 = await get_pool()
                async with pool3.acquire() as conn:
                    async with conn.transaction():
                        exists = await conn.fetchval(
                            "SELECT 1 FROM drift_detections"
                            " WHERE execution_id = $1 AND kind = 'ping_pong_loop'",
                            str(cur["execution_id"]),
                        )
                        if not exists:
                            if _schema["has_user_id"]:
                                await conn.execute(
                                    "INSERT INTO drift_detections(session_id,"
                                    " execution_id, prior_execution_id, user_id,"
                                    " agent_id, kind, similarity, threshold, evidence)"
                                    " VALUES($1,$2,$3,$4,$5,'ping_pong_loop',$6,$7,$8)",
                                    session_id, str(cur["execution_id"]),
                                    str(prev["execution_id"]),
                                    uuid.UUID(user_id) if user_id else None,
                                    cur["agent_id"], sim, threshold,
                                    json.dumps({"reason": reason}),
                                )
                            else:
                                await conn.execute(
                                    "INSERT INTO drift_detections(session_id,"
                                    " execution_id, prior_execution_id,"
                                    " agent_id, kind, similarity, threshold, evidence)"
                                    " VALUES($1,$2,$3,$4,'ping_pong_loop',$5,$6,$7)",
                                    session_id, str(cur["execution_id"]),
                                    str(prev["execution_id"]),
                                    cur["agent_id"], sim, threshold,
                                    json.dumps({"reason": reason}),
                                )
                return (
                    "CRITICAL — LOOP CIRCUIT BREAKER TRIPPED. "
                    f"Session '{session_id}' turns #{prev['sequence']} -> "
                    f"#{cur['sequence']} are repeating ({reason}). "
                    "STOP repeating the same action immediately: backtrack, "
                    "re-read the latest tool output, and try a DIFFERENT "
                    "approach before your next turn."
                )
        return (
            f"OK: session '{session_id}' scanned {len(rows)} turns, "
            f"no consecutive pair exceeds threshold {threshold}."
        )

    @mcp.tool()
    async def get_session_trajectory(
        session_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Recent turns for context pruning (newest last, capped by limit)."""
        ident = _identity()
        user_id = ident.get("user_id")
        if not ident["service"] and user_id is None and _require_auth():
            raise ValueError("unauthenticated: provide a Supabase JWT Bearer token")
        pool = await get_pool()
        async with pool.acquire() as conn:
            user_frag, user_params = _user_where(user_id)
            rows = await conn.fetch(
                "SELECT execution_id, session_id, agent_id, node_id, sequence,"
                " payload, thinking, state_hash, created_at FROM agent_executions"
                f" WHERE session_id = $1{user_frag}"
                " ORDER BY sequence DESC LIMIT $2",
                session_id, *user_params, max(limit, 1),
            )
        turns = [_row_turn(dict(r)) for r in reversed(rows)]
        return turns

    _normalize_list_output_schemas(mcp)
    return mcp


mcp = create_cloud_mcp()


# ---------------------------------------------------------------------------
# ASGI app (uvicorn target) + CLI runner
# ---------------------------------------------------------------------------

def build_app(transport: str = "streamable-http", token: str | None = None):
    """Starlette app: /health (open) + MCP endpoint (Bearer-enforced)."""
    from starlette.applications import Starlette  # lazy: keeps import light
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    async def _health(_request):
        return JSONResponse({"status": "ok", "service": "agentdrift-cloud-mcp"})

    if hasattr(mcp, "http_app"):
        inner = mcp.http_app(path="/mcp", transport=transport)
    elif transport == "sse" and hasattr(mcp, "sse_app"):
        inner = mcp.sse_app()
    elif hasattr(mcp, "streamable_http_app"):
        inner = mcp.streamable_http_app()
    elif hasattr(mcp, "sse_app"):
        inner = mcp.sse_app()
    else:
        raise RuntimeError("Unsupported MCP server object: no app builder found")
    routes = [Route("/health", _health), Mount("/", app=inner)]
    lifespan = getattr(inner, "lifespan", None)
    # The cloud server ALWAYS enforces its own JWT/API-token middleware so
    # per-user sandboxing cannot be bypassed, even with --allow-unauthenticated.
    from starlette.middleware import Middleware

    extra = []
    if token:  # optional legacy static-token layer on top of JWT auth
        from mcp_server import _BearerAuthMiddleware

        extra.append(Middleware(_BearerAuthMiddleware, token=token))
    return Starlette(
        middleware=[Middleware(_CloudAuthMiddleware), *extra],
        routes=routes,
        lifespan=lifespan,
    )


# Default uvicorn target. Transport override via CLOUD_TRANSPORT=sse.
app = build_app(os.getenv("CLOUD_TRANSPORT", "streamable-http"))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AgentDrift Cloud MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http", "http"],
        default="streamable-http",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--token", default=None,
        help="Optional extra static Bearer token (JWT auth always enforced)",
    )
    parser.add_argument(
        "--allow-unauthenticated", action="store_true",
        help="Allow requests without any token (local dev only; JWT still "
             "checked when present)",
    )
    args = parser.parse_args(argv)
    transport = "streamable-http" if args.transport == "http" else args.transport

    if args.transport == "stdio":
        if not resolve_database_url():
            parser.error("stdio cloud mode needs SUPABASE_DATABASE_URL set")
        mcp.run(transport="stdio")
        return

    if _require_auth() and not args.allow_unauthenticated:
        log.info("cloud auth enforced (Supabase JWT / API token required)")
    import uvicorn  # lazy

    application = build_app(transport, args.token)
    log.info(
        "agentdrift-cloud-mcp serving %s on %s:%d", transport, args.host, args.port
    )
    uvicorn.run(application, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
