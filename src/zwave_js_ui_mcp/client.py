"""Connection to zwave-js-server, plus projections of and actions on its state.

The whole backend is isolated here: `server.py` only ever touches the plain
dicts these functions return (and the action functions they delegate to),
never a library object. That keeps the MCP tool layer independent of the
`zwave-js-server-python` object model, so the transport can be swapped without
touching the tools.

Connection model (per call, matching the stateless MCP tool style): open an
aiohttp session, connect the client (which negotiates the protocol schema),
run `client.listen()` as a background task — it issues `start_listening`,
populates `client.driver` with the full network state, and fires the
`driver_ready` event — then read the driver and tear everything down.

Mutating actions (set value/config, associations, lifecycle) live alongside
the read-only projections. `read_only()` reports whether the operator has
locked the server with `ZWAVE_JS_READ_ONLY`; the tool layer uses it to hide
the mutating tools from the registry entirely.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import aiohttp
from zwave_js_server.client import Client
from zwave_js_server.const import InclusionStrategy, ProtocolVersion
from zwave_js_server.model.association import AssociationAddress
from zwave_js_server.model.driver import Driver
from zwave_js_server.model.node import Node

DEFAULT_URL = "ws://localhost:3000"

# Configuration command class; its values are surfaced by the dedicated config
# tool, so the generic value listing filters them out to avoid duplication.
_CONFIGURATION_CC = 112

# protocol_version comes off the wire as a plain int; the library models the
# meaning as an enum, so derive the label table from it rather than copy it.
_PROTOCOL_VERSION_LABELS = {v.value: v.name for v in ProtocolVersion}

# controller_type is a raw int with no enum in zwave-js-server-python, so mirror
# node-zwave-js's ZWaveLibraryTypes here (sequential 0..11).
# https://github.com/zwave-js/zwave-js/blob/master/packages/core/src/definitions/LibraryTypes.ts
_CONTROLLER_TYPE_LABELS = {
    0: "Unknown",
    1: "Static Controller",
    2: "Controller",
    3: "Enhanced Slave",
    4: "Slave",
    5: "Installer",
    6: "Routing Slave",
    7: "Bridge Controller",
    8: "Device under Test",
    9: "N/A",
    10: "AV Remote",
    11: "AV Device",
}

# Bound the wait for the initial full-state dump so a wedged or wrong-URL
# connection fails fast instead of hanging the MCP tool call.
_CONNECT_TIMEOUT = 30.0

# Env values that count as "on" for the read-only lockdown flag.
_TRUTHY = {"1", "true", "yes", "on"}

# Inclusion strategies exposed to callers as short strings. SMART_START is
# omitted: it needs QR/provisioning data that doesn't fit a stateless call.
_INCLUSION_STRATEGIES = {
    "default": InclusionStrategy.DEFAULT,
    "s2": InclusionStrategy.SECURITY_S2,
    "s0": InclusionStrategy.SECURITY_S0,
    "insecure": InclusionStrategy.INSECURE,
}


def server_url() -> str:
    """WebSocket URL of the zwave-js-server, from ZWAVE_JS_URL."""
    return os.environ.get("ZWAVE_JS_URL", DEFAULT_URL)


def read_only() -> bool:
    """Whether mutating tools are disabled, per ZWAVE_JS_READ_ONLY."""
    return os.environ.get("ZWAVE_JS_READ_ONLY", "").strip().lower() in _TRUTHY


@asynccontextmanager
async def connected_driver() -> AsyncIterator[Driver]:
    """Connect, wait for full network state, and yield the ready Driver.

    Raises ConnectionError if the connection closes before the driver is
    ready, and TimeoutError if the initial state dump does not arrive in time.
    """
    async with aiohttp.ClientSession() as session:
        client = Client(server_url(), session)
        await client.connect()

        driver_ready = asyncio.Event()
        listen_task = asyncio.create_task(client.listen(driver_ready))
        ready_task = asyncio.create_task(driver_ready.wait())
        try:
            done, _ = await asyncio.wait(
                {listen_task, ready_task},
                timeout=_CONNECT_TIMEOUT,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if listen_task in done:
                # listen() returning before driver_ready means the socket
                # closed or errored during startup; surface its exception.
                exc = listen_task.exception()
                raise exc or ConnectionError(
                    "connection closed before the driver was ready"
                )
            if not done:
                raise TimeoutError(
                    f"driver not ready within {_CONNECT_TIMEOUT:.0f}s ({server_url()})"
                )
            assert client.driver is not None
            yield client.driver
        finally:
            ready_task.cancel()
            listen_task.cancel()
            with suppress(asyncio.CancelledError):
                await listen_task
            await client.disconnect()


def get_node(driver: Driver, node_id: int) -> Node:
    """Return the node with the given id, or raise ValueError if unknown."""
    node = driver.controller.nodes.get(node_id)
    if node is None:
        raise ValueError(f"No node with id {node_id}")
    return node


# --- Projections: library model objects -> plain JSON-serializable dicts ---


def _device_class_item(item: Any) -> str | None:
    """Human label of a DeviceClass generic/specific item, if present."""
    return getattr(item, "label", None) if item is not None else None


def _labeled(value: int | None, labels: dict[int, str]) -> dict | None:
    """Wrap a raw enum int as {value, label}; label is None for unknown ints."""
    if value is None:
        return None
    return {"value": value, "label": labels.get(value)}


def project_controller(driver: Driver) -> dict:
    """Controller / network summary."""
    c = driver.controller
    nodes = c.nodes.values()
    return {
        "home_id": c.home_id,
        "controller_type": _labeled(c.controller_type, _CONTROLLER_TYPE_LABELS),
        "sdk_version": c.sdk_version,
        "zwave_api_version": c.zwave_api_version,
        "firmware_version": c.firmware_version,
        "rf_region": getattr(c.rf_region, "name", c.rf_region),
        "is_primary": c.is_primary,
        "own_node_id": c.own_node_id,
        "supports_long_range": c.supports_long_range,
        "inclusion_state": getattr(c.inclusion_state, "name", c.inclusion_state),
        "status": getattr(c.status, "name", c.status),
        "node_count": len(c.nodes),
        "nodes_ready": sum(1 for n in nodes if n.ready),
    }


def project_node_summary(node: Node) -> dict:
    """One-line-per-node view for listings."""
    return {
        "node_id": node.node_id,
        "name": node.name,
        "location": node.location,
        "status": getattr(node.status, "name", node.status),
        "ready": node.ready,
        "is_listening": node.is_listening,
        "is_routing": node.is_routing,
        "can_sleep": node.can_sleep,
        "is_secure": node.is_secure,
        "manufacturer": node.manufacturer,
        "label": node.label,
        "firmware_version": node.firmware_version,
        "interview_stage": node.interview_stage,
    }


def project_node_detail(node: Node) -> dict:
    """Full detail for a single node."""
    device_class = node.device_class
    statistics = node.statistics
    return {
        **project_node_summary(node),
        "product_id": node.product_id,
        "product_type": node.product_type,
        "manufacturer_id": node.manufacturer_id,
        "hardware_version": node.hardware_version,
        "protocol_version": _labeled(node.protocol_version, _PROTOCOL_VERSION_LABELS),
        "highest_security_class": getattr(
            node.highest_security_class, "name", node.highest_security_class
        ),
        "is_frequent_listening": node.is_frequent_listening,
        "in_interview": node.in_interview,
        "last_seen": node.last_seen,
        "zwave_plus_version": node.zwave_plus_version,
        "device_class": {
            "generic": _device_class_item(getattr(device_class, "generic", None)),
            "specific": _device_class_item(getattr(device_class, "specific", None)),
        }
        if device_class is not None
        else None,
        "command_classes": sorted({cc.name for cc in node.command_classes if cc.name}),
        "endpoint_count": node.individual_endpoint_count,
        "statistics": {"rssi": getattr(statistics, "rssi", None)}
        if statistics is not None
        else None,
    }


def _project_metadata(metadata: Any) -> dict:
    """Useful subset of a value's metadata."""
    return {
        "label": metadata.label,
        "type": metadata.type,
        "unit": metadata.unit,
        "description": metadata.description,
        "readable": metadata.readable,
        "writeable": metadata.writeable,
        "min": metadata.min,
        "max": metadata.max,
        "states": metadata.states,
    }


def project_value(value: Any) -> dict:
    """A single Z-Wave value with its current reading and metadata."""
    return {
        "value_id": value.value_id,
        "command_class": value.command_class,
        "command_class_name": value.command_class_name,
        "endpoint": value.endpoint,
        "property_name": value.property_name,
        "property_key_name": value.property_key_name,
        "value": value.value,
        "metadata": _project_metadata(value.metadata),
    }


def project_node_values(node: Node) -> list[dict]:
    """All non-configuration values for a node (config has its own tool)."""
    return [
        project_value(v)
        for v in node.values.values()
        if v.command_class != _CONFIGURATION_CC
    ]


def project_config_value(cv: Any) -> dict:
    """A single configuration parameter with its current value and metadata."""
    metadata = cv.metadata
    return {
        "property": cv.property_,
        "property_key": cv.property_key,
        "label": metadata.label,
        "description": metadata.description,
        "value": cv.value,
        "default": metadata.default,
        "min": metadata.min,
        "max": metadata.max,
        "unit": metadata.unit,
        "states": metadata.states,
        "writeable": metadata.writeable,
        "value_size": metadata.value_size,
    }


def project_node_config(node: Node) -> list[dict]:
    """All configuration parameters for a node."""
    return [project_config_value(cv) for cv in node.get_configuration_values().values()]


# --- Result projections: library result objects -> plain dicts ---


def project_set_value_result(result: Any) -> dict:
    """Outcome of a setValue command as a plain dict.

    `result` is a library SetValueResult, or None when the server returns no
    result (the command was queued for a sleeping node).
    """
    if result is None:
        return {"status": "QUEUED", "message": None, "remaining_duration": None}
    remaining = getattr(result, "remaining_duration", None)
    return {
        "status": result.status.name,
        "message": result.message,
        "remaining_duration": str(remaining) if remaining is not None else None,
    }


def project_set_config_result(result: Any) -> dict:
    """Outcome of a setRawConfigParameterValue command as a plain dict."""
    inner = getattr(result, "result", None)
    supervision = getattr(getattr(inner, "status", None), "name", None)
    return {"status": result.status.name, "supervision": supervision}


def project_association_group(group: Any) -> dict:
    """An association group's capabilities."""
    return {
        "max_nodes": group.max_nodes,
        "is_lifeline": group.is_lifeline,
        "multi_channel": group.multi_channel,
        "label": group.label,
        "profile": group.profile,
    }


def project_association_address(address: Any) -> dict:
    """A single association target (node + optional endpoint)."""
    return {"node_id": address.node_id, "endpoint": address.endpoint}


# --- Actions: mutate the network, return a plain dict describing the outcome ---


def _check_writeable(metadata: Any, target: str) -> None:
    """Raise ValueError if the target's metadata marks it read-only."""
    if metadata.writeable is False:
        raise ValueError(f"{target} is not writeable")


def _check_numeric_range(metadata: Any, new_value: Any, target: str) -> None:
    """Raise ValueError if a numeric new_value falls outside metadata min/max.

    Booleans (binary switches) and non-numeric values are left to the device.
    """
    if isinstance(new_value, bool) or not isinstance(new_value, (int, float)):
        return
    if metadata.min is not None and new_value < metadata.min:
        raise ValueError(f"{target}: {new_value} is below minimum {metadata.min}")
    if metadata.max is not None and new_value > metadata.max:
        raise ValueError(f"{target}: {new_value} is above maximum {metadata.max}")


async def set_value(
    driver: Driver, node_id: int, value_id: str, new_value: Any
) -> dict:
    """Set a node value by value_id and report the command outcome.

    Validates against the value's live metadata: raises ValueError if the node
    or value_id is unknown, the value is not writeable, or a numeric value is
    out of the metadata's range.
    """
    node = get_node(driver, node_id)
    value = node.values.get(value_id)
    if value is None:
        raise ValueError(f"No value {value_id!r} on node {node_id}")
    target = f"Value {value_id!r}"
    _check_writeable(value.metadata, target)
    _check_numeric_range(value.metadata, new_value, target)
    result = await node.async_set_value(value, new_value, wait_for_result=True)
    return project_set_value_result(result)


def _find_config_value(node: Node, parameter: int, bitmask: int | None) -> Any:
    """The configuration value matching a parameter number and bit mask, or None."""
    for cv in node.get_configuration_values().values():
        if cv.property_ == parameter and cv.property_key == bitmask:
            return cv
    return None


async def set_config_parameter(
    driver: Driver,
    node_id: int,
    parameter: int,
    new_value: int,
    bitmask: int | None = None,
) -> dict:
    """Set a manufacturer configuration parameter and report the outcome.

    `parameter` is the parameter number (the `property` field from
    project_node_config); `bitmask` is the optional partial-parameter bit mask
    (its `property_key`). Validates against the parameter's live metadata:
    raises ValueError if the node or parameter is unknown, the parameter is not
    writeable, or the value is out of range.
    """
    node = get_node(driver, node_id)
    cv = _find_config_value(node, parameter, bitmask)
    if cv is None:
        suffix = f"[{bitmask}]" if bitmask is not None else ""
        raise ValueError(
            f"No configuration parameter {parameter}{suffix} on node {node_id}"
        )
    target = f"Parameter {parameter}"
    _check_writeable(cv.metadata, target)
    _check_numeric_range(cv.metadata, new_value, target)
    result = await node.async_set_raw_config_parameter_value(
        new_value, parameter, bitmask
    )
    return project_set_config_result(result)


async def set_node_name(driver: Driver, node_id: int, name: str) -> dict:
    """Set a node's name."""
    node = get_node(driver, node_id)
    await node.async_set_name(name)
    return {"status": "ok", "node_id": node_id, "name": name}


async def set_node_location(driver: Driver, node_id: int, location: str) -> dict:
    """Set a node's location."""
    node = get_node(driver, node_id)
    await node.async_set_location(location)
    return {"status": "ok", "node_id": node_id, "location": location}


def rebuild_routes_status(driver: Driver) -> dict:
    """Whether a network-wide route rebuild is in progress (from controller state)."""
    return {"is_rebuilding": driver.controller.is_rebuilding_routes}


async def firmware_update_status(driver: Driver) -> dict:
    """Whether any OTA firmware update is currently in progress."""
    in_progress = await driver.controller.async_is_firmware_update_in_progress()
    return {"in_progress": in_progress}


async def get_association_groups(
    driver: Driver, node_id: int, endpoint: int | None = None
) -> dict:
    """List a node endpoint's association groups, keyed by group id."""
    get_node(driver, node_id)
    source = AssociationAddress(driver.controller, node_id=node_id, endpoint=endpoint)
    groups = await driver.controller.async_get_association_groups(source)
    return {gid: project_association_group(g) for gid, g in groups.items()}


async def get_associations(
    driver: Driver, node_id: int, endpoint: int | None = None
) -> dict:
    """List a node endpoint's current associations, keyed by group id."""
    get_node(driver, node_id)
    source = AssociationAddress(driver.controller, node_id=node_id, endpoint=endpoint)
    associations = await driver.controller.async_get_associations(source)
    return {
        gid: [project_association_address(a) for a in addrs]
        for gid, addrs in associations.items()
    }


async def add_association(
    driver: Driver,
    node_id: int,
    group: int,
    target_node_id: int,
    source_endpoint: int | None = None,
    target_endpoint: int | None = None,
) -> dict:
    """Add `target_node_id` to a source node's association group."""
    get_node(driver, node_id)
    source = AssociationAddress(
        driver.controller, node_id=node_id, endpoint=source_endpoint
    )
    target = AssociationAddress(
        driver.controller, node_id=target_node_id, endpoint=target_endpoint
    )
    await driver.controller.async_add_associations(
        source, group, [target], wait_for_result=True
    )
    return {"status": "added", "node_id": node_id, "group": group}


async def remove_association(
    driver: Driver,
    node_id: int,
    group: int,
    target_node_id: int,
    source_endpoint: int | None = None,
    target_endpoint: int | None = None,
) -> dict:
    """Remove `target_node_id` from a source node's association group."""
    get_node(driver, node_id)
    source = AssociationAddress(
        driver.controller, node_id=node_id, endpoint=source_endpoint
    )
    target = AssociationAddress(
        driver.controller, node_id=target_node_id, endpoint=target_endpoint
    )
    await driver.controller.async_remove_associations(
        source, group, [target], wait_for_result=True
    )
    return {"status": "removed", "node_id": node_id, "group": group}


async def reinterview_node(driver: Driver, node_id: int) -> dict:
    """Re-run a node's interview (refreshInfo). Fire-and-forget."""
    node = get_node(driver, node_id)
    await node.async_refresh_info()
    return {"status": "started", "node_id": node_id}


async def rebuild_node_routes(driver: Driver, node_id: int) -> dict:
    """Rebuild mesh routes for a single node."""
    node = get_node(driver, node_id)
    success = await driver.controller.async_rebuild_node_routes(node)
    return {"node_id": node_id, "success": success}


async def begin_rebuilding_routes(driver: Driver) -> dict:
    """Start a network-wide route rebuild (network heal)."""
    success = await driver.controller.async_begin_rebuilding_routes()
    return {"status": "started", "success": success}


async def stop_rebuilding_routes(driver: Driver) -> dict:
    """Stop an in-progress network-wide route rebuild."""
    success = await driver.controller.async_stop_rebuilding_routes()
    return {"status": "stopped", "success": success}


async def remove_failed_node(driver: Driver, node_id: int) -> dict:
    """Remove a node the controller has marked failed from the network."""
    node = get_node(driver, node_id)
    await driver.controller.async_remove_failed_node(node)
    return {"status": "removed", "node_id": node_id}


async def begin_inclusion(driver: Driver, strategy: str = "default") -> dict:
    """Put the controller into inclusion mode to add a node.

    Returns as soon as inclusion mode is entered; the physical add and any
    secure (S2) bootstrap happen afterward via events this stateless call does
    not observe. Raises ValueError for an unknown strategy.
    """
    key = strategy.strip().lower()
    if key not in _INCLUSION_STRATEGIES:
        raise ValueError(
            f"Unknown inclusion strategy {strategy!r}; "
            f"expected one of {sorted(_INCLUSION_STRATEGIES)}"
        )
    success = await driver.controller.async_begin_inclusion(_INCLUSION_STRATEGIES[key])
    return {"status": "inclusion_started", "strategy": key, "success": success}


async def stop_inclusion(driver: Driver) -> dict:
    """Take the controller out of inclusion mode."""
    success = await driver.controller.async_stop_inclusion()
    return {"status": "inclusion_stopped", "success": success}


async def begin_exclusion(driver: Driver) -> dict:
    """Put the controller into exclusion mode to remove a node."""
    success = await driver.controller.async_begin_exclusion()
    return {"status": "exclusion_started", "success": success}


async def stop_exclusion(driver: Driver) -> dict:
    """Take the controller out of exclusion mode."""
    success = await driver.controller.async_stop_exclusion()
    return {"status": "exclusion_stopped", "success": success}
