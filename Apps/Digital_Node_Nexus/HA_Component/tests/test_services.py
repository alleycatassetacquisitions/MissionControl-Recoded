"""Tests for Digital Node Nexus services and MCS roster read."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.digital_node_nexus.const import DOMAIN

MOCK_ROSTER = {
    "count": 1,
    "players": [
        {
            "id": "p1",
            "name": "Alice",
            "role": "hunter",
            "neocorp": "helix",
            "faction": "Phoenix",
            "neo_id": "n1",
        }
    ],
}


def _mock_response(json_data=None, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)

    tracker = MagicMock()
    tracker.list_devices.return_value = [
        {
            "device_id": "fdn-1",
            "presence": "online",
            "entity_id": "sensor.digital_node_nexus_fdn_1_presence",
        }
    ]

    with (
        patch(
            "custom_components.digital_node_nexus.async_ensure_mqtt",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.digital_node_nexus.async_start_presence_tracking",
            new=AsyncMock(return_value=tracker),
        ),
        patch(
            "custom_components.digital_node_nexus.get_presence_tracker",
            return_value=tracker,
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.asyncio
async def test_page_device_publishes_cmd_topic(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.digital_node_nexus.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "page",
            {"message": "Hello FDN", "device_id": "fdn-1", "duration": 8},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_pub.assert_awaited_once()
    args, kwargs = mock_pub.await_args
    assert args[0] is hass
    assert args[1] == "dnn"
    assert args[2:] == ("cmd", "fdn-1", "page")
    body = json.loads(kwargs["payload"].decode("utf-8"))
    assert body["text"] == "Hello FDN"
    assert body["duration"] == 8
    assert body["player_id"] == ""
    assert kwargs["qos"] == 1


@pytest.mark.asyncio
async def test_page_all_and_broadcast(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.digital_node_nexus.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "page",
            {"message": "All hands", "target": "all"},
            blocking=True,
        )
        await hass.async_block_till_done()
        await hass.services.async_call(
            DOMAIN,
            "page",
            {"message": "Group", "broadcast_group_id": "bg-3"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_pub.await_count == 2
    first = mock_pub.await_args_list[0].args
    second = mock_pub.await_args_list[1].args
    assert first[2:] == ("cmd", "all", "page")
    assert second[2:] == ("cmd", "broadcast", "bg-3", "page")


@pytest.mark.asyncio
async def test_page_player_stamps_and_routes_all(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.digital_node_nexus.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "page",
            {"message": "Find Alice", "player_id": "p1"},
            blocking=True,
        )
        await hass.async_block_till_done()

    args, kwargs = mock_pub.await_args
    assert args[2:] == ("cmd", "all", "page")
    body = json.loads(kwargs["payload"].decode("utf-8"))
    assert body["player_id"] == "p1"
    assert body["text"] == "Find Alice"


@pytest.mark.asyncio
async def test_page_filter_stamps_role_neocorp(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.digital_node_nexus.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "page",
            {"message": "Hunters", "role": "hunter", "neocorp": "helix"},
            blocking=True,
        )
        await hass.async_block_till_done()

    body = json.loads(mock_pub.await_args.kwargs["payload"].decode("utf-8"))
    assert body["role"] == "hunter"
    assert body["neocorp"] == "helix"
    assert mock_pub.await_args.args[2:] == ("cmd", "all", "page")


@pytest.mark.asyncio
async def test_set_led_and_haptic(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.digital_node_nexus.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "set_led",
            {"target": "all", "state": True, "effect": "pulse"},
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "trigger_haptic",
            {"device_id": "fdn-1", "pattern": "double"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_pub.await_count == 2
    assert mock_pub.await_args_list[0].args[2:] == ("cmd", "all", "led")
    assert mock_pub.await_args_list[1].args[2:] == ("cmd", "fdn-1", "haptic")


@pytest.mark.asyncio
async def test_fetch_roster_fail_closed_without_token(hass: HomeAssistant):
    from custom_components.digital_node_nexus.mcs import fetch_roster

    with patch(
        "custom_components.digital_node_nexus.mcs.mcs_token", return_value=""
    ):
        roster = await fetch_roster(hass)
    assert roster == {"players": [], "count": 0}


@pytest.mark.asyncio
async def test_fetch_roster_from_mcs(hass: HomeAssistant):
    from custom_components.digital_node_nexus.mcs import fetch_roster

    with (
        patch(
            "custom_components.digital_node_nexus.mcs.mcs_token",
            return_value="tok",
        ),
        patch(
            "custom_components.digital_node_nexus.mcs.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
    ):
        roster = await fetch_roster(hass)
    assert roster["count"] == 1
    assert roster["players"][0]["id"] == "p1"
