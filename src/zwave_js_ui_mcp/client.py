"""Connection to zwave-js-server and read-only projections of its state.

The whole backend is isolated here: `server.py` only ever touches the plain
dicts these functions return, never a library object. That keeps the MCP tool
layer independent of the `zwave-js-server-python` object model, so the
transport can be swapped without touching the tools.

Connection model (per call, matching the stateless MCP tool style): open an
aiohttp session, connect the client (which negotiates the protocol schema),
run `client.listen()` as a background task — it issues `start_listening`,
populates `client.driver` with the full network state, and fires the
`driver_ready` event — then read the driver and tear everything down.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

import aiohttp
from zwave_js_server.client import Client
from zwave_js_server.model.driver import Driver
from zwave_js_server.model.node import Node

DEFAULT_URL = "ws://localhost:3000"

# Configuration command class; its values are surfaced by the dedicated config
# tool, so the generic value listing filters them out to avoid duplication.
_CONFIGURATION_CC = 112

# Bound the wait for the initial full-state dump so a wedged or wrong-URL
# connection fails fast instead of hanging the MCP tool call.
_CONNECT_TIMEOUT = 30.0


def server_url() -> str:
    """WebSocket URL of the zwave-js-server, from ZWAVE_JS_URL."""
    return os.environ.get("ZWAVE_JS_URL", DEFAULT_URL)


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


def project_controller(driver: Driver) -> dict:
    """Controller / network summary."""
    c = driver.controller
    nodes = c.nodes.values()
    return {
        "home_id": c.home_id,
        "controller_type": c.controller_type,
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
        "protocol_version": getattr(
            node.protocol_version, "name", node.protocol_version
        ),
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
