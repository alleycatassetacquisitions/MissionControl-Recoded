"""Registration integration — Home Assistant face of Master Control Server.

Design contracts:
  P2  Authority: MCS is the single Central adapter. Registration reads from MCS only.
  P5  Propagate truth: on setup AND on core_configurator_updated, push one
      peer snapshot to MCS POST /config (Central URLs + LXC peer URLs). MCS fans
      out to companions; AlleycatTV HA publishes retained Pi config over MQTT.
  P6  No retry loops: if MCS is down during config push, log and continue.
      The coordinator /health poll surfaces unavailability.
  P8  Reusable primitives: all HTTP goes through shared_libraries.http.async_request.

Event ownership: Game Master creates / edits / sets-active events (Phase 1c).
Registration is read-only for the active event — the active event id gates
player registration but operators cannot change it from this panel.

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
    AFFILIATION_CATALOG_KEY,
    DOMAIN,
    KEY_ALLEYCATTV,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_GBN,
    KEY_MCS,
    KEY_NET_TIME,
    KEY_PROXMOX,
    PLAYER_NAME_MAX_LEN,
    WS_GET_ACTIVE_EVENT,
    WS_GET_AFFILIATION_CATALOG,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    alleycattv_url = get_url(hass, KEY_ALLEYCATTV)
    net_time_url = get_url(hass, KEY_NET_TIME)
    net_time_token = str(get_extra(hass, KEY_NET_TIME, "token", "") or "")
    host_clock_url = _host_clock_url_from_proxmox(get_url(hass, KEY_PROXMOX))
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


async def _refresh_affiliation_catalog(
    hass: HomeAssistant, *, event_id: str | None = None
) -> dict[str, Any]:
    """Delegate to Game Master catalog (owner). Keep a local mirror for legacy WS."""
    try:
        from custom_components.game_master.affiliations import (
            defaults_memory,
            enrich_catalog_with_defaults,
            refresh_catalog as gm_refresh,
        )

        result = await gm_refresh(hass, event_id=event_id)
        enriched = enrich_catalog_with_defaults(result, defaults_memory(hass))
        hass.data.setdefault(DOMAIN, {})[AFFILIATION_CATALOG_KEY] = enriched
        return enriched
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

    _register_services(hass, entry)
    _register_ws(hass)

    await _push_central_config(hass)

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

    # Affiliation catalog CRUD and event management live on Game Master.

    registrations = (
        ("sync_now", _handle_sync_now, None),
        ("register_player", _handle_register_player, _PLAYER_WRITE_SCHEMA),
        ("update_player", _handle_update_player, _PLAYER_UPDATE_SCHEMA),
        ("delete_player", _handle_delete_player, _PLAYER_DELETE_SCHEMA),
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


@websocket_api.websocket_command({vol.Required("type"): WS_GET_ACTIVE_EVENT})
@websocket_api.async_response
async def ws_get_active_event(hass: HomeAssistant, connection, msg) -> None:
    """Return active event from MCS (Central game-state backed).

    Enriches the name from Game Master's event cache when MCS only returns
    the UUID (e.g. after an MCS restart before Central responds).
    """
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
    # Enrich from Game Master's event cache (GM owns event names after Phase 1c).
    try:
        from custom_components.game_master.events import (
            cache_event as gm_cache_event,
            enrich_active_from_cache as gm_enrich_active,
        )

        data = gm_enrich_active(hass, data)
        if data.get("event"):
            gm_cache_event(hass, data["event"])
    except ImportError:
        pass
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
        # Prefer MCS active, then Game Master's persisted active id.
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
            # Fall back to Game Master's persisted active event id.
            try:
                from custom_components.game_master.const import (
                    ACTIVE_EVENT_ID_KEY as GM_ACTIVE_ID,
                    DOMAIN as GM_DOMAIN,
                )

                event_id = str(
                    hass.data.get(GM_DOMAIN, {}).get(GM_ACTIVE_ID) or ""
                )
            except ImportError:
                pass
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
    websocket_api.async_register_command(hass, ws_get_active_event)
    websocket_api.async_register_command(hass, ws_get_teams)
    websocket_api.async_register_command(hass, ws_get_affiliation_catalog)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
