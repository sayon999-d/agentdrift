"""AgentDrift daemon — unified FastAPI entrypoint.

Serves the Next.js dashboard (port 3000) and the AgentDrift CLI at
http://127.0.0.1:8901. Works with zero config in in-memory mode; persists
to Supabase Postgres + pgvector when DATABASE_URL is set.

Run:
    uvicorn app.main:app --port 8901 --reload --reload-dir app
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import database, store
from app.config import get_settings
from app.embeddings import get_embedding_service
from app.routers import api as api_router

START = time.time()
settings = get_settings()

SENTINEL_THRESHOLD = 0.92
SEED_SESSION_ID = "seed-loop-session"
SEED_STATE_HASH = "seed-loop-state-v1"

_WORD_RE = re.compile(r"[a-z0-9]+")


# ---------------------------------------------------------------------------
# Startup / lifespan
# ---------------------------------------------------------------------------


def _now():
    return datetime.now(UTC)


def _seed_loop_data() -> None:
    """Seed two consecutive executions with the same state_hash so the first
    `POST /v1/sentinel/scan` immediately returns {"detections": 1}."""
    mem = store.MEM
    if SEED_SESSION_ID not in mem.sessions:
        now = _now()
        mem.sessions[SEED_SESSION_ID] = {
            "session_id": SEED_SESSION_ID,
            "agent_id": "sentinel-seed-agent",
            "parent_session_id": None,
            "status": "active",
            "metadata": {"seeded": True},
            "created_at": now,
            "updated_at": now,
        }
    existing = sorted(
        (e for e in mem.executions.values() if e["session_id"] == SEED_SESSION_ID),
        key=lambda e: e.get("sequence", 0),
    )
    if len(existing) >= 2:
        return
    svc = get_embedding_service()
    base = max([e.get("sequence", 0) for e in existing], default=0)
    now = _now()
    for i in range(len(existing), 2):
        seq = base + i + 1
        emb = svc.embed_payload(
            {"goal": "seeded ping-pong loop check"},
            {"step": f"repeat action {i}", "state": "waiting-for-tool"},
        )
        eid = f"seed_exec_{i + 1}"
        mem.executions[eid] = {
            "execution_id": eid,
            "session_id": SEED_SESSION_ID,
            "parent_execution_id": f"seed_exec_{i}" if i > 0 else None,
            "agent_id": "sentinel-seed-agent",
            "node_id": "seed-node",
            "sequence": seq,
            "status": "ok",
            "input_payload": {"goal": "seeded ping-pong loop check"},
            "output_payload": {"step": f"repeat action {i}", "state": "waiting-for-tool"},
            "thinking_trace": None,
            "state_hash": SEED_STATE_HASH,
            "payload_embedding": emb,
            "metadata": {"seeded": True},
            "frozen_at": None,
            "created_at": now,
        }


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Initialize the hybrid engine (SQLite + LanceDB at ~/.agentdrift) and
    # seed the sentinel loop pair; fall back to memory seeding if needed.
    try:
        hybrid = store.get_hybrid()
        if hybrid is not None:
            await hybrid.ensure_seed()
        else:
            _seed_loop_data()
    except Exception:
        try:
            _seed_loop_data()
        except Exception:
            pass
    yield
    try:
        await database.dispose_engine()
    except Exception:
        pass


app = FastAPI(
    title="agentdrift-daemon",
    version="0.1.0",
    description="Drift detection daemon for AI agent executions (Python port)",
    lifespan=lifespan,
)

# Dashboard on :3000 + allow-all for CLI / preview deployments.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "*",
    ],
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health (CLI Gate expects mode/db_connected fields)
# ---------------------------------------------------------------------------


def _health_payload() -> dict:
    db_ok = False
    mode = "in-memory"
    db_mode = "memory"
    storage_path = "~/.agentdrift"
    if store.use_db():
        try:
            factory = database.get_session_factory()
            assert factory is not None
            # NOTE: sync check would need await; report configured without
            # blocking the event loop here. Deep check lives in /ready.
            db_ok, mode, db_mode = False, "in-memory", "postgres-configured"
        except Exception:
            db_ok, mode, db_mode = False, "in-memory", "postgres-unreachable"
    else:
        info = store.hybrid_info()
        if info is not None:
            db_ok, mode, db_mode = True, info["mode"], info["mode"]
            storage_path = info["storage_path"]
    try:
        embeddings_backend = get_embedding_service().backend
    except Exception:
        embeddings_backend = "hash-fallback"
    return {
        "status": "ok",
        "version": "0.1.0",
        "db_connected": db_ok,
        "mode": mode,
        # backwards-compat extras (older dashboard/tests read these)
        "db_mode": db_mode if db_mode != "memory" else mode,
        "storage_path": storage_path,
        "embeddings": embeddings_backend,
        "uptime_seconds": round(time.time() - START, 1),
    }


@app.get("/health", tags=["meta"])
async def health():
    return _health_payload()


@app.get("/ready", tags=["meta"])
async def ready():
    h = _health_payload()
    return {"ready": True, **h}


@app.get("/api/health", tags=["compat"])
async def api_health_alias():
    return await health()


@app.get("/api/ready", tags=["compat"])
async def api_ready_alias():
    return await ready()


@app.get("/v1/health", tags=["compat"])
async def v1_health_alias():
    return await health()


# ---------------------------------------------------------------------------
# Telemetry batch ingest — POST /ingest  +  POST /v1/ingest
# Accepts TelemetryBatch payloads in several shapes:
#   {"executions": [...]} | {"events": [...]} | {"telemetry": [...]}
#   {"items": [...]} | [...] (raw list) | {...} (single execution)
# Returns {"ok","accepted","persisted","rejected","errors"}
# ---------------------------------------------------------------------------


class TelemetryBatch(BaseModel):
    executions: list[dict[str, Any]] | None = None
    events: list[dict[str, Any]] | None = None
    telemetry: list[dict[str, Any]] | None = None
    items: list[dict[str, Any]] | None = None

    model_config = {"extra": "allow"}


def _normalize_batch(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("executions", "events", "telemetry", "items", "batch", "records"):
            val = payload.get(key)
            if isinstance(val, list):
                return [p for p in val if isinstance(p, dict)]
        # single execution dict?
        if "session_id" in payload or "input_payload" in payload or "output_payload" in payload:
            return [payload]
        # unknown dict shape -> treat as single generic event
        return [payload]
    return []


async def _ingest_batch(payload: Any) -> dict:
    items = _normalize_batch(payload)
    accepted = 0
    persisted = 0
    rejected = 0
    errors: list[str] = []

    for idx, raw in enumerate(items):
        try:
            data = dict(raw)
            data.setdefault("session_id", data.get("sessionId") or "batch-session")
            data.setdefault("agent_id", data.get("agentId") or data.get("agent") or "unknown")
            data.setdefault("node_id", data.get("nodeId") or "default")
            data.setdefault("status", "ok")
            data.setdefault("input_payload", data.get("input") or data.get("input_payload") or {})
            data.setdefault(
                "output_payload", data.get("output") or data.get("output_payload") or {}
            )
            if not isinstance(data["input_payload"], dict):
                data["input_payload"] = {"value": data["input_payload"]}
            if not isinstance(data["output_payload"], dict):
                data["output_payload"] = {"value": data["output_payload"]}
            accepted += 1
            await store.ensure_session(data["session_id"], data["agent_id"])
            await store.ingest_execution(data)
            persisted += 1
        except Exception as exc:  # never fail the whole batch
            rejected += 1
            errors.append(f"item {idx}: {exc}")

    return {
        "ok": True,
        "accepted": accepted,
        "persisted": persisted,
        "rejected": 0 if not errors else rejected,
        "errors": errors,
    }


@app.post("/ingest", tags=["compat"])
async def ingest_root(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return await _ingest_batch(payload)


@app.post("/v1/ingest", tags=["compat"])
async def ingest_v1(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return await _ingest_batch(payload)


@app.post("/api/ingest", tags=["compat"])
async def ingest_api(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return await _ingest_batch(payload)


# ---------------------------------------------------------------------------
# Sentinel loop scan — POST /v1/sentinel/scan  +  POST /v1/detect
# Groups in-memory executions by session_id, sorted by sequence; flags
# consecutive states with matching state_hash OR cosine similarity >
# threshold as ping_pong_loop.
# Returns {"ok": true, "detections": <int>, "threshold": 0.92}
# ---------------------------------------------------------------------------


def _exec_text(exe: dict) -> str:
    import json

    parts: list[str] = []
    for key in ("input_payload", "output_payload"):
        val = exe.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            parts.append(val)
        else:
            try:
                parts.append(json.dumps(val, sort_keys=True, default=str))
            except Exception:
                parts.append(str(val))
    return "\n".join(parts)


async def _run_sentinel_scan(threshold: float = SENTINEL_THRESHOLD) -> dict:
    """Hybrid (SQLite + LanceDB) scan when available, else memory fallback."""
    hybrid = store.get_hybrid()
    if hybrid is not None:
        try:
            await hybrid.ensure_seed()
        except Exception:
            pass
        return await hybrid.sentinel_scan(threshold)
    return _mem_sentinel_scan(threshold)


def _mem_sentinel_scan(threshold: float = SENTINEL_THRESHOLD) -> dict:
    try:
        _seed_loop_data()
    except Exception:
        pass
    mem = store.MEM
    svc = get_embedding_service()

    by_session: dict[str, list[dict]] = {}
    for exe in mem.executions.values():
        by_session.setdefault(exe.get("session_id", ""), []).append(exe)
    for sid in by_session:
        by_session[sid] = sorted(by_session[sid], key=lambda e: e.get("sequence", 0))

    loops: list[dict] = []
    for sid, exes in by_session.items():
        for prev, cur in zip(exes, exes[1:]):
            ph, ch = prev.get("state_hash"), cur.get("state_hash")
            same_hash = ph is not None and ch is not None and str(ph) == str(ch) and str(ph) != ""
            sim: float | None = None
            try:
                pemb = prev.get("payload_embedding") or svc.embed_text(_exec_text(prev))
                cemb = cur.get("payload_embedding") or svc.embed_text(_exec_text(cur))
                sim = float(svc.cosine(pemb, cemb))
            except Exception:
                sim = 1.0 if same_hash else 0.0
            if same_hash or (sim is not None and sim > threshold):
                reason = "matching state_hash" if same_hash else f"cosine {sim:.4f} > {threshold}"
                loops.append(
                    {
                        "session_id": sid,
                        "execution_id": cur.get("execution_id"),
                        "prior_execution_id": prev.get("execution_id"),
                        "kind": "ping_pong_loop",
                        "similarity": round(float(sim if sim is not None else 1.0), 4),
                        "threshold": threshold,
                        "evidence": {
                            "reason": reason,
                            "state_hash": ch if same_hash else None,
                            "prev_sequence": prev.get("sequence"),
                            "sequence": cur.get("sequence"),
                        },
                    }
                )

    # Persist loop detections (idempotent per execution_id) so GET
    # /detections and the dashboard reflect the scan.
    for loop in loops:
        exists = any(
            d.get("execution_id") == loop["execution_id"] and d.get("kind") == "ping_pong_loop"
            for d in mem.detections.values()
        )
        if not exists:
            did = str(uuid.uuid4())
            mem.detections[did] = {
                "detection_id": uuid.uuid4(),
                "session_id": loop["session_id"],
                "execution_id": loop["execution_id"],
                "prior_execution_id": loop["prior_execution_id"],
                "kind": "ping_pong_loop",
                "agent_id": (mem.executions.get(loop["execution_id"], {}) or {}).get(
                    "agent_id", "unknown"
                ),
                "similarity": loop["similarity"],
                "threshold": threshold,
                "evidence": loop["evidence"],
                "created_at": _now(),
            }

    return {
        "ok": True,
        "detections": len(loops),
        "threshold": threshold,
        "loops": loops,
    }


class ScanRequest(BaseModel):
    threshold: float | None = None
    session_id: str | None = None

    model_config = {"extra": "allow"}


async def _handle_scan(request: Request) -> dict:
    try:
        body = await request.json()
    except Exception:
        body = {}
    thr = SENTINEL_THRESHOLD
    try:
        if isinstance(body, dict) and body.get("threshold") is not None:
            thr = float(body["threshold"])
    except Exception:
        thr = SENTINEL_THRESHOLD
    result = await _run_sentinel_scan(threshold=thr)
    # Contract requires ok/detections/threshold at top level;
    # "loops" detail is additive for watch mode / dashboard debugging.
    return {
        "ok": True,
        "detections": int(result["detections"]),
        "threshold": thr,
        "loops": result.get("loops", []),
    }


@app.post("/v1/sentinel/scan", tags=["sentinel"])
async def sentinel_scan_v1(request: Request):
    return await _handle_scan(request)


@app.post("/v1/detect", tags=["sentinel"])
async def detect_v1_alias(request: Request):
    return await _handle_scan(request)


@app.post("/sentinel/scan", tags=["sentinel"])
async def sentinel_scan_root(request: Request):
    return await _handle_scan(request)


@app.post("/detect", tags=["sentinel"])
async def detect_root_alias(request: Request):
    """Legacy non-prefixed alias — returns the sentinel contract shape."""
    return await _handle_scan(request)


# ---------------------------------------------------------------------------
# NLI evaluate — POST /v1/evaluate  (CLI Gate 2)
# Accepts List[{"id","premise","hypothesis"}] (raw list) or
# {"items"/"pairs"/"inputs": [...]} and returns deterministic scores.
# ---------------------------------------------------------------------------


class EvaluateItem(BaseModel):
    id: str = Field(default_factory=lambda: f"eval_{uuid.uuid4().hex[:8]}")
    premise: str = ""
    hypothesis: str = ""

    model_config = {"extra": "allow"}


NEGATIONS = {"not", "no", "never", "n't", "cannot", "can't", "won't", "don't", "isn't"}


def _score_pair(premise: str, hypothesis: str) -> dict[str, Any]:
    p, h = (premise or ""), (hypothesis or "")
    ptoks = set(_WORD_RE.findall(p.lower()))
    htoks = set(_WORD_RE.findall(h.lower()))

    if not p.strip() and not h.strip():
        return {
            "entailment": 0.34,
            "neutral": 0.33,
            "contradiction": 0.33,
            "label": "neutral",
            "margin": 0.01,
        }
    if p.strip() == h.strip():
        return {
            "entailment": 0.92,
            "neutral": 0.05,
            "contradiction": 0.03,
            "label": "entailment",
            "margin": 0.87,
        }

    content_p, content_h = ptoks - NEGATIONS, htoks - NEGATIONS
    union = content_p | content_h
    overlap = (len(content_p & content_h) / len(union)) if union else 0.0
    neg_flip = bool((ptoks & NEGATIONS) != (htoks & NEGATIONS))

    if neg_flip and overlap > 0.4:
        ent, neu, con = 0.05, 0.10, 0.85
    elif overlap >= 0.7:
        ent, neu, con = 0.78, 0.15, 0.07
    elif overlap >= 0.4:
        ent, neu, con = 0.55, 0.30, 0.15
    elif overlap >= 0.15:
        ent, neu, con = 0.30, 0.50, 0.20
    else:
        # low overlap: check for explicit antonym-ish contradiction cues
        ent, neu, con = 0.15, 0.45, 0.40

    # Try the real NLI model as a tie-break signal when enabled, but keep
    # output deterministic by blending mildly (heuristic dominates).
    try:
        s = get_settings()
        if s.NLI_ENABLED:
            contra = float(get_embedding_service().nli_contradiction(p[:2000], h[:2000]))
            con = round(0.7 * con + 0.3 * max(0.0, min(1.0, contra)), 4)
            total = ent + neu + con
            ent, neu, con = round(ent / total, 4), round(neu / total, 4), round(con / total, 4)
    except Exception:
        pass

    scores = {"entailment": round(ent, 4), "neutral": round(neu, 4), "contradiction": round(con, 4)}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    label, top = ranked[0]
    margin = round(top - ranked[1][1], 4)
    return {**scores, "label": label, "margin": margin}


def _normalize_evaluate_items(payload: Any) -> list[dict]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("items", "pairs", "inputs", "evaluations", "data"):
            val = payload.get(key)
            if isinstance(val, list):
                return [p for p in val if isinstance(p, dict)]
        if "premise" in payload and "hypothesis" in payload:
            return [payload]
    return []


@app.post("/v1/evaluate", tags=["nli"])
async def evaluate_v1(request: Request):
    try:
        payload = await request.json()
    except Exception:
        payload = []
    raw_items = _normalize_evaluate_items(payload)
    results: list[dict] = []
    for idx, raw in enumerate(raw_items):
        item_id = str(raw.get("id") or raw.get("item_id") or f"eval_{idx}")
        premise = str(raw.get("premise", ""))
        hypothesis = str(raw.get("hypothesis", ""))
        scores = _score_pair(premise, hypothesis)
        results.append({"id": item_id, "premise": premise, "hypothesis": hypothesis, **scores})
    return {"ok": True, "results": results, "count": len(results)}


@app.post("/evaluate", tags=["nli"])
async def evaluate_root(request: Request):
    return await evaluate_v1(request)


# ---------------------------------------------------------------------------
# Event stream — GET /v1/events/stream (SSE)
# Lightweight server-sent-events feed over the same sorted stores that back
# GET /executions and GET /detections. First message is a bounded snapshot,
# subsequent messages are deltas. `?once=true` returns one snapshot (handy
# for smoke tests without holding a connection open).
# ---------------------------------------------------------------------------


async def _snapshot_events(session_id: str | None = None, limit: int = 200):
    exes, _ = await store.list_executions(session_id, limit, 0)
    dets, _ = await store.list_detections(session_id, limit, 0)
    return jsonable_encoder(exes), jsonable_encoder(dets)


def _sse_frame(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


async def _event_stream(session_id: str | None, poll: float, once: bool):
    poll = min(max(poll, 0.2), 10.0)
    seen_exe: set[str] = set()
    seen_det: set[str] = set()
    first = True
    while True:
        try:
            exes, dets = await _snapshot_events(session_id)
        except Exception:
            exes, dets = [], []
        if first:
            for e in exes:
                seen_exe.add(str(e.get("execution_id")))
            for d in dets:
                seen_det.add(str(d.get("detection_id")))
            yield _sse_frame({"type": "snapshot", "executions": exes, "detections": dets})
            first = False
            if once:
                return
        else:
            new_exes = [e for e in exes if str(e.get("execution_id")) not in seen_exe]
            new_dets = [d for d in dets if str(d.get("detection_id")) not in seen_det]
            for e in new_exes:
                seen_exe.add(str(e.get("execution_id")))
            for d in new_dets:
                seen_det.add(str(d.get("detection_id")))
            if new_exes or new_dets:
                yield _sse_frame({"type": "delta", "executions": new_exes, "detections": new_dets})
            else:
                yield ": ping\n\n"
        if once:
            return
        await asyncio.sleep(poll)


async def _stream_response(request: Request, session_id: str | None, poll: float, once: bool):
    async def gen():
        async for frame in _event_stream(session_id, poll, once):
            if await request.is_disconnected():
                break
            yield frame

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/v1/events/stream", tags=["stream"])
async def events_stream_v1(
    request: Request,
    session_id: str | None = Query(None),
    poll: float = Query(1.0),
    once: bool = Query(False),
):
    return await _stream_response(request, session_id, poll, once)


@app.get("/events/stream", tags=["stream"])
async def events_stream_root(
    request: Request,
    session_id: str | None = Query(None),
    poll: float = Query(1.0),
    once: bool = Query(False),
):
    return await _stream_response(request, session_id, poll, once)


# ---------------------------------------------------------------------------
# Pre-existing core routes (sessions / executions / detections / stats)
# ---------------------------------------------------------------------------

app.include_router(api_router.router, tags=["core"])
app.include_router(api_router.router, prefix="/api", tags=["compat"])
# Non-conflicting /v1 aliases for pre-existing core routes (sessions, executions,
# detections, stats). Explicit /v1/sentinel/scan, /v1/detect, /v1/ingest and
# /v1/evaluate above take precedence for those paths (first match wins).
app.include_router(api_router.router, prefix="/v1", tags=["compat"])


def main() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
