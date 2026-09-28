"""Broadcast Group Controller — placement + membership for fabric devices.

Design contracts:
  - Physical placement = HA Area (device_registry.area_id).
  - Membership = broadcast_group_id in BGC Store (not HA Labels — see README).
  - Publishes mc/{kind}/cmd/device/{id}/membership so devices learn the group.
  - Does not own playlists or media (AlleycatTV content server).
"""
from __future__ import annotations

import json
import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import SOURCE_IMPORT, ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    KIND_DOMAIN,
    SERVICE_CLEAR_BROADCAST_GROUP,
    SERVICE_SET_AREA,
    SERVICE_SET_BROADCAST_GROUP,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUPPORTED_KINDS,
    WS_GET_MEMBERSHIP,
    WS_LIST_AREAS,
    WS_LIST_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

try:
    from custom_components.shared_libraries.fabric import get_presence_tracker
    from custom_components.shared_libraries.mqtt import async_ensure_mqtt, async_publish
except ImportError:  # pragma: no cover
    get_presence_tracker = None  # type: ignore[assignment]
    async_ensure_mqtt = None  # type: ignore[assignment]
    async_publish = None  # type: ignore[assignment]


_KIND_DEVICE = {
    vol.Required("kind"): vol.In(list(SUPPORTED_KINDS)),
    vol.Required("device_id"): cv.string,
}
_SET_AREA_SCHEMA = vol.Schema(
    {**_KIND_DEVICE, vol.Optional("area_id", default=""): cv.string}
)
_SET_BG_SCHEMA = vol.Schema(
    {
        **_KIND_DEVICE,
        vol.Optional("broadcast_group_id", default=""): cv.string,
    }
)
_CLEAR_BG_SCHEMA = vol.Schema(_KIND_DEVICE)


def _store_key(kind: str, device_id: str) -> str:
    return f"{kind}:{device_id}"


def _membership_map(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DOMAIN, {}).setdefault("membership", {})


async def _save(hass: HomeAssistant) -> None:
    store: Store | None = hass.data.get(DOMAIN, {}).get("store")
    if store:
        await store.async_save(_membership_map(hass))


def _get_entry(hass: HomeAssistant, kind: str, device_id: str) -> dict:
    return dict(_membership_map(hass).get(_store_key(kind, device_id), {}))


async def _set_entry(
    hass: HomeAssistant,
    kind: str,
    device_id: str,
    *,
    area_id: str | None = None,
    broadcast_group_id: str | None = None,
) -> dict:
    key = _store_key(kind, device_id)
    current = _get_entry(hass, kind, device_id)
    current["kind"] = kind
    current["device_id"] = device_id
    if area_id is not None:
        current["area_id"] = area_id
    if broadcast_group_id is not None:
        current["broadcast_group_id"] = broadcast_group_id
    _membership_map(hass)[key] = current
    await _save(hass)
    return current


async def _write_area(
    hass: HomeAssistant, kind: str, device_id: str, area_id: str
) -> None:
    domain = KIND_DOMAIN.get(kind)
    if not domain:
        return
    registry = dr.async_get(hass)
    device = registry.async_get_device(identifiers={(domain, device_id)})
    if device:
        registry.async_update_device(device.id, area_id=area_id or None)


async def _publish_membership(
    hass: HomeAssistant, kind: str, device_id: str, broadcast_group_id: str
) -> None:
    if async_publish is None:
        _LOGGER.error("BGC: shared_libraries.mqtt not available")
        return
    payload = json.dumps(
        {"broadcast_group_id": broadcast_group_id or None}
    ).encode("utf-8")
    await async_publish(
        hass,
        kind,
        "cmd",
        "device",
        device_id,
        "membership",
        payload=payload,
        qos=1,
        retain=False,
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    _LOGGER.info("Broadcast Group Controller: async_setup")
    _register_services(hass)
    _register_ws(hass)
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN, context={"source": SOURCE_IMPORT}, data={}
            )
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    membership = await store.async_load() or {}
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["store"] = store
    hass.data[DOMAIN]["membership"] = membership
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    if async_ensure_mqtt is None:
        _LOGGER.error("BGC: shared_libraries not available")
        return False

    _register_services(hass)
    _register_ws(hass)

    try:
        await async_ensure_mqtt(hass)
    except HomeAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop("entry_id", None)
    return True


def _register_services(hass: HomeAssistant) -> None:
    async def handle_set_area(call: ServiceCall) -> None:
        kind = call.data["kind"]
        device_id = call.data["device_id"]
        area_id = (call.data.get("area_id") or "").strip()
        await _set_entry(hass, kind, device_id, area_id=area_id)
        await _write_area(hass, kind, device_id, area_id)

    async def handle_set_bg(call: ServiceCall) -> None:
        kind = call.data["kind"]
        device_id = call.data["device_id"]
        bg = (call.data.get("broadcast_group_id") or "").strip()
        await _set_entry(hass, kind, device_id, broadcast_group_id=bg)
        await _publish_membership(hass, kind, device_id, bg)

    async def handle_clear_bg(call: ServiceCall) -> None:
        kind = call.data["kind"]
        device_id = call.data["device_id"]
        await _set_entry(hass, kind, device_id, broadcast_group_id="")
        await _publish_membership(hass, kind, device_id, "")

    for name, handler, schema in (
        (SERVICE_SET_AREA, handle_set_area, _SET_AREA_SCHEMA),
        (SERVICE_SET_BROADCAST_GROUP, handle_set_bg, _SET_BG_SCHEMA),
        (SERVICE_CLEAR_BROADCAST_GROUP, handle_clear_bg, _CLEAR_BG_SCHEMA),
    ):
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handler, schema=schema)


def _list_fabric_devices(hass: HomeAssistant) -> list[dict]:
    """Merge fabric presence with BGC membership for all supported kinds."""
    out: list[dict] = []
    membership = _membership_map(hass)
    for kind in SUPPORTED_KINDS:
        devices: list[dict] = []
        if get_presence_tracker is not None:
            tracker = get_presence_tracker(hass, kind)
            if tracker is not None:
                devices = tracker.list_devices()
        seen: set[str] = set()
        for d in devices:
            device_id = d.get("device_id") or ""
            if not device_id:
                continue
            seen.add(device_id)
            mem = membership.get(_store_key(kind, device_id), {})
            out.append(
                {
                    "kind": kind,
                    "device_id": device_id,
                    "presence": d.get("presence") or "unknown",
                    "area_id": mem.get("area_id") or "",
                    "broadcast_group_id": mem.get("broadcast_group_id") or "",
                }
            )
        for key, mem in membership.items():
            if not key.startswith(f"{kind}:"):
                continue
            device_id = mem.get("device_id") or key.split(":", 1)[-1]
            if device_id in seen:
                continue
            out.append(
                {
                    "kind": kind,
                    "device_id": device_id,
                    "presence": "unknown",
                    "area_id": mem.get("area_id") or "",
                    "broadcast_group_id": mem.get("broadcast_group_id") or "",
                }
            )
    out.sort(key=lambda x: (x["kind"], x["device_id"]))
    return out


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_DEVICES})
@websocket_api.async_response
async def ws_list_devices(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"devices": _list_fabric_devices(hass)})


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_AREAS})
@websocket_api.async_response
async def ws_list_areas(hass: HomeAssistant, connection, msg) -> None:
    registry = ar.async_get(hass)
    areas = [{"area_id": a.id, "name": a.name} for a in registry.async_list_areas()]
    connection.send_result(msg["id"], {"areas": areas})


@websocket_api.websocket_command({vol.Required("type"): WS_GET_MEMBERSHIP})
@websocket_api.async_response
async def ws_get_membership(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], {"membership": _membership_map(hass)})


@callback
def _register_ws(hass: HomeAssistant) -> None:
    store = hass.data.setdefault(DOMAIN, {})
    if store.get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_list_devices)
    websocket_api.async_register_command(hass, ws_list_areas)
    websocket_api.async_register_command(hass, ws_get_membership)
    store["ws_registered"] = True
