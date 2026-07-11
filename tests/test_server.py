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


_READ_ONLY_TOOLS = {
    "zwave_controller_info",
    "zwave_list_nodes",
    "zwave_node_info",
    "zwave_node_values",
    "zwave_node_config",
    "zwave_rebuild_routes_status",
    "zwave_firmware_update_status",
    "zwave_association_groups",
    "zwave_associations",
}


async def test_expected_tools_are_registered():
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == _READ_ONLY_TOOLS | server._MUTATING_TOOLS


async def test_read_only_and_mutating_sets_are_disjoint():
    # Every registered tool is classified exactly once, so a new mutating tool
    # can't silently escape the read-only gate.
    assert _READ_ONLY_TOOLS.isdisjoint(server._MUTATING_TOOLS)


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


async def test_set_node_name_delegates(patched_driver, monkeypatch):
    set_name = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr(server.client, "set_node_name", set_name)
    result = await server.zwave_set_node_name(5, "Porch Light")
    assert result == {"status": "ok"}
    set_name.assert_awaited_once_with(patched_driver, 5, "Porch Light")


async def test_firmware_update_status_delegates(patched_driver, monkeypatch):
    status = AsyncMock(return_value={"in_progress": False})
    monkeypatch.setattr(server.client, "firmware_update_status", status)
    assert await server.zwave_firmware_update_status() == {"in_progress": False}
    status.assert_awaited_once_with(patched_driver)


async def test_begin_inclusion_delegates(patched_driver, monkeypatch):
    begin = AsyncMock(return_value={"status": "inclusion_started"})
    monkeypatch.setattr(server.client, "begin_inclusion", begin)
    result = await server.zwave_begin_inclusion("s2")
    assert result == {"status": "inclusion_started"}
    begin.assert_awaited_once_with(patched_driver, "s2")


@pytest.fixture
def restore_registry():
    """Snapshot and restore the tool registry around a read-only mutation."""
    saved = dict(server.mcp._tool_manager._tools)
    yield
    server.mcp._tool_manager._tools.clear()
    server.mcp._tool_manager._tools.update(saved)


async def test_read_only_hides_mutating_tools(monkeypatch, restore_registry):
    monkeypatch.setenv("ZWAVE_JS_READ_ONLY", "1")
    server._apply_read_only()
    names = {t.name for t in await server.mcp.list_tools()}
    assert names == _READ_ONLY_TOOLS
    assert names.isdisjoint(server._MUTATING_TOOLS)


async def test_apply_read_only_is_noop_when_writable(restore_registry):
    before = {t.name for t in await server.mcp.list_tools()}
    server._apply_read_only()  # writable fixture leaves ZWAVE_JS_READ_ONLY unset
    after = {t.name for t in await server.mcp.list_tools()}
    assert before == after == _READ_ONLY_TOOLS | server._MUTATING_TOOLS
