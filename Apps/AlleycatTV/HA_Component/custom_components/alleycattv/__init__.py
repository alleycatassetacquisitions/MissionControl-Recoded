"""AlleycatTV — TV Pi playback over the MQTT fabric.

Design contracts:
  - Home Assistant is the only MQTT command publisher (shared_libraries.mqtt).
  - Fabric owns presence (shared_libraries.fabric); AlleycatTV owns playback payloads.
  - Content server stays on Proxmox; HA proxies HTTP for Content Manager.
  - Panels call HA services/websocket / proxy only — no LAN fetch.
  - Topics use broadcast (not zone): mc/tv/cmd/… and desired/…/playback.
"""
from __future__ import annotations

import json
import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    MQTT_KIND,
    SERVICE_CACHE_DELETE,
    SERVICE_CACHE_PURGE,
    SERVICE_CACHE_SYNC,
    SERVICE_INTERRUPT_BROADCAST_GROUP,
    SERVICE_INTERRUPT_PI,
    SERVICE_PLAY_BROADCAST_GROUP,
    SERVICE_RELOAD_PLAYLIST,
    SERVICE_SET_PLACEMENT,
    SERVICE_SET_VOLUME_BROADCAST_GROUP,
    SERVICE_STOP_BROADCAST_GROUP,
    SIGNAL_NEW_DEVICE,
    SIGNAL_UPDATE,
    STORAGE_KEY,
    STORAGE_VERSION,
    WS_GET_DEVICES,
    WS_LIST_AREAS,
    WS_SET_PLACEMENT,
)
from .payloads import (
    encode_cache_cmd,
    encode_desired_playback,
    encode_interrupt_cmd,
    encode_play_cmd,
    encode_reload_cmd,
    encode_stop_cmd,
    encode_volume_cmd,
)
from .routing import resolve_cmd_segments

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

# Allow `alleycattv:` in configuration.yaml so HA loads the component (and
# registers proxy/WS) even before the install-only config entry is added.
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

try:
    from custom_components.shared_libraries.fabric import (
        async_start_presence_tracking,
        async_stop_presence_tracking,
        get_presence_tracker,
    )
    from custom_components.shared_libraries.mqtt import (
        async_ensure_mqtt,
        async_publish,
        async_subscribe,
    )
except ImportError:  # pragma: no cover
    async_start_presence_tracking = None  # type: ignore[assignment]
    async_stop_presence_tracking = None  # type: ignore[assignment]
    get_presence_tracker = None  # type: ignore[assignment]
    async_ensure_mqtt = None  # type: ignore[assignment]
    async_publish = None  # type: ignore[assignment]
    async_subscribe = None  # type: ignore[assignment]


_BG_SCHEMA = vol.Schema({vol.Required("broadcast_group_id"): cv.string})
_INTERRUPT_BG_SCHEMA = vol.Schema(
    {
        vol.Required("broadcast_group_id"): cv.string,
        vol.Required("file_url"): cv.string,
    }
)
_INTERRUPT_PI_SCHEMA = vol.Schema(
    {
        vol.Required("pi_id"): cv.string,
        vol.Required("file_url"): cv.string,
    }
)
_VOLUME_SCHEMA = vol.Schema(
    {
        vol.Required("broadcast_group_id"): cv.string,
        vol.Required("volume"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
    }
)
_PLACEMENT_SCHEMA = vol.Schema(
    {
        vol.Required("pi_id"): cv.string,
        vol.Optional("area_id"): cv.string,
    }
)
_CACHE_DELETE_SCHEMA = vol.Schema(
    {
        vol.Required("pi_id"): cv.string,
        vol.Required("subdir"): vol.In(["videos", "photos", "announcements"]),
        vol.Required("filename"): cv.string,
    }
)
_CACHE_PI_SCHEMA = vol.Schema({vol.Required("pi_id"): cv.string})


async def _publish_cmd(
    hass: HomeAssistant,
    segments: list[str],
    action: str,
    payload: bytes,
) -> None:
    if async_publish is None:
        _LOGGER.error("AlleycatTV: shared_libraries.mqtt not available")
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


async def _publish_desired(
    hass: HomeAssistant,
    broadcast_group_id: str,
    payload: bytes,
) -> None:
    if async_publish is None:
        return
    await async_publish(
        hass,
        MQTT_KIND,
        "desired",
        "broadcast",
        broadcast_group_id,
        "playback",
        payload=payload,
        qos=1,
        retain=True,
    )


def _register_panel_apis(hass: HomeAssistant) -> None:
    """Register WS + HTTP views (idempotent). Safe before MQTT is ready."""
    hass.data.setdefault(DOMAIN, {})
    _register_ws(hass)
    if hass.data[DOMAIN].get("http_registered"):
        return
    from .http import register_http_views

    try:
        register_http_views(hass)
        hass.data[DOMAIN]["http_registered"] = True
        _LOGGER.info("AlleycatTV: proxy + websocket APIs registered")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("AlleycatTV HTTP views failed to register: %s", err)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Load from YAML: register proxy/WS and import the install-only config entry."""
    _LOGGER.info("AlleycatTV: async_setup (yaml)")
    _register_services(hass)
    _register_panel_apis(hass)

    # YAML ``alleycattv:`` alone does not create a config entry — import it
    # (same pattern as Core Configurator) so presence/MQTT setup runs.
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
        _LOGGER.info("AlleycatTV: starting config-entry import from YAML")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AlleycatTV: fabric presence, services, proxy, media_player."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    device_meta = await store.async_load() or {}
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry}
    hass.data[DOMAIN].setdefault("devices", {})
    hass.data[DOMAIN]["device_meta"] = device_meta
    hass.data[DOMAIN]["store"] = store
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    if async_start_presence_tracking is None or async_ensure_mqtt is None:
        _LOGGER.error(
            "AlleycatTV: shared_libraries not available — "
            "add shared_libraries to manifest dependencies"
        )
        return False

    # Panel APIs before MQTT so Content Manager / WS work while broker comes up.
    _register_services(hass)
    _register_panel_apis(hass)

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
            name_prefix="TV",
            model="TV Pi",
        )
    except HomeAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if async_subscribe is not None and not hass.data[DOMAIN].get("telemetry_sub"):
        unsub = await async_subscribe(
            hass,
            MQTT_KIND,
            "status",
            "+",
            "json",
            callback=_make_status_json_handler(hass),
            qos=0,
        )
        hass.data[DOMAIN]["telemetry_sub"] = unsub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if get_presence_tracker is not None:
        tracker = get_presence_tracker(hass, MQTT_KIND)
        if tracker is not None:
            for item in tracker.list_devices():
                pi_id = item.get("device_id")
                if pi_id:
                    hass.data[DOMAIN]["devices"].setdefault(
                        pi_id,
                        {
                            "pi_id": pi_id,
                            "online": item.get("presence") == "online",
                        },
                    )
                    async_dispatcher_send(hass, SIGNAL_NEW_DEVICE, pi_id)

    return True


def _make_status_json_handler(hass: HomeAssistant):
    @callback
    def _on_msg(msg) -> None:
        try:
            topic_parts = msg.topic.split("/")
            # mc/tv/status/{pi_id}/json
            if len(topic_parts) < 5:
                return
            pi_id = topic_parts[3]
            raw = msg.payload
            if isinstance(raw, bytes):
                text = raw.decode("utf-8") if raw else ""
            else:
                text = str(raw or "")
            if not text:
                devices = hass.data[DOMAIN]["devices"]
                if pi_id in devices:
                    devices[pi_id]["online"] = False
                    async_dispatcher_send(hass, SIGNAL_UPDATE, pi_id)
                return
            parsed = json.loads(text)
            bg = parsed.get("broadcast_group_id") or parsed.get("zone") or ""
            hass.data[DOMAIN]["devices"][pi_id] = {
                "pi_id": parsed.get("pi_id") or pi_id,
                "broadcast_group_id": bg,
                "state": parsed.get("state") or "",
                "current_file": parsed.get("current_file") or "",
                "next_file": parsed.get("next_file") or "",
                "playlist_index": parsed.get("playlist_index") or 0,
                "ip": parsed.get("ip") or "",
                "uptime": parsed.get("uptime") or 0,
                "online": bool(parsed.get("online", True)),
            }
            async_dispatcher_send(hass, SIGNAL_NEW_DEVICE, pi_id)
            async_dispatcher_send(hass, SIGNAL_UPDATE, pi_id)
            hass.bus.async_fire(
                "alleycattv_device_update",
                dict(hass.data[DOMAIN]["devices"][pi_id]),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("AlleycatTV status json parse failed: %s", err)

    return _on_msg


def _register_services(hass: HomeAssistant) -> None:
    async def handle_play_bg(call: ServiceCall) -> None:
        bg = call.data["broadcast_group_id"]
        segments = resolve_cmd_segments(broadcast_group_id=bg)
        await _publish_cmd(hass, segments, "play", encode_play_cmd())
        await _publish_desired(hass, bg, encode_desired_playback(state="playing"))

    async def handle_stop_bg(call: ServiceCall) -> None:
        bg = call.data["broadcast_group_id"]
        segments = resolve_cmd_segments(broadcast_group_id=bg)
        await _publish_cmd(hass, segments, "stop", encode_stop_cmd())
        await _publish_desired(hass, bg, encode_desired_playback(state="stopped"))

    async def handle_interrupt_bg(call: ServiceCall) -> None:
        bg = call.data["broadcast_group_id"]
        segments = resolve_cmd_segments(broadcast_group_id=bg)
        payload = encode_interrupt_cmd(file_url=call.data["file_url"])
        await _publish_cmd(hass, segments, "interrupt", payload)

    async def handle_interrupt_pi(call: ServiceCall) -> None:
        segments = resolve_cmd_segments(pi_id=call.data["pi_id"])
        payload = encode_interrupt_cmd(file_url=call.data["file_url"])
        await _publish_cmd(hass, segments, "interrupt", payload)

    async def handle_reload(call: ServiceCall) -> None:
        bg = call.data["broadcast_group_id"]
        segments = resolve_cmd_segments(broadcast_group_id=bg)
        await _publish_cmd(hass, segments, "reload", encode_reload_cmd())

    async def handle_volume(call: ServiceCall) -> None:
        bg = call.data["broadcast_group_id"]
        volume = call.data["volume"]
        segments = resolve_cmd_segments(broadcast_group_id=bg)
        await _publish_cmd(hass, segments, "volume", encode_volume_cmd(volume=volume))
        await _publish_desired(
            hass, bg, encode_desired_playback(state="playing", volume=volume)
        )

    async def handle_set_placement(call: ServiceCall) -> None:
        """Forward to Broadcast Group Controller when available; else local area write."""
        pi_id = call.data["pi_id"]
        area_id = call.data.get("area_id") or ""
        if hass.services.has_service("broadcast_group_controller", "set_area"):
            await hass.services.async_call(
                "broadcast_group_controller",
                "set_area",
                {"kind": "tv", "device_id": pi_id, "area_id": area_id},
                blocking=True,
            )
            return
        await _set_placement(hass, pi_id, area_id)

    async def handle_cache_delete(call: ServiceCall) -> None:
        segments = resolve_cmd_segments(pi_id=call.data["pi_id"])
        payload = encode_cache_cmd(
            {"subdir": call.data["subdir"], "filename": call.data["filename"]}
        )
        await _publish_cmd(hass, segments, "cache_delete", payload)

    async def handle_cache_purge(call: ServiceCall) -> None:
        segments = resolve_cmd_segments(pi_id=call.data["pi_id"])
        await _publish_cmd(hass, segments, "cache_purge", encode_cache_cmd())

    async def handle_cache_sync(call: ServiceCall) -> None:
        segments = resolve_cmd_segments(pi_id=call.data["pi_id"])
        await _publish_cmd(hass, segments, "cache_sync", encode_cache_cmd())

    services = [
        (SERVICE_PLAY_BROADCAST_GROUP, handle_play_bg, _BG_SCHEMA),
        (SERVICE_STOP_BROADCAST_GROUP, handle_stop_bg, _BG_SCHEMA),
        (SERVICE_INTERRUPT_BROADCAST_GROUP, handle_interrupt_bg, _INTERRUPT_BG_SCHEMA),
        (SERVICE_INTERRUPT_PI, handle_interrupt_pi, _INTERRUPT_PI_SCHEMA),
        (SERVICE_RELOAD_PLAYLIST, handle_reload, _BG_SCHEMA),
        (SERVICE_SET_VOLUME_BROADCAST_GROUP, handle_volume, _VOLUME_SCHEMA),
        (SERVICE_SET_PLACEMENT, handle_set_placement, _PLACEMENT_SCHEMA),
        (SERVICE_CACHE_DELETE, handle_cache_delete, _CACHE_DELETE_SCHEMA),
        (SERVICE_CACHE_PURGE, handle_cache_purge, _CACHE_PI_SCHEMA),
        (SERVICE_CACHE_SYNC, handle_cache_sync, _CACHE_PI_SCHEMA),
    ]
    for name, handler, schema in services:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


async def _set_placement(
    hass: HomeAssistant, pi_id: str, area_id: str | None
) -> None:
    meta = hass.data[DOMAIN].setdefault("device_meta", {})
    current = dict(meta.get(pi_id, {}))
    if area_id is not None:
        current["area_id"] = area_id
        registry = dr.async_get(hass)
        device = registry.async_get_device(identifiers={(DOMAIN, pi_id)})
        if device:
            registry.async_update_device(device.id, area_id=area_id or None)
    meta[pi_id] = current
    store: Store | None = hass.data[DOMAIN].get("store")
    if store:
        await store.async_save(meta)
    async_dispatcher_send(hass, SIGNAL_UPDATE, pi_id)


@websocket_api.websocket_command({vol.Required("type"): WS_GET_DEVICES})
@websocket_api.async_response
async def ws_get_devices(hass: HomeAssistant, connection, msg) -> None:
    devices: list[dict] = []
    if get_presence_tracker is not None:
        tracker = get_presence_tracker(hass, MQTT_KIND)
        if tracker is not None:
            devices = tracker.list_devices()
    # Merge playback telemetry when present.
    telemetry = hass.data.get(DOMAIN, {}).get("devices", {})
    meta = hass.data.get(DOMAIN, {}).get("device_meta", {})
    bgc_mem = hass.data.get("broadcast_group_controller", {}).get("membership", {})
    out = []
    for d in devices:
        item = dict(d)
        pi_id = item.get("device_id") or ""
        tel = telemetry.get(pi_id, {})
        bgc = bgc_mem.get(f"tv:{pi_id}", {})
        item["broadcast_group_id"] = (
            bgc.get("broadcast_group_id")
            or tel.get("broadcast_group_id")
            or ""
        )
        item["state"] = tel.get("state") or ""
        item["current_file"] = tel.get("current_file") or ""
        item["next_file"] = tel.get("next_file") or ""
        item["area_id"] = bgc.get("area_id") or meta.get(pi_id, {}).get("area_id", "")
        out.append(item)
    connection.send_result(msg["id"], {"devices": out})


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_AREAS})
@websocket_api.async_response
async def ws_list_areas(hass: HomeAssistant, connection, msg) -> None:
    registry = ar.async_get(hass)
    areas = [{"area_id": a.id, "name": a.name} for a in registry.async_list_areas()]
    connection.send_result(msg["id"], {"areas": areas})


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SET_PLACEMENT,
        vol.Required("pi_id"): str,
        vol.Optional("area_id"): str,
    }
)
@websocket_api.async_response
async def ws_set_placement(hass: HomeAssistant, connection, msg) -> None:
    pi_id = msg["pi_id"]
    area_id = msg.get("area_id") or ""
    if hass.services.has_service("broadcast_group_controller", "set_area"):
        await hass.services.async_call(
            "broadcast_group_controller",
            "set_area",
            {"kind": "tv", "device_id": pi_id, "area_id": area_id},
            blocking=True,
        )
    else:
        await _set_placement(hass, pi_id, area_id)
    connection.send_result(msg["id"], {"ok": True})


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_devices)
    websocket_api.async_register_command(hass, ws_list_areas)
    websocket_api.async_register_command(hass, ws_set_placement)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if async_stop_presence_tracking is not None:
        async_stop_presence_tracking(hass, MQTT_KIND)
    unsub = hass.data.get(DOMAIN, {}).pop("telemetry_sub", None)
    if unsub:
        unsub()
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
