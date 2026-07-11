"""MCP server for Z-Wave device management via zwave-js-server.

Read (level 1): controller info, node listing/detail, values, config params,
association views, rebuild-routes and firmware-update status.
Write (level 2): set values, config parameters, node name/location, associations.
Admin/lifecycle (level 3): re-interview, single-node and network route rebuild,
inclusion/exclusion, remove failed node.

Setting ZWAVE_JS_READ_ONLY removes the mutating tools (`_MUTATING_TOOLS`) from
the registry entirely, so a locked-down server only exposes the read tools.

Not yet implemented: triggering an OTA firmware update. Flashing streams
progress events over minutes, which the per-call connection model can't observe
within one tool call; delivering it needs a persistent-connection design (see
CLAUDE.md). `zwave_firmware_update_status` reports whether one is in progress.
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
    quick health snapshot of the mesh. `controller_type` is a
    {"value": int, "label": str} object (label is null for an unmapped code).
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
    the summary fields. `protocol_version` is a {"value": int, "label": str}
    object (label is null for an unmapped code). Raises ValueError if the node
    id is unknown.

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
    sensitivity, etc.). Set a parameter with zwave_set_config_parameter.
    Raises ValueError if the node id is unknown.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return client.project_node_config(client.get_node(driver, node_id))


@mcp.tool()
async def zwave_rebuild_routes_status() -> dict:
    """Report whether a network-wide route rebuild (heal) is in progress.

    Returns {"is_rebuilding": bool | null} from the controller state. Poll this
    after zwave_begin_rebuilding_routes to track a heal to completion.
    """
    async with client.connected_driver() as driver:
        return client.rebuild_routes_status(driver)


@mcp.tool()
async def zwave_firmware_update_status() -> dict:
    """Report whether an OTA firmware update is currently in progress.

    Returns {"in_progress": bool}. (Triggering an update is not yet supported;
    see the project roadmap.)
    """
    async with client.connected_driver() as driver:
        return await client.firmware_update_status(driver)


# --- Write control (level 2). Hidden when ZWAVE_JS_READ_ONLY is set. ---


@mcp.tool()
async def zwave_set_value(node_id: int, value_id: str, value: object) -> dict:
    """Set a Z-Wave value and report the command outcome.

    `value_id` is the id from zwave_node_values (e.g. "5-38-0-targetValue").
    `value` must match the value's type (a number, bool, or string as its
    metadata describes). Returns the command status (SUCCESS, WORKING, FAIL,
    QUEUED for a sleeping node, etc.) with any message. Raises ValueError for
    an unknown node id; the value must exist on the node and be writeable.

    Args:
        node_id: The Z-Wave node id, e.g. 5
        value_id: The value id from zwave_node_values
        value: The new value to set
    """
    async with client.connected_driver() as driver:
        return await client.set_value(driver, node_id, value_id, value)


@mcp.tool()
async def zwave_set_config_parameter(
    node_id: int, parameter: int, value: int, bitmask: int | None = None
) -> dict:
    """Set a node's manufacturer configuration parameter.

    `parameter` is the parameter number (the `property` field from
    zwave_node_config). `bitmask` is the optional partial-parameter bit mask
    (its `property_key`); omit it for whole-parameter writes. Returns the
    command status (ACCEPTED or QUEUED). Raises ValueError for an unknown node.

    Args:
        node_id: The Z-Wave node id, e.g. 5
        parameter: The configuration parameter number
        value: The new integer value
        bitmask: Optional partial-parameter bit mask
    """
    async with client.connected_driver() as driver:
        return await client.set_config_parameter(
            driver, node_id, parameter, value, bitmask
        )


@mcp.tool()
async def zwave_set_node_name(node_id: int, name: str) -> dict:
    """Set a node's friendly name.

    Raises ValueError for an unknown node id.

    Args:
        node_id: The Z-Wave node id, e.g. 5
        name: The new name for the node
    """
    async with client.connected_driver() as driver:
        return await client.set_node_name(driver, node_id, name)


@mcp.tool()
async def zwave_set_node_location(node_id: int, location: str) -> dict:
    """Set a node's location label.

    Raises ValueError for an unknown node id.

    Args:
        node_id: The Z-Wave node id, e.g. 5
        location: The new location for the node
    """
    async with client.connected_driver() as driver:
        return await client.set_node_location(driver, node_id, location)


@mcp.tool()
async def zwave_association_groups(node_id: int, endpoint: int | None = None) -> dict:
    """List a node's association groups and their capabilities.

    Returns each group id mapped to its max node count, lifeline flag,
    multi-channel flag, and label. Use this to find the group to pass to
    zwave_add_association. Raises ValueError for an unknown node id.

    Args:
        node_id: The source Z-Wave node id, e.g. 5
        endpoint: Optional endpoint index (defaults to the root device)
    """
    async with client.connected_driver() as driver:
        return await client.get_association_groups(driver, node_id, endpoint)


@mcp.tool()
async def zwave_associations(node_id: int, endpoint: int | None = None) -> dict:
    """List a node's current associations, keyed by group id.

    Each group maps to a list of association targets ({node_id, endpoint}).
    Raises ValueError for an unknown node id.

    Args:
        node_id: The source Z-Wave node id, e.g. 5
        endpoint: Optional endpoint index (defaults to the root device)
    """
    async with client.connected_driver() as driver:
        return await client.get_associations(driver, node_id, endpoint)


@mcp.tool()
async def zwave_add_association(
    node_id: int,
    group: int,
    target_node_id: int,
    source_endpoint: int | None = None,
    target_endpoint: int | None = None,
) -> dict:
    """Add an association from a source node's group to a target node.

    Associations let a device control another directly (e.g. a switch driving
    a light). Use zwave_association_groups to pick a valid group. Raises
    ValueError for an unknown source node id.

    Args:
        node_id: The source Z-Wave node id, e.g. 5
        group: The association group id on the source node
        target_node_id: The node id to associate into the group
        source_endpoint: Optional source endpoint (defaults to the root device)
        target_endpoint: Optional target endpoint (defaults to the root device)
    """
    async with client.connected_driver() as driver:
        return await client.add_association(
            driver, node_id, group, target_node_id, source_endpoint, target_endpoint
        )


@mcp.tool()
async def zwave_remove_association(
    node_id: int,
    group: int,
    target_node_id: int,
    source_endpoint: int | None = None,
    target_endpoint: int | None = None,
) -> dict:
    """Remove an association from a source node's group to a target node.

    Raises ValueError for an unknown source node id.

    Args:
        node_id: The source Z-Wave node id, e.g. 5
        group: The association group id on the source node
        target_node_id: The associated node id to remove from the group
        source_endpoint: Optional source endpoint (defaults to the root device)
        target_endpoint: Optional target endpoint (defaults to the root device)
    """
    async with client.connected_driver() as driver:
        return await client.remove_association(
            driver, node_id, group, target_node_id, source_endpoint, target_endpoint
        )


# --- Admin / lifecycle (level 3). Hidden when ZWAVE_JS_READ_ONLY is set. ---


@mcp.tool()
async def zwave_reinterview_node(node_id: int) -> dict:
    """Re-run a node's interview to refresh its capabilities and values.

    Fire-and-forget: returns once the interview is requested; the interview
    itself runs in the background and can take a while for battery devices.
    Raises ValueError for an unknown node id.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return await client.reinterview_node(driver, node_id)


@mcp.tool()
async def zwave_rebuild_node_routes(node_id: int) -> dict:
    """Rebuild mesh network routes for a single node.

    Returns {node_id, success}. Raises ValueError for an unknown node id.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return await client.rebuild_node_routes(driver, node_id)


@mcp.tool()
async def zwave_begin_rebuilding_routes() -> dict:
    """Start a network-wide route rebuild (network heal).

    Returns once the rebuild is started; it proceeds in the background across
    the whole mesh. Use zwave_stop_rebuilding_routes to cancel.
    """
    async with client.connected_driver() as driver:
        return await client.begin_rebuilding_routes(driver)


@mcp.tool()
async def zwave_stop_rebuilding_routes() -> dict:
    """Stop an in-progress network-wide route rebuild."""
    async with client.connected_driver() as driver:
        return await client.stop_rebuilding_routes(driver)


@mcp.tool()
async def zwave_remove_failed_node(node_id: int) -> dict:
    """Remove a node the controller has marked failed from the network.

    Only works on nodes the controller considers failed (dead/unreachable).
    Raises ValueError for an unknown node id.

    Args:
        node_id: The Z-Wave node id, e.g. 5
    """
    async with client.connected_driver() as driver:
        return await client.remove_failed_node(driver, node_id)


@mcp.tool()
async def zwave_begin_inclusion(strategy: str = "default") -> dict:
    """Put the controller into inclusion mode to add a new node.

    Returns as soon as inclusion mode is entered; put the device into pairing
    mode to complete the add. `strategy` is one of "default", "s2", "s0", or
    "insecure". Note: interactive S2 security bootstrap (DSK/PIN grant) cannot
    complete through this stateless server — use the Z-Wave JS UI for secure
    inclusion. Use zwave_stop_inclusion to cancel.

    Args:
        strategy: Inclusion strategy — "default", "s2", "s0", or "insecure"
    """
    async with client.connected_driver() as driver:
        return await client.begin_inclusion(driver, strategy)


@mcp.tool()
async def zwave_stop_inclusion() -> dict:
    """Take the controller out of inclusion mode."""
    async with client.connected_driver() as driver:
        return await client.stop_inclusion(driver)


@mcp.tool()
async def zwave_begin_exclusion() -> dict:
    """Put the controller into exclusion mode to remove a node.

    Returns as soon as exclusion mode is entered; put the device into its
    exclusion/unpair mode to complete removal. Use zwave_stop_exclusion to
    cancel.
    """
    async with client.connected_driver() as driver:
        return await client.begin_exclusion(driver)


@mcp.tool()
async def zwave_stop_exclusion() -> dict:
    """Take the controller out of exclusion mode."""
    async with client.connected_driver() as driver:
        return await client.stop_exclusion(driver)


# Tools that change network or device state. When ZWAVE_JS_READ_ONLY is set
# these are removed from the registry (see _apply_read_only), so a locked-down
# server never even advertises them.
_MUTATING_TOOLS = frozenset(
    {
        "zwave_set_value",
        "zwave_set_config_parameter",
        "zwave_set_node_name",
        "zwave_set_node_location",
        "zwave_add_association",
        "zwave_remove_association",
        "zwave_reinterview_node",
        "zwave_rebuild_node_routes",
        "zwave_begin_rebuilding_routes",
        "zwave_stop_rebuilding_routes",
        "zwave_remove_failed_node",
        "zwave_begin_inclusion",
        "zwave_stop_inclusion",
        "zwave_begin_exclusion",
        "zwave_stop_exclusion",
    }
)


def _apply_read_only() -> None:
    """Remove the mutating tools from the registry when read-only is enabled."""
    if client.read_only():
        for name in _MUTATING_TOOLS:
            mcp.remove_tool(name)


_apply_read_only()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
