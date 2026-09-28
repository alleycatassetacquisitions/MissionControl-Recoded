"""Authenticated HA HTTP views that proxy GBN poster-server APIs.

Panels use ``/api/gbn/proxy/...`` with HA session auth — no LAN fetch.
"""
from __future__ import annotations

import logging

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import KEY_GBN

_LOGGER = logging.getLogger(__name__)

CHUNK_MAX = 100 * 1024 * 1024  # poster video uploads

try:
    from custom_components.core_configurator.helpers import get_url
except ImportError:  # pragma: no cover
    get_url = None  # type: ignore[assignment]


def _server_url(hass: HomeAssistant) -> str | None:
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
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "GBN URL not configured in Core Configurator"},
                status=503,
            )
        qs = request.query_string
        url = f"{base}/{path.lstrip('/')}"
        if qs:
            url = f"{url}?{qs}"
        body = await request.read() if method in ("POST", "PUT") else None
        headers = {}
        if request.content_type:
            headers["Content-Type"] = request.content_type
        session = async_get_clientsession(hass)
        timeout = aiohttp.ClientTimeout(total=120)
        try:
            async with session.request(
                method, url, data=body, headers=headers, timeout=timeout
            ) as resp:
                payload = await resp.read()
                if resp.status >= 400:
                    _LOGGER.warning(
                        "GBN proxy upstream %s %s -> %s", method, url, resp.status
                    )
                return web.Response(
                    body=payload,
                    status=resp.status,
                    content_type=resp.content_type or "application/json",
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("GBN proxy %s %s failed: %s", method, url, err)
            return web.json_response(
                {"error": f"Cannot reach GBN server: {err}"}, status=502
            )
