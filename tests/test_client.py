"""Tests for the projection helpers and node lookup in client.py.

The projections are pure functions over the library model objects, so they are
exercised here with lightweight fakes that expose just the attributes each
projection reads. This keeps the tests fast and free of a live server while
still covering the field-mapping logic, which is where bugs actually hide.
"""

from __future__ import annotations

from enum import Enum
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from zwave_js_server.const import InclusionStrategy

from zwave_js_ui_mcp import client


class _Status(Enum):
    ALIVE = 4


def _metadata(**overrides) -> SimpleNamespace:
    base = {
        "label": "Test",
        "type": "number",
        "unit": None,
        "description": None,
        "readable": True,
        "writeable": True,
        "min": 0,
        "max": 100,
        "states": None,
        "default": 0,
        "value_size": 1,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _node(node_id=5, **overrides) -> SimpleNamespace:
    base = {
        "node_id": node_id,
        "name": "Office Lamp",
        "location": "Office",
        "status": _Status.ALIVE,
        "ready": True,
        "is_listening": True,
        "is_routing": True,
        "can_sleep": False,
        "is_secure": True,
        "manufacturer": "Acme",
        "label": "Dimmer",
        "firmware_version": "1.2",
        "interview_stage": "Complete",
        "product_id": 1,
        "product_type": 2,
        "manufacturer_id": 3,
        "hardware_version": 1,
        "protocol_version": 3,
        "highest_security_class": "S2_Authenticated",
        "is_frequent_listening": False,
        "in_interview": False,
        "last_seen": "2026-07-09T00:00:00Z",
        "zwave_plus_version": 2,
        "device_class": SimpleNamespace(
            generic=SimpleNamespace(label="Multilevel Switch"),
            specific=SimpleNamespace(label="Multilevel Power Switch"),
        ),
        "command_classes": [
            SimpleNamespace(name="Configuration"),
            SimpleNamespace(name="Multilevel Switch"),
        ],
        "individual_endpoint_count": 1,
        "statistics": SimpleNamespace(rssi=-60),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _value(command_class=38, **overrides) -> SimpleNamespace:
    base = {
        "value_id": "5-38-0-currentValue",
        "command_class": command_class,
        "command_class_name": "Multilevel Switch",
        "endpoint": 0,
        "property_name": "currentValue",
        "property_key_name": None,
        "value": 99,
        "metadata": _metadata(label="Current value"),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _config_value(prop=1, **overrides) -> SimpleNamespace:
    base = {
        "property_": prop,
        "property_key": None,
        "value": 10,
        "metadata": _metadata(
            label="Ramp rate", description="Dimming ramp", default=5, states=None
        ),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _driver(nodes, **overrides) -> SimpleNamespace:
    base = dict(
        home_id=0xABCD,
        controller_type=1,
        sdk_version="7.0",
        zwave_api_version="1.0",
        firmware_version="1.0",
        rf_region="USA",
        is_primary=True,
        own_node_id=1,
        supports_long_range=False,
        inclusion_state="Idle",
        status="Ready",
        nodes={n.node_id: n for n in nodes},
    )
    base.update(overrides)
    return SimpleNamespace(controller=SimpleNamespace(**base))


def test_get_node_found():
    node = _node(node_id=7)
    driver = _driver([node])
    assert client.get_node(driver, 7) is node


def test_get_node_missing_raises():
    driver = _driver([])
    with pytest.raises(ValueError, match="No node with id 99"):
        client.get_node(driver, 99)


def test_project_controller_counts_ready_nodes():
    driver = _driver([_node(node_id=2, ready=True), _node(node_id=3, ready=False)])
    result = client.project_controller(driver)
    assert result["home_id"] == 0xABCD
    assert result["node_count"] == 2
    assert result["nodes_ready"] == 1
    assert result["is_primary"] is True


def test_project_controller_labels_controller_type():
    result = client.project_controller(_driver([]))
    assert result["controller_type"] == {"value": 1, "label": "Static Controller"}


def test_project_controller_labels_unknown_controller_type():
    result = client.project_controller(_driver([], controller_type=99))
    assert result["controller_type"] == {"value": 99, "label": None}


def test_project_controller_handles_none_controller_type():
    result = client.project_controller(_driver([], controller_type=None))
    assert result["controller_type"] is None


def test_project_node_detail_labels_protocol_version():
    result = client.project_node_detail(_node())
    assert result["protocol_version"] == {
        "value": 3,
        "label": "VERSION_4_5X_OR_6_0X",
    }


def test_project_node_detail_handles_none_protocol_version():
    result = client.project_node_detail(_node(protocol_version=None))
    assert result["protocol_version"] is None


def test_project_node_summary_serializes_status_enum():
    result = client.project_node_summary(_node())
    assert result["node_id"] == 5
    assert result["status"] == "ALIVE"
    assert result["name"] == "Office Lamp"


def test_project_node_detail_flattens_device_class():
    result = client.project_node_detail(_node())
    assert result["device_class"] == {
        "generic": "Multilevel Switch",
        "specific": "Multilevel Power Switch",
    }
    assert result["command_classes"] == ["Configuration", "Multilevel Switch"]
    assert result["statistics"] == {"rssi": -60}


def test_project_node_detail_handles_missing_device_class():
    result = client.project_node_detail(_node(device_class=None))
    assert result["device_class"] is None


def test_project_node_values_excludes_configuration_cc():
    node = _node()
    node.values = {
        "a": _value(command_class=38),
        "b": _value(command_class=client._CONFIGURATION_CC),
    }
    result = client.project_node_values(node)
    assert len(result) == 1
    assert result[0]["command_class"] == 38
    assert result[0]["metadata"]["label"] == "Current value"


def test_project_node_config_maps_parameters():
    node = _node()
    node.get_configuration_values = lambda: {"1": _config_value(prop=1)}
    result = client.project_node_config(node)
    assert result == [
        {
            "property": 1,
            "property_key": None,
            "label": "Ramp rate",
            "description": "Dimming ramp",
            "value": 10,
            "default": 5,
            "min": 0,
            "max": 100,
            "unit": None,
            "states": None,
            "writeable": True,
            "value_size": 1,
        }
    ]


def test_server_url_defaults(monkeypatch):
    monkeypatch.delenv("ZWAVE_JS_URL", raising=False)
    assert client.server_url() == client.DEFAULT_URL


def test_server_url_from_env(monkeypatch):
    monkeypatch.setenv("ZWAVE_JS_URL", "ws://zwave.example:3000")
    assert client.server_url() == "ws://zwave.example:3000"


# --- Read-only gate ---


def test_read_only_unset_is_false(monkeypatch):
    monkeypatch.delenv("ZWAVE_JS_READ_ONLY", raising=False)
    assert client.read_only() is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on"])
def test_read_only_truthy_values(monkeypatch, value):
    monkeypatch.setenv("ZWAVE_JS_READ_ONLY", value)
    assert client.read_only() is True


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_read_only_falsey_values(monkeypatch, value):
    monkeypatch.setenv("ZWAVE_JS_READ_ONLY", value)
    assert client.read_only() is False


# --- Result projections ---


def test_project_set_value_result_maps_status():
    result = SimpleNamespace(
        status=SimpleNamespace(name="SUCCESS"), message=None, remaining_duration=None
    )
    assert client.project_set_value_result(result) == {
        "status": "SUCCESS",
        "message": None,
        "remaining_duration": None,
    }


def test_project_set_value_result_stringifies_remaining_duration():
    result = SimpleNamespace(
        status=SimpleNamespace(name="WORKING"), message=None, remaining_duration="10s"
    )
    assert client.project_set_value_result(result)["remaining_duration"] == "10s"


def test_project_set_value_result_none_is_queued():
    assert client.project_set_value_result(None) == {
        "status": "QUEUED",
        "message": None,
        "remaining_duration": None,
    }


def test_project_set_config_result_without_supervision():
    result = SimpleNamespace(status=SimpleNamespace(name="ACCEPTED"), result=None)
    assert client.project_set_config_result(result) == {
        "status": "ACCEPTED",
        "supervision": None,
    }


def test_project_set_config_result_with_supervision():
    result = SimpleNamespace(
        status=SimpleNamespace(name="ACCEPTED"),
        result=SimpleNamespace(status=SimpleNamespace(name="SUCCESS")),
    )
    assert client.project_set_config_result(result)["supervision"] == "SUCCESS"


def test_project_association_group():
    group = SimpleNamespace(
        max_nodes=5,
        is_lifeline=True,
        multi_channel=False,
        label="Lifeline",
        profile=None,
    )
    assert client.project_association_group(group) == {
        "max_nodes": 5,
        "is_lifeline": True,
        "multi_channel": False,
        "label": "Lifeline",
        "profile": None,
    }


def test_project_association_address():
    addr = SimpleNamespace(node_id=7, endpoint=2)
    assert client.project_association_address(addr) == {"node_id": 7, "endpoint": 2}


# --- Actions ---


def _action_driver(node_id=5, controller=None, **node_methods):
    """Driver whose node and controller carry AsyncMock command methods."""
    node = SimpleNamespace(node_id=node_id, **node_methods)
    controller = controller or SimpleNamespace()
    controller.nodes = {node_id: node}
    return SimpleNamespace(controller=controller), node


def _writeable_value(**md):
    """A Value stand-in exposing just the metadata set_value inspects."""
    return SimpleNamespace(metadata=_metadata(**md))


def _cfg_value(prop=3, key=None, **md):
    """A ConfigurationValue stand-in for set_config_parameter lookups."""
    return SimpleNamespace(property_=prop, property_key=key, metadata=_metadata(**md))


def _set_value_ok():
    return AsyncMock(
        return_value=SimpleNamespace(
            status=SimpleNamespace(name="SUCCESS"),
            message=None,
            remaining_duration=None,
        )
    )


async def test_set_value_delegates_and_projects():
    val = _writeable_value(min=0, max=99)
    driver, node = _action_driver(
        values={"5-38-0-targetValue": val}, async_set_value=_set_value_ok()
    )
    result = await client.set_value(driver, 5, "5-38-0-targetValue", 99)
    assert result["status"] == "SUCCESS"
    # the resolved Value object is passed, not the value_id string
    node.async_set_value.assert_awaited_once_with(val, 99, wait_for_result=True)


async def test_set_value_unknown_node_raises():
    driver, _ = _action_driver()
    with pytest.raises(ValueError, match="No node with id 99"):
        await client.set_value(driver, 99, "x", 1)


async def test_set_value_unknown_value_id_raises():
    driver, _ = _action_driver(values={}, async_set_value=_set_value_ok())
    with pytest.raises(ValueError, match="No value 'x-1-0' on node 5"):
        await client.set_value(driver, 5, "x-1-0", 1)


async def test_set_value_unwriteable_raises():
    val = _writeable_value(writeable=False)
    driver, node = _action_driver(
        values={"5-38-0-currentValue": val}, async_set_value=_set_value_ok()
    )
    with pytest.raises(ValueError, match="is not writeable"):
        await client.set_value(driver, 5, "5-38-0-currentValue", 1)
    node.async_set_value.assert_not_awaited()


async def test_set_value_out_of_range_raises():
    val = _writeable_value(min=0, max=99)
    driver, node = _action_driver(
        values={"5-38-0-targetValue": val}, async_set_value=_set_value_ok()
    )
    with pytest.raises(ValueError, match="above maximum 99"):
        await client.set_value(driver, 5, "5-38-0-targetValue", 200)
    node.async_set_value.assert_not_awaited()


async def test_set_value_allows_boolean_regardless_of_range():
    val = _writeable_value(min=0, max=99, type="boolean")
    driver, node = _action_driver(
        values={"5-37-0-targetValue": val}, async_set_value=_set_value_ok()
    )
    await client.set_value(driver, 5, "5-37-0-targetValue", True)
    node.async_set_value.assert_awaited_once_with(val, True, wait_for_result=True)


def _set_config_ok():
    return AsyncMock(
        return_value=SimpleNamespace(
            status=SimpleNamespace(name="ACCEPTED"), result=None
        )
    )


async def test_set_config_parameter_delegates_and_projects():
    cv = _cfg_value(prop=3, min=0, max=100)
    driver, node = _action_driver(
        get_configuration_values=lambda: {"5-112-0-3": cv},
        async_set_raw_config_parameter_value=_set_config_ok(),
    )
    result = await client.set_config_parameter(driver, 5, 3, 10, bitmask=None)
    assert result == {"status": "ACCEPTED", "supervision": None}
    node.async_set_raw_config_parameter_value.assert_awaited_once_with(10, 3, None)


async def test_set_config_parameter_unknown_raises():
    driver, node = _action_driver(
        get_configuration_values=lambda: {},
        async_set_raw_config_parameter_value=_set_config_ok(),
    )
    with pytest.raises(ValueError, match="No configuration parameter 7 on node 5"):
        await client.set_config_parameter(driver, 5, 7, 1)
    node.async_set_raw_config_parameter_value.assert_not_awaited()


async def test_set_config_parameter_out_of_range_raises():
    cv = _cfg_value(prop=3, min=0, max=100)
    driver, node = _action_driver(
        get_configuration_values=lambda: {"5-112-0-3": cv},
        async_set_raw_config_parameter_value=_set_config_ok(),
    )
    with pytest.raises(ValueError, match="above maximum 100"):
        await client.set_config_parameter(driver, 5, 3, 500)
    node.async_set_raw_config_parameter_value.assert_not_awaited()


async def test_set_node_name_delegates():
    driver, node = _action_driver(async_set_name=AsyncMock(return_value=None))
    result = await client.set_node_name(driver, 5, "Porch Light")
    assert result == {"status": "ok", "node_id": 5, "name": "Porch Light"}
    node.async_set_name.assert_awaited_once_with("Porch Light")


async def test_set_node_location_delegates():
    driver, node = _action_driver(async_set_location=AsyncMock(return_value=None))
    result = await client.set_node_location(driver, 5, "Porch")
    assert result == {"status": "ok", "node_id": 5, "location": "Porch"}
    node.async_set_location.assert_awaited_once_with("Porch")


async def test_rebuild_routes_status_reads_controller():
    controller = SimpleNamespace(is_rebuilding_routes=True)
    driver, _ = _action_driver(controller=controller)
    assert client.rebuild_routes_status(driver) == {"is_rebuilding": True}


async def test_firmware_update_status_queries_controller():
    controller = SimpleNamespace(
        async_is_firmware_update_in_progress=AsyncMock(return_value=False)
    )
    driver, _ = _action_driver(controller=controller)
    assert await client.firmware_update_status(driver) == {"in_progress": False}


async def test_get_association_groups_projects_each():
    controller = SimpleNamespace(
        async_get_association_groups=AsyncMock(
            return_value={
                1: SimpleNamespace(
                    max_nodes=5,
                    is_lifeline=True,
                    multi_channel=False,
                    label="Lifeline",
                    profile=None,
                )
            }
        )
    )
    driver, _ = _action_driver(controller=controller)
    result = await client.get_association_groups(driver, 5)
    assert result[1]["label"] == "Lifeline"
    source = controller.async_get_association_groups.await_args.args[0]
    assert source.node_id == 5


async def test_get_associations_projects_targets():
    controller = SimpleNamespace(
        async_get_associations=AsyncMock(
            return_value={1: [SimpleNamespace(node_id=8, endpoint=None)]}
        )
    )
    driver, _ = _action_driver(controller=controller)
    result = await client.get_associations(driver, 5)
    assert result == {1: [{"node_id": 8, "endpoint": None}]}


async def test_add_association_delegates():
    controller = SimpleNamespace(async_add_associations=AsyncMock(return_value=None))
    driver, _ = _action_driver(controller=controller)
    result = await client.add_association(driver, 5, 2, 8)
    assert result == {"status": "added", "node_id": 5, "group": 2}
    call = controller.async_add_associations.await_args
    assert call.args[1] == 2  # group
    assert call.args[2][0].node_id == 8  # target
    assert call.kwargs["wait_for_result"] is True


async def test_remove_association_delegates():
    controller = SimpleNamespace(async_remove_associations=AsyncMock(return_value=None))
    driver, _ = _action_driver(controller=controller)
    result = await client.remove_association(driver, 5, 2, 8)
    assert result == {"status": "removed", "node_id": 5, "group": 2}
    controller.async_remove_associations.assert_awaited_once()


async def test_reinterview_node_delegates():
    driver, node = _action_driver(async_refresh_info=AsyncMock(return_value=None))
    result = await client.reinterview_node(driver, 5)
    assert result == {"status": "started", "node_id": 5}
    node.async_refresh_info.assert_awaited_once()


async def test_rebuild_node_routes_reports_success():
    controller = SimpleNamespace(async_rebuild_node_routes=AsyncMock(return_value=True))
    driver, node = _action_driver(controller=controller)
    result = await client.rebuild_node_routes(driver, 5)
    assert result == {"node_id": 5, "success": True}
    controller.async_rebuild_node_routes.assert_awaited_once_with(node)


async def test_begin_rebuilding_routes():
    controller = SimpleNamespace(
        async_begin_rebuilding_routes=AsyncMock(return_value=True)
    )
    driver, _ = _action_driver(controller=controller)
    assert await client.begin_rebuilding_routes(driver) == {
        "status": "started",
        "success": True,
    }


async def test_stop_rebuilding_routes():
    controller = SimpleNamespace(
        async_stop_rebuilding_routes=AsyncMock(return_value=True)
    )
    driver, _ = _action_driver(controller=controller)
    assert await client.stop_rebuilding_routes(driver) == {
        "status": "stopped",
        "success": True,
    }


async def test_remove_failed_node_delegates():
    controller = SimpleNamespace(async_remove_failed_node=AsyncMock(return_value=None))
    driver, node = _action_driver(controller=controller)
    result = await client.remove_failed_node(driver, 5)
    assert result == {"status": "removed", "node_id": 5}
    controller.async_remove_failed_node.assert_awaited_once_with(node)


async def test_begin_inclusion_maps_strategy():
    controller = SimpleNamespace(async_begin_inclusion=AsyncMock(return_value=True))
    driver, _ = _action_driver(controller=controller)
    result = await client.begin_inclusion(driver, "s2")
    assert result == {
        "status": "inclusion_started",
        "strategy": "s2",
        "success": True,
    }
    controller.async_begin_inclusion.assert_awaited_once_with(
        InclusionStrategy.SECURITY_S2
    )


async def test_begin_inclusion_rejects_unknown_strategy():
    controller = SimpleNamespace(async_begin_inclusion=AsyncMock())
    driver, _ = _action_driver(controller=controller)
    with pytest.raises(ValueError, match="Unknown inclusion strategy"):
        await client.begin_inclusion(driver, "bogus")
    controller.async_begin_inclusion.assert_not_awaited()


async def test_stop_inclusion():
    controller = SimpleNamespace(async_stop_inclusion=AsyncMock(return_value=True))
    driver, _ = _action_driver(controller=controller)
    assert await client.stop_inclusion(driver) == {
        "status": "inclusion_stopped",
        "success": True,
    }


async def test_begin_exclusion():
    controller = SimpleNamespace(async_begin_exclusion=AsyncMock(return_value=True))
    driver, _ = _action_driver(controller=controller)
    assert await client.begin_exclusion(driver) == {
        "status": "exclusion_started",
        "success": True,
    }


async def test_stop_exclusion():
    controller = SimpleNamespace(async_stop_exclusion=AsyncMock(return_value=True))
    driver, _ = _action_driver(controller=controller)
    assert await client.stop_exclusion(driver) == {
        "status": "exclusion_stopped",
        "success": True,
    }
