"""Registration integration — Home Assistant face of Master Control Server.

Design contracts:
  P2  Authority: MCS is the single Central adapter. Registration reads from MCS only.
  P5  Propagate truth: on setup AND on core_configurator_updated, push
      central_primary/central_secondary to MCS POST /config so MCS is always current.
  P6  No retry loops: if MCS is down during config push, log and continue.
      The coordinator /health poll surfaces unavailability.
  P8  Reusable primitives: all HTTP goes through shared_libraries.http.async_request.

Token storage: MCS API token lives in Core Configurator (extra.token on
master_control_server). Registration never stores credentials in its config entry.
"""
from __future__ import annotations

import logging

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import (
    DOMAIN,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_MCS,
    WS_GET_ROSTER,
)
from .coordinator import McsDataUpdateCoordinator, _mcs_token

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

_PLAYER_WRITE_SCHEMA = vol.Schema(
    {
        vol.Required("name"): cv.string,
        vol.Optional("role", default="hunter"): cv.string,
        vol.Optional("neocorp", default="freelancer"): cv.string,
        vol.Optional("faction", default=""): cv.string,
        vol.Optional("neo_id", default=""): cv.string,
    }
)

_PLAYER_UPDATE_SCHEMA = _PLAYER_WRITE_SCHEMA.extend(
    {vol.Required("player_id"): cv.string}
)

_PLAYER_DELETE_SCHEMA = vol.Schema({vol.Required("player_id"): cv.string})


# ---------------------------------------------------------------------------
# Config-push helper
# ---------------------------------------------------------------------------


async def _push_central_config(hass: HomeAssistant) -> None:
    """Push current central_primary / central_secondary from CC to MCS /config.

    Called on setup (first boot + every HA restart) and whenever
    core_configurator_updated fires for either key.

    If MCS is unreachable: log and continue. No retry (design principle 6).
    """
    try:
        from custom_components.core_configurator.helpers import get_url
        from custom_components.shared_libraries.http import async_request as request
    except ImportError as err:
        _LOGGER.warning(
            "Registration: cannot push Central config — dependency missing: %s", err
        )
        return

    token = _mcs_token(hass)
    if not token:
        _LOGGER.warning(
            "Registration: MCS token not set in Core Configurator — Central config push skipped."
        )
        return

    primary = get_url(hass, KEY_CENTRAL_PRIMARY)
    secondary = get_url(hass, KEY_CENTRAL_SECONDARY)

    response = await request(
        hass,
        KEY_MCS,
        "POST",
        "/config",
        token=token,
        json={"central_primary": primary, "central_secondary": secondary},
    )
    if response is None:
        _LOGGER.warning(
            "Registration: MCS is unreachable — Central config push skipped. "
            "Will retry on next HA restart or sync_now call."
        )
    elif response.status >= 400:
        _LOGGER.warning(
            "Registration: MCS /config returned HTTP %d — config not applied.",
            response.status,
        )
    else:
        _LOGGER.debug(
            "Registration: Central config pushed — primary=%r secondary=%r",
            primary,
            secondary,
        )


def _player_payload(service_call) -> dict:
    return {
        "name": service_call.data.get("name", ""),
        "role": service_call.data.get("role", "hunter") or "hunter",
        "neocorp": service_call.data.get("neocorp", "freelancer") or "freelancer",
        "faction": service_call.data.get("faction", "") or "",
        "neo_id": service_call.data.get("neo_id", "") or "",
    }


async def _mcs_mutate(
    hass: HomeAssistant,
    method: str,
    path: str,
    *,
    json: dict | None = None,
    action: str,
) -> bool:
    if async_request is None:
        _LOGGER.error("Registration: shared_libraries not available")
        return False
    token = _mcs_token(hass)
    if not token:
        _LOGGER.warning(
            "Registration: MCS token not set in Core Configurator — %s skipped.",
            action,
        )
        return False
    response = await async_request(
        hass, KEY_MCS, method, path, token=token, json=json
    )
    if response is None or response.status >= 400:
        _LOGGER.warning(
            "Registration: %s failed (status=%s)",
            action,
            response.status if response else "no response",
        )
        return False
    return True


# ---------------------------------------------------------------------------
# HA lifecycle
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Registration.

    Services and websocket must register before any MCS poll. MCS /players can
    exceed the HA HTTP timeout while Central is slow; using first_refresh would
    raise ConfigEntryNotReady and leave Sync Now unavailable (design principle 6).
    """
    coordinator = McsDataUpdateCoordinator(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    _register_services(hass, entry)
    _register_ws(hass)

    await _push_central_config(hass)

    @callback
    def _on_cc_updated(event: Event) -> None:
        changed_key = event.data.get("key")
        if changed_key in (KEY_CENTRAL_PRIMARY, KEY_CENTRAL_SECONDARY, None):
            hass.async_create_task(_push_central_config(hass))
        if changed_key in (KEY_MCS, KEY_CENTRAL_PRIMARY, KEY_CENTRAL_SECONDARY, None):
            hass.async_create_task(coordinator.async_refresh())

    entry.async_on_unload(
        hass.bus.async_listen("core_configurator_updated", _on_cc_updated)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Soft refresh — unavailable sensors are OK when MCS/Central is slow.
    await coordinator.async_refresh()
    return True


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register HA services for Registration."""

    async def _handle_sync_now(_service_call) -> None:
        coordinator: McsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()

    async def _handle_register_player(service_call) -> None:
        ok = await _mcs_mutate(
            hass,
            "POST",
            "/players",
            json=_player_payload(service_call),
            action="register_player",
        )
        if ok:
            await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_update_player(service_call) -> None:
        player_id = service_call.data["player_id"]
        ok = await _mcs_mutate(
            hass,
            "PUT",
            f"/players/{player_id}",
            json=_player_payload(service_call),
            action="update_player",
        )
        if ok:
            await hass.data[DOMAIN][entry.entry_id].async_refresh()

    async def _handle_delete_player(service_call) -> None:
        player_id = service_call.data["player_id"]
        ok = await _mcs_mutate(
            hass,
            "DELETE",
            f"/players/{player_id}",
            action="delete_player",
        )
        if ok:
            await hass.data[DOMAIN][entry.entry_id].async_refresh()

    if not hass.services.has_service(DOMAIN, "sync_now"):
        hass.services.async_register(DOMAIN, "sync_now", _handle_sync_now)
    if not hass.services.has_service(DOMAIN, "register_player"):
        hass.services.async_register(
            DOMAIN,
            "register_player",
            _handle_register_player,
            schema=_PLAYER_WRITE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, "update_player"):
        hass.services.async_register(
            DOMAIN,
            "update_player",
            _handle_update_player,
            schema=_PLAYER_UPDATE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, "delete_player"):
        hass.services.async_register(
            DOMAIN,
            "delete_player",
            _handle_delete_player,
            schema=_PLAYER_DELETE_SCHEMA,
        )


@websocket_api.websocket_command({vol.Required("type"): WS_GET_ROSTER})
@websocket_api.async_response
async def ws_get_roster(hass: HomeAssistant, connection, msg) -> None:
    """Return the coordinator-cached roster for the Registration panel."""
    domain_data = hass.data.get(DOMAIN) or {}
    # Prefer a coordinator entry over the ws_registered flag key.
    coordinator: McsDataUpdateCoordinator | None = None
    for value in domain_data.values():
        if isinstance(value, McsDataUpdateCoordinator):
            coordinator = value
            break
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


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_roster)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
