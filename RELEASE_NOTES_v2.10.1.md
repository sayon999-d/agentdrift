# AgentDrift MCP v2.10.1

AgentDrift MCP 2.10.1 improves the first-run experience for local MCP server users and adds a prerequisite diagnostic command.

## Highlights

- `agentdrift-mcp run` starts the MCP server with SSE transport on `127.0.0.1:8000` by default.
- Running `agentdrift-mcp` without a subcommand uses the same server defaults.
- Local runs without a configured token start in unauthenticated development mode and print the bound URL. An explicit `--token` or `AGENTDRIFT_MCP_TOKEN` enables bearer authentication.
- Existing root-level server flags remain available for compatibility, including `--transport`, `--host`, `--port`, and `--allow-unauthenticated`.
- `agentdrift-mcp doctor` checks that the `fastmcp` and `uvicorn` runtime dependencies are installed.
- The web package metadata, landing page version badge, install examples, and MCP integration documentation now identify version 2.10.1.

## Release details

- Package: `agentdrift-mcp`
- Version: `2.10.1`
- Python: 3.12+
- Git tag: `v2.10.1`

This is a patch release. It does not change the package name or supported Python minimum.
