"""Game Master — gameplay controls via MCS → Central game-state / scoring.

Event selection and player registration stay on the Registration panel.
This integration exposes websocket commands for the Game Master sidebar panel.
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
    EXTRA_MCS_TOKEN,
    KEY_MCS,
    WS_GET_GAME_STATE,
    WS_SET_DELAYED_SCORES,
    WS_SET_SCORING,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.Schema({}, extra=vol.ALLOW_EXTRA)},
    extra=vol.ALLOW_EXTRA,
)


def _mcs_token(hass: HomeAssistant) -> str:
    try:
        from custom_components.core_configurator.helpers import get_extra

        return str(get_extra(hass, KEY_MCS, EXTRA_MCS_TOKEN, "") or "")
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
    """Set up from YAML ``game_master: {}`` if present."""
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


@websocket_api.websocket_command({vol.Required("type"): WS_GET_GAME_STATE})
@websocket_api.async_response
async def ws_get_game_state(hass: HomeAssistant, connection, msg) -> None:
    """Proxy MCS GET /game-state."""
    if async_request is None:
        connection.send_error(msg["id"], "shared_libraries", "not available")
        return
    token = _mcs_token(hass)
    if not token:
        connection.send_error(
            msg["id"], "mcs_token", "MCS token not set in Core Configurator"
        )
        return
    response = await async_request(hass, KEY_MCS, "GET", "/game-state", token=token)
    if response is None:
        connection.send_error(msg["id"], "mcs_unreachable", "MCS unreachable")
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_error(
            msg["id"],
            "mcs_error",
            detail or f"MCS returned HTTP {response.status}",
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_error(msg["id"], "bad_json", "Invalid game-state JSON")
        return
    connection.send_result(msg["id"], data if isinstance(data, dict) else {})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SET_SCORING,
        vol.Required("enabled"): cv.boolean,
        vol.Optional("event_id"): cv.string,
    }
)
@websocket_api.async_response
async def ws_set_scoring(hass: HomeAssistant, connection, msg) -> None:
    """Proxy MCS PUT scoring (active event or explicit event_id)."""
    await _put_enabled(
        hass,
        connection,
        msg,
        path_for_event=lambda eid: f"/events/{eid}/scoring",
        convenience_path="/scoring",
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SET_DELAYED_SCORES,
        vol.Required("enabled"): cv.boolean,
        vol.Optional("event_id"): cv.string,
    }
)
@websocket_api.async_response
async def ws_set_delayed_scores(hass: HomeAssistant, connection, msg) -> None:
    """Proxy MCS PUT delayed-scores."""
    await _put_enabled(
        hass,
        connection,
        msg,
        path_for_event=lambda eid: f"/events/{eid}/delayed-scores",
        convenience_path="/delayed-scores",
    )


async def _put_enabled(
    hass: HomeAssistant,
    connection,
    msg: dict[str, Any],
    *,
    path_for_event,
    convenience_path: str,
) -> None:
    if async_request is None:
        connection.send_error(msg["id"], "shared_libraries", "not available")
        return
    token = _mcs_token(hass)
    if not token:
        connection.send_error(
            msg["id"], "mcs_token", "MCS token not set in Core Configurator"
        )
        return
    event_id = (msg.get("event_id") or "").strip()
    path = path_for_event(event_id) if event_id else convenience_path
    response = await async_request(
        hass,
        KEY_MCS,
        "PUT",
        path,
        token=token,
        json={"enabled": bool(msg["enabled"])},
    )
    if response is None:
        connection.send_error(msg["id"], "mcs_unreachable", "MCS unreachable")
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_error(
            msg["id"],
            "mcs_error",
            detail or f"MCS returned HTTP {response.status}",
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        data = {"enabled": bool(msg["enabled"])}
    connection.send_result(msg["id"], data if isinstance(data, dict) else {})


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_game_state)
    websocket_api.async_register_command(hass, ws_set_scoring)
    websocket_api.async_register_command(hass, ws_set_delayed_scores)
    store["ws_registered"] = True
