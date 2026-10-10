"""Smoke tests (memory backend — no DB required)."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body.get("mode", body.get("db_mode")) in (
        "in-memory",
        "memory",
        "postgres+pgvector",
        "postgres-unreachable",
        "postgres-configured",
        "hybrid (sqlite + lancedb)",
    )
    assert body.get("db_mode") in (
        "in-memory",
        "memory",
        "postgres+pgvector",
        "postgres-unreachable",
        "postgres-configured",
        "hybrid (sqlite + lancedb)",
    )


def test_session_execution_drift_flow():
    s = client.post("/sessions", json={"agent_id": "agent-1"}).json()
    sid = s["session_id"]

    e1 = client.post(
        "/executions",
        json={
            "session_id": sid,
            "agent_id": "agent-1",
            "node_id": "planner",
            "input_payload": {"goal": "book a flight to Paris"},
            "output_payload": {"plan": "search flights then book cheapest direct"},
        },
    ).json()
    assert e1["kind"] == "no_drift"

    e2 = client.post(
        "/executions",
        json={
            "session_id": sid,
            "agent_id": "agent-1",
            "node_id": "planner",
            "input_payload": {"goal": "book a flight to Paris"},
            "output_payload": {"plan": "order sushi and cancel all travel immediately"},
        },
    ).json()
    assert e2["drifted"] is True
    assert e2["kind"] in ("semantic_drift", "logical_drift", "schema_drift", "state_drift")

    dets = client.get(f"/sessions/{sid}/detections").json()
    assert len(dets) >= 1

    tl = client.get(f"/sessions/{sid}/timeline").json()
    assert len(tl["executions"]) == 2


def test_state_hash_drift():
    s = client.post("/sessions", json={"agent_id": "agent-2"}).json()
    sid = s["session_id"]
    client.post(
        "/executions",
        json={
            "session_id": sid,
            "agent_id": "agent-2",
            "input_payload": {"x": 1},
            "output_payload": {"y": 1},
            "state_hash": "abc",
        },
    )
    e2 = client.post(
        "/executions",
        json={
            "session_id": sid,
            "agent_id": "agent-2",
            "input_payload": {"x": 1},
            "output_payload": {"y": 1},
            "state_hash": "DIFFERENT",
        },
    ).json()
    assert e2["kind"] == "state_drift"
