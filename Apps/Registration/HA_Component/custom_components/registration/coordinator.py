"""DataUpdateCoordinator for the Registration integration.

Polls Master Control Server GET /players on the configured interval.
All HTTP calls go through shared_libraries.http.async_request so:
  - The MCS URL comes from Core Configurator (fail-closed).
  - The HA-managed aiohttp session is used — no bare ClientSession.
  - Bearer token comes from get_mcs_token (Core Configurator extra.token).
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from custom_components.shared_libraries.http import async_request, get_mcs_token

from .const import DOMAIN, KEY_MCS, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

# MCS may spend up to ~20s trying Central primary then secondary before answering.
_MCS_TIMEOUT = ClientTimeout(total=25)


class McsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches the player roster from MCS."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch /players from MCS. Raises UpdateFailed on error."""
        token = get_mcs_token(self.hass)
        if not token:
            raise UpdateFailed(
                "MCS API token not set in Core Configurator "
                "(master_control_server → API token)."
            )

        response = await async_request(
            self.hass,
            KEY_MCS,
            "GET",
            "/players",
            token=token,
            timeout=_MCS_TIMEOUT,
        )
        if response is None:
            raise UpdateFailed(
                "MCS is unreachable or master_control_server URL not configured in "
                "Core Configurator."
            )

        if response.status >= 400:
            raise UpdateFailed(
                f"MCS /players returned HTTP {response.status}"
            )

        try:
            data = await response.json()
        except Exception as exc:
            raise UpdateFailed(f"MCS /players response is not valid JSON: {exc}") from exc

        return {
            "players": data.get("players", []),
            "count": data.get("count", 0),
        }
