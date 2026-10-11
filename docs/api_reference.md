# AgentDrift daemon API reference

The FastAPI daemon is implemented in `app/main.py`, `app/routers/api.py`, and
`app/schemas.py`. It defaults to `http://127.0.0.1:8901`. The API accepts and
returns JSON except for the event stream. Interactive OpenAPI documentation is
available at `/docs` and `/openapi.json` while the service is running.

> **Route correction:** the implemented SSE endpoint is `GET /v1/events/stream`.
> `GET /v1/stream` is not currently registered. The examples below document
> the implemented route; clients relying on `/v1/stream` must use the actual
> route or add an alias in a future code change.

## Common behavior

- JSON requests use `Content-Type: application/json`.
- Pydantic request models reject invalid typed fields with FastAPI's standard
  `422` response. Unknown fields are ignored by default in typed models.
- Datetimes serialize as ISO-8601 strings. IDs are opaque strings; detection
  IDs are UUIDs.
- Routes also exist under `/api` and `/v1` for several core operations. The
  canonical routes below are at the root.
- There is no single custom API error envelope. FastAPI HTTP errors use
  `{"detail":"..."}`; validation errors use
  `{"detail":[{"loc":[],"msg":"...","type":"..."}]}`.

## `POST /sessions`

Create a session. Returns **201 Created** and a `SessionOut`.

```json
{
  "session_id": "session-42",
  "agent_id": "codex",
  "parent_session_id": null,
  "status": "active",
  "metadata": {"task": "refactor"}
}
```

`session_id` is optional and generated when omitted. `agent_id` is required.
`parent_session_id` is nullable; `status` defaults to `active`; `metadata`
defaults to `{}`.

```json
{
  "session_id": "session-42",
  "agent_id": "codex",
  "parent_session_id": null,
  "status": "active",
  "metadata": {"task": "refactor"},
  "created_at": "2026-10-11T08:00:00Z",
  "updated_at": "2026-10-11T08:00:00Z"
}
```

| Status | Meaning |
|---|---|
| 201 | Created |
| 409 | Session ID already exists (`detail` explains conflict) |
| 422 | Invalid request model |

## `PATCH /sessions/{session_id}`

Update only supplied session properties. Returns **200** and the updated
`SessionOut`. Fields: `status` (string or null), `metadata` (object or null),
and `parent_session_id` (string or null). Omitted fields remain unchanged;
explicit `parent_session_id: null` clears the parent.

```json
{"status":"completed","metadata":{"result":"ok"}}
```

| Status | Meaning |
|---|---|
| 200 | Updated session |
| 404 | `{"detail":"session not found"}` |
| 422 | Invalid field types |

## `POST /executions`

Ingests an execution, assigns a sequence if omitted, and automatically compares
it with the previous execution in the session. Returns **201**.

```json
{
  "execution_id": "exec-100",
  "session_id": "session-42",
  "parent_execution_id": null,
  "agent_id": "codex",
  "node_id": "edit-file",
  "sequence": 1,
  "status": "ok",
  "input_payload": {"file": "app/main.py"},
  "output_payload": {"changed": true},
  "thinking_trace": null,
  "state_hash": "sha256:...",
  "metadata": {},
  "freeze": false
}
```

`session_id` and `agent_id` are required. `node_id` defaults to `default`,
`sequence` is optional, payloads and metadata default to empty objects,
`status` defaults to `ok`, and `freeze` defaults to false. `thinking_trace`
may be an object, list, or null. IDs are generated where supported if omitted.

```json
{
  "execution": {"execution_id":"exec-100","session_id":"session-42","sequence":1,"status":"ok"},
  "detection": null,
  "drifted": false,
  "kind": "no_drift"
}
```

The `execution` object includes the stored execution fields; `detection` is
null when no drift is produced, otherwise includes detection ID, kind,
similarity, threshold, evidence, and timestamps.

| Status | Meaning |
|---|---|
| 201 | Ingested; response includes detection outcome |
| 404 | Referenced session does not exist; create it first |
| 422 | Invalid typed request |

## `GET /executions`

Returns an array of `ExecutionOut` records sorted by sequence. Query
parameters: `session_id` (optional), `limit` (default 200, max 1000), and
`offset` (default 0).

```http
GET /executions?session_id=session-42&limit=50&offset=0
```

Returns **200** with `[]` when there are no matching executions. An execution
contains identifiers, sequence/status, input/output payloads, trace, state
hash, metadata, frozen time, and creation time. Internal embedding vectors are
not part of `ExecutionOut`.

## `POST /v1/sentinel/scan`

Scans adjacent executions for repeated state. Body is optional; supported field
is `threshold` (number; defaults to **0.92**). Although `session_id` is accepted
by the request helper, the current route scans all sessions and does not apply
that filter.

```json
{"threshold":0.92}
```

```json
{
  "ok": true,
  "detections": 1,
  "threshold": 0.92,
  "loops": [
    {
      "session_id":"session-42",
      "execution_id":"exec-100",
      "prior_execution_id":"exec-99",
      "kind":"ping_pong_loop",
      "similarity":1.0,
      "threshold":0.92,
      "evidence":{"reason":"matching state_hash","sequence":10}
    }
  ]
}
```

Returns **200**. A repeated non-empty state hash trips immediately; otherwise
the scan uses cosine similarity and flags scores above the scan threshold.
Malformed or absent JSON is treated as an empty body and uses the default.

## `POST /v1/evaluate`

Scores premise/hypothesis pairs using the deterministic heuristic. If
`NLI_ENABLED=true`, the configured model contributes a blended contradiction
signal. Accepted input forms are a raw array or an object containing the array
under `items`, `pairs`, `inputs`, `evaluations`, or `data`; one object with
`premise` and `hypothesis` is also accepted. Each item accepts optional `id`
and string `premise`/`hypothesis` fields.

```json
{"items":[{"id":"check-1","premise":"The job completed","hypothesis":"The job did not complete"}]}
```

```json
{"ok":true,"count":1,"results":[{"id":"check-1","premise":"The job completed","hypothesis":"The job did not complete","entailment":0.05,"neutral":0.1,"contradiction":0.85,"label":"contradiction","margin":0.75}]}
```

Returns **200** with normalized scores in `[0,1]`, `label` (`entailment`,
`neutral`, or `contradiction`), and top-score `margin`. Invalid/non-JSON bodies
currently normalize to an empty result list. This endpoint is an evaluation
utility, not a cryptographic policy gate or a substitute for human review.

## `GET /v1/events/stream` (SSE)

Streams a bounded initial snapshot and subsequent new execution/detection
deltas. Query parameters: `session_id` (optional), `poll` (default 1 second,
clamped to 0.2–10 seconds), and `once` (default false; returns only the initial
snapshot).

```http
GET /v1/events/stream?session_id=session-42&poll=1&once=true
Accept: text/event-stream
```

Response media type: `text/event-stream`. Frames are JSON in `data:` lines:

```text
data: {"type":"snapshot","executions":[...],"detections":[...]}

data: {"type":"delta","executions":[...],"detections":[...]}

: ping
```

The first frame is always `snapshot`; later frames are `delta` when records
appear and an SSE comment ping otherwise. The stream is polling-based, not a
durable message queue. Disconnect and reconnect to obtain a fresh snapshot.

## Other routes

Additional API routes include health/readiness (`/health`, `/ready`), session
listing/detail, session executions/timeline/detections, `/detect`, `/stats`,
and compatibility aliases. See FastAPI's generated OpenAPI document for the
complete live route inventory.
