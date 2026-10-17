# AgentDrift MCP v2.10.0

AgentDrift MCP 2.10.0 refreshes package metadata for a new PyPI release and brings the current runtime, cloud service, and landing page together under one release. The release keeps the package name `agentdrift-mcp` and supports Python 3.12 and newer.

## Highlights

- **Coordinated agent runtime.** Agents can share structured task execution commits, workspace history, exported contracts, and cross-agent workspace timelines.
- **Cloud service discovery.** The FastAPI service root now returns JSON metadata with service version, configured MCP transport, endpoint paths, health status endpoint, and an absolute documentation link. `/health` remains available for Render health checks.
- **Runtime supervision.** AgentDrift continues to provide drift detection, loop interruption, circuit-breaker guardrails, and local or hosted MCP transports.
- **Developer landing page.** The static landing page includes package installation methods, an animated dataflow view, configuration examples for 13 client environments, a technical comparison, and an interactive execution stream. The header includes the AgentDrift interwoven diamond mark.
- **Release automation.** The publishing workflow validates that a `v*` Git tag matches the package version, runs Ruff and the Python test suite, builds wheel and source distributions, and publishes to PyPI and GitHub Releases using Trusted Publishing.

## Compatibility and upgrade notes

- Install the PyPI distribution with `pip install --upgrade agentdrift-mcp`.
- Launch the local MCP server with `uvx agentdrift-mcp run` or install it with `pipx install agentdrift-mcp`.
- Python 3.12 or newer is required.
- Existing client configurations using the `agentdrift-mcp` command remain compatible. Hosted deployments can use the configured Streamable HTTP or SSE transport; consult the [MCP integration matrix](docs/MCP_INTEGRATION_MATRIX.md) for client-specific setup.
- Deployments using shared workspace task history should apply the task execution commits migration at `supabase/migrations/20261017_task_execution_commits.sql` after the shared workspace memory migration.

## Verification

- Ruff formatting and lint checks are run before release.
- The publishing workflow runs `pytest tests/ -q` and builds both the wheel and source distribution before publishing.
- Render uses `/health` for service health probes. The unified ASGI service binds to `0.0.0.0` and the configured `$PORT`.

## Distribution

- **PyPI:** [agentdrift-mcp](https://pypi.org/project/agentdrift-mcp/)
- **Version:** `2.10.0`
- **Python:** `>=3.12`
- **Git tag:** `v2.10.0`
- **Artifacts:** wheel (`.whl`) and source distribution (`.tar.gz`)

For full setup details, see the [README](README.md), [MCP integration matrix](docs/MCP_INTEGRATION_MATRIX.md), and [memory and storage guide](docs/memory_and_storage.md).
