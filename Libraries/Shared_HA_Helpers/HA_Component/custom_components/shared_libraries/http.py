"""HTTP helper for Mission Control integrations.

All integrations use this instead of opening their own aiohttp sessions.

Usage
-----
    from custom_components.shared_libraries.http import async_request

    response = await async_request(hass, KEY_GBN, "GET", "/api/posters")
    if response is None:
        # No URL configured — fail-closed, do not fall back to a hardcoded IP.
        return

    data = await response.json()

With bearer auth:
    response = await async_request(
        hass, KEY_REGISTRATION_PRIMARY, "POST", "/players",
        token=my_token,
    )

Design contracts
----------------
- Fail-closed: if Core Configurator has no URL for service_key, returns None.
  Callers must handle None without falling back to a hardcoded address.
- Never opens a bare aiohttp.ClientSession. Always uses
  homeassistant.helpers.aiohttp_client.async_get_clientsession(hass).
- Bearer auth only: if token is provided, adds Authorization: Bearer {token}.
  Token storage is the caller's responsibility (Phase 4+).
- path must start with "/" and is appended directly to the base URL.
"""
from __future__ import annotations

import logging
from typing import Any

from aiohttp import ClientResponse, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

# core_configurator is listed in manifest dependencies so it is loaded before
# this helper is called in production.  The module-level name makes get_url
# patchable in tests via:
#   patch("custom_components.shared_libraries.http.get_url", return_value=…)
# The try/except lets the test runner import this module without core_configurator
# on its path; tests replace the None sentinel via patch before calling
# async_request.
try:
    from custom_components.core_configurator.helpers import get_url  # type: ignore[import]
except ImportError:
    get_url = None  # type: ignore[assignment]

_LOGGER = logging.getLogger(__name__)

# Default timeout for all Mission Control HTTP requests.
_DEFAULT_TIMEOUT = ClientTimeout(total=10)


async def async_request(
    hass: HomeAssistant,
    service_key: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    json: Any | None = None,
    timeout: ClientTimeout = _DEFAULT_TIMEOUT,
) -> ClientResponse | None:
    """Make an authenticated HTTP request via the HA-managed session.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    service_key:
        A Core Configurator service key (e.g. ``KEY_GBN``).  The base URL is
        read from Core Configurator; if none is stored the call returns None.
    method:
        HTTP method string, e.g. ``"GET"``, ``"POST"``.
    path:
        URL path starting with ``/``, e.g. ``"/api/posters"``.
    token:
        Optional bearer token.  When provided, an ``Authorization: Bearer``
        header is added.  Passing ``None`` skips auth entirely.
    headers:
        Additional headers to merge.  These are applied after the bearer
        header so callers can override if necessary.
    json:
        Optional JSON-serialisable body.  Passed to the underlying session
        request as ``json=``.
    timeout:
        Request timeout.  Defaults to 10 s total.

    Returns
    -------
    ClientResponse or None
        The raw aiohttp response, or ``None`` when no URL is configured.
        The caller is responsible for reading the body and closing the response.
    """
    if get_url is None:
        _LOGGER.error(
            "shared_libraries.http: core_configurator is not available — "
            "add it to your manifest dependencies."
        )
        return None

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
