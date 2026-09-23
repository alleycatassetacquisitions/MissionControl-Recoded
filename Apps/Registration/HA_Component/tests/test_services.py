"""Tests for Registration HA services.

registration.sync_now   — forces coordinator refresh
registration.register_player — POSTs a new player to MCS

All HTTP is mocked — no live MCS needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import DOMAIN

TOKEN = "svc-token"
MOCK_ROSTER = {
    "count": 1,
    "players": [{"id": "p1", "name": "Alice", "role": "hunter",
                 "neocorp": "Helix", "faction": "Phoenix", "neo_id": "n1"}],
}


def _mock_response(json_data=None, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration._push_central_config",
            new=AsyncMock(),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.asyncio
async def test_sync_now_triggers_coordinator_refresh(
    hass: HomeAssistant, loaded_entry
):
    """sync_now calls async_request again to refresh the roster."""
    with (
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ) as mock_req,
    ):
        await hass.services.async_call(
            DOMAIN, "sync_now", {}, blocking=True
        )
        await hass.async_block_till_done()

    mock_req.assert_called()


@pytest.mark.asyncio
async def test_register_player_calls_mcs_post(
    hass: HomeAssistant, loaded_entry
):
    """register_player POSTs to MCS /players with the correct payload."""
    with (
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(return_value=_mock_response({}, 201)),
        ) as mock_post,
    ):
        await hass.services.async_call(
            DOMAIN,
            "register_player",
            {"name": "New Player", "role": "hunter", "neocorp": "Helix", "faction": ""},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs.get("token") == TOKEN
    body = kwargs.get("json", {})
    assert body["name"] == "New Player"
    assert body["role"] == "hunter"
