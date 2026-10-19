# AgentDrift MCP v2.10.2

## Summary

AgentDrift MCP 2.10.2 scopes its embedded SQLite and LanceDB storage to the
current project by default, making local data easier to find and keeping
separate projects isolated.

## Changes

- The hybrid store now creates data under `./.agentdrift/` by default.
- `AGENTDRIFT_DIR` overrides the storage directory, while
  `AGENTDRIFT_DB_PATH` selects a specific SQLite database file. The existing
  `AGENTDRIFT_DATA_DIR` override remains supported.
- `agentdrift-mcp --global` and `agentdrift-mcp run --global` select
  `~/.agentdrift/` when no explicit storage path override is configured.
- When a project-local `.agentdrift/` directory exists, startup ensures that
  `.agentdrift/` is listed in the current working directory's `.gitignore`.
- Health reporting and storage documentation now show the resolved project
  path and describe the new overrides.

## Compatibility

- Existing `AGENTDRIFT_DATA_DIR` configurations continue to work.
- Cloud storage selection and the MCP server transports are unchanged.
- The default HTTP/SSE binding remains loopback at `127.0.0.1:8000`.

## Release metadata

- Package: `agentdrift-mcp`
- Version: `2.10.2`
- Python: 3.12+
- Git tag: `v2.10.2`
