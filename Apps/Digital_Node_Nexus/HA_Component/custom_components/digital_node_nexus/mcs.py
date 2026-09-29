"""MCS roster read helper for Digital Node Nexus (read-only).

DNN uses Master Control Server to build page targets (player / role / NeoCorp).
It never opens a Central socket and never writes players — Registration owns that.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientTimeout

from homeassistant.core import HomeAssistant

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import EXTRA_MCS_TOKEN, KEY_MCS

_LOGGER = logging.getLogger(__name__)

_MCS_TIMEOUT = ClientTimeout(total=25)


def mcs_token(hass: HomeAssistant) -> str:
    """Read the MCS Bearer from Core Configurator. Fail closed if blank."""
    try:
        from custom_components.core_configurator.helpers import get_extra
    except ImportError:
        return ""
    return get_extra(hass, KEY_MCS, EXTRA_MCS_TOKEN) or ""


async def fetch_roster(hass: HomeAssistant) -> dict[str, Any]:
    """GET /players from MCS. Returns empty roster on failure (fail-closed)."""
    if async_request is None:
        _LOGGER.error("Digital Node Nexus: shared_libraries not available")
        return {"players": [], "count": 0}

    token = mcs_token(hass)
    if not token:
        _LOGGER.warning(
            "Digital Node Nexus: MCS token not set in Core Configurator — roster empty."
        )
        return {"players": [], "count": 0}

    response = await async_request(
        hass,
        KEY_MCS,
        "GET",
        "/players",
        token=token,
        timeout=_MCS_TIMEOUT,
    )
    if response is None:
        _LOGGER.warning(
            "Digital Node Nexus: MCS unreachable or URL not configured — roster empty."
        )
        return {"players": [], "count": 0}

    if response.status >= 400:
        _LOGGER.warning(
            "Digital Node Nexus: MCS /players returned HTTP %s", response.status
        )
        return {"players": [], "count": 0}

    try:
        data = await response.json()
    except Exception as exc:  # noqa: BLE001 — surface empty roster, not crash
        _LOGGER.warning("Digital Node Nexus: MCS /players not JSON: %s", exc)
        return {"players": [], "count": 0}

    players = list(data.get("players") or [])
    return {"players": players, "count": int(data.get("count") or len(players))}
