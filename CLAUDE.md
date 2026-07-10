# CLAUDE.md

## Project Overview

Python MCP server for Z-Wave device management. It connects to the
`zwave-js-server` WebSocket exposed by [Z-Wave JS UI](https://github.com/zwave-js/zwave-js-ui)
(the "Z-Wave JS Server" port, default 3000 — **not** the 8091 web UI) and
exposes the Z-Wave network as MCP tools.

Scope is delivered in levels:
1. **Read-only** (current) — controller info, node listing/detail, values, config parameters.
2. **Read/write** (planned) — set values, set config parameters, manage associations.
3. **Admin/lifecycle** (planned) — inclusion/exclusion, re-interview, network heal, OTA firmware.

## Commands

```bash
uv venv --python 3.13 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
ZWAVE_JS_URL=ws://borg:3002 python -m zwave_js_ui_mcp  # run server (stdio)
```

## Architecture

- `src/zwave_js_ui_mcp/server.py` — MCP tool registration (FastMCP). Tools are thin: connect, delegate to a projection, return the dict.
- `src/zwave_js_ui_mcp/client.py` — the entire backend. `connected_driver()` opens/tears down a connection; `project_*` functions turn library model objects into plain JSON-serializable dicts.

**The tool layer never touches a `zwave-js-server-python` object** — only the dicts `client.py` returns. This isolates the transport so it can be swapped without touching tools.

## Key Design Decisions

- Depends on `zwave-js-server-python` (the Home Assistant library) for connection, schema negotiation, and — decisive for level 3 — firmware/heal **progress events**. This pins **Python >= 3.12** (the library's floor).
- Connection is **per tool call** (open → wait for full-state dump → read → close), matching the stateless MCP style. `client.listen()` must run as a background task for `driver_ready` to fire and for `async_send_command` futures to resolve.
- Configuration-CC (112) values are excluded from `zwave_node_values` and surfaced only by `zwave_node_config`, so parameters aren't reported twice.
- Server URL via `ZWAVE_JS_URL` (default `ws://localhost:3000`). The WS server needs no auth by default; only the 8091 UI does.

## Integration Risk (validate against a live server)

- **Protocol schema version.** The library negotiates a schema version with the server; a library much newer than the `zwave-js-server` bundled in your Z-Wave JS UI image can raise `InvalidServerVersion`. If connecting fails on version, pin `zwave-js-server-python` to a release matching the deployed Z-Wave JS UI. This is the first thing to confirm when wiring up the read-only level.

## CI / Contribution Flow

- `main` is protected by a ruleset requiring PRs (0 approvals) with the **`CI Success`** and **GitGuardian** checks green — no direct pushes. Work on a branch, open a PR, self-merge when green.
- `CI Success` is the aggregate job in `.github/workflows/ci.yml` (test matrix + lint + dependency-review). The required check is that job's name.
- Releases/PyPI publish via release-please (`release-please.yml`, App-token auth) + a tag-triggered `release.yml` that publishes to PyPI via trusted publishing. **One-time setup required before publishing works:** a dedicated GitHub App (contents + pull-requests write) installed on the repo with its `RELEASE_PLEASE_APP_CLIENT_ID` + `RELEASE_PLEASE_APP_PRIVATE_KEY` repo secrets, a PyPI trusted-publisher pointing at `release.yml`'s `publish-pypi` job, and a `pypi` GitHub environment. Until configured, release automation is inactive but does not block PRs.

## Testing

- Projections are pure functions tested with lightweight fakes (`tests/test_client.py`) — no live server needed.
- Tool plumbing is tested by patching `connected_driver` with a fake driver (`tests/test_server.py`).
- For end-to-end checks, point `ZWAVE_JS_URL` at a real server via a gitignored `.env`.
