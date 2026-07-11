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

> **Status: early / read + write + lifecycle.** Read-only introspection, write
> control (values, config parameters, node name/location, associations), and
> admin/lifecycle operations (re-interview, route rebuild, inclusion/exclusion,
> remove failed node) are available. Set `ZWAVE_JS_READ_ONLY` to hide every
> mutating tool and expose only the read tools. Triggering an OTA firmware
> update is still on the [roadmap](#roadmap).

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

| Variable             | Default               | Description                                                        |
|----------------------|-----------------------|--------------------------------------------------------------------|
| `ZWAVE_JS_URL`       | `ws://localhost:3000` | WebSocket URL of the Z-Wave JS Server.                             |
| `ZWAVE_JS_READ_ONLY` | *(unset)*             | Set to `1`/`true`/`yes`/`on` to hide all write and admin tools (only the read tools are registered). |

## Use with Claude Code

```bash
claude mcp add zwave-js-ui \
  --env ZWAVE_JS_URL=ws://<host>:3000 \
  -- uvx mcp-server-zwave-js-ui
```

Or add it to an MCP client config directly:

```json
{
  "mcpServers": {
    "zwave-js-ui": {
      "command": "uvx",
      "args": ["mcp-server-zwave-js-ui"],
      "env": { "ZWAVE_JS_URL": "ws://<host>:3000" }
    }
  }
}
```

## Tools

Write and admin tools (everything below the read-only rows) are hidden from the
registry when `ZWAVE_JS_READ_ONLY` is set.

### Read-only

| Tool                     | Description                                                        |
|--------------------------|-------------------------------------------------------------------|
| `zwave_controller_info`  | Controller and network summary (home id, versions, RF region, node counts). |
| `zwave_list_nodes`       | One-line summary of every node (status, readiness, security, device). |
| `zwave_node_info`        | Full detail for a node (device class, command classes, endpoints, signal). |
| `zwave_node_values`      | A node's current values, excluding configuration parameters.      |
| `zwave_node_config`      | A node's configuration parameters with current values and metadata. |
| `zwave_association_groups` | A node's association groups and their capabilities.             |
| `zwave_associations`     | A node's current associations, keyed by group.                    |
| `zwave_rebuild_routes_status` | Whether a network-wide route rebuild (heal) is in progress.  |
| `zwave_firmware_update_status` | Whether an OTA firmware update is in progress.              |

### Write control (level 2)

| Tool                       | Description                                                      |
|----------------------------|------------------------------------------------------------------|
| `zwave_set_value`          | Set a value by id (on/off/dim/etc.); validated against live metadata. |
| `zwave_set_config_parameter` | Set a manufacturer configuration parameter (optional bit mask). |
| `zwave_set_node_name`      | Set a node's friendly name.                                     |
| `zwave_set_node_location`  | Set a node's location label.                                    |
| `zwave_add_association`    | Associate a target node into a source node's group.             |
| `zwave_remove_association` | Remove a target node from a source node's group.                |

### Admin / lifecycle (level 3)

| Tool                          | Description                                                   |
|-------------------------------|---------------------------------------------------------------|
| `zwave_reinterview_node`      | Re-run a node's interview to refresh capabilities and values. |
| `zwave_rebuild_node_routes`   | Rebuild mesh routes for a single node.                        |
| `zwave_begin_rebuilding_routes` / `zwave_stop_rebuilding_routes` | Start/stop a network-wide route rebuild (heal). |
| `zwave_remove_failed_node`    | Remove a controller-flagged failed node from the network.     |
| `zwave_begin_inclusion` / `zwave_stop_inclusion` | Enter/leave inclusion mode to add a node.  |
| `zwave_begin_exclusion` / `zwave_stop_exclusion` | Enter/leave exclusion mode to remove a node. |

> **Note on secure inclusion:** interactive S2 security bootstrap (DSK/PIN
> grant) can't complete through this stateless server — use the Z-Wave JS UI
> for secure inclusion.

## Roadmap

- **Trigger OTA firmware updates.** Reporting update status is available
  (`zwave_firmware_update_status`), but starting a flash streams progress events
  over minutes, which the per-call connection model can't observe within a
  single tool call; delivering it needs a persistent-connection design.

## Development

```bash
git clone https://github.com/cacack/mcp-server-zwave-js-ui
cd mcp-server-zwave-js-ui
uv sync --extra dev            # create .venv from the checked-in uv.lock
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

See [CLAUDE.md](CLAUDE.md) for architecture and design notes.

## License

[MIT](LICENSE)
