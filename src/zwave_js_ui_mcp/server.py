"""MCP server for Z-Wave device management via zwave-js-server.

This is the read-only foundation (level 1): controller info, node listing and
detail, current values, and configuration parameters. Write control (setting
values and config parameters, associations) and administrative/lifecycle
operations (inclusion, re-interview, network heal, firmware update) are planned
follow-ups; when they land, mutating tools will be gated behind a
ZWAVE_JS_READ_ONLY env flag.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from zwave_js_ui_mcp import client

mcp = FastMCP("mcp-server-zwave-js-ui")


@mcp.tool()
async def zwave_controller_info() -> dict:
    """Get Z-Wave controller and network summary.

    Returns the controller's home id, type, SDK/API/firmware versions, RF
    region, primary/inclusion state, and node counts. Use this first for a
    quick health snapshot of the mesh.
    """
    async with client.connected_driver() as driver:
        return client.project_controller(driver)


@mcp.tool()
async def zwave_list_nodes() -> list[dict]:
    """List all Z-Wave nodes with a one-line summary each.

    Each entry has node id, name, location, status (alive/asleep/dead/etc.),
    readiness, listening/routing/sleep capability, security, manufacturer,
    device label, firmware version, and interview stage. Use zwave_node_info
    for full detail on a single node.
    """
    async with client.connected_driver() as driver:
        return [
            client.project_node_summary(node)
            for node in driver.controller.nodes.values()
        ]


@mcp.tool()
async def zwave_node_info(node_id: int) -> dict:
    """Get full detail for a single Z-Wave node.

    Includes device class, supported command classes, endpoint count, security
    class, protocol version, last-seen time, and signal statistics, on top of
    the summary fields. Raises ValueError if the node id is unknown.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return client.project_node_detail(client.get_node(driver, node_id))


@mcp.tool()
async def zwave_node_values(node_id: int) -> list[dict]:
    """List a node's current values (excluding configuration parameters).

    Returns each value's id, command class, endpoint, property, current
    reading, and metadata (label, unit, type, range, states, writeability).
    Configuration parameters are reported separately by zwave_node_config.
    Raises ValueError if the node id is unknown.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return client.project_node_values(client.get_node(driver, node_id))


@mcp.tool()
async def zwave_node_config(node_id: int) -> list[dict]:
    """List a node's configuration parameters and their current values.

    Returns each manufacturer-defined parameter with its current value,
    default, allowed range or named states, unit, size, and writeability —
    the device-specific tuning knobs (LED behavior, report intervals, motion
    sensitivity, etc.). This is a read-only view; setting parameters is a
    planned follow-up. Raises ValueError if the node id is unknown.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return client.project_node_config(client.get_node(driver, node_id))


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
