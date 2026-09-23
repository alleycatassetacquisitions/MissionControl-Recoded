"""Registration integration — Home Assistant face of Master Control Server.

Design contracts:
  P2  Authority: MCS is the single Central adapter. Registration reads from MCS only.
  P5  Propagate truth: on setup AND on core_configurator_updated, push
      central_primary/central_secondary to MCS POST /config so MCS is always current.
  P6  No retry loops: if MCS is down during config push, log and continue.
      The coordinator /health poll surfaces unavailability.
  P8  Reusable primitives: all HTTP goes through shared_libraries.http.async_request.

Token storage: MCS API token lives in the Registration config entry, never in CC.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

try:
    from custom_components.shared_libraries.http import async_request
except ImportError:
    async_request = None  # type: ignore[assignment]

from .const import (
    CONF_MCS_TOKEN,
    DOMAIN,
    KEY_CENTRAL_PRIMARY,
    KEY_CENTRAL_SECONDARY,
    KEY_MCS,
)
from .coordinator import McsDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


# ---------------------------------------------------------------------------
# Config-push helper
# ---------------------------------------------------------------------------


async def _push_central_config(hass: HomeAssistant, token: str) -> None:
    """Push current central_primary / central_secondary from CC to MCS /config.

    Called on setup (first boot + every HA restart) and whenever
    core_configurator_updated fires for either key.

    If MCS is unreachable: log and continue. No retry (design principle 6).
    """
    try:
        from custom_components.core_configurator.helpers import get_url
        from custom_components.shared_libraries.http import async_request
    except ImportError as err:
        _LOGGER.warning(
            "Registration: cannot push Central config — dependency missing: %s", err
        )
        return

    primary = get_url(hass, KEY_CENTRAL_PRIMARY)
    secondary = get_url(hass, KEY_CENTRAL_SECONDARY)

    response = await async_request(
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


# ---------------------------------------------------------------------------
# HA lifecycle
# ---------------------------------------------------------------------------


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token: str = entry.data[CONF_MCS_TOKEN]

    # Set up the coordinator.
    coordinator = McsDataUpdateCoordinator(hass, token)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # First-boot push: send current CC Central URLs to MCS immediately.
    await _push_central_config(hass, token)

    # Live-change listener: re-push when operator updates CC.
    @callback
    def _on_cc_updated(event: Event) -> None:
        changed_key = event.data.get("key")
        if changed_key not in (KEY_CENTRAL_PRIMARY, KEY_CENTRAL_SECONDARY, None):
            return  # Not a key we care about — skip.
        hass.async_create_task(_push_central_config(hass, token))

    entry.async_on_unload(
        hass.bus.async_listen("core_configurator_updated", _on_cc_updated)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services.
    _register_services(hass, entry, token)

    return True


def _register_services(
    hass: HomeAssistant, entry: ConfigEntry, token: str
) -> None:
    """Register HA services for Registration."""

    async def _handle_sync_now(_service_call) -> None:
        # async_refresh() — not async_request_refresh() — so an explicit operator
        # action bypasses the coordinator's debounce cooldown.
        coordinator: McsDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        await coordinator.async_refresh()

    async def _handle_register_player(service_call) -> None:
        if async_request is None:
            _LOGGER.error("Registration: shared_libraries not available")
            return
        payload = {
            "name": service_call.data.get("name", ""),
            "role": service_call.data.get("role", ""),
            "neocorp": service_call.data.get("neocorp", ""),
            "faction": service_call.data.get("faction", ""),
        }
        response = await async_request(
            hass, KEY_MCS, "POST", "/players", token=token, json=payload
        )
        if response is None or response.status >= 400:
            _LOGGER.warning(
                "Registration: register_player call failed (status=%s)",
                response.status if response else "no response",
            )

    if not hass.services.has_service(DOMAIN, "sync_now"):
        hass.services.async_register(DOMAIN, "sync_now", _handle_sync_now)
    if not hass.services.has_service(DOMAIN, "register_player"):
        hass.services.async_register(
            DOMAIN,
            "register_player",
            _handle_register_player,
            schema=vol.Schema(
                {
                    vol.Required("name"): cv.string,
                    vol.Optional("role", default=""): cv.string,
                    vol.Optional("neocorp", default=""): cv.string,
                    vol.Optional("faction", default=""): cv.string,
                }
            ),
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
