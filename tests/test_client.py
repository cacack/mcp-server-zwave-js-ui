"""Tests for the projection helpers and node lookup in client.py.

The projections are pure functions over the library model objects, so they are
exercised here with lightweight fakes that expose just the attributes each
projection reads. This keeps the tests fast and free of a live server while
still covering the field-mapping logic, which is where bugs actually hide.
"""

from __future__ import annotations

from enum import Enum
from types import SimpleNamespace

import pytest

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
        "protocol_version": "1.0",
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


def _driver(nodes) -> SimpleNamespace:
    controller = SimpleNamespace(
        home_id=0xABCD,
        controller_type="Static Controller",
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
    return SimpleNamespace(controller=controller)


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
    monkeypatch.setenv("ZWAVE_JS_URL", "ws://borg:3002")
    assert client.server_url() == "ws://borg:3002"
