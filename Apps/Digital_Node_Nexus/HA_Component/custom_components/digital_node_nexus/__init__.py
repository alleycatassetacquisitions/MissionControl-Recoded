"""Digital Node Nexus — FDN paging / LED / haptic over the MQTT fabric.

Design contracts:
  - Home Assistant is the only MQTT command publisher (via shared_libraries.mqtt).
  - Fabric owns presence (shared_libraries.fabric); DNN owns page/LED/haptic payloads.
  - Player / role / NeoCorp lists come from MCS read-only — never Central.
  - Panels call HA services/websocket only — no LAN fetch.
"""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, MQTT_KIND, WS_GET_DEVICES, WS_GET_ROSTER
from .mcs import fetch_roster
from .payloads import encode_haptic_cmd, encode_led_cmd, encode_page_cmd
from .routing import resolve_cmd_segments

_LOGGER = logging.getLogger(__name__)

try:
    from custom_components.shared_libraries.fabric import (
        async_start_presence_tracking,
        async_stop_presence_tracking,
        get_presence_tracker,
    )
    from custom_components.shared_libraries.mqtt import async_ensure_mqtt, async_publish
except ImportError:  # pragma: no cover — fail loudly at runtime if deps missing
    async_start_presence_tracking = None  # type: ignore[assignment]
    async_stop_presence_tracking = None  # type: ignore[assignment]
    get_presence_tracker = None  # type: ignore[assignment]
    async_ensure_mqtt = None  # type: ignore[assignment]
    async_publish = None  # type: ignore[assignment]


_PAGE_SCHEMA = vol.Schema(
    {
        vol.Required("message"): cv.string,
        vol.Optional("duration", default=10): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=60)
        ),
        vol.Optional("scroll", default=False): cv.boolean,
        vol.Optional("device_id"): cv.string,
        vol.Optional("target"): vol.In(["all"]),
        vol.Optional("broadcast_group_id"): cv.string,
        vol.Optional("player_id"): cv.string,
        vol.Optional("role"): cv.string,
        vol.Optional("neocorp"): cv.string,
    }
)

_LED_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("target"): vol.In(["all"]),
        vol.Optional("state", default=True): cv.boolean,
        vol.Optional("brightness", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("r", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("g", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("b", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("effect", default="solid"): cv.string,
    }
)

_HAPTIC_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("target"): vol.In(["all"]),
        vol.Optional("pattern", default="short"): cv.string,
        vol.Optional("intensity", default=255): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=255)
        ),
        vol.Optional("duration_ms", default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=5000)
        ),
        vol.Optional("repeat", default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=20)
        ),
    }
)


async def _publish_cmd(
    hass: HomeAssistant,
    segments: list[str],
    action: str,
    payload: bytes,
) -> None:
    if async_publish is None:
        _LOGGER.error("Digital Node Nexus: shared_libraries.mqtt not available")
        return
    await async_publish(
        hass,
        MQTT_KIND,
        *segments,
        action,
        payload=payload,
        qos=1,
        retain=False,
    )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Digital Node Nexus: fabric presence, services, websocket."""
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"entry": entry}

    if async_start_presence_tracking is None or async_ensure_mqtt is None:
        _LOGGER.error(
            "Digital Node Nexus: shared_libraries not available — "
            "add shared_libraries to manifest dependencies"
        )
        return False

    # Wait for HA MQTT (or retry later). Presence subscribe needs the broker client.
    try:
        await async_ensure_mqtt(hass)
    except HomeAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    try:
        await async_start_presence_tracking(
            hass,
            MQTT_KIND,
            config_entry_id=entry.entry_id,
            domain=DOMAIN,
            name_prefix="FDN",
            model="FDN",
        )
    except HomeAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    _register_services(hass)
    _register_ws(hass)
    return True


def _register_services(hass: HomeAssistant) -> None:
    async def handle_page(call: ServiceCall) -> None:
        data = call.data
        device_id = data.get("device_id") or None
        target = data.get("target") or None
        broadcast_group_id = data.get("broadcast_group_id") or None
        player_id = (data.get("player_id") or "").strip()
        role = (data.get("role") or "").strip()
        neocorp = (data.get("neocorp") or "").strip()
        has_stamps = bool(player_id or role or neocorp)

        try:
            segments = resolve_cmd_segments(
                device_id=device_id,
                target=target,
                broadcast_group_id=broadcast_group_id,
                default_all_for_stamps=has_stamps,
            )
        except ValueError as err:
            _LOGGER.warning("Digital Node Nexus page: %s", err)
            return

        payload = encode_page_cmd(
            text=data["message"],
            duration=data.get("duration", 10),
            scroll=bool(data.get("scroll", False)),
            player_id=player_id,
            role=role,
            neocorp=neocorp,
        )
        await _publish_cmd(hass, segments, "page", payload)

    async def handle_set_led(call: ServiceCall) -> None:
        data = call.data
        try:
            segments = resolve_cmd_segments(
                device_id=data.get("device_id") or None,
                target=data.get("target") or None,
            )
        except ValueError as err:
            _LOGGER.warning("Digital Node Nexus set_led: %s", err)
            return
        payload = encode_led_cmd(
            state=bool(data.get("state", True)),
            brightness=data.get("brightness", 255),
            r=data.get("r", 255),
            g=data.get("g", 255),
            b=data.get("b", 255),
            effect=data.get("effect", "solid"),
        )
        await _publish_cmd(hass, segments, "led", payload)

    async def handle_trigger_haptic(call: ServiceCall) -> None:
        data = call.data
        try:
            segments = resolve_cmd_segments(
                device_id=data.get("device_id") or None,
                target=data.get("target") or None,
            )
        except ValueError as err:
            _LOGGER.warning("Digital Node Nexus trigger_haptic: %s", err)
            return
        payload = encode_haptic_cmd(
            pattern=data.get("pattern", "short"),
            intensity=data.get("intensity", 255),
            duration_ms=data.get("duration_ms", 100),
            repeat=data.get("repeat", 1),
        )
        await _publish_cmd(hass, segments, "haptic", payload)

    if not hass.services.has_service(DOMAIN, "page"):
        hass.services.async_register(
            DOMAIN, "page", handle_page, schema=_PAGE_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, "set_led"):
        hass.services.async_register(
            DOMAIN, "set_led", handle_set_led, schema=_LED_SCHEMA
        )
    if not hass.services.has_service(DOMAIN, "trigger_haptic"):
        hass.services.async_register(
            DOMAIN,
            "trigger_haptic",
            handle_trigger_haptic,
            schema=_HAPTIC_SCHEMA,
        )


@websocket_api.websocket_command({vol.Required("type"): WS_GET_DEVICES})
@websocket_api.async_response
async def ws_get_devices(hass: HomeAssistant, connection, msg) -> None:
    """Return fabric-tracked FDN devices for the DNN panel."""
    devices: list[dict] = []
    if get_presence_tracker is not None:
        tracker = get_presence_tracker(hass, MQTT_KIND)
        if tracker is not None:
            devices = tracker.list_devices()
    connection.send_result(msg["id"], {"devices": devices})


@websocket_api.websocket_command({vol.Required("type"): WS_GET_ROSTER})
@websocket_api.async_response
async def ws_get_roster(hass: HomeAssistant, connection, msg) -> None:
    """Return MCS roster (read-only) for page targeting."""
    roster = await fetch_roster(hass)
    connection.send_result(msg["id"], roster)


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_get_roster)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if async_stop_presence_tracking is not None:
        async_stop_presence_tracking(hass, MQTT_KIND)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True
