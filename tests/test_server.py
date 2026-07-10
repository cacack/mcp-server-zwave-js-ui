"""Tests for the MCP tool layer.

The tools are thin wrappers that open a connection and delegate to the
projections. Here the connection is patched with a fake driver so the tool
plumbing (registration, node lookup, delegation) is covered without a live
server; the projection logic itself is tested in test_client.py.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

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


async def test_expected_read_only_tools_are_registered():
    tools = await server.mcp.list_tools()
    names = {t.name for t in tools}
    assert names == {
        "zwave_controller_info",
        "zwave_list_nodes",
        "zwave_node_info",
        "zwave_node_values",
        "zwave_node_config",
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
