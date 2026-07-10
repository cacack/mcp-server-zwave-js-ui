# mcp-server-zwave-js-ui

[![PyPI](https://img.shields.io/pypi/v/mcp-server-zwave-js-ui.svg)](https://pypi.org/project/mcp-server-zwave-js-ui/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-server-zwave-js-ui.svg)](https://pypi.org/project/mcp-server-zwave-js-ui/)
[![CI](https://github.com/cacack/mcp-server-zwave-js-ui/actions/workflows/ci.yml/badge.svg)](https://github.com/cacack/mcp-server-zwave-js-ui/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/pypi/l/mcp-server-zwave-js-ui.svg)](LICENSE)

An [MCP](https://modelcontextprotocol.io/) server for managing a Z-Wave network
through [Z-Wave JS UI](https://github.com/zwave-js/zwave-js-ui). It connects to
the `zwave-js-server` WebSocket that Z-Wave JS UI exposes and surfaces the mesh
— controller, nodes, values, and configuration parameters — as tools an MCP
client (e.g. Claude) can call.

> **Status: early / read-only.** This first release covers read-only
> introspection. Write control and administrative operations are on the
> roadmap — see [Roadmap](#roadmap).

## Quickstart

1. In Z-Wave JS UI, make sure the **Z-Wave JS Server** WebSocket is enabled
   (Settings → Home Assistant → *WS Server*; default port `3000`). See
   [What it connects to](#what-it-connects-to).
2. Add the server to Claude Code, pointing `ZWAVE_JS_URL` at that WebSocket.
   No manual install needed — `uvx` fetches and runs the published package:

   ```bash
   claude mcp add zwave-js-ui \
     --env ZWAVE_JS_URL=ws://<host>:3000 \
     -- uvx mcp-server-zwave-js-ui
   ```

3. Ask Claude about your mesh — it calls the read-only [tools](#tools) to answer:

   > *"Which Z-Wave controller am I running, and how many nodes are on the network?"*
   >
   > *"List my Z-Wave nodes and flag any that are dead or asleep."*

For other MCP clients, isolated installs, and configuration details, see the
sections below.

## What it connects to

Z-Wave JS UI runs two servers: the **web UI** (default port `8091`) and the
**Z-Wave JS Server** WebSocket (default port `3000`) that Home Assistant and
this MCP server talk to. Point `ZWAVE_JS_URL` at the WebSocket, not the UI.

## Install

Requires Python **3.12+**.

```bash
pip install mcp-server-zwave-js-ui
# or, isolated:
pipx install mcp-server-zwave-js-ui
# or, no install:
uvx mcp-server-zwave-js-ui
```

## Configure

| Variable       | Default                 | Description                                  |
|----------------|-------------------------|----------------------------------------------|
| `ZWAVE_JS_URL` | `ws://localhost:3000`   | WebSocket URL of the Z-Wave JS Server.       |

## Use with Claude Code

```bash
claude mcp add zwave-js-ui \
  --env ZWAVE_JS_URL=ws://borg:3002 \
  -- uvx mcp-server-zwave-js-ui
```

Or add it to an MCP client config directly:

```json
{
  "mcpServers": {
    "zwave-js-ui": {
      "command": "uvx",
      "args": ["mcp-server-zwave-js-ui"],
      "env": { "ZWAVE_JS_URL": "ws://borg:3002" }
    }
  }
}
```

## Tools

| Tool                     | Description                                                        |
|--------------------------|-------------------------------------------------------------------|
| `zwave_controller_info`  | Controller and network summary (home id, versions, RF region, node counts). |
| `zwave_list_nodes`       | One-line summary of every node (status, readiness, security, device). |
| `zwave_node_info`        | Full detail for a node (device class, command classes, endpoints, signal). |
| `zwave_node_values`      | A node's current values, excluding configuration parameters.      |
| `zwave_node_config`      | A node's configuration parameters with current values and metadata. |

## Roadmap

- **Level 2 — read/write:** set values (on/off/dim), set configuration parameters, manage association groups. Mutating tools will be gated behind a `ZWAVE_JS_READ_ONLY` flag.
- **Level 3 — admin/lifecycle:** inclusion/exclusion, re-interview, network heal / rebuild routes, OTA firmware update.

## Development

```bash
git clone https://github.com/cacack/mcp-server-zwave-js-ui
cd mcp-server-zwave-js-ui
uv venv --python 3.13 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

See [CLAUDE.md](CLAUDE.md) for architecture and design notes.

## License

[MIT](LICENSE)
