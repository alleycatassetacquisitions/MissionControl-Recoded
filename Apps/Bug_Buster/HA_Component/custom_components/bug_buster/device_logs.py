"""Central device crash logs via MCS GET /device-logs."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEFAULT_LOGS_PER_PAGE, KEY_MCS

_LOGGER = logging.getLogger(__name__)

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:  # pragma: no cover
    async_request = None  # type: ignore[assignment]

try:
    from custom_components.core_configurator.helpers import get_extra
except ImportError:  # pragma: no cover
    get_extra = None  # type: ignore[assignment]


def _mcs_token(hass: HomeAssistant) -> str | None:
    if get_extra is None:
        return None
    token = get_extra(hass, KEY_MCS, "token", "")
    return token or None


async def fetch_device_logs(
    hass: HomeAssistant,
    *,
    page: int = 1,
    per_page: int = DEFAULT_LOGS_PER_PAGE,
) -> dict[str, Any]:
    """Proxy MCS GET /device-logs. Returns {device_logs, pagination, error?}."""
    empty_pagination = {"page": page, "per_page": per_page}
    if async_request is None:
        return {
            "device_logs": [],
            "pagination": empty_pagination,
            "error": "shared_libraries unavailable",
        }
    token = _mcs_token(hass)
    if not token:
        return {
            "device_logs": [],
            "pagination": empty_pagination,
            "error": "MCS token not set in Core Configurator",
        }

    path = f"/device-logs?page={int(page)}&per_page={int(per_page)}"
    try:
        response = await async_request(hass, KEY_MCS, "GET", path, token=token)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Bug Buster device_logs request failed: %s", err)
        return {
            "device_logs": [],
            "pagination": empty_pagination,
            "error": str(err) or type(err).__name__,
        }

    if response is None:
        return {
            "device_logs": [],
            "pagination": empty_pagination,
            "error": "MCS URL not configured or unreachable",
        }

    status = response.status
    try:
        if status >= 400:
            try:
                detail = await response.text()
            except Exception:  # noqa: BLE001
                detail = ""
            return {
                "device_logs": [],
                "pagination": empty_pagination,
                "error": detail.strip() or f"HTTP {status}",
            }
        data = await response.json(content_type=None)
    finally:
        response.release()

    if not isinstance(data, dict):
        return {
            "device_logs": [],
            "pagination": empty_pagination,
            "error": "MCS device-logs response was not JSON object",
        }

    logs = data.get("device_logs") or []
    pagination = data.get("pagination") or empty_pagination
    if not isinstance(logs, list):
        logs = []
    if not isinstance(pagination, dict):
        pagination = empty_pagination
    return {
        "device_logs": logs,
        "pagination": {
            "page": int(pagination.get("page") or page),
            "per_page": int(pagination.get("per_page") or per_page),
        },
    }
