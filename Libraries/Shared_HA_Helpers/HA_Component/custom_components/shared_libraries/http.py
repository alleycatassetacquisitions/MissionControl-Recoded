"""HTTP helper — async_request + get_mcs_token via Core Configurator + HA session.

Returns None when no URL is configured; callers must handle None without fallback IPs.
core_configurator is a declared manifest dependency — import hard; fail loudly if missing.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponse, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.core_configurator.const import (
    EXTRA_TOKEN,
    KEY_MASTER_CONTROL_SERVER,
)
from custom_components.core_configurator.helpers import get_extra, get_url

_LOGGER = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = ClientTimeout(total=10)


def get_mcs_token(hass: HomeAssistant) -> str:
    """MCS Bearer from Core Configurator. Empty when unset (fail-closed)."""
    return str(get_extra(hass, KEY_MASTER_CONTROL_SERVER, EXTRA_TOKEN, "") or "")


async def async_request(
    hass: HomeAssistant,
    service_key: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    json: Any | None = None,
    data: Any | None = None,
    timeout: ClientTimeout = _DEFAULT_TIMEOUT,
) -> ClientResponse | None:
    """Make an authenticated HTTP request via the HA-managed session.

    Returns the raw aiohttp response, or None when no URL is configured.
    Caller reads the body and closes/releases the response.
    """
    base_url = get_url(hass, service_key)
    if not base_url:
        _LOGGER.debug(
            "shared_libraries.http: no URL configured for service_key=%r — skipping request",
            service_key,
        )
        return None

    url = base_url.rstrip("/") + path

    merged_headers: dict[str, str] = {}
    if token:
        merged_headers["Authorization"] = f"Bearer {token}"
    if headers:
        merged_headers.update(headers)

    session = async_get_clientsession(hass)
    try:
        response = await session.request(
            method.upper(),
            url,
            headers=merged_headers or None,
            json=json,
            data=data,
            timeout=timeout,
        )
        _LOGGER.debug(
            "shared_libraries.http: %s %s → %d",
            method.upper(),
            url,
            response.status,
        )
        return response
    except Exception as err:  # noqa: BLE001
        _LOGGER.error(
            "shared_libraries.http: %s %s failed: %s",
            method.upper(),
            url,
            err or type(err).__name__,
        )
        return None
