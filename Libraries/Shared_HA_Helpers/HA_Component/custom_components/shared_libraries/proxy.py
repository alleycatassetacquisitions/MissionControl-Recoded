"""HA→LAN companion proxy via async_request.

Panels hit authenticated HA views; this helper forwards to the companion URL
from Core Configurator. App-specific transforms (RTSP overlay, uploads) stay local.
"""
from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable

import aiohttp
from aiohttp import web

from homeassistant.core import HomeAssistant

from .http import async_request

_LOGGER = logging.getLogger(__name__)

ResponseTransform = Callable[
    [HomeAssistant, str, str, bytes, str, int],
    tuple[bytes, str] | Awaitable[tuple[bytes, str]],
]


async def async_proxy_lan(
    hass: HomeAssistant,
    *,
    service_key: str,
    method: str,
    path: str,
    not_configured_error: str,
    unreachable_error: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_total: int = 60,
    transform_response: ResponseTransform | None = None,
    passthrough_content_disposition: bool = False,
) -> web.Response:
    """Forward one request to a Core Configurator companion URL."""
    from custom_components.core_configurator.helpers import get_url

    if not get_url(hass, service_key):
        return web.json_response({"error": not_configured_error}, status=503)

    api_path = path if path.startswith("/") else f"/{path}"
    timeout = aiohttp.ClientTimeout(total=timeout_total)
    resp = await async_request(
        hass,
        service_key,
        method,
        api_path,
        headers=headers,
        data=body,
        timeout=timeout,
    )
    if resp is None:
        return web.json_response({"error": unreachable_error}, status=502)

    try:
        payload = await resp.read()
        ctype = resp.content_type or "application/json"
        if transform_response is not None:
            result = transform_response(
                hass, method, api_path, payload, ctype, resp.status
            )
            if inspect.isawaitable(result):
                payload, ctype = await result
            else:
                payload, ctype = result
        if resp.status >= 400:
            _LOGGER.warning(
                "LAN proxy %s %s %s -> %s",
                service_key,
                method,
                api_path,
                resp.status,
            )
        out_headers: dict[str, str] = {}
        if passthrough_content_disposition:
            cd = resp.headers.get("Content-Disposition")
            if cd:
                out_headers["Content-Disposition"] = cd
        return web.Response(
            body=payload,
            status=resp.status,
            content_type=ctype,
            headers=out_headers,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "LAN proxy %s %s %s failed: %s", service_key, method, api_path, err
        )
        return web.json_response(
            {"error": f"{unreachable_error}: {err}"}, status=502
        )
    finally:
        resp.release()


async def proxy_request_parts(
    request: web.Request,
    path: str,
    method: str,
    *,
    max_client_size: int | None = None,
) -> tuple[str, bytes | None, dict[str, str] | None]:
    """Path + query + body + Content-Type from an HA proxy view request."""
    if max_client_size is not None:
        request._client_max_size = max_client_size  # noqa: SLF001
    qs = request.query_string
    api_path = "/" + path.lstrip("/")
    if qs:
        api_path = f"{api_path}?{qs}"
    body = await request.read() if method in ("POST", "PUT") else None
    headers: dict[str, str] = {}
    ctype = request.headers.get(aiohttp.hdrs.CONTENT_TYPE)
    if ctype:
        headers["Content-Type"] = ctype
    return api_path, body, headers or None
