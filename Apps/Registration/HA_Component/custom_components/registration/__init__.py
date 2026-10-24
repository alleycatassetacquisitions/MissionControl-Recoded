"""Registration integration — Home Assistant face of Master Control Server.

Design contracts:
  P2  Authority: MCS is the single Central adapter. Registration reads from MCS only.
  P5  Propagate truth: on setup AND on core_configurator_updated, push one
      peer snapshot to MCS POST /config (Central URLs + LXC peer URLs). MCS fans
      out to companions; AlleycatTV HA publishes retained Pi config over MQTT.
  P6  No retry loops: if MCS is down during config push, log and continue.
      The coordinator /health poll surfaces unavailability.
  P8  Reusable primitives: all HTTP goes through shared_libraries.http.async_request.

Token storage: MCS API token lives in Core Configurator (extra.token on
master_control_server). Registration never stores credentials in its config entry.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import (
    ACTIVE_EVENT_ID_KEY,
    AFFILIATION_CATALOG_KEY,
    DOMAIN,
    EVENT_CACHE_KEY,
    EVENT_STORE,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_GBN,
    KEY_MCS,
    PLAYER_NAME_MAX_LEN,
    STORAGE_KEY,
    STORAGE_VERSION,
    WS_GET_ACTIVE_EVENT,
    WS_GET_AFFILIATION_CATALOG,
    WS_GET_EVENTS,
    WS_GET_ROSTER,
    WS_GET_TEAMS,
)
from .coordinator import McsDataUpdateCoordinator, _mcs_token

# Core Configurator keys that belong in the MCS peer snapshot.
_PEER_PUSH_KEYS = frozenset(
    {
        KEY_MCS,
        KEY_CENTRAL_PRIMARY,
        KEY_CENTRAL_SECONDARY,
        KEY_GBN,
        "alleycattv",
        "net_time",
        "proxmox",
    }
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

PLATFORMS = ["sensor"]

_PLAYER_NAME = vol.All(cv.string, vol.Length(min=1, max=PLAYER_NAME_MAX_LEN))

_PLAYER_WRITE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): _PLAYER_NAME,
        vol.Optional("email", default=""): cv.string,
        vol.Optional("affiliations"): dict,
    }
)

_PLAYER_UPDATE_SCHEMA = vol.Schema(
    {
        vol.Required("player_id"): cv.string,
        vol.Optional("name"): _PLAYER_NAME,
        vol.Optional("email"): vol.Any(cv.string, None),
        vol.Optional("team_id"): vol.Any(cv.string, None),
        vol.Optional("active"): cv.boolean,
        vol.Optional("clear_email", default=False): cv.boolean,
        vol.Optional("clear_team", default=False): cv.boolean,
        vol.Optional("affiliations"): dict,
    }
)

_PLAYER_DELETE_SCHEMA = vol.Schema({vol.Required("player_id"): cv.string})

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
# Helpers
# ---------------------------------------------------------------------------


def _event_cache(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    store = hass.data.setdefault(DOMAIN, {})
    return store.setdefault(EVENT_CACHE_KEY, {})


def _cache_event(hass: HomeAssistant, event: dict[str, Any] | None) -> None:
    """Merge into session cache — never clobber a known name with a blank."""
    if not isinstance(event, dict):
        return
    event_id = event.get("id")
    if not event_id:
        return
    key = str(event_id)
    prev = _event_cache(hass).get(key) or {}
    new_name = (event.get("name") or "").strip()
    new_created = (event.get("created_at") or "").strip()
    venue = event.get("venue_name")
    if venue is None and "venue_name" not in event:
        venue = prev.get("venue_name")
    _event_cache(hass)[key] = {
        "id": key,
        "name": new_name or prev.get("name") or "",
        "venue_name": venue,
        "created_at": new_created or prev.get("created_at") or "",
    }


async def _save_event_store(hass: HomeAssistant) -> None:
    """Persist known events + active id so names survive HA restart."""
    store: Store | None = hass.data.get(DOMAIN, {}).get(EVENT_STORE)
    if store is None:
        return
    await store.async_save(
        {
            "events": dict(_event_cache(hass)),
            "active_event_id": hass.data[DOMAIN].get(ACTIVE_EVENT_ID_KEY),
        }
    )


async def _load_event_store(hass: HomeAssistant) -> None:
    """Load persisted events into memory (until Central GET /events is ready)."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    hass.data.setdefault(DOMAIN, {})[EVENT_STORE] = store
    data = await store.async_load() or {}
    for item in (data.get("events") or {}).values():
        if isinstance(item, dict):
            _cache_event(hass, item)
    active_id = data.get("active_event_id")
    if active_id:
        hass.data[DOMAIN][ACTIVE_EVENT_ID_KEY] = str(active_id)


async def _remember_active(hass: HomeAssistant, event_id: str | None) -> None:
    hass.data.setdefault(DOMAIN, {})[ACTIVE_EVENT_ID_KEY] = event_id
    await _save_event_store(hass)


def _enrich_active_from_cache(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Fill empty active-event name from session cache when MCS only has the id."""
    event_id = data.get("active_event_id")
    event = data.get("event")
    if not event_id:
        # Fall back to HA-persisted active when MCS memory was wiped
        event_id = hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY)
        if event_id:
            data = {**data, "active_event_id": event_id}
    if not event_id:
        return data
    cached = _event_cache(hass).get(str(event_id))
    if not cached:
        return data
    if not isinstance(event, dict):
        event = {
            "id": str(event_id),
            "name": "",
            "venue_name": None,
            "created_at": "",
        }
    if not (event.get("name") or "").strip() and cached.get("name"):
        event = {**event, "name": cached["name"]}
    if event.get("venue_name") is None and cached.get("venue_name") is not None:
        event = {**event, "venue_name": cached.get("venue_name")}
    if not (event.get("id") or "").strip():
        event = {**event, "id": str(event_id)}
    data = {**data, "event": event, "active_event_id": str(event_id)}
    return data


async def _push_active_event_to_gbn(
    hass: HomeAssistant, event_id: str, event_name: str = ""
) -> None:
    """Tell GBN the active event so /poster-cycle kiosks do not wait on MCS."""
    if async_request is None or not event_id:
        return
    name = (event_name or "").strip()
    if not name:
        cached = _event_cache(hass).get(str(event_id)) or {}
        name = str(cached.get("name") or "").strip()
    try:
        response = await async_request(
            hass,
            KEY_GBN,
            "PUT",
            "/api/events/active",
            json={
                "active_event_id": str(event_id),
                "event_name": name,
            },
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Registration: GBN active-event push failed: %s", err)
        return
    if response is None:
        _LOGGER.debug("Registration: GBN URL not configured — skip active push")
        return
    try:
        if response.status >= 400:
            detail = await _response_detail(response)
            _LOGGER.warning(
                "Registration: GBN active-event push HTTP %s: %s",
                response.status,
                detail or "(no body)",
            )
        else:
            _LOGGER.info(
                "Registration: pushed active event %s (%s) to GBN",
                event_id,
                name or "unnamed",
            )
    finally:
        response.release()


async def _restore_active_to_mcs(hass: HomeAssistant) -> None:
    """After HA/MCS restart, re-apply last active + name hint to MCS memory."""
    event_id = hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY)
    if not event_id:
        return
    cached = _event_cache(hass).get(str(event_id)) or {}
    memory: dict[str, Any] = {}
    if cached.get("name"):
        memory["name"] = cached["name"]
    if cached.get("venue_name") is not None:
        memory["venue_name"] = cached["venue_name"]
    try:
        await _mcs_request(
            hass,
            "PUT",
            f"/events/{event_id}/active",
            json_body=memory or None,
            action="restore_active_event",
        )
        _LOGGER.info(
            "Registration: restored active event %s (%s) to MCS memory",
            event_id,
            cached.get("name") or "unnamed",
        )
    except HomeAssistantError as err:
        _LOGGER.warning(
            "Registration: could not restore active event to MCS: %s", err
        )
    await _push_active_event_to_gbn(
        hass, str(event_id), str(cached.get("name") or "")
    )


async def _response_detail(response) -> str:
    """Extract human-readable detail from MCS/Central error body."""
    try:
        text = (await response.text()).strip()
    except Exception:  # noqa: BLE001
        return ""
    if not text:
        return ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            detail = data.get("detail") or data.get("message") or data.get("error")
            if detail:
                return str(detail)
    except Exception:  # noqa: BLE001
        pass
    return text


def _host_clock_url_from_proxmox(proxmox_url: str) -> str:
    """Derive Net Time host clock agent URL from Core Configurator Proxmox URL."""
    raw = (proxmox_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = parsed.hostname
    if not host:
        return ""
    return f"http://{host}:8721"


def _mqtt_broker_hint(hass: HomeAssistant) -> tuple[str, str]:
    """Best-effort MQTT host/port for Pi retained config (empty if unknown)."""
    try:
        entries = hass.config_entries.async_entries("mqtt")
        for entry in entries:
            data = entry.data or {}
            host = str(data.get("broker") or data.get("host") or "").strip()
            if host:
                port = str(data.get("port") or "1883")
                return host, port
    except Exception:  # noqa: BLE001
        pass
    return "", ""


async def _push_central_config(hass: HomeAssistant) -> None:
    """Push Central URLs + venue peer snapshot to MCS POST /config."""
    try:
        from custom_components.core_configurator.helpers import get_extra, get_url
        from custom_components.shared_libraries.http import async_request as request
    except ImportError as err:
        _LOGGER.warning(
            "Registration: cannot push peer config — dependency missing: %s", err
        )
        return

    token = _mcs_token(hass)
    if not token:
        _LOGGER.warning(
            "Registration: MCS token not set in Core Configurator — peer config push skipped."
        )
        return

    primary = get_url(hass, KEY_CENTRAL_PRIMARY)
    secondary = get_url(hass, KEY_CENTRAL_SECONDARY)
    mcs_url = get_url(hass, KEY_MCS)
    gbn_url = get_url(hass, KEY_GBN)
    alleycattv_url = get_url(hass, "alleycattv")
    net_time_url = get_url(hass, "net_time")
    net_time_token = str(get_extra(hass, "net_time", "token", "") or "")
    host_clock_url = _host_clock_url_from_proxmox(get_url(hass, "proxmox"))
    mqtt_host, mqtt_port = _mqtt_broker_hint(hass)

    payload = {
        "central_primary": primary,
        "central_secondary": secondary,
        "mcs_url": mcs_url,
        "gbn_url": gbn_url,
        "alleycattv_url": alleycattv_url,
        "net_time_url": net_time_url,
        "net_time_token": net_time_token,
        "host_clock_url": host_clock_url,
        "mqtt_host": mqtt_host,
        "mqtt_port": mqtt_port,
    }

    response = await request(
        hass,
        KEY_MCS,
        "POST",
        "/config",
        token=token,
        json=payload,
    )
    if response is None:
        _LOGGER.warning(
            "Registration: MCS is unreachable — peer config push skipped. "
            "Will retry on next HA restart or sync_now call."
        )
    elif response.status >= 400:
        _LOGGER.warning(
            "Registration: MCS /config returned HTTP %d — config not applied.",
            response.status,
        )
    else:
        _LOGGER.info(
            "Registration: peer config pushed — mcs=%r gbn=%r net_time=%r alleycattv=%r",
            mcs_url,
            gbn_url,
            net_time_url,
            alleycattv_url,
        )


def _player_payload(service_call: ServiceCall) -> dict[str, Any]:
    """Build MCS player create/update JSON body."""
    payload: dict[str, Any] = {}
    if "name" in service_call.data and service_call.data.get("name") is not None:
        name = str(service_call.data.get("name") or "").strip()
        if name:
            if len(name) > PLAYER_NAME_MAX_LEN:
                raise HomeAssistantError(
                    f"name must be at most {PLAYER_NAME_MAX_LEN} characters"
                )
            payload["name"] = name
    if service_call.data.get("clear_email"):
        payload["clear_email"] = True
    elif "email" in service_call.data:
        email = service_call.data.get("email")
        if email is None:
            payload["clear_email"] = True
        else:
            email_s = str(email).strip()
            if email_s:
                payload["email"] = email_s
            else:
                payload["clear_email"] = True
    if service_call.data.get("clear_team"):
        payload["clear_team"] = True
    elif "team_id" in service_call.data:
        team_id = service_call.data.get("team_id")
        if team_id is None or str(team_id).strip() == "":
            payload["clear_team"] = True
        else:
            payload["team_id"] = str(team_id).strip()
    if "active" in service_call.data and service_call.data.get("active") is not None:
        payload["active"] = bool(service_call.data["active"])
    if "affiliations" in service_call.data:
        raw = service_call.data.get("affiliations")
        if isinstance(raw, dict):
            cleaned: dict[str, str | None] = {}
            for key, value in raw.items():
                cat = str(key).strip()
                if not cat:
                    continue
                if value is None or value == "":
                    cleaned[cat] = None
                else:
                    cleaned[cat] = str(value).strip()
            payload["affiliations"] = cleaned
    return payload


def _affiliation_catalog(hass: HomeAssistant) -> dict[str, Any]:
    store = hass.data.setdefault(DOMAIN, {})
    return store.setdefault(
        AFFILIATION_CATALOG_KEY,
        {"event_id": None, "categories": []},
    )


def _clear_affiliation_catalog(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    store[AFFILIATION_CATALOG_KEY] = {"event_id": None, "categories": []}
    # Game Master owns the durable panel cache — clear it on active-event change.
    try:
        from custom_components.game_master.affiliations import clear_catalog as gm_clear

        gm_clear(hass)
    except ImportError:
        pass


async def _resolve_active_event_id(hass: HomeAssistant) -> str:
    """Best-effort active event id from MCS, then HA memory."""
    token = _mcs_token(hass)
    if async_request is not None and token:
        response = await async_request(
            hass, KEY_MCS, "GET", "/events/active", token=token
        )
        if response is not None and response.status < 400:
            try:
                data = await response.json()
                if isinstance(data, dict):
                    eid = str(data.get("active_event_id") or "")
                    if eid:
                        return eid
            except Exception:  # noqa: BLE001
                pass
    return str(hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY) or "")


async def _refresh_affiliation_catalog(
    hass: HomeAssistant, *, event_id: str | None = None
) -> dict[str, Any]:
    """Delegate to Game Master catalog (owner). Keep a local mirror for legacy WS."""
    try:
        from custom_components.game_master.affiliations import (
            refresh_catalog as gm_refresh,
        )

        result = await gm_refresh(hass, event_id=event_id)
        hass.data.setdefault(DOMAIN, {})[AFFILIATION_CATALOG_KEY] = result
        return result
    except ImportError:
        _LOGGER.warning(
            "Registration: game_master not available — affiliation catalog empty"
        )
        empty = {"event_id": (event_id or None), "categories": []}
        hass.data.setdefault(DOMAIN, {})[AFFILIATION_CATALOG_KEY] = empty
        return empty


async def _mcs_request(
    hass: HomeAssistant,
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    action: str,
) -> Any | None:
    """Call MCS; raise HomeAssistantError with Central/MCS detail on failure.

    Returns parsed JSON body (or None for empty success bodies).
    """
    if async_request is None:
        raise HomeAssistantError("Registration: shared_libraries not available")
    token = _mcs_token(hass)
    if not token:
        raise HomeAssistantError(
            "MCS token not set in Core Configurator — "
            f"{action} skipped."
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
# HA lifecycle
# ---------------------------------------------------------------------------


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load from YAML ``registration:`` and import the install-only config entry."""
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
        _LOGGER.info("Registration: starting config-entry import from YAML")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Registration."""
    coordinator = McsDataUpdateCoordinator(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _event_cache(hass)  # ensure cache exists
    await _load_event_store(hass)

    _register_services(hass, entry)
    _register_ws(hass)

    await _push_central_config(hass)
    # MCS memory is wiped on its restart — re-seed last active + display name
    await _restore_active_to_mcs(hass)

    @callback
    def _on_cc_updated(event: Event) -> None:
        changed_key = event.data.get("key")
        if changed_key is None or changed_key in _PEER_PUSH_KEYS:
            hass.async_create_task(_push_central_config(hass))
        if changed_key in (KEY_MCS, KEY_CENTRAL_PRIMARY, KEY_CENTRAL_SECONDARY, None):
            hass.async_create_task(coordinator.async_refresh())

    entry.async_on_unload(
        hass.bus.async_listen("core_configurator_updated", _on_cc_updated)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_refresh()
    return True


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register HA services for Registration."""

    async def _handle_sync_now(_service_call: ServiceCall) -> None:
        # Re-push Central URLs then refresh roster + affiliation catalog
        await _push_central_config(hass)
        coordinator: McsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()
        await _refresh_affiliation_catalog(hass)

    async def _handle_register_player(service_call: ServiceCall) -> None:
        body = _player_payload(service_call)
        if not body.get("name"):
            raise HomeAssistantError("name is required")
        await _mcs_request(
            hass,
            "POST",
            "/players",
            json_body=body,
            action="register_player",
        )
        await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_update_player(service_call: ServiceCall) -> None:
        player_id = service_call.data["player_id"]
        body = _player_payload(service_call)
        if not body:
            raise HomeAssistantError(
                "Supply name, email, team_id, active, or affiliations"
            )
        await _mcs_request(
            hass,
            "PUT",
            f"/players/{player_id}",
            json_body=body,
            action="update_player",
        )
        await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_delete_player(service_call: ServiceCall) -> None:
        """Soft-deactivate player (MCS maps DELETE → PATCH active=false)."""
        player_id = service_call.data["player_id"]
        await _mcs_request(
            hass,
            "DELETE",
            f"/players/{player_id}",
            action="delete_player",
        )
        await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_create_event(service_call: ServiceCall) -> None:
        name = service_call.data["name"].strip()
        venue = (service_call.data.get("venue_name") or "").strip()
        set_active = bool(service_call.data.get("set_active"))
        body: dict[str, Any] = {"name": name}
        if venue:
            body["venue_name"] = venue
        # Create first, then set-active with name hint — more reliable than
        # ?set_active=true alone for MCS display memory after restarts.
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
        await _save_event_store(hass)

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
            _clear_affiliation_catalog(hass)
            await _refresh_affiliation_catalog(hass, event_id=event_id)
            await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_update_event(service_call: ServiceCall) -> None:
        event_id = service_call.data["event_id"]
        body: dict[str, Any] = {}
        if "name" in service_call.data and service_call.data["name"] is not None:
            body["name"] = service_call.data["name"]
        if "venue_name" in service_call.data:
            body["venue_name"] = service_call.data["venue_name"]
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
        await _save_event_store(hass)

    async def _handle_set_active_event(service_call: ServiceCall) -> None:
        event_id = service_call.data["event_id"]
        cached = _event_cache(hass).get(event_id) or {}
        # Pass known name to MCS memory (not forwarded to Central) so Active
        # keeps showing the title instead of a bare UUID after set-active.
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
        _clear_affiliation_catalog(hass)
        await _refresh_affiliation_catalog(hass, event_id=event_id)
        await hass.data[DOMAIN][entry.entry_id].async_refresh()

    # Affiliation catalog CRUD lives on Game Master (year-1 ownership).

    registrations = (
        ("sync_now", _handle_sync_now, None),
        ("register_player", _handle_register_player, _PLAYER_WRITE_SCHEMA),
        ("update_player", _handle_update_player, _PLAYER_UPDATE_SCHEMA),
        ("delete_player", _handle_delete_player, _PLAYER_DELETE_SCHEMA),
        ("create_event", _handle_create_event, _EVENT_CREATE_SCHEMA),
        ("update_event", _handle_update_event, _EVENT_UPDATE_SCHEMA),
        ("set_active_event", _handle_set_active_event, _EVENT_SET_ACTIVE_SCHEMA),
    )
    for name, handler, schema in registrations:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


def _coordinator(hass: HomeAssistant) -> McsDataUpdateCoordinator | None:
    domain_data = hass.data.get(DOMAIN) or {}
    for value in domain_data.values():
        if isinstance(value, McsDataUpdateCoordinator):
            return value
    return None


@websocket_api.websocket_command({vol.Required("type"): WS_GET_ROSTER})
@websocket_api.async_response
async def ws_get_roster(hass: HomeAssistant, connection, msg) -> None:
    """Return the coordinator-cached roster for the Registration panel."""
    coordinator = _coordinator(hass)
    if coordinator is None:
        connection.send_result(msg["id"], {"players": [], "count": 0})
        return
    data = coordinator.data or {}
    connection.send_result(
        msg["id"],
        {
            "players": list(data.get("players") or []),
            "count": int(data.get("count") or 0),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): WS_GET_EVENTS})
@websocket_api.async_response
async def ws_get_events(hass: HomeAssistant, connection, msg) -> None:
    """List events from MCS; stub-aware when Central GET /events is not ready."""
    cached = list(_event_cache(hass).values())
    if async_request is None:
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached,
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
                "events": cached,
                "detail": "MCS token not set in Core Configurator",
            },
        )
        return
    response = await async_request(hass, KEY_MCS, "GET", "/events", token=token)
    if response is None:
        connection.send_result(
            msg["id"],
            {"ready": False, "events": cached, "detail": "MCS unreachable"},
        )
        return
    if response.status == 501:
        detail = await _response_detail(response)
        connection.send_result(
            msg["id"],
            {
                "ready": False,
                "events": cached,
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
                "events": cached,
                "detail": detail or f"MCS returned HTTP {response.status}",
            },
        )
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_result(
            msg["id"],
            {"ready": False, "events": cached, "detail": "Invalid events JSON"},
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
        {"ready": True, "events": events or cached, "detail": None},
    )


@websocket_api.websocket_command({vol.Required("type"): WS_GET_ACTIVE_EVENT})
@websocket_api.async_response
async def ws_get_active_event(hass: HomeAssistant, connection, msg) -> None:
    """Return active event from MCS (Central game-state backed)."""
    empty = {
        "ready": False,
        "active_event_id": None,
        "event": None,
        "source": "mcs_memory",
    }
    if async_request is None:
        connection.send_result(msg["id"], empty)
        return
    token = _mcs_token(hass)
    if not token:
        connection.send_result(msg["id"], empty)
        return
    response = await async_request(
        hass, KEY_MCS, "GET", "/events/active", token=token
    )
    if response is None or response.status >= 400:
        connection.send_result(msg["id"], empty)
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_result(msg["id"], empty)
        return
    if not isinstance(data, dict):
        connection.send_result(msg["id"], empty)
        return
    data = _enrich_active_from_cache(hass, data)
    if data.get("event"):
        _cache_event(hass, data["event"])
    connection.send_result(msg["id"], data)


@websocket_api.websocket_command({vol.Required("type"): WS_GET_AFFILIATION_CATALOG})
@websocket_api.async_response
async def ws_get_affiliation_catalog(hass: HomeAssistant, connection, msg) -> None:
    """Return event-keyed affiliation catalog (refresh from MCS when needed)."""
    catalog = await _refresh_affiliation_catalog(hass)
    connection.send_result(
        msg["id"],
        {
            "event_id": catalog.get("event_id"),
            "categories": list(catalog.get("categories") or []),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_GET_TEAMS,
        vol.Optional("event_id"): cv.string,
    }
)
@websocket_api.async_response
async def ws_get_teams(hass: HomeAssistant, connection, msg) -> None:
    """List teams for an event (defaults to active event)."""
    event_id = (msg.get("event_id") or "").strip()
    if not event_id:
        # Prefer MCS active, then HA-persisted
        active_resp = None
        token = _mcs_token(hass)
        if async_request is not None and token:
            active_resp = await async_request(
                hass, KEY_MCS, "GET", "/events/active", token=token
            )
        if active_resp is not None and active_resp.status < 400:
            try:
                active_data = await active_resp.json()
                if isinstance(active_data, dict):
                    event_id = str(active_data.get("active_event_id") or "")
            except Exception:  # noqa: BLE001
                event_id = ""
        if not event_id:
            event_id = str(
                hass.data.get(DOMAIN, {}).get(ACTIVE_EVENT_ID_KEY) or ""
            )
    if not event_id:
        connection.send_result(msg["id"], {"teams": [], "event_id": None})
        return
    if async_request is None:
        connection.send_result(msg["id"], {"teams": [], "event_id": event_id})
        return
    token = _mcs_token(hass)
    if not token:
        connection.send_result(msg["id"], {"teams": [], "event_id": event_id})
        return
    response = await async_request(
        hass, KEY_MCS, "GET", f"/events/{event_id}/teams", token=token
    )
    if response is None or response.status >= 400:
        connection.send_result(msg["id"], {"teams": [], "event_id": event_id})
        return
    try:
        data = await response.json()
    except Exception:  # noqa: BLE001
        connection.send_result(msg["id"], {"teams": [], "event_id": event_id})
        return
    teams = data if isinstance(data, list) else []
    connection.send_result(msg["id"], {"teams": teams, "event_id": event_id})


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_roster)
    websocket_api.async_register_command(hass, ws_get_events)
    websocket_api.async_register_command(hass, ws_get_active_event)
    websocket_api.async_register_command(hass, ws_get_teams)
    websocket_api.async_register_command(hass, ws_get_affiliation_catalog)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
