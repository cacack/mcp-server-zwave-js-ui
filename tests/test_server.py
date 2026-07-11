"""Tests for the MCP tool layer.

The tools are thin wrappers that open a connection and delegate to the
projections. Here the connection is patched with a fake driver so the tool
plumbing (registration, node lookup, delegation) is covered without a live
server; the projection logic itself is tested in test_client.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zwave_js_ui_mcp import server


def _driver_with_node(node_id=5):
    node = SimpleNamespace(node_id=node_id)
    controller = SimpleNamespace(nodes={node_id: node})
    return SimpleNamespace(controller=controller)


@pytest.fixture
def patched_driver(monkeypatch):
    driver = _driver_with_node()

    @asynccontextmanager
    async def fake_connected_driver():
        yield driver

    monkeypatch.setattr(server.client, "connected_driver", fake_connected_driver)
    return driver


@pytest.fixture(autouse=True)
def writable(monkeypatch):
    """Default every test to writable; read-only tests opt back in."""
    monkeypatch.delenv("ZWAVE_JS_READ_ONLY", raising=False)


async def test_expected_tools_are_registered():
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        # read-only (level 1)
        "zwave_controller_info",
        "zwave_list_nodes",
        "zwave_node_info",
        "zwave_node_values",
        "zwave_node_config",
        # write control (level 2)
        "zwave_set_value",
        "zwave_set_config_parameter",
        "zwave_association_groups",
        "zwave_associations",
        "zwave_add_association",
        "zwave_remove_association",
        # admin / lifecycle (level 3)
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


async def test_controller_info_delegates_to_projection(patched_driver, monkeypatch):
    monkeypatch.setattr(
        server.client, "project_controller", lambda d: {"home_id": 0xABCD}
    )
    assert await server.zwave_controller_info() == {"home_id": 0xABCD}


async def test_list_nodes_projects_each_node(patched_driver, monkeypatch):
    monkeypatch.setattr(
        server.client, "project_node_summary", lambda n: {"node_id": n.node_id}
    )
    assert await server.zwave_list_nodes() == [{"node_id": 5}]


async def test_node_info_unknown_node_raises(patched_driver):
    with pytest.raises(ValueError, match="No node with id 99"):
        await server.zwave_node_info(99)


async def test_set_value_delegates(patched_driver, monkeypatch):
    set_value = AsyncMock(return_value={"status": "SUCCESS"})
    monkeypatch.setattr(server.client, "set_value", set_value)
    result = await server.zwave_set_value(5, "5-38-0-targetValue", 99)
    assert result == {"status": "SUCCESS"}
    set_value.assert_awaited_once_with(patched_driver, 5, "5-38-0-targetValue", 99)


async def test_begin_inclusion_delegates(patched_driver, monkeypatch):
    begin = AsyncMock(return_value={"status": "inclusion_started"})
    monkeypatch.setattr(server.client, "begin_inclusion", begin)
    result = await server.zwave_begin_inclusion("s2")
    assert result == {"status": "inclusion_started"}
    begin.assert_awaited_once_with(patched_driver, "s2")


async def test_read_only_blocks_mutating_tool(monkeypatch):
    monkeypatch.setenv("ZWAVE_JS_READ_ONLY", "1")
    # Fail loudly if the gate lets execution reach the connection.
    monkeypatch.setattr(server.client, "connected_driver", _should_not_connect)
    with pytest.raises(PermissionError, match="ZWAVE_JS_READ_ONLY"):
        await server.zwave_set_value(5, "x", 1)


async def test_read_only_allows_reads(monkeypatch, patched_driver):
    monkeypatch.setenv("ZWAVE_JS_READ_ONLY", "1")
    monkeypatch.setattr(
        server.client, "project_node_summary", lambda n: {"node_id": n.node_id}
    )
    assert await server.zwave_list_nodes() == [{"node_id": 5}]


@asynccontextmanager
async def _should_not_connect():
    raise AssertionError("read-only gate should block before connecting")
    yield  # pragma: no cover
