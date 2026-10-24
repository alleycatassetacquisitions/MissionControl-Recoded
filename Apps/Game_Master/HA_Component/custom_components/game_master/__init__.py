"""Game Master — gameplay controls + affiliation catalog via MCS → Central.

Event selection and player registration stay on the Registration panel.
Game Master owns affiliation category/choice CRUD and the event-keyed catalog
cache. This integration exposes websocket commands for the Game Master sidebar.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .affiliations import (
    async_load_defaults,
    clear_catalog,
    get_enriched_catalog,
    refresh_catalog,
    set_default_affiliation,
)
from .const import (
    DOMAIN,
    EXTRA_MCS_TOKEN,
    KEY_MCS,
    WS_GET_AFFILIATION_CATALOG,
    WS_GET_GAME_STATE,
    WS_SET_DELAYED_SCORES,
    WS_SET_SCORING,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.Schema({}, extra=vol.ALLOW_EXTRA)},
    extra=vol.ALLOW_EXTRA,
)

_AFFILIATION_NAME_SCHEMA = vol.Schema({vol.Required("name"): cv.string})
_CREATE_AFFILIATION_SCHEMA = vol.Schema(
    {
        vol.Required("category_id"): cv.string,
        vol.Required("name"): cv.string,
    }
)
_RENAME_CATEGORY_SCHEMA = vol.Schema(
    {
        vol.Required("category_id"): cv.string,
        vol.Required("name"): cv.string,
    }
)
_RENAME_AFFILIATION_SCHEMA = vol.Schema(
    {
        vol.Required("category_id"): cv.string,
        vol.Required("affiliation_id"): cv.string,
        vol.Required("name"): cv.string,
    }
)
_SET_DEFAULT_AFFILIATION_SCHEMA = vol.Schema(
    {
        vol.Required("category_id"): cv.string,
        vol.Optional("affiliation_id", default=""): cv.string,
    }
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


async def _mcs_request(
    hass: HomeAssistant,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    action: str,
) -> Any | None:
    if async_request is None:
        raise HomeAssistantError("Game Master: shared_libraries not available")
    token = _mcs_token(hass)
    if not token:
        raise HomeAssistantError(
            f"MCS token not set in Core Configurator — {action} skipped."
        )
    response = await async_request(
        hass, KEY_MCS, method, path, token=token, json=json_body
    )
    if response is None:
        raise HomeAssistantError(f"MCS unreachable during {action}.")
    if response.status >= 400:
        detail = await _response_detail(response)
        raise HomeAssistantError(
            detail or f"MCS returned HTTP {response.status} during {action}."
        )
    if response.status == 204:
        return None
    try:
        text = (await response.text()).strip()
    except Exception:  # noqa: BLE001
        return None
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        return text


def _register_services(hass: HomeAssistant) -> None:
    if hass.data.get(DOMAIN, {}).get("services_registered"):
        return

    async def _create_category(call: ServiceCall) -> None:
        name = str(call.data["name"]).strip()
        await _mcs_request(
            hass,
            "POST",
            "/affiliation-categories",
            json_body={"name": name},
            action="create_affiliation_category",
        )
        await refresh_catalog(hass)

    async def _rename_category(call: ServiceCall) -> None:
        category_id = call.data["category_id"]
        name = str(call.data["name"]).strip()
        await _mcs_request(
            hass,
            "PATCH",
            f"/affiliation-categories/{category_id}",
            json_body={"name": name},
            action="rename_affiliation_category",
        )
        await refresh_catalog(hass)

    async def _create_affiliation(call: ServiceCall) -> None:
        category_id = call.data["category_id"]
        name = str(call.data["name"]).strip()
        await _mcs_request(
            hass,
            "POST",
            f"/affiliation-categories/{category_id}/affiliations",
            json_body={"name": name},
            action="create_affiliation",
        )
        await refresh_catalog(hass)

    async def _rename_affiliation(call: ServiceCall) -> None:
        category_id = call.data["category_id"]
        affiliation_id = call.data["affiliation_id"]
        name = str(call.data["name"]).strip()
        await _mcs_request(
            hass,
            "PATCH",
            f"/affiliation-categories/{category_id}/affiliations/{affiliation_id}",
            json_body={"name": name},
            action="rename_affiliation",
        )
        await refresh_catalog(hass)

    async def _set_default_affiliation(call: ServiceCall) -> None:
        category_id = call.data["category_id"]
        affiliation_id = str(call.data.get("affiliation_id") or "")
        try:
            await set_default_affiliation(
                hass,
                category_id=category_id,
                affiliation_id=affiliation_id,
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        "create_affiliation_category",
        _create_category,
        schema=_AFFILIATION_NAME_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "rename_affiliation_category",
        _rename_category,
        schema=_RENAME_CATEGORY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "create_affiliation",
        _create_affiliation,
        schema=_CREATE_AFFILIATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "rename_affiliation",
        _rename_affiliation,
        schema=_RENAME_AFFILIATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        "set_default_affiliation",
        _set_default_affiliation,
        schema=_SET_DEFAULT_AFFILIATION_SCHEMA,
    )
    hass.data.setdefault(DOMAIN, {})["services_registered"] = True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up from YAML ``game_master: {}`` if present."""
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    await async_load_defaults(hass)
    _register_ws(hass)
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {}
    await async_load_defaults(hass)
    _register_ws(hass)
    _register_services(hass)
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
    # Clear affiliation cache when Central active event changes.
    if isinstance(data, dict):
        active = data.get("active_event")
        eid = ""
        if isinstance(active, dict):
            eid = str(active.get("id") or "")
        from .affiliations import catalog_store

        cached = catalog_store(hass)
        if eid and cached.get("event_id") and str(cached.get("event_id")) != eid:
            clear_catalog(hass)
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


@websocket_api.websocket_command(
    {vol.Required("type"): WS_GET_AFFILIATION_CATALOG}
)
@websocket_api.async_response
async def ws_get_affiliation_catalog(hass: HomeAssistant, connection, msg) -> None:
    """Return event-keyed affiliation catalog with HA-only defaults attached."""
    catalog = await get_enriched_catalog(hass)
    connection.send_result(msg["id"], catalog)


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
    websocket_api.async_register_command(hass, ws_get_affiliation_catalog)
    store["ws_registered"] = True
