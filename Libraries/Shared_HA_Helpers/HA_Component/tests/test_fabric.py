"""Tests for shared_libraries.fabric presence tracking."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers import device_registry as dr

from custom_components.shared_libraries.fabric import (
    PRESENCE_OFFLINE,
    PRESENCE_ONLINE,
    PRESENCE_UNKNOWN,
    async_start_presence_tracking,
    async_stop_presence_tracking,
    device_id_from_status_topic,
    get_presence_tracker,
    parse_presence_payload,
    presence_entity_id,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestParsePresencePayload:
    def test_online_string(self):
        assert parse_presence_payload("online") == PRESENCE_ONLINE

    def test_offline_string_case_insensitive(self):
        assert parse_presence_payload("OFFLINE") == PRESENCE_OFFLINE

    def test_empty_bytes_are_offline(self):
        assert parse_presence_payload(b"") == PRESENCE_OFFLINE

    def test_none_is_offline(self):
        assert parse_presence_payload(None) == PRESENCE_OFFLINE

    def test_json_online_bool(self):
        assert parse_presence_payload('{"online": true}') == PRESENCE_ONLINE
        assert parse_presence_payload('{"online": false}') == PRESENCE_OFFLINE

    def test_json_state_string(self):
        assert parse_presence_payload('{"state": "unknown"}') == PRESENCE_UNKNOWN

    def test_garbage_is_unknown(self):
        assert parse_presence_payload("not-a-status") == PRESENCE_UNKNOWN


class TestTopicHelpers:
    def test_device_id_from_status_topic(self):
        assert device_id_from_status_topic("dnn", "mc/dnn/status/fdn-01") == "fdn-01"

    def test_rejects_nested_device_path(self):
        assert device_id_from_status_topic("dnn", "mc/dnn/status/a/b") is None

    def test_rejects_wrong_kind(self):
        assert device_id_from_status_topic("dnn", "mc/tv/status/fdn-01") is None

    def test_presence_entity_id_slugs(self):
        assert (
            presence_entity_id("digital_node_nexus", "FDN-01")
            == "sensor.digital_node_nexus_fdn_01_presence"
        )


# ---------------------------------------------------------------------------
# Integration-style presence tracking
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mqtt_subscribe():
    with (
        patch(
            "custom_components.shared_libraries.mqtt.async_ensure_mqtt",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.shared_libraries.fabric.async_subscribe",
            new_callable=AsyncMock,
        ) as mocked,
    ):
        mocked.return_value = MagicMock(name="unsub")
        yield mocked


async def test_start_presence_subscribes_status_wildcard(hass, mock_mqtt_subscribe):
    tracker = await async_start_presence_tracking(
        hass,
        "dnn",
        config_entry_id="entry-1",
        domain="digital_node_nexus",
        name_prefix="FDN",
    )

    mock_mqtt_subscribe.assert_awaited_once()
    args, kwargs = mock_mqtt_subscribe.await_args
    assert args[0] is hass
    assert args[1] == "dnn"
    assert args[2:] == ("status", "#")
    assert kwargs["qos"] == 1
    assert get_presence_tracker(hass, "dnn") is tracker

    async_stop_presence_tracking(hass, "dnn")
    assert get_presence_tracker(hass, "dnn") is None


async def test_status_message_creates_device_and_presence_entity(
    hass, mock_mqtt_subscribe
):
    tracker = await async_start_presence_tracking(
        hass,
        "dnn",
        config_entry_id="entry-dnn",
        domain="digital_node_nexus",
        name_prefix="FDN",
        model="FDN",
    )

    callback = mock_mqtt_subscribe.await_args.kwargs["callback"]
    callback(
        SimpleNamespace(
            topic="mc/dnn/status/node-42",
            payload=b"online",
        )
    )

    entity_id = "sensor.digital_node_nexus_node_42_presence"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == PRESENCE_ONLINE
    assert state.attributes["device_id"] == "node-42"
    assert state.attributes["kind"] == "dnn"

    registry = dr.async_get(hass)
    device = registry.async_get_device({("digital_node_nexus", "node-42")})
    assert device is not None
    assert device.name == "FDN node-42"
    assert device.manufacturer == "Alleycat"

    devices = tracker.list_devices()
    assert len(devices) == 1
    assert devices[0]["device_id"] == "node-42"
    assert devices[0]["presence"] == PRESENCE_ONLINE


async def test_lwt_empty_payload_marks_offline(hass, mock_mqtt_subscribe):
    await async_start_presence_tracking(
        hass,
        "dnn",
        config_entry_id="entry-dnn",
        domain="digital_node_nexus",
    )
    callback = mock_mqtt_subscribe.await_args.kwargs["callback"]
    callback(SimpleNamespace(topic="mc/dnn/status/node-7", payload=b"online"))
    callback(SimpleNamespace(topic="mc/dnn/status/node-7", payload=b""))

    state = hass.states.get("sensor.digital_node_nexus_node_7_presence")
    assert state is not None
    assert state.state == PRESENCE_OFFLINE


async def test_json_status_copies_telemetry_attributes(hass, mock_mqtt_subscribe):
    await async_start_presence_tracking(
        hass,
        "dnn",
        config_entry_id="entry-dnn",
        domain="digital_node_nexus",
    )
    callback = mock_mqtt_subscribe.await_args.kwargs["callback"]
    callback(
        SimpleNamespace(
            topic="mc/dnn/status/node-9",
            payload=b'{"online": true, "rssi": -62, "firmware": "1.2.3"}',
        )
    )

    state = hass.states.get("sensor.digital_node_nexus_node_9_presence")
    assert state is not None
    assert state.state == PRESENCE_ONLINE
    assert state.attributes["rssi"] == -62
    assert state.attributes["firmware"] == "1.2.3"
