"""Core Configurator — single authority for Alleycat URLs and shared API tokens.

Design principles applied:
  P2  Prefer authority over consensus — every caller reads get_url / get_extra here.
  P5  Propagate truth — fire core_configurator_updated so listeners resync.
  P8  Reusable primitive — websocket + hass.data["core_configurator"]["services"].

Fail-closed contract: get_url / get_extra return "" when nothing is stored.
There are no built-in IP fallbacks. Callers that need a value must have it configured.
"""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.components import websocket_api

from .const import (
    DOMAIN,
    EVENT_UPDATED,
    EXTRA_ENABLED,
    EXTRA_TOKEN,
    KEY_RTSP,
    KEY_VENUE_UPDATER,
    YAML_KEYS,
    YAML_RTSP_ENABLED,
)
from .helpers import catalog_public, get_extra, get_url, save_services
from .urlutil import _truthy, empty_services, normalize_url, services_from_mapping

_LOGGER = logging.getLogger(__name__)

_YAML_FIELD_SCHEMA = {
    vol.Optional(key): cv.string
    for key in YAML_KEYS
    if key != YAML_RTSP_ENABLED
}
_YAML_FIELD_SCHEMA[vol.Optional(YAML_RTSP_ENABLED)] = vol.Any(cv.boolean, cv.string)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Optional(DOMAIN): vol.Schema(
            _YAML_FIELD_SCHEMA,
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _store(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DOMAIN, {"services": empty_services(), "entry_id": None})


# ---------------------------------------------------------------------------
# Websocket commands
# ---------------------------------------------------------------------------

@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_services"})
@websocket_api.async_response
async def ws_get_services(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"services": catalog_public(hass)})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/get_url",
        vol.Required("key"): str,
    }
)
@websocket_api.async_response
async def ws_get_url(hass: HomeAssistant, connection, msg) -> None:
    key = msg["key"]
    extra = (_store(hass)["services"].get(key) or {}).get("extra") or {}
    connection.send_result(
        msg["id"],
        {"key": key, "url": get_url(hass, key), "extra": dict(extra)},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_service",
        vol.Required("key"): str,
        vol.Optional("url"): str,
        vol.Optional("extra"): dict,
    }
)
@websocket_api.async_response
async def ws_set_service(hass: HomeAssistant, connection, msg) -> None:
    if not getattr(connection.user, "is_admin", False):
        connection.send_error(msg["id"], "unauthorized", "Admin required")
        return
    key = msg["key"]
    services = dict(_store(hass)["services"])
    current = dict(services.get(key) or {"url": "", "extra": {}})
    if "url" in msg and msg["url"] is not None:
        current["url"] = normalize_url(str(msg["url"]), key=key)
    if msg.get("extra") is not None:
        merged = {**dict(current.get("extra") or {}), **dict(msg["extra"])}
        if key == KEY_RTSP and EXTRA_ENABLED in merged:
            merged[EXTRA_ENABLED] = _truthy(merged[EXTRA_ENABLED])
        current["extra"] = merged
    services[key] = current
    save_services(hass, services, changed_key=key)
    _LOGGER.info("Core Configurator: %s → %s", key, current.get("url"))
    connection.send_result(
        msg["id"],
        {
            "ok": True,
            "key": key,
            "url": current.get("url") or "",
            "extra": dict(current.get("extra") or {}),
        },
    )


async def _venue_updater_request(
    hass: HomeAssistant, method: str, path: str
) -> dict:
    """Call the Proxmox venue-update agent. Returns a result dict."""
    from aiohttp import ClientTimeout

    from custom_components.shared_libraries.http import async_request

    token = str(get_extra(hass, KEY_VENUE_UPDATER, EXTRA_TOKEN, "") or "")
    if not get_url(hass, KEY_VENUE_UPDATER):
        return {"status": "error", "detail": "venue_updater URL not configured"}
    if not token:
        return {"status": "error", "detail": "venue_updater token not configured"}
    # Check may download/compare a release; allow longer than the shared 10s default.
    response = await async_request(
        hass,
        KEY_VENUE_UPDATER,
        method,
        path,
        token=token,
        timeout=ClientTimeout(total=180),
    )
    if response is None:
        return {"status": "error", "detail": "venue updater unreachable"}
    try:
        if response.status >= 400:
            text = await response.text()
            return {
                "status": "error",
                "detail": f"HTTP {response.status}: {text[:400]}",
            }
        data = await response.json(content_type=None)
        return data if isinstance(data, dict) else {"status": "ok", "data": data}
    except Exception as err:  # noqa: BLE001
        return {"status": "error", "detail": str(err)}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/update_status"})
@websocket_api.async_response
async def ws_update_status(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], await _venue_updater_request(hass, "GET", "/status"))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/update_check"})
@websocket_api.async_response
async def ws_update_check(hass: HomeAssistant, connection, msg) -> None:
    if not getattr(connection.user, "is_admin", False):
        connection.send_error(msg["id"], "unauthorized", "Admin required")
        return
    connection.send_result(msg["id"], await _venue_updater_request(hass, "POST", "/check"))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/update_apply"})
@websocket_api.async_response
async def ws_update_apply(hass: HomeAssistant, connection, msg) -> None:
    if not getattr(connection.user, "is_admin", False):
        connection.send_error(msg["id"], "unauthorized", "Admin required")
        return
    connection.send_result(msg["id"], await _venue_updater_request(hass, "POST", "/apply"))


# ---------------------------------------------------------------------------
# HA lifecycle
# ---------------------------------------------------------------------------

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    data = _store(hass)
    yaml_conf = config.get(DOMAIN)
    if yaml_conf is not None:
        data["_yaml"] = dict(yaml_conf)
        if not hass.config_entries.async_entries(DOMAIN):
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN, context={"source": SOURCE_IMPORT}, data=yaml_conf or {}
                )
            )
    _register_ws(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = _store(hass)
    services = entry.data.get("services")
    if not isinstance(services, dict) or not services:
        services = services_from_mapping(entry.data)
    data["services"] = services
    data["entry_id"] = entry.entry_id
    _register_ws(hass)
    hass.bus.async_fire(EVENT_UPDATED, {"key": None, "services": catalog_public(hass)})
    _LOGGER.info("Core Configurator ready (%d services)", len(services))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.pop(DOMAIN, None)
    return True


@callback
def _register_ws(hass: HomeAssistant) -> None:
    if _store(hass).get("ws_registered"):
        return
    try:
        websocket_api.async_register_command(hass, ws_get_services)
        websocket_api.async_register_command(hass, ws_get_url)
        websocket_api.async_register_command(hass, ws_set_service)
        websocket_api.async_register_command(hass, ws_update_status)
        websocket_api.async_register_command(hass, ws_update_check)
        websocket_api.async_register_command(hass, ws_update_apply)
        _store(hass)["ws_registered"] = True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Core Configurator websocket already registered: %s", err)
