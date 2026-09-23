"""Tests for McsDataUpdateCoordinator.

All HTTP calls are replaced by aioclient_mock / patch so no live MCS is needed.

Groups:
  1. Happy path   — /players returns a roster, data is stored
  2. Fail-closed  — no MCS URL → UpdateFailed
  3. HTTP errors  — 4xx/5xx → UpdateFailed
  4. Bad JSON     — UpdateFailed
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.registration.coordinator import McsDataUpdateCoordinator

TOKEN = "test-token"

MOCK_ROSTER = {
    "count": 2,
    "players": [
        {"id": "p1", "name": "Alice", "role": "hunter", "neocorp": "Helix",
         "faction": "Phoenix", "neo_id": "neo-001"},
        {"id": "p2", "name": "Bob", "role": "freelancer", "neocorp": "Freelancer",
         "faction": "", "neo_id": "neo-002"},
    ],
}


def _mock_response(json_data=None, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


def _patch_request(response=None):
    return patch(
        "custom_components.registration.coordinator.async_request",
        new=AsyncMock(return_value=response),
    )


@pytest.mark.asyncio
async def test_coordinator_fetches_roster(hass: HomeAssistant):
    """Happy path: /players returns a roster and coordinator stores it."""
    coordinator = McsDataUpdateCoordinator(hass, TOKEN)
    with _patch_request(_mock_response(MOCK_ROSTER)):
        await coordinator.async_refresh()

    assert coordinator.data is not None
    assert coordinator.data["count"] == 2
    assert len(coordinator.data["players"]) == 2


@pytest.mark.asyncio
async def test_coordinator_stores_player_fields(hass: HomeAssistant):
    """Player objects use canonical field names."""
    coordinator = McsDataUpdateCoordinator(hass, TOKEN)
    with _patch_request(_mock_response(MOCK_ROSTER)):
        await coordinator.async_refresh()

    player = coordinator.data["players"][0]
    assert player["id"] == "p1"
    assert player["name"] == "Alice"
    assert player["role"] == "hunter"
    assert player["neocorp"] == "Helix"


@pytest.mark.asyncio
async def test_coordinator_raises_when_mcs_unreachable(hass: HomeAssistant):
    """None response (no MCS URL or network error) → UpdateFailed."""
    coordinator = McsDataUpdateCoordinator(hass, TOKEN)
    with _patch_request(None), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_on_http_error(hass: HomeAssistant):
    """4xx/5xx from MCS → UpdateFailed."""
    coordinator = McsDataUpdateCoordinator(hass, TOKEN)
    with _patch_request(_mock_response(status=503)), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_raises_on_bad_json(hass: HomeAssistant):
    """Non-JSON body → UpdateFailed."""
    coordinator = McsDataUpdateCoordinator(hass, TOKEN)
    bad_resp = AsyncMock()
    bad_resp.status = 200
    bad_resp.json = AsyncMock(side_effect=ValueError("not json"))

    with _patch_request(bad_resp), pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_coordinator_uses_mcs_token(hass: HomeAssistant):
    """The MCS token is passed as Bearer to async_request."""
    coordinator = McsDataUpdateCoordinator(hass, "super-secret")
    with patch(
        "custom_components.registration.coordinator.async_request",
        new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
    ) as mock_req:
        await coordinator.async_refresh()

    _, call_kwargs = mock_req.call_args
    assert call_kwargs.get("token") == "super-secret"
