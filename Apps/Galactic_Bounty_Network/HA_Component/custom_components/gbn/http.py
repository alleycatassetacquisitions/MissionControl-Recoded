"""Authenticated HA HTTP views that proxy GBN poster-server APIs.

Panels use ``/api/gbn/proxy/...`` with HA session auth — no LAN fetch.
Uses ``shared_libraries.http.async_request``.
"""
from __future__ import annotations

import logging

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import KEY_GBN

_LOGGER = logging.getLogger(__name__)

CHUNK_MAX = 100 * 1024 * 1024  # poster video uploads

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:  # pragma: no cover
    async_request = None  # type: ignore[assignment]

try:
    from custom_components.core_configurator.helpers import get_url
except ImportError:  # pragma: no cover
    get_url = None  # type: ignore[assignment]


def _server_url(hass: HomeAssistant) -> str | None:
    """Return configured GBN base URL, or None when unset/unavailable."""
    if get_url is None:
        return None
    url = get_url(hass, KEY_GBN)
    if not url:
        return None
    return str(url).rstrip("/")


def register_http_views(hass: HomeAssistant) -> None:
    hass.http.register_view(GbnProxyView())


class GbnProxyView(HomeAssistantView):
    """Forward panel requests to the GBN Proxmox server."""

    url = "/api/gbn/proxy/{path:.*}"
    name = "api:gbn:proxy"
    requires_auth = True

    async def get(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "GET")

    async def post(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "POST")

    async def put(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "PUT")

    async def delete(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "DELETE")

    async def _forward(
        self, request: web.Request, path: str, method: str
    ) -> web.Response:
        # Allow large multipart poster uploads through HA.
        request._client_max_size = CHUNK_MAX  # noqa: SLF001
        hass = getattr(self, "hass", None) or request.app.get("hass")
        if hass is None:
            return web.Response(text="Home Assistant not ready", status=503)
        if async_request is None or not _server_url(hass):
            return web.json_response(
                {"error": "GBN URL not configured in Core Configurator"},
                status=503,
            )
        qs = request.query_string
        api_path = "/" + path.lstrip("/")
        if qs:
            api_path = f"{api_path}?{qs}"
        body = await request.read() if method in ("POST", "PUT") else None
        headers = {}
        # Use the raw header so multipart boundary is preserved.
        ctype = request.headers.get(aiohttp.hdrs.CONTENT_TYPE)
        if ctype:
            headers["Content-Type"] = ctype
        timeout = aiohttp.ClientTimeout(total=120)
        resp = await async_request(
            hass,
            KEY_GBN,
            method,
            api_path,
            headers=headers or None,
            data=body,
            timeout=timeout,
        )
        if resp is None:
            return web.json_response(
                {"error": "Cannot reach GBN server"},
                status=502,
            )
        try:
            payload = await resp.read()
            if resp.status >= 400:
                _LOGGER.warning(
                    "GBN proxy upstream %s %s -> %s", method, api_path, resp.status
                )
            return web.Response(
                body=payload,
                status=resp.status,
                content_type=resp.content_type or "application/json",
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("GBN proxy %s %s failed: %s", method, api_path, err)
            return web.json_response(
                {"error": f"Cannot reach GBN server: {err}"}, status=502
            )
        finally:
            resp.release()
