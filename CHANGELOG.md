# Changelog

## [0.4.0](https://github.com/cacack/mcp-server-zwave-js-ui/compare/v0.3.0...v0.4.0) (2026-07-11)


### ⚠ BREAKING CHANGES

* zwave_controller_info's `controller_type` and zwave_node_info's `protocol_version` change from a bare int to a `{"value": int, "label": str|null}` object.

### Features

* add write control and admin/lifecycle tools (levels 2–3) ([1b4a469](https://github.com/cacack/mcp-server-zwave-js-ui/commit/1b4a46949126a3bcf0367ff8aaad38179f960497))
* close level-2/3 gaps — node name/location, status polls, validation, hide-gate ([c700963](https://github.com/cacack/mcp-server-zwave-js-ui/commit/c700963438ad2da58048f7ed1cb4460dac775f85))


### Bug Fixes

* label controller_type and protocol_version enum ints ([62607cc](https://github.com/cacack/mcp-server-zwave-js-ui/commit/62607cce284dec2e0cfdab6d73bd41379245ef9c)), closes [#2](https://github.com/cacack/mcp-server-zwave-js-ui/issues/2)

## [0.3.0](https://github.com/cacack/mcp-server-zwave-js-ui/compare/v0.2.0...v0.3.0) (2026-07-10)


### Features

* scaffold read-only Z-Wave MCP server ([411ba39](https://github.com/cacack/mcp-server-zwave-js-ui/commit/411ba39ecbfbcf41c64f11281aff3e79e8da4ff3))
* scaffold read-only Z-Wave MCP server ([d0b13f9](https://github.com/cacack/mcp-server-zwave-js-ui/commit/d0b13f9335516d03d178c9f2aa2adfab88321a18))


### Bug Fixes

* **release:** correct release tag format and __version__ sync ([494ec99](https://github.com/cacack/mcp-server-zwave-js-ui/commit/494ec9967be074fc925389f8229154550c764527))
* **release:** correct release tag format and __version__ sync ([7695173](https://github.com/cacack/mcp-server-zwave-js-ui/commit/7695173790219ae4a38b76858ec5634590be7baa))

## [0.2.0](https://github.com/cacack/mcp-server-zwave-js-ui/compare/mcp-server-zwave-js-ui-v0.1.0...mcp-server-zwave-js-ui-v0.2.0) (2026-07-10)


### Features

* scaffold read-only Z-Wave MCP server ([411ba39](https://github.com/cacack/mcp-server-zwave-js-ui/commit/411ba39ecbfbcf41c64f11281aff3e79e8da4ff3))
* scaffold read-only Z-Wave MCP server ([d0b13f9](https://github.com/cacack/mcp-server-zwave-js-ui/commit/d0b13f9335516d03d178c9f2aa2adfab88321a18))

## Changelog
