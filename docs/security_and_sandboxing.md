# Security and sandboxing

## Threat model and boundaries

AgentDrift handles agent-generated payloads, code execution telemetry,
database credentials, and potentially sensitive traces. A connected MCP server
can expose tools to an agent that may read or mutate local or remote state.
Threats include secret leakage in payloads/logs, malicious or malformed tool
input, unauthorized remote access, cross-tenant data access, vulnerable
dependencies, and retries that repeat external side effects.

Trust boundaries:

1. **Agent/client:** untrusted planner and tool arguments; enforce client
   approval/sandbox policy independently.
2. **MCP transport:** stdio is local process IPC; HTTP/SSE crosses a network and
   needs TLS, authentication, and deployment controls.
3. **Daemon:** validates typed REST schemas but not every arbitrary nested
   payload's semantic safety.
4. **Storage:** local files follow OS permissions; cloud database requires
   least-privilege credentials and tenant isolation.
5. **Dashboard:** CORS is not authentication. Do not expose an unauthenticated
   daemon to an untrusted network.

## Security controls

- Bind local development to `127.0.0.1`. Put network-facing services behind
  HTTPS and an authenticated reverse proxy or the cloud MCP auth layer.
- Supply only short-lived, user-scoped credentials to MCP clients. Never
  place a Supabase service-role key in a coding agent config.
- Keep secrets in environment/secret managers; `.env` must remain untracked.
- Do not record API keys, raw authorization headers, private keys, or
  unnecessary personal data in execution payloads or thinking traces.
- In authenticated Cloud mode, REST data routes require a service bearer token
  (`AGENTDRIFT_REST_API_TOKEN`, falling back to `AGENTDRIFT_MCP_TOKEN` or
  `MCP_TOKEN`). REST queries are not user-scoped today, so the middleware rejects
  ordinary Supabase user JWTs there. Cloud MCP endpoints keep their separate
  JWT-based per-user scoping.
- Limit auto-approved MCP tools and review each server's source and requested
  permissions.
- Sanitize/validate at the boundary. Typed REST models validate known fields;
  consumers must still treat arbitrary JSON payload values as untrusted.
- Preserve tenant `user_id` scoping and RLS policies in multi-tenant Supabase
  configurations. Service-role database access bypasses RLS by design and
  must stay server-side.

## Multi-agent isolation

Use distinct session IDs for distinct logical runs and tenant/user boundaries
for remote storage. Do not share a session ID across trust domains. Session IDs
are identifiers, not authentication. Verify authorization before reading or
mutating a session. Do not claim that a separate session provides process or
filesystem isolation; use OS/container sandboxing for that.

## Audit criteria

The repository security workflow runs:

- **Bandit** AST analysis over `agentdrift` and `app` at low-confidence/low
  severity filters specified by the script (`-ll -ii`).
- **pip-audit** against `requirements.txt` for known Python dependency CVEs.
- **npm audit** over `web` with high severity as the failure threshold.
- **detect-secrets** repository scanning, failing on findings for review.

Run locally with:

```bash
scripts/security_audit.sh
```

Review and remove true secrets; do not add a baseline/allowlist to make a real
credential disappear. Rotate any credential that was committed or exposed.
The workflow is a useful gate, not a substitute for code review, deployment
hardening, or periodic threat-model updates.

## Incident and recovery guidance

If credentials appear in a trace, log, or repository: revoke/rotate first,
remove the exposed value from future artifacts, assess access using provider
logs, and follow repository history cleanup policy. Deleting a visible value
does not invalidate a leaked token. For suspected cross-tenant exposure,
disable the affected endpoint/credential, preserve evidence, inspect RLS and
server auth logs, and notify the responsible security owner.
