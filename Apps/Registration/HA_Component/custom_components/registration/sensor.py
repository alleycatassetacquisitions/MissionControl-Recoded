"""Sensor platform for Registration.

One sensor: registration_roster_count.
  - State: integer — number of players currently in the roster.
  - Attributes: roster list (id, name, role per player).

Players are game records, NOT Home Assistant devices. Do not create a
device_tracker or any per-player entity.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import McsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: McsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    # False: do not block platform setup on MCS/Central latency (sync_now already live).
    async_add_entities([RegistrationRosterSensor(coordinator, entry)], False)


class RegistrationRosterSensor(
    CoordinatorEntity[McsDataUpdateCoordinator], SensorEntity
):
    """Roster count from Master Control Server."""

    _attr_name = "Registration Roster Count"
    _attr_native_unit_of_measurement = "players"
    _attr_icon = "mdi:account-group"
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: McsDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_roster_count"
        self._entry = entry

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("count", 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        players = self.coordinator.data.get("players", [])
        return {
            "roster": [
                {
                    "id": p.get("id", ""),
                    "name": p.get("name", ""),
                    "role": p.get("role", ""),
                }
                for p in players
            ]
        }
