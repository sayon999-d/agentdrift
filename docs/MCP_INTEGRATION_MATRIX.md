# AgentDrift MCP integration matrix

AgentDrift exposes the same MCP tools through a local process or a hosted
server. This guide summarizes client support and gives copyable configurations
for common coding CLIs and IDEs. Client support changes over time; consult the
linked vendor documentation when a client rejects a transport or config field.

## AgentDrift transports

| AgentDrift mode | MCP transport | Endpoint | Storage | Use |
|---|---|---|---|---|
| Local | stdio | Run `agentdrift-mcp` | Local SQLite + LanceDB | Private, offline, one workstation |
| Cloud (recommended remote) | Streamable HTTP | `/mcp` | Supabase Postgres + pgvector | Hosted and multi-client |
| Cloud (legacy clients) | SSE | `/sse` (cloud server) or `/mcp` (standalone legacy server) | Supabase | Compatibility with SSE-only clients |

The examples below assume the package is installed with `pip3 install agentdrift-mcp`
for local stdio, or that a secured AgentDrift Cloud MCP deployment is available
at `https://mcp.example.com/mcp`. Replace the URL and token with your own
deployment. For local development from a checkout, replace `agentdrift-mcp`
with `python /absolute/path/to/agentdrift/mcp_server.py --transport stdio`.

| Client | Local stdio | Streamable HTTP | Legacy SSE | Config surface |
|---|---:|---:|---:|---|
| Claude Code | Yes | Yes | Yes | `claude mcp add` or project `.mcp.json` |
| Claude Desktop | Yes | Yes* | Yes* | `claude_desktop_config.json` / MCP settings |
| Cursor | Yes | Yes | Yes | `.cursor/mcp.json` or `~/.cursor/mcp.json` |
| Windsurf Cascade / Devin Desktop | Yes | Yes | Yes | `mcp_config.json` |
| VS Code / GitHub Copilot | Yes | Yes | Yes | `.vscode/mcp.json` (`servers`) |
| GitHub Copilot CLI | Yes | Yes | Yes | `~/.copilot/mcp-config.json` (`mcpServers`) |
| Codex CLI / IDE extension | Yes | Yes | Yes† | `codex mcp` or `~/.codex/config.toml` |
| Gemini CLI | Yes | Yes | Yes | `~/.gemini/settings.json` (`mcpServers`) |
| Cline | Yes | Yes | Yes | Cline MCP settings (`mcpServers`) |
| Roo Code | Yes | Yes | Yes | Roo MCP settings (`mcpServers`) |
| OpenCode | Yes | Yes | Client/version dependent‡ | `opencode.json` (`mcp`) |
| Zed | Yes | Yes | Version dependent | Settings → AI → MCP Servers / `settings.json` |
| Continue | Yes | Yes* | Yes* | `config.yaml` (`mcpServers`) |
| JetBrains IDEs (MCP Client) | Yes§ | Yes§ | Version dependent | MCP settings / AI Assistant plugin |

`Yes` means documented support for an MCP server in a current client release;
availability can depend on product version, extension, and policy. It does not
mean the client is itself an MCP server. In particular, JetBrains IDEs also
provide an IDE MCP **server** that exposes IDE actions to external clients.

* Claude Desktop capabilities can differ by edition and release. Verify in the
  app's MCP settings; Claude Code's CLI supports local and remote entries.
† Codex supports stdio and Streamable HTTP as documented. For SSE, use an MCP
  bridge/proxy that presents stdio or HTTP if the installed Codex version does
  not accept an SSE endpoint directly.
‡ OpenCode's current remote MCP configuration is Streamable HTTP. Do not assume
  legacy SSE support from older OpenCode versions; use a bridge if needed.
§ JetBrains AI Assistant's MCP client capabilities vary by IDE/plugin version.
Zed's documented configuration describes local servers and remote MCP URLs;
legacy SSE availability depends on the server/client version. Continue's MCP
transport fields vary by extension and CLI release, so confirm its current
config reference before choosing remote HTTP or SSE.

## Copyable client configurations

The package's tools are `record_execution`, `check_drift`, `list_recent_executions`,
and `get_health`. The local examples run a subprocess. The cloud examples use a
Bearer token; prefer an OAuth flow or the client’s secret store when available.
Never put a Supabase service-role key in an editor or CLI config.

### Claude Code

```bash
# Local
claude mcp add agentdrift-mcp -- agentdrift-mcp

# Cloud Streamable HTTP
claude mcp add --transport http agentdrift-mcp-cloud \
  https://mcp.example.com/mcp --header "Authorization: Bearer $AGENTDRIFT_MCP_TOKEN"

# Cloud legacy SSE
claude mcp add --transport sse agentdrift-mcp-sse \
  https://mcp.example.com/sse --header "Authorization: Bearer $AGENTDRIFT_MCP_TOKEN"
```

Project `.mcp.json` entries can use `command`/`args` for stdio or `type: http`
and `url` for cloud HTTP. Keep credentials in environment variables and out of
committed project config. See [Claude Code MCP docs](https://docs.anthropic.com/en/docs/claude-code/mcp).

### Claude Desktop

Add this local stdio entry to `claude_desktop_config.json`, then restart Claude
Desktop. No token or environment variables are needed for local use.

```json
{
  "mcpServers": {
    "agentdrift-mcp": {
      "command": "agentdrift-mcp",
      "args": []
    }
  }
}
```

### Cursor, Windsurf, Cline, and Roo Code

Cursor (`.cursor/mcp.json`), Windsurf (`mcp_config.json`), Cline, and Roo Code
use an `mcpServers` object for local stdio entries:

```json
{
  "mcpServers": {
    "agentdrift-mcp": {
      "command": "agentdrift-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

For Cline remote Streamable HTTP, use the following entry shape. Roo Code uses
the same fields but spells the type `streamable-http`. Cursor uses its own
remote server setup and can be configured through MCP settings; verify the
current `mcp.json` format in its docs for your release.

```json
{
  "mcpServers": {
    "agentdrift-mcp-cloud": {
      "type": "streamableHttp",
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${AGENTDRIFT_MCP_TOKEN}"
      }
    }
  }
}
```

For legacy SSE, use `"type": "sse"` and the `/sse` URL. Cline and Roo Code
require an explicit transport type for URL entries. Cursor and Windsurf expose
MCP settings through their UI as well as config files. See [Cursor](https://docs.cursor.com/context/model-context-protocol),
[Cline](https://docs.cline.bot/mcp/mcp-overview), and
[Roo Code](https://docs.roocode.com/features/mcp/using-mcp-in-roo).

Windsurf Cascade uses `serverUrl` for remote HTTP and `url` for its remote
endpoint configuration. Example:

```json
{
  "mcpServers": {
    "agentdrift-mcp-cloud": {
      "serverUrl": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${env:AGENTDRIFT_MCP_TOKEN}"
      }
    }
  }
}
```

Cascade supports stdio, Streamable HTTP, and SSE. See its
[MCP configuration docs](https://docs.windsurf.com/windsurf/cascade/mcp).

### VS Code and GitHub Copilot

VS Code workspace config uses `.vscode/mcp.json` and a top-level `servers`
object. GitHub Copilot CLI uses `mcpServers` instead.

```json
{
  "servers": {
    "agentdrift-mcp": {
      "type": "stdio",
      "command": "agentdrift-mcp",
      "args": []
    },
    "agentdrift-mcp-cloud": {
      "type": "http",
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer ${input:agentdrift-mcp-token}"
      }
    }
  },
  "inputs": [
    {
      "id": "agentdrift-mcp-token",
      "type": "promptString",
      "description": "AgentDrift MCP access token",
      "password": true
    }
  ]
}
```

Set `type` to `sse` and the URL to `/sse` for legacy SSE. See [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration).

### Codex CLI and IDE extension

```bash
# Local stdio
codex mcp add agentdrift-mcp -- agentdrift-mcp

# Remote Streamable HTTP
codex mcp add agentdrift-mcp-cloud --url https://mcp.example.com/mcp
```

To add a bearer token, configure an `http_headers` value or a supported
environment-backed header in `~/.codex/config.toml`. Codex also supports
`codex mcp` commands for listing and removing servers. See [Codex MCP docs](https://developers.openai.com/codex/mcp/).

### Gemini CLI

```bash
gemini mcp add agentdrift-mcp agentdrift-mcp
gemini mcp add --transport http agentdrift-mcp-cloud https://mcp.example.com/mcp \
  --header "Authorization: Bearer $AGENTDRIFT_MCP_TOKEN"
gemini mcp add --transport sse agentdrift-mcp-sse https://mcp.example.com/sse \
  --header "Authorization: Bearer $AGENTDRIFT_MCP_TOKEN"
```

Gemini CLI also accepts `command` (stdio), `httpUrl` (Streamable HTTP), and
`url` (SSE) in its `mcpServers` settings. See [Gemini CLI MCP docs](https://geminicli.com/docs/tools/mcp-server/).

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "agentdrift-mcp": {
      "type": "local",
      "command": ["agentdrift-mcp"],
      "enabled": true
    },
    "agentdrift-mcp-cloud": {
      "type": "remote",
      "url": "https://mcp.example.com/mcp",
      "oauth": false,
      "headers": {
        "Authorization": "Bearer {env:AGENTDRIFT_MCP_TOKEN}"
      }
    }
  }
}
```

Current OpenCode remote MCP uses Streamable HTTP. See [OpenCode MCP docs](https://opencode.ai/docs/mcp-servers/).

### Zed

Use **Settings → AI → MCP Servers** to add either a local command or remote
server. Zed's settings JSON supports `context_servers` with `command` for stdio or
`url` for remote HTTP. For a secured remote service, configure the `Authorization`
header or complete the OAuth flow when prompted. See [Zed MCP docs](https://zed.dev/docs/ai/mcp).

```json
{
  "context_servers": {
    "agentdrift-mcp": {
      "command": "agentdrift-mcp",
      "args": []
    },
    "agentdrift-mcp-cloud": {
      "url": "https://mcp.example.com/mcp",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

### Continue

Continue stores MCP definitions in YAML. Example local config:

```yaml
name: AgentDrift
version: 2.10.0
schema: v1
mcpServers:
  - name: agentdrift-mcp
    command: agentdrift-mcp
    args: []
```

Continue's current `mcpServers` schema supports local command/args and remote
transport request options; consult the versioned YAML reference for the exact
`type` and `requestOptions` fields for SSE or Streamable HTTP. See [Continue MCP docs](https://docs.continue.dev/customize/mcp-tools).

## Security and troubleshooting

- Run the local process as your user, with only the environment variables it
  needs. Stdio servers must keep protocol output on stdout and send logs to
  stderr.
- Prefer HTTPS, short-lived user-scoped tokens, and OAuth where the client and
  server support it. Avoid service-role credentials in client-side configs.
- Do not commit credentials in workspace MCP config. Use environment-variable
  substitution, prompts, OS credential stores, or the client's OAuth flow.
- Restrict exposed tools and tool auto-approval. AgentDrift writes execution
  telemetry; treat the stored payloads as potentially sensitive.
- For connection failures, confirm endpoint path (`/mcp` for Streamable HTTP,
  `/sse` for cloud legacy SSE), authentication headers, server logs, and client
  version. SSE and Streamable HTTP are distinct transports.

## Vendor references

- [Model Context Protocol transports](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/mcp)
- [Cursor](https://docs.cursor.com/context/model-context-protocol)
- [Windsurf](https://docs.windsurf.com/windsurf/cascade/mcp)
- [VS Code](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
- [Codex](https://developers.openai.com/codex/mcp/)
- [Gemini CLI](https://geminicli.com/docs/tools/mcp-server/)
- [Cline](https://docs.cline.bot/mcp/mcp-overview)
- [Roo Code](https://docs.roocode.com/features/mcp/using-mcp-in-roo)
- [OpenCode](https://opencode.ai/docs/mcp-servers/)
- [Zed](https://zed.dev/docs/ai/mcp)
- [Continue](https://docs.continue.dev/customize/mcp-tools)
- [JetBrains MCP Server](https://www.jetbrains.com/help/idea/mcp-server.html)
