"""Coverage for watch-mode daemon contracts (poll + SSE + scan detail)."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    # Enter lifespan so startup seeding runs on every Starlette version.
    with TestClient(app) as c:
        yield c


def test_executions_sorted_by_sequence(client):
    r = client.get("/v1/executions?limit=50")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 2
    seqs = [row["sequence"] for row in rows]
    assert seqs == sorted(seqs)


def test_detections_list(client):
    r = client.get("/v1/detections?limit=50")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_scan_includes_loops(client):
    r = client.post("/v1/sentinel/scan", json={"threshold": 0.92})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["detections"] >= 1
    assert body["threshold"] == 0.92
    assert isinstance(body.get("loops"), list) and body["loops"]
    loop = body["loops"][0]
    assert loop["kind"] == "ping_pong_loop"
    assert {"session_id", "execution_id", "prior_execution_id", "similarity"} <= set(loop)


def test_detect_alias_matches_scan(client):
    a = client.post("/v1/sentinel/scan", json={}).json()
    b = client.post("/v1/detect", json={}).json()
    assert a["detections"] == b["detections"] and b["ok"] is True


def test_sse_snapshot_once(client):
    r = client.get("/v1/events/stream?once=true")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert "data:" in r.text and '"snapshot"' in r.text
