"""Tests for RegistrationRosterSensor.

Verifies that the sensor state and attributes reflect coordinator data.
Players are game records — no per-player HA devices are created.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import CONF_MCS_TOKEN, DOMAIN

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


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    """Set up a loaded Registration entry with a mocked MCS /players response."""
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
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.asyncio
async def test_sensor_state_is_roster_count(hass: HomeAssistant, loaded_entry):
    """sensor.registration_roster_count state equals the player count."""
    state = hass.states.get("sensor.registration_roster_count")
    assert state is not None
    assert int(state.state) == 2


@pytest.mark.asyncio
async def test_sensor_attributes_contain_roster(hass: HomeAssistant, loaded_entry):
    """Attributes include a roster list with id/name/role per player."""
    state = hass.states.get("sensor.registration_roster_count")
    roster = state.attributes.get("roster", [])
    assert len(roster) == 2
    assert roster[0]["id"] == "p1"
    assert roster[0]["name"] == "Alice"
    assert roster[0]["role"] == "hunter"


@pytest.mark.asyncio
async def test_no_per_player_devices_created(hass: HomeAssistant, loaded_entry):
    """Players are game records — no device_tracker or device per player."""
    from homeassistant.helpers import device_registry as dr
    registry = dr.async_get(hass)
    # Only the Registration integration itself may create a device (none expected).
    # There should be NO per-player devices.
    all_entries = list(registry.devices.values())
    # Zero devices expected from Registration — we create no hardware devices.
    assert len(all_entries) == 0
