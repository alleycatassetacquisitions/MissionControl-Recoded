"""Net Time — LAN NTP companion bridge via Core Configurator.

Websocket commands for the Core Configurator Net Time card:
  net_time/health  → GET /health (no token)
  net_time/status  → GET /status (Bearer)
  net_time/sync    → POST /sync  (Bearer, iso8601 from operator PC)
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import (
    DOMAIN,
    EXTRA_TOKEN,
    KEY_NET_TIME,
    WS_HEALTH,
    WS_STATUS,
    WS_SYNC,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.Schema({}, extra=vol.ALLOW_EXTRA)},
    extra=vol.ALLOW_EXTRA,
)


def _net_time_token(hass: HomeAssistant) -> str:
    try:
        from custom_components.core_configurator.helpers import get_extra

        return str(get_extra(hass, KEY_NET_TIME, EXTRA_TOKEN, "") or "")
    except Exception:  # noqa: BLE001
        return ""


async def _response_detail(response) -> str:
    try:
        data = await response.json()
        if isinstance(data, dict):
            for key in ("detail", "message", "error"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return str(data)
    except Exception:  # noqa: BLE001
        try:
            text = await response.text()
            return (text or "").strip()
        except Exception:  # noqa: BLE001
            return ""


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML ``net_time: {}`` if present."""
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    _register_ws(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    _register_ws(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


async def handle_health(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Confirm Net Time is reachable from Mission Control (GET /health)."""
    if async_request is None:
        connection.send_error(msg["id"], "shared_libraries", "not available")
        return
    response = await async_request(hass, KEY_NET_TIME, "GET", "/health")
    if response is None:
        connection.send_error(
            msg["id"],
            "net_time_unreachable",
            "Net Time URL not set in Core Configurator or unreachable",
        )
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_error(
            msg["id"],
            "net_time_error",
            detail or f"Net Time returned HTTP {response.status}",
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        data = {"status": "ok"}
    connection.send_result(
        msg["id"],
        {
            "online": True,
            "health": data if isinstance(data, dict) else {"status": "ok"},
        },
    )


async def handle_status(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Fetch chrony / public NTP status (GET /status)."""
    if async_request is None:
        connection.send_error(msg["id"], "shared_libraries", "not available")
        return
    token = _net_time_token(hass)
    if not token:
        connection.send_error(
            msg["id"],
            "net_time_token",
            "Net Time token not set in Core Configurator",
        )
        return
    response = await async_request(
        hass, KEY_NET_TIME, "GET", "/status", token=token
    )
    if response is None:
        connection.send_error(
            msg["id"],
            "net_time_unreachable",
            "Net Time URL not set in Core Configurator or unreachable",
        )
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_error(
            msg["id"],
            "net_time_error",
            detail or f"Net Time returned HTTP {response.status}",
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_error(msg["id"], "bad_json", "Invalid status JSON")
        return
    if not isinstance(data, dict):
        connection.send_error(msg["id"], "bad_json", "Invalid status JSON")
        return
    connection.send_result(msg["id"], data)


async def handle_sync(hass: HomeAssistant, connection, msg: dict[str, Any]) -> None:
    """Sync Net Time clock from operator PC ISO-8601 (POST /sync)."""
    if async_request is None:
        connection.send_error(msg["id"], "shared_libraries", "not available")
        return
    token = _net_time_token(hass)
    if not token:
        connection.send_error(
            msg["id"],
            "net_time_token",
            "Net Time token not set in Core Configurator",
        )
        return
    iso8601 = (msg.get("iso8601") or "").strip()
    if not iso8601:
        connection.send_error(msg["id"], "bad_iso", "iso8601 is required")
        return
    response = await async_request(
        hass,
        KEY_NET_TIME,
        "POST",
        "/sync",
        token=token,
        json={"iso8601": iso8601},
    )
    if response is None:
        connection.send_error(
            msg["id"],
            "net_time_unreachable",
            "Net Time URL not set in Core Configurator or unreachable",
        )
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_error(
            msg["id"],
            "net_time_error",
            detail or f"Net Time returned HTTP {response.status}",
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_error(msg["id"], "bad_json", "Invalid sync JSON")
        return
    connection.send_result(msg["id"], data if isinstance(data, dict) else {})


@websocket_api.websocket_command({vol.Required("type"): WS_HEALTH})
@websocket_api.async_response
async def ws_health(hass: HomeAssistant, connection, msg) -> None:
    await handle_health(hass, connection, msg)


@websocket_api.websocket_command({vol.Required("type"): WS_STATUS})
@websocket_api.async_response
async def ws_status(hass: HomeAssistant, connection, msg) -> None:
    await handle_status(hass, connection, msg)


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SYNC,
        vol.Required("iso8601"): cv.string,
    }
)
@websocket_api.async_response
async def ws_sync(hass: HomeAssistant, connection, msg) -> None:
    await handle_sync(hass, connection, msg)


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_health)
    websocket_api.async_register_command(hass, ws_status)
    websocket_api.async_register_command(hass, ws_sync)
    store["ws_registered"] = True
