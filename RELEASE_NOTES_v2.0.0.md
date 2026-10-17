# AgentDrift MCP v2.0.0

AgentDrift MCP is a runtime supervisor and circuit breaker for autonomous coding agents. It detects repetitive tool calls and execution spirals, provides diagnostics to help agents recover, and exposes local and hosted monitoring through a Python CLI, MCP servers, APIs, and a web telemetry interface.

This release note consolidates the v2.0.0 package release and the project changes recorded on `main` through the current release workflow and structured task history updates.

## What's New

- **Structured task execution history.** Added the typed `TaskExecutionCommit` model with a short commit identifier, timestamp, agent identity, task intent, technical summary, typed file changes, optional exported contracts, and completed/reverted/audited status.
- **Shared workspace memory improvements.** Workspace actions can be stored and returned as structured commit history instead of an unstructured summary. Added a Supabase migration to create the task execution commit records and backfill existing action records.
- **Cross-agent workspace timeline.** Workspace APIs and MCP tools expose shared workspace history and timeline data for agents that share a session/workspace.
- **Structured GitHub release notes.** The release workflow derives categorized notes from commits between version tags, then creates a GitHub Release with the package distributions and GitHub-generated comparison/contributor details after PyPI publishing.
- **Expanded MCP client setup guidance.** Updated the integration matrix and examples for local stdio and hosted MCP connections, including Claude Desktop/Code, Codex, Cline, OpenCode, and other compatible clients.
- **Package branding and installation.** The published distribution is `agentdrift-mcp`, with the `agentdrift-mcp` MCP executable and `agentdrift` CLI compatibility command.

## Breaking Changes & Upgrades

- **Package identity and commands.** Install the distribution as `agentdrift-mcp`. Use `agentdrift-mcp` to start the MCP server; `agentdrift` remains the CLI command.
- **Workspace database upgrade.** For deployments using shared workspace memory, apply `supabase/migrations/20261017_task_execution_commits.sql` after the existing shared workspace memory migration. The new migration creates structured task commit history and backfills existing action data.
- **Python support.** Python 3.12 or newer is required.
- **MCP setup.** Client configuration examples now use the `agentdrift-mcp` server name and command. Hosted clients require the endpoint and authentication setup documented in `docs/MCP_INTEGRATION_MATRIX.md`.

## Bug Fixes & Hardening

- Corrected the package entry point to use `agentdrift.cli` and aligned the package name and version metadata for PyPI publishing.
- Switched PyPI publishing to Trusted Publishing and hardened the workflow so branch pushes run CI while version tags run CI and publishing. Manual workflow runs can target a version tag.
- Fixed the release workflow's tag/version validation so it is applied to version tags and skipped for non-release branch refs.
- Fixed Ruff import ordering and removed lint errors in the MCP workspace tools.
- Updated the Starlette dependency and unified the FastAPI/MCP entry point.
- Updated the Cloudflare Pages workflow/action configuration and avoided tracking generated Wrangler artifacts.
- Fixed web asset loading for Safari byte-range requests.

## Existing AgentDrift Capabilities

- **Drift and loop detection.** Detects state, schema, logical, and semantic drift, including repetitive executions and ping-pong behavior. Reports a similarity score and diagnostic evidence to support intervention.
- **Circuit-breaker monitoring.** The CLI and MCP surfaces provide drift checks and health information; the default CLI/MCP similarity trip line is 0.92.
- **Python CLI.** Provides health, scan, ingest, evaluate, test, and live watch workflows.
- **MCP servers.** Supports local stdio and hosted transports, including Streamable HTTP and legacy SSE where configured. Tools include execution recording, drift checks, recent execution listing, and health information.
- **REST API and cloud deployment.** Includes unified FastAPI routes, OpenAPI documentation, authenticated cloud MCP access, and Supabase/Postgres storage with pgvector.
- **Web telemetry interface.** Provides an interface for execution traces, signal telemetry, and similarity metrics.

## Install and Run

Install from PyPI:

```bash
pip3 install --upgrade agentdrift-mcp
```

Run the local MCP server:

```bash
uvx --from agentdrift-mcp agentdrift-mcp
```

Run the CLI:

```bash
agentdrift --help
```

For client-specific setup, hosted server configuration, and migration instructions, see the [README](README.md), [MCP integration matrix](docs/MCP_INTEGRATION_MATRIX.md), and [memory and storage guide](docs/memory_and_storage.md).

## Distribution

- **PyPI package:** [`agentdrift-mcp`](https://pypi.org/project/agentdrift-mcp/)
- **Version:** `2.0.0`
- **Python:** `>=3.12`
- **Artifacts:** wheel (`.whl`) and source distribution (`.tar.gz`)
- **Git tag:** [`v2.0.0`](https://github.com/sayon999-d/agentdrift/releases/tag/v2.0.0)

## Full Changelog & Contributors

The project history includes the initial daemon, drift engine, MCP server, CLI, and telemetry UI; cloud schema and deployment/API integration; release and publishing workflow fixes; package branding and entry point updates; and structured task execution history. See the [full commit history](https://github.com/sayon999-d/agentdrift/commits/main) and [GitHub Releases](https://github.com/sayon999-d/agentdrift/releases) for commit details and contributor attribution.
