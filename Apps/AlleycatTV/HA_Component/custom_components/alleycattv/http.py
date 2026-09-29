"""Authenticated HA HTTP views that proxy AlleycatTV content-server APIs.

Uses ``shared_libraries.http.async_request`` + Core Configurator. Live RTSP
comes from Core Configurator (not content-server settings.json).
"""
from __future__ import annotations

import json
import logging

import aiohttp
from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import KEY_ALLEYCATTV

_LOGGER = logging.getLogger(__name__)

CHUNK_MAX = 8 * 1024 * 1024

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:  # pragma: no cover
    async_request = None  # type: ignore[assignment]

try:
    from custom_components.core_configurator.helpers import get_extra, get_url
except ImportError:  # pragma: no cover
    get_extra = None  # type: ignore[assignment]
    get_url = None  # type: ignore[assignment]


def register_http_views(hass: HomeAssistant) -> None:
    hass.http.register_view(AlleycatTVProxyView())
    hass.http.register_view(AlleycatTVUploadStartView())
    hass.http.register_view(AlleycatTVChunkView())
    hass.http.register_view(AlleycatTVUploadCompleteView())
    hass.http.register_view(AlleycatTVUploadDeleteView())


def _hass(request: web.Request) -> HomeAssistant:
    return request.app["hass"]


def _not_configured() -> web.Response:
    return web.json_response(
        {"error": "AlleycatTV URL not configured in Core Configurator"},
        status=503,
    )


def _rtsp_source(hass: HomeAssistant) -> dict:
    """Single live-1 RTSP entry from Core Configurator (SoR)."""
    url = ""
    label = "Live RTSP"
    enabled = False
    if get_url is not None:
        url = (get_url(hass, "rtsp") or "").strip()
    if get_extra is not None:
        label = (get_extra(hass, "rtsp", "label", "Live RTSP") or "Live RTSP").strip()
        enabled = get_extra(hass, "rtsp", "enabled", "false").strip().lower() == "true"
    return {
        "id": "live-1",
        "label": label or "Live RTSP",
        "url": url,
        "enabled": bool(enabled and url),
    }


def _overlay_rtsp_payload(hass: HomeAssistant, path: str, payload: bytes, content_type: str) -> tuple[bytes, str]:
    """Inject Core Configurator RTSP into content list / settings responses."""
    clean = path.lstrip("/")
    if not clean.startswith("api/"):
        return payload, content_type
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return payload, content_type

    src = _rtsp_source(hass)

    path_only = clean.split("?", 1)[0].rstrip("/")

    if path_only == "api/settings" or path_only.startswith("api/settings/"):
        if isinstance(data, dict):
            data["rtsp_sources"] = [src]
            return json.dumps(data).encode("utf-8"), "application/json"
        return payload, content_type

    if path_only == "api/content":
        # GET /api/content/ — list may be a bare array or {files: [...]}
        files = data if isinstance(data, list) else (
            data.get("files") if isinstance(data, dict) else None
        )
        if isinstance(files, list):
            files = [f for f in files if not (
                isinstance(f, dict) and (
                    f.get("media_type") == "rtsp"
                    or f.get("entry_id") == "live-1"
                )
            )]
            if src["enabled"]:
                files.append(
                    {
                        "filename": src["label"],
                        "media_type": "rtsp",
                        "size_bytes": 0,
                        "url": src["url"],
                        "subdir": "announcements",
                        "duration": None,
                        "entry_id": "live-1",
                    }
                )
            if isinstance(data, list):
                return json.dumps(files).encode("utf-8"), "application/json"
            data["files"] = files
            return json.dumps(data).encode("utf-8"), "application/json"

    return payload, content_type


async def _proxy(
    hass: HomeAssistant,
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout_total: int = 60,
) -> web.Response:
    if async_request is None:
        return _not_configured()
    if get_url is not None and not get_url(hass, KEY_ALLEYCATTV):
        return _not_configured()

    api_path = "/" + path.lstrip("/")
    timeout = aiohttp.ClientTimeout(total=timeout_total)
    resp = await async_request(
        hass,
        KEY_ALLEYCATTV,
        method,
        api_path,
        headers=headers,
        data=body,
        timeout=timeout,
    )
    if resp is None:
        return web.json_response(
            {"error": "Cannot reach content server"},
            status=502,
        )
    try:
        payload = await resp.read()
        ctype = resp.content_type or "application/json"
        if method.upper() == "GET" and resp.status < 400:
            payload, ctype = _overlay_rtsp_payload(hass, path, payload, ctype)
        # Strip rtsp_sources writes — Core Configurator is SoR
        if method.upper() == "PUT" and path.lstrip("/").startswith("api/settings"):
            src = _rtsp_source(hass)
            try:
                data = json.loads(payload.decode("utf-8"))
                if isinstance(data, dict):
                    data["rtsp_sources"] = [src]
                    payload = json.dumps(data).encode("utf-8")
                    ctype = "application/json"
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        if resp.status >= 400:
            _LOGGER.warning(
                "AlleycatTV proxy upstream %s %s -> %s", method, api_path, resp.status
            )
        return web.Response(body=payload, status=resp.status, content_type=ctype)
    finally:
        resp.release()


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
        # Ignore client attempts to write RTSP via settings — CC is SoR.
        body = await request.read() if method in ("POST", "PUT") else None
        if method == "PUT" and path.lstrip("/").startswith("api/settings") and body:
            try:
                data = json.loads(body.decode("utf-8"))
                if isinstance(data, dict) and "rtsp_sources" in data:
                    data.pop("rtsp_sources", None)
                    body = json.dumps(data).encode("utf-8")
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        qs = request.query_string
        api_path = path
        if qs:
            api_path = f"{path}?{qs}"
        headers = {}
        if request.content_type:
            headers["Content-Type"] = request.content_type
        return await _proxy(
            hass, method, api_path, body=body, headers=headers or None, timeout_total=60
        )


class AlleycatTVUploadStartView(HomeAssistantView):
    url = "/api/alleycattv/uploads"
    name = "api:alleycattv:upload_start"
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass = _hass(request)
        payload = await request.json()
        return await _proxy(
            hass,
            "POST",
            "api/content/uploads",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout_total=30,
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
        body = await request.read()
        return await _proxy(
            hass,
            "PUT",
            f"api/content/uploads/{upload_id}/chunks/{index}",
            body=body,
            timeout_total=120,
        )


class AlleycatTVUploadCompleteView(HomeAssistantView):
    url = "/api/alleycattv/uploads/{upload_id}/complete"
    name = "api:alleycattv:upload_complete"
    requires_auth = True

    async def post(self, request: web.Request, upload_id: str) -> web.Response:
        hass = _hass(request)
        return await _proxy(
            hass,
            "POST",
            f"api/content/uploads/{upload_id}/complete",
            timeout_total=120,
        )


class AlleycatTVUploadDeleteView(HomeAssistantView):
    url = "/api/alleycattv/uploads/{upload_id}"
    name = "api:alleycattv:upload_delete"
    requires_auth = True

    async def delete(self, request: web.Request, upload_id: str) -> web.Response:
        hass = _hass(request)
        return await _proxy(
            hass,
            "DELETE",
            f"api/content/uploads/{upload_id}",
            timeout_total=30,
        )
