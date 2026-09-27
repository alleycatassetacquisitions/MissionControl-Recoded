"""Authenticated HA HTTP views that proxy AlleycatTV content-server APIs.

Uses Core Configurator ``alleycattv`` URL via shared_libraries.http — no
hardcoded LAN fallbacks.
"""
from __future__ import annotations

import logging

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import KEY_ALLEYCATTV

_LOGGER = logging.getLogger(__name__)

CHUNK_MAX = 8 * 1024 * 1024

try:
    from custom_components.core_configurator.helpers import get_url
except ImportError:  # pragma: no cover
    get_url = None  # type: ignore[assignment]


def _server_url(hass: HomeAssistant) -> str | None:
    """Return content-server base URL or None (fail-closed)."""
    if get_url is None:
        return None
    url = get_url(hass, KEY_ALLEYCATTV)
    if not url:
        return None
    return str(url).rstrip("/")


def register_http_views(hass: HomeAssistant) -> None:
    hass.http.register_view(AlleycatTVProxyView())
    hass.http.register_view(AlleycatTVUploadStartView())
    hass.http.register_view(AlleycatTVChunkView())
    hass.http.register_view(AlleycatTVUploadCompleteView())
    hass.http.register_view(AlleycatTVUploadDeleteView())


def _hass(request: web.Request) -> HomeAssistant:
    return request.app["hass"]


class AlleycatTVProxyView(HomeAssistantView):
    """JSON proxy so panels use HA session auth — no LAN fetch from the browser."""

    url = "/api/alleycattv/proxy/{path:.*}"
    name = "api:alleycattv:proxy"
    requires_auth = True

    async def get(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "GET")

    async def post(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "POST")

    async def put(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "PUT")

    async def delete(self, request: web.Request, path: str) -> web.Response:
        return await self._forward(request, path, "DELETE")

    async def _forward(self, request: web.Request, path: str, method: str) -> web.Response:
        hass = getattr(self, "hass", None) or request.app.get("hass")
        if hass is None:
            return web.Response(text="Home Assistant not ready", status=503)
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "AlleycatTV URL not configured in Core Configurator"},
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
        timeout = aiohttp.ClientTimeout(total=60)
        try:
            async with session.request(
                method, url, data=body, headers=headers, timeout=timeout
            ) as resp:
                payload = await resp.read()
                return web.Response(
                    body=payload,
                    status=resp.status,
                    content_type=resp.content_type or "application/json",
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("AlleycatTV proxy %s %s failed: %s", method, url, err)
            return web.json_response(
                {"error": f"Cannot reach content server: {err}"}, status=502
            )


class AlleycatTVUploadStartView(HomeAssistantView):
    url = "/api/alleycattv/uploads"
    name = "api:alleycattv:upload_start"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass = _hass(request)
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "AlleycatTV URL not configured in Core Configurator"},
                status=503,
            )
        payload = await request.json()
        session = async_get_clientsession(hass)
        url = f"{base}/api/content/uploads"
        async with session.post(
            url, json=payload, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return web.Response(
                body=await resp.read(),
                status=resp.status,
                content_type=resp.content_type,
            )


class AlleycatTVChunkView(HomeAssistantView):
    url = "/api/alleycattv/uploads/{upload_id}/chunks/{index}"
    name = "api:alleycattv:upload_chunk"
    requires_auth = True

    async def put(
        self, request: web.Request, upload_id: str, index: str
    ) -> web.Response:
        request._client_max_size = CHUNK_MAX  # noqa: SLF001
        hass = _hass(request)
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "AlleycatTV URL not configured in Core Configurator"},
                status=503,
            )
        body = await request.read()
        session = async_get_clientsession(hass)
        url = f"{base}/api/content/uploads/{upload_id}/chunks/{index}"
        timeout = aiohttp.ClientTimeout(total=120)
        async with session.put(url, data=body, timeout=timeout) as resp:
            return web.Response(
                body=await resp.read(),
                status=resp.status,
                content_type=resp.content_type,
            )


class AlleycatTVUploadCompleteView(HomeAssistantView):
    url = "/api/alleycattv/uploads/{upload_id}/complete"
    name = "api:alleycattv:upload_complete"
    requires_auth = True

    async def post(self, request: web.Request, upload_id: str) -> web.Response:
        hass = _hass(request)
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "AlleycatTV URL not configured in Core Configurator"},
                status=503,
            )
        session = async_get_clientsession(hass)
        url = f"{base}/api/content/uploads/{upload_id}/complete"
        async with session.post(
            url, timeout=aiohttp.ClientTimeout(total=120)
        ) as resp:
            return web.Response(
                body=await resp.read(),
                status=resp.status,
                content_type=resp.content_type,
            )


class AlleycatTVUploadDeleteView(HomeAssistantView):
    url = "/api/alleycattv/uploads/{upload_id}"
    name = "api:alleycattv:upload_delete"
    requires_auth = True

    async def delete(self, request: web.Request, upload_id: str) -> web.Response:
        hass = _hass(request)
        base = _server_url(hass)
        if not base:
            return web.json_response(
                {"error": "AlleycatTV URL not configured in Core Configurator"},
                status=503,
            )
        session = async_get_clientsession(hass)
        url = f"{base}/api/content/uploads/{upload_id}"
        async with session.delete(
            url, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            return web.Response(
                body=await resp.read(),
                status=resp.status,
                content_type=resp.content_type,
            )
