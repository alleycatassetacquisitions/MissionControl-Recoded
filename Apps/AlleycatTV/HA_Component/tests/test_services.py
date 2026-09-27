"""Tests for AlleycatTV play/stop broadcast group MQTT publishes."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alleycattv.const import DOMAIN


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=DOMAIN)
    entry.add_to_hass(hass)

    tracker = MagicMock()
    tracker.list_devices.return_value = [
        {
            "device_id": "pi-lobby-1",
            "presence": "online",
            "entity_id": "sensor.alleycattv_pi_lobby_1_presence",
        }
    ]

    with (
        patch(
            "custom_components.alleycattv.async_ensure_mqtt",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.alleycattv.async_start_presence_tracking",
            new=AsyncMock(return_value=tracker),
        ),
        patch(
            "custom_components.alleycattv.get_presence_tracker",
            return_value=tracker,
        ),
        patch(
            "custom_components.alleycattv.async_subscribe",
            new=AsyncMock(return_value=lambda: None),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.asyncio
async def test_play_broadcast_group_publishes_cmd_and_desired(
    hass: HomeAssistant, loaded_entry
):
    with patch(
        "custom_components.alleycattv.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "play_broadcast_group",
            {"broadcast_group_id": "lobby"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_pub.await_count == 2
    cmd_call = mock_pub.await_args_list[0]
    desired_call = mock_pub.await_args_list[1]

    assert cmd_call.args[1] == "tv"
    assert cmd_call.args[2:] == ("cmd", "broadcast", "lobby", "play")
    assert cmd_call.kwargs["retain"] is False

    assert desired_call.args[2:] == (
        "desired",
        "broadcast",
        "lobby",
        "playback",
    )
    assert desired_call.kwargs["retain"] is True
    body = json.loads(desired_call.kwargs["payload"].decode("utf-8"))
    assert body["state"] == "playing"


@pytest.mark.asyncio
async def test_stop_broadcast_group(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.alleycattv.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "stop_broadcast_group",
            {"broadcast_group_id": "lobby"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_pub.await_count == 2
    assert mock_pub.await_args_list[0].args[2:] == (
        "cmd",
        "broadcast",
        "lobby",
        "stop",
    )
    body = json.loads(mock_pub.await_args_list[1].kwargs["payload"].decode("utf-8"))
    assert body["state"] == "stopped"


@pytest.mark.asyncio
async def test_interrupt_pi_uses_device_segment(hass: HomeAssistant, loaded_entry):
    with patch(
        "custom_components.alleycattv.async_publish",
        new=AsyncMock(),
    ) as mock_pub:
        await hass.services.async_call(
            DOMAIN,
            "interrupt_pi",
            {
                "pi_id": "pi-lobby-1",
                "file_url": "http://server/media/announcements/a.mp4",
            },
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_pub.assert_awaited_once()
    assert mock_pub.await_args.args[2:] == (
        "cmd",
        "device",
        "pi-lobby-1",
        "interrupt",
    )
    body = json.loads(mock_pub.await_args.kwargs["payload"].decode("utf-8"))
    assert body["file_url"].endswith("a.mp4")
