"""Companion /health probes via shared_libraries.http."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant

from .const import HEALTH_KEYS

_LOGGER = logging.getLogger(__name__)

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:  # pragma: no cover
    async_request = None  # type: ignore[assignment]

try:
    from custom_components.core_configurator.helpers import get_extra, get_url
except ImportError:  # pragma: no cover
    get_extra = None  # type: ignore[assignment]
    get_url = None  # type: ignore[assignment]


def _mcs_token(hass: HomeAssistant) -> str | None:
    if get_extra is None:
        return None
    token = get_extra(hass, "master_control_server", "token", "")
    return token or None


async def probe_companions(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return health rows for MCS / AlleycatTV / GBN."""
    results: list[dict[str, Any]] = []
    if async_request is None or get_url is None:
        for key in HEALTH_KEYS:
            results.append(
                {
                    "key": key,
                    "url": "",
                    "ok": False,
                    "status": None,
                    "error": "shared_libraries / core_configurator unavailable",
                    "checked_at": time.time(),
                }
            )
        return results

    for key in HEALTH_KEYS:
        url = get_url(hass, key)
        row: dict[str, Any] = {
            "key": key,
            "url": url,
            "ok": False,
            "status": None,
            "error": None,
            "checked_at": time.time(),
        }
        if not url:
            row["error"] = "not configured"
            results.append(row)
            continue
        token = _mcs_token(hass) if key == "master_control_server" else None
        try:
            response = await async_request(
                hass, key, "GET", "/health", token=token
            )
            if response is None:
                row["error"] = "no response"
            else:
                row["status"] = response.status
                row["ok"] = response.status < 400
                if not row["ok"]:
                    row["error"] = f"HTTP {response.status}"
                response.release()
        except Exception as err:  # noqa: BLE001
            row["error"] = str(err) or type(err).__name__
            _LOGGER.debug("Bug Buster health %s failed: %s", key, err)
        results.append(row)
    return results
