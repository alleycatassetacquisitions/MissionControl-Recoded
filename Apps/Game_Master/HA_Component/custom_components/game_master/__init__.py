"""Game Master — gameplay controls + event management + affiliation catalog via MCS.

Design contracts:
  P2  Authority: MCS is the single Central adapter. Game Master reads/writes
      events and game-state through MCS only.
  P5  Event ownership: Game Master creates / edits / sets-active events.
      Registration is read-only (active event for roster gating).
  P8  Reusable primitives: all HTTP goes through shared_libraries.http.async_request.

Event ownership moved from Registration in Phase 1c so registration-desk staff
cannot mis-click set-active.  Registration panels read ``registration/get_active_event``
(MCS-backed, name-enriched from this integration's cache) but cannot mutate events.
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
    ACTIVE_EVENT_ID_KEY,
    DOMAIN,
    EVENT_CACHE_KEY,
    EXTRA_MCS_TOKEN,
    KEY_MCS,
    WS_GET_AFFILIATION_CATALOG,
    WS_GET_EVENTS,
    WS_GET_GAME_STATE,
    WS_SET_DELAYED_SCORES,
    WS_SET_SCORING,
)
from .events import (
    cache_event as _cache_event,
    event_cache as _event_cache,
    load_event_store,
    push_active_event_to_gbn as _push_active_event_to_gbn,
    remember_active as _remember_active,
    restore_active_to_mcs,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {vol.Optional(DOMAIN): vol.Schema({}, extra=vol.ALLOW_EXTRA)},
    extra=vol.ALLOW_EXTRA,
)

# ---------------------------------------------------------------------------
# Voluptuous schemas
# ---------------------------------------------------------------------------

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

_EVENT_CREATE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("venue_name", default=""): cv.string,
        vol.Optional("set_active", default=False): cv.boolean,
    }
)
_EVENT_UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required("event_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("venue_name"): vol.Any(cv.string, None),
    }
)
_EVENT_SET_ACTIVE_SCHEMA = vol.Schema({vol.Required("event_id"): cv.string})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Service registration
# ---------------------------------------------------------------------------


def _register_services(hass: HomeAssistant) -> None:
    if hass.data.get(DOMAIN, {}).get("services_registered"):
        return

    # -- Affiliation catalog CRUD ------------------------------------------

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

    # -- Event CRUD (Phase 1c — moved from Registration) -------------------

    async def _handle_create_event(call: ServiceCall) -> None:
        name = call.data["name"].strip()
        venue = (call.data.get("venue_name") or "").strip()
        set_active = bool(call.data.get("set_active"))
        body: dict[str, Any] = {"name": name}
        if venue:
            body["venue_name"] = venue
        # Create first, then set-active with name hint for MCS display memory.
        event = await _mcs_request(
            hass, "POST", "/events", json_body=body, action="create_event"
        )
        merged: dict[str, Any] = {"name": name}
        if venue:
            merged["venue_name"] = venue
        if isinstance(event, dict):
            merged = {**merged, **event}
            if not (merged.get("name") or "").strip():
                merged["name"] = name
        _cache_event(hass, merged if merged.get("id") else None)
        from .events import save_event_store

        await save_event_store(hass)

        event_id = str(merged["id"]) if merged.get("id") else ""
        if set_active and event_id:
            memory: dict[str, Any] = {"name": name}
            if venue:
                memory["venue_name"] = venue
            await _mcs_request(
                hass,
                "PUT",
                f"/events/{event_id}/active",
                json_body=memory,
                action="set_active_event",
            )
            await _remember_active(hass, event_id)
            await _push_active_event_to_gbn(hass, event_id, name)
            clear_catalog(hass)
            await refresh_catalog(hass, event_id=event_id)

    async def _handle_update_event(call: ServiceCall) -> None:
        event_id = call.data["event_id"]
        body: dict[str, Any] = {}
        if "name" in call.data and call.data["name"] is not None:
            body["name"] = call.data["name"]
        if "venue_name" in call.data:
            body["venue_name"] = call.data["venue_name"]
        if not body:
            raise HomeAssistantError("Supply at least one of name or venue_name.")
        event = await _mcs_request(
            hass,
            "PATCH",
            f"/events/{event_id}",
            json_body=body,
            action="update_event",
        )
        merged: dict[str, Any] = {"id": event_id, **body}
        if isinstance(event, dict):
            merged = {**merged, **event}
        _cache_event(hass, merged)
        from .events import save_event_store

        await save_event_store(hass)

    async def _handle_set_active_event(call: ServiceCall) -> None:
        event_id = call.data["event_id"]
        cached = _event_cache(hass).get(event_id) or {}
        memory: dict[str, Any] = {}
        if cached.get("name"):
            memory["name"] = cached["name"]
        if cached.get("venue_name") is not None:
            memory["venue_name"] = cached["venue_name"]
        await _mcs_request(
            hass,
            "PUT",
            f"/events/{event_id}/active",
            json_body=memory or None,
            action="set_active_event",
        )
        if event_id not in _event_cache(hass):
            _event_cache(hass)[event_id] = {
                "id": event_id,
                "name": cached.get("name") or "",
                "venue_name": cached.get("venue_name"),
                "created_at": cached.get("created_at") or "",
            }
        await _remember_active(hass, event_id)
        await _push_active_event_to_gbn(
            hass, event_id, str(cached.get("name") or "")
        )
        clear_catalog(hass)
        await refresh_catalog(hass, event_id=event_id)

    # -- Register all -------------------------------------------------------

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
    hass.services.async_register(
        DOMAIN, "create_event", _handle_create_event, schema=_EVENT_CREATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, "update_event", _handle_update_event, schema=_EVENT_UPDATE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        "set_active_event",
        _handle_set_active_event,
        schema=_EVENT_SET_ACTIVE_SCHEMA,
    )
    hass.data.setdefault(DOMAIN, {})["services_registered"] = True


# ---------------------------------------------------------------------------
# HA lifecycle
# ---------------------------------------------------------------------------


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
    _event_cache(hass)  # ensure cache dict exists
    await load_event_store(hass)
    await async_load_defaults(hass)
    _register_ws(hass)
    _register_services(hass)
    # MCS memory is wiped on its restart — re-seed last active + display name
    await restore_active_to_mcs(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


# ---------------------------------------------------------------------------
# Websocket handlers
# ---------------------------------------------------------------------------


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
            # Cache active event name so Registration's get_active_event can enrich.
            if eid:
                _cache_event(hass, active)
        from .affiliations import catalog_store

        cached = catalog_store(hass)
        if eid and cached.get("event_id") and str(cached.get("event_id")) != eid:
            clear_catalog(hass)
    connection.send_result(msg["id"], data if isinstance(data, dict) else {})


@websocket_api.websocket_command({vol.Required("type"): WS_GET_EVENTS})
@websocket_api.async_response
async def ws_get_events(hass: HomeAssistant, connection, msg) -> None:
    """List events from MCS; stub-aware when Central GET /events is not ready."""
    cached_list = list(_event_cache(hass).values())
    if async_request is None:
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached_list,
                "detail": "shared_libraries not available",
            },
        )
        return
    token = _mcs_token(hass)
    if not token:
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached_list,
                "detail": "MCS token not set in Core Configurator",
            },
        )
        return
    response = await async_request(hass, KEY_MCS, "GET", "/events", token=token)
    if response is None:
        connection.send_result(
            msg["id"],
            {"ready": False, "events": cached_list, "detail": "MCS unreachable"},
        )
        return
    if response.status == 501:
        detail = await _response_detail(response)
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached_list,
                "detail": detail
                or "Waiting on Central GET /events — using session cache only",
            },
        )
        return
    if response.status >= 400:
        detail = await _response_detail(response)
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached_list,
                "detail": detail or f"MCS returned HTTP {response.status}",
            },
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_result(
            msg["id"],
            {"ready": False, "events": cached_list, "detail": "Invalid events JSON"},
        )
        return
    events: list[dict[str, Any]] = []
    raw_list = data.get("events") if isinstance(data, dict) else data
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, dict) and item.get("id"):
                _cache_event(hass, item)
                events.append(_event_cache(hass)[str(item["id"])])
    connection.send_result(
        msg["id"],
        {"ready": True, "events": events or cached_list, "detail": None},
    )


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
    websocket_api.async_register_command(hass, ws_get_events)
    websocket_api.async_register_command(hass, ws_set_scoring)
    websocket_api.async_register_command(hass, ws_set_delayed_scores)
    websocket_api.async_register_command(hass, ws_get_affiliation_catalog)
    store["ws_registered"] = True
