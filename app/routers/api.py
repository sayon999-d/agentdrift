"""Session + execution + detection routes.

Canonical paths (used by the Python port):
  POST /sessions   GET /sessions   GET /sessions/{id}   PATCH /sessions/{id}
  POST /executions (ingest + auto drift-detect)
  GET  /sessions/{id}/executions   GET /executions
  GET  /sessions/{id}/detections   GET /detections
  POST /detect   GET /stats

Dashboard-compat aliases (Next.js on :3000 historically called the Rust daemon):
  POST /api/sessions, GET /api/sessions, POST /api/ingest, GET /api/health, ...
are registered in app/main.py as thin aliases to the same handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import store
from app.config import get_settings
from app.drift import decide_drift
from app.schemas import (
    DetectRequest,
    DriftDetectionOut,
    ExecutionIngest,
    ExecutionOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
)

router = APIRouter()


# --- sessions ---
@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(body: SessionCreate):
    data = body.model_dump()
    try:
        row = await store.create_session(data)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return row


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(limit: int = Query(100, le=500), offset: int = 0):
    rows, _ = await store.list_sessions(limit, offset)
    return rows


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: str):
    row = await store.get_session(session_id)
    if not row:
        raise HTTPException(404, "session not found")
    return row


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def update_session(session_id: str, body: SessionUpdate):
    patch = {
        k: v for k, v in body.model_dump().items() if v is not None or k == "parent_session_id"
    }
    row = await store.update_session(session_id, patch)
    if not row:
        raise HTTPException(404, "session not found")
    return row


# --- executions ---
@router.post("/executions", status_code=201)
async def ingest_execution(body: ExecutionIngest):
    """Ingest one execution; auto-runs drift detection vs prior sequence.

    Returns {"execution": {...}, "detection": {...}|None}.
    """
    data = body.model_dump()
    try:
        exe, det = await store.ingest_execution(data)
    except KeyError:
        raise HTTPException(404, "session not found — create it via POST /sessions first")
    return {
        "execution": exe,
        "detection": det,
        "drifted": det is not None,
        "kind": (det["kind"] if det else "no_drift"),
    }


@router.get("/executions", response_model=list[ExecutionOut])
async def list_executions(
    session_id: str | None = None, limit: int = Query(200, le=1000), offset: int = 0
):
    rows, _ = await store.list_executions(session_id, limit, offset)
    return rows


@router.get("/sessions/{session_id}/executions", response_model=list[ExecutionOut])
async def list_session_executions(
    session_id: str, limit: int = Query(200, le=1000), offset: int = 0
):
    # mirror 404 semantics of Rust daemon: unknown session -> 404
    exists = await store.get_session(session_id)
    if not exists:
        raise HTTPException(404, "session not found")
    rows, _ = await store.list_executions(session_id, limit, offset)
    return rows


@router.get("/sessions/{session_id}/timeline")
async def session_timeline(session_id: str):
    """Dashboard convenience: executions + detections interleaved by sequence."""
    exists = await store.get_session(session_id)
    if not exists:
        raise HTTPException(404, "session not found")
    exes, _ = await store.list_executions(session_id, 1000, 0)
    dets, _ = await store.list_detections(session_id, 1000, 0)
    det_by_exe = {d["execution_id"]: d for d in dets}
    return {
        "session": exists,
        "executions": [{**e, "detection": det_by_exe.get(e["execution_id"])} for e in exes],
        "detections": dets,
    }


# --- detections ---
@router.get("/detections", response_model=list[DriftDetectionOut])
async def list_detections(
    session_id: str | None = None, limit: int = Query(200, le=1000), offset: int = 0
):
    rows, _ = await store.list_detections(session_id, limit, offset)
    return rows


@router.get("/sessions/{session_id}/detections", response_model=list[DriftDetectionOut])
async def list_session_detections(
    session_id: str, limit: int = Query(200, le=1000), offset: int = 0
):
    rows, _ = await store.list_detections(session_id, limit, offset)
    return rows


@router.post("/detect")
async def detect(body: DetectRequest):
    """Re-run drift decision for an execution vs its predecessor (read-only)."""
    threshold = body.threshold or get_settings().DRIFT_SIMILARITY_THRESHOLD
    exes, _ = await store.list_executions(body.session_id, 1000, 0)
    if not exes:
        raise HTTPException(404, "no executions for session")
    target = (
        next((e for e in exes if e["execution_id"] == body.execution_id), None)
        if body.execution_id
        else max(exes, key=lambda e: e["sequence"])
    )
    if not target:
        raise HTTPException(404, "execution not found")
    prior = next((e for e in exes if e["sequence"] < target["sequence"]), None)
    if prior:
        prior = max(
            [e for e in exes if e["sequence"] < target["sequence"]], key=lambda e: e["sequence"]
        )
    decision = decide_drift(prior=prior, current=target, threshold=threshold)
    decision.pop("embedding", None)
    kinds = body.kinds
    if kinds and decision["kind"] not in kinds and decision["kind"] != "no_drift":
        decision["kind"] = "no_drift"
        decision["evidence"] = {"reason": "filtered by kinds", **decision["evidence"]}
    return {
        "session_id": body.session_id,
        "execution_id": target["execution_id"],
        "prior_execution_id": prior["execution_id"] if prior else None,
        **decision,
    }


@router.get("/stats")
async def stats():
    return await store.stats()
