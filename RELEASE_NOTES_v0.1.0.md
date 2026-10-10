# agentdrift v0.1.0 — Initial Public Release: Runtime Supervisor & Circuit Breaker

**agentdrift is the runtime supervisor and circuit breaker for autonomous coding agents.** It detects repetitive tool calls and execution spirals, then surfaces an intervention before endless retries consume a token budget.

This is the initial public release of the AgentDrift Python package, command-line tools, MCP server, and web interface.

## What’s included

- **Ping-pong and state spiral detection.** Compares execution state and payload embeddings to identify repetitive behavior, including repeated failing tests and back-and-forth file changes. Drift reports include a similarity score and evidence to help explain the detection.
- **Circuit-breaker diagnostics.** The CLI and MCP tools use a default similarity trip line of **0.92**. When a loop is detected, AgentDrift reports the intervention and its diagnostic so an integrating agent or supervisor can stop or redirect execution before further retries.
- **Agent environment compatibility.** Provides MCP configuration examples for Claude Code, Cline, OpenCode, and Codex.
- **MCP protocol server.** Run `agentdrift mcp` for a local stdio Model Context Protocol server. Its tools expose execution recording, drift checks, recent executions, and health information to MCP-compatible clients.
- **Cyber-botanical telemetry interface.** The `web/` frontend presents execution traces, CRT-inspired signal telemetry, and similarity metrics in a high-fidelity dashboard.

## Quick start

Install from PyPI:

```bash
pip install agentdrift
```

Run the local MCP server on demand with `uvx`:

```bash
uvx --from agentdrift agentdrift-mcp
```

The standalone MCP executable is published as `agentdrift-mcp`; `agentdrift mcp` is not a subcommand in this release.

Watch a live agent session from the terminal:

```bash
agentdrift watch
```

Use `agentdrift watch --help` to see session filters and polling options. For client setup, MCP tools, and cloud deployment details, see the documentation link below.

## Package and distribution

- **Python requirement:** `>=3.12`, as declared by this release’s package metadata.
- **Distributions:** universal Python wheel (`.whl`) and source distribution (`.tar.gz`).
- **Release tag:** `v0.1.0` (package version `0.1.0`).

## Project links

- [GitHub repository](https://github.com/sayon999-d/agentdrift)
- [Documentation and setup guide](https://github.com/sayon999-d/agentdrift#readme)
- [PyPI package](https://pypi.org/project/agentdrift/)
- [Issue tracker](https://github.com/sayon999-d/agentdrift/issues)

## Changelog

### Added

- Initial public Python package with the `agentdrift` CLI and `agentdrift-mcp` entry points.
- Local and cloud MCP server implementations for connecting agent clients to drift monitoring tools.
- Execution and state drift detection with similarity scoring, diagnostics, and configurable thresholds.
- Terminal session watching and a web telemetry interface.
- GitHub Actions workflow to lint, test, build, publish distributions to PyPI, and attach artifacts to a GitHub Release when a version tag is pushed.
