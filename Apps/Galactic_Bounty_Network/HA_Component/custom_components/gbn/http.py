"""Authenticated HA HTTP views that proxy GBN poster-server APIs.

Panels use ``/api/gbn/proxy/...`` with HA session auth — no LAN fetch.
Forwarding uses ``shared_libraries.proxy.async_proxy_lan``.
"""
from __future__ import annotations

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from custom_components.shared_libraries.proxy import async_proxy_lan, proxy_request_parts

from .const import KEY_GBN

CHUNK_MAX = 100 * 1024 * 1024  # poster video uploads


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
        hass = getattr(self, "hass", None) or request.app.get("hass")
        if hass is None:
            return web.Response(text="Home Assistant not ready", status=503)
        api_path, body, headers = await proxy_request_parts(
            request, path, method, max_client_size=CHUNK_MAX
        )
        return await async_proxy_lan(
            hass,
            service_key=KEY_GBN,
            method=method,
            path=api_path,
            body=body,
            headers=headers,
            timeout_total=120,
            not_configured_error="GBN URL not configured in Core Configurator",
            unreachable_error="Cannot reach GBN server",
            passthrough_content_disposition=True,
        )
