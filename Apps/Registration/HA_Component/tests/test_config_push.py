"""Tests for the config-push mechanism.

When Core Configurator fires core_configurator_updated with
central_primary or central_secondary, Registration must push
those URLs to MCS POST /config immediately.

Also tests that unrelated CC key changes do NOT trigger a push.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import CONF_MCS_TOKEN, DOMAIN

TOKEN = "test-token"

MOCK_ROSTER = {"count": 0, "players": []}


def _mock_response(json_data=None, status: int = 200):
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


@pytest.fixture
async def running_entry(hass: HomeAssistant):
    """Loaded Registration entry — coordinator and event listener active."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MCS_TOKEN: TOKEN},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    with (
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

    return entry, mock_push


@pytest.mark.asyncio
async def test_push_called_on_central_primary_update(
    hass: HomeAssistant, running_entry
):
    """Firing CC updated with central_primary triggers a config push."""
    entry, _ = running_entry

    with patch(
        "custom_components.registration._push_central_config",
        new=AsyncMock(),
    ) as mock_push:
        hass.bus.async_fire(
            "core_configurator_updated",
            {"key": "central_primary", "services": {}},
        )
        await hass.async_block_till_done()

    mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_push_called_on_central_secondary_update(
    hass: HomeAssistant, running_entry
):
    """Firing CC updated with central_secondary triggers a config push."""
    entry, _ = running_entry

    with patch(
        "custom_components.registration._push_central_config",
        new=AsyncMock(),
    ) as mock_push:
        hass.bus.async_fire(
            "core_configurator_updated",
            {"key": "central_secondary", "services": {}},
        )
        await hass.async_block_till_done()

    mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_push_not_called_for_unrelated_key(
    hass: HomeAssistant, running_entry
):
    """A CC update for an unrelated key (e.g. gbn) must NOT trigger a push."""
    entry, _ = running_entry

    with patch(
        "custom_components.registration._push_central_config",
        new=AsyncMock(),
    ) as mock_push:
        hass.bus.async_fire(
            "core_configurator_updated",
            {"key": "gbn", "services": {}},
        )
        await hass.async_block_till_done()

    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_push_called_on_full_catalog_refresh(
    hass: HomeAssistant, running_entry
):
    """CC fires key=None on setup (full-catalog refresh) — push is also triggered."""
    entry, _ = running_entry

    with patch(
        "custom_components.registration._push_central_config",
        new=AsyncMock(),
    ) as mock_push:
        hass.bus.async_fire(
            "core_configurator_updated",
            {"key": None, "services": {}},
        )
        await hass.async_block_till_done()

    mock_push.assert_called_once()
