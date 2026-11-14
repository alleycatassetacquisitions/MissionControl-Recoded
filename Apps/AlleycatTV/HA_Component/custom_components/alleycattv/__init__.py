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
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.dispatcher import async_dispatcher_send
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
    SERVICE_SET_VOLUME_BROADCAST_GROUP,
    KEY_ALLEYCATTV,
    SERVICE_STOP_BROADCAST_GROUP,
    SIGNAL_NEW_DEVICE,
    SIGNAL_UPDATE,
    WS_GET_DEVICES,
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
_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]

# Allow `alleycattv:` in configuration.yaml so HA loads the component (and
# registers proxy/WS) even before the install-only config entry is added.
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

from custom_components.core_configurator.helpers import get_url
from custom_components.shared_libraries.fabric import (
    async_start_presence_tracking,
    async_stop_presence_tracking,
    get_presence_tracker,
)
from custom_components.shared_libraries.mqtt import (
    async_ensure_mqtt,
    async_publish,
    async_subscribe,
    resolve_cmd_segments,
)


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
    *,
    retain: bool = False,
) -> None:
    await async_publish(
        hass,
        MQTT_KIND,
        *segments,
        action,
        payload=payload,
        qos=1,
        retain=retain,
    )


def _mqtt_broker_hint(hass: HomeAssistant) -> tuple[str, str]:
    try:
        for entry in hass.config_entries.async_entries("mqtt"):
            data = entry.data or {}
            host = str(data.get("broker") or data.get("host") or "").strip()
            if host:
                return host, str(data.get("port") or "1883")
    except Exception:  # noqa: BLE001
        pass
    return "", ""


async def _publish_pi_config(hass: HomeAssistant) -> None:
    """Publish retained year-1 Pi config (server URL + MQTT broker hint)."""
    server_url = (get_url(hass, KEY_ALLEYCATTV) or "").rstrip("/")
    mqtt_host, mqtt_port = _mqtt_broker_hint(hass)
    if not server_url and not mqtt_host:
        return
    body = {
        "server_url": server_url,
        "mqtt_host": mqtt_host,
        "mqtt_port": mqtt_port,
    }
    payload = json.dumps(body).encode("utf-8")
    await _publish_cmd(hass, ["cmd", "all"], "config", payload, retain=True)
    _LOGGER.info(
        "AlleycatTV: retained Pi config published — server=%r mqtt=%r:%s",
        server_url,
        mqtt_host,
        mqtt_port,
    )


async def _publish_desired(
    hass: HomeAssistant,
    broadcast_group_id: str,
    payload: bytes,
) -> None:
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
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"entry": entry}
    hass.data[DOMAIN].setdefault("devices", {})
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

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

    # Year-1: retained MQTT config for Pis (MCS owns LXC fan-out; HA publishes MQTT).
    await _publish_pi_config(hass)

    @callback
    def _on_cc_updated(event) -> None:
        key = event.data.get("key")
        if key in ("alleycattv", "master_control_server", None):
            hass.async_create_task(_publish_pi_config(hass))

    entry.async_on_unload(
        hass.bus.async_listen("core_configurator_updated", _on_cc_updated)
    )

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
        (SERVICE_CACHE_DELETE, handle_cache_delete, _CACHE_DELETE_SCHEMA),
        (SERVICE_CACHE_PURGE, handle_cache_purge, _CACHE_PI_SCHEMA),
        (SERVICE_CACHE_SYNC, handle_cache_sync, _CACHE_PI_SCHEMA),
    ]
    for name, handler, schema in services:
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


@websocket_api.websocket_command({vol.Required("type"): WS_GET_DEVICES})
@websocket_api.async_response
async def ws_get_devices(hass: HomeAssistant, connection, msg) -> None:
    devices: list[dict] = []
    tracker = get_presence_tracker(hass, MQTT_KIND)
    if tracker is not None:
        devices = tracker.list_devices()
    telemetry = hass.data.get(DOMAIN, {}).get("devices", {})
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
        item["area_id"] = bgc.get("area_id") or ""
        out.append(item)
    connection.send_result(msg["id"], {"devices": out})



@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_devices)
    store["ws_registered"] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    async_stop_presence_tracking(hass, MQTT_KIND)
    unsub = hass.data.get(DOMAIN, {}).pop("telemetry_sub", None)
    if unsub:
        unsub()
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
