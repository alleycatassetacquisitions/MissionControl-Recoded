"""DataUpdateCoordinator for the Registration integration.

Polls Master Control Server GET /players on the configured interval.
All HTTP calls go through shared_libraries.http.async_request so:
  - The MCS URL comes from Core Configurator (fail-closed).
  - The HA-managed aiohttp session is used — no bare ClientSession.
  - Bearer token comes from the Registration config entry.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    # Keep the name at module scope so tests can patch it; fail closed at runtime.
    async_request = None  # type: ignore[assignment]

from .const import DOMAIN, KEY_MCS, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class McsDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that fetches the player roster from MCS."""

    def __init__(self, hass: HomeAssistant, mcs_token: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._token = mcs_token

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch /players from MCS. Raises UpdateFailed on error."""
        if async_request is None:
            raise UpdateFailed(
                "shared_libraries not available — add it to manifest dependencies"
            )

        response = await async_request(
            self.hass,
            KEY_MCS,
            "GET",
            "/players",
            token=self._token,
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
