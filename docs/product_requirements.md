# Product requirements document

## Vision

Give autonomous coding agents a lightweight runtime supervisor that detects
repeated execution patterns, records evidence, and makes it easier to stop
unproductive loops before they exhaust time, tokens, or change budgets.

## Problem

Agents can repeat failed tool calls, alternate between two states, or report
progress without meaningful state change. These loops consume model budgets
and can cause repeated writes. Semantic contradictions and output-shape
changes can also pass unnoticed when a workflow only checks whether a tool
returned successfully.

AgentDrift captures execution telemetry, compares neighboring steps, and
surfaces a stop signal to the client. The product does not guarantee that every
hallucination is detected, nor does it automatically cancel arbitrary tools.

## Users and use cases

- Developers running Claude Code, Cline, Codex, OpenCode, and MCP-compatible
  coding environments.
- Teams connecting local agents to a shared authenticated Cloud MCP server.
- Operators inspecting session timelines and loop evidence in a web UI or CLI.

Primary flows: record an execution, check for repeated state, stop/recover on a
trip, inspect telemetry, and resume only after the agent's plan changes.

## Functional requirements

1. **Session and execution tracking:** create/update sessions and ingest
   ordered executions with payload, status, state hash, metadata, and optional
   trace.
2. **Runtime supervision:** identify repeated state hashes and high cosine
   similarity between adjacent steps; report threshold, IDs, and evidence.
3. **Drift classification:** expose state, schema, logical, semantic, and
   no-drift outcomes for supported execution comparisons.
4. **MCP integration:** provide stdio for local use and authenticated remote
   Streamable HTTP/SSE options for hosted use.
5. **CLI operations:** health, ingest, scan, evaluate, test-all, and watch
   workflows should be available through the Python CLI.
6. **Telemetry streaming:** provide a bounded snapshot followed by SSE deltas
   for live clients; reconnecting clients can obtain a new snapshot.
7. **Web presentation:** present sessions/detections and clear stop signals in
   a responsive telemetry-oriented interface.

## Non-functional requirements and targets

| Area | Requirement / target | Status |
|---|---|---|
| Local check latency | Target p99 < 25 ms for hash fast-path checks on a representative local workload | Benchmark target; not guaranteed by all paths/models |
| Data durability | Production mode must use persistent relational and vector storage | Operator configuration responsibility |
| Safety | A trip must be explicit and include inspectable evidence | Implemented in sentinel contract |
| Browser media | No WebKit autoplay regression; decorative video has a static fallback | UI acceptance target |
| Dependencies | Keep runtime dependencies limited to necessary server/storage/model integrations | Design constraint, not a zero-dependency claim |
| Recovery | Unknown mutation outcome must be inspected before retry | Client integration requirement |
| Security | Authenticated cloud MCP, least-privilege credentials, and audit scans | Configuration + CI requirement |

## Out of scope

- Guaranteeing semantic correctness or detecting every hallucination.
- Killing external tools or rolling back third-party side effects automatically.
- Providing a complete organization-wide agent execution policy engine.
- Claiming bounded latency for model loading or remote database/network paths.

## Success measures

- Loop signals include useful execution IDs, threshold, similarity, and reason.
- Client guidance causes agents to halt blind retries and inspect before
  recovery.
- Local operation remains possible without a hosted database.
- Cloud deployments isolate tenant data and expose auditable health status.
- Dashboards and event consumers recover cleanly after reconnect.
