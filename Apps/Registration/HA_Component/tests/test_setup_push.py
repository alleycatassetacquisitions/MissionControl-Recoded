"""Tests for the first-boot config push on async_setup_entry.

On every HA start (every async_setup_entry call), Registration must
immediately push the current central_primary / central_secondary values
from Core Configurator to MCS POST /config — before any coordinator poll.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import DOMAIN

TOKEN = "first-boot-token"
MOCK_ROSTER = {"count": 0, "players": []}


def _mock_response(json_data=None, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


@pytest.mark.asyncio
async def test_setup_pushes_config_immediately(hass: HomeAssistant):
    """_push_central_config is called exactly once during async_setup_entry."""
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
        ) as mock_push,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    mock_push.assert_called_once_with(hass)


@pytest.mark.asyncio
async def test_setup_continues_when_push_fails(hass: HomeAssistant):
    """MCS down during setup push must not prevent the entry from loading."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    async def _push_that_logs(*_args):
        return None

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
            side_effect=_push_that_logs,
        ),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert DOMAIN in hass.data
