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
    SERVICE_REMOVE_DEVICE,
    SERVICE_SET_AREA,
    SERVICE_SET_BROADCAST_GROUP,
    STORAGE_KEY,
    STORAGE_VERSION,
    SUPPORTED_KINDS,
    WS_GET_MEMBERSHIP,
    WS_LIST_AREAS,
    WS_LIST_BROADCAST_GROUPS,
    WS_LIST_DEVICES,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

try:
    from custom_components.shared_libraries.fabric import (
        PRESENCE_ONLINE,
        device_id_from_status_topic,
        get_presence_tracker,
        parse_presence_payload,
    )
    from custom_components.shared_libraries.mqtt import (
        async_ensure_mqtt,
        async_publish,
        async_subscribe,
    )
except ImportError:  # pragma: no cover
    PRESENCE_ONLINE = "online"  # type: ignore[assignment]
    device_id_from_status_topic = None  # type: ignore[assignment]
    get_presence_tracker = None  # type: ignore[assignment]
    parse_presence_payload = None  # type: ignore[assignment]
    async_ensure_mqtt = None  # type: ignore[assignment]
    async_publish = None  # type: ignore[assignment]
    async_subscribe = None  # type: ignore[assignment]


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
_REMOVE_DEVICE_SCHEMA = vol.Schema(_KIND_DEVICE)


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
    """Publish membership with retain so rebooting devices re-learn the group.

    Clear (empty broadcast_group_id) still publishes a retained JSON payload
    with ``broadcast_group_id: null`` so the broker topic is overwritten and
    late subscribers do not keep a stale group.
    """
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
        retain=True,
    )


async def _clear_retained_membership(
    hass: HomeAssistant, kind: str, device_id: str
) -> None:
    """Wipe the retained membership topic entirely (empty payload)."""
    if async_publish is None:
        _LOGGER.error("BGC: shared_libraries.mqtt not available")
        return
    await async_publish(
        hass,
        kind,
        "cmd",
        "device",
        device_id,
        "membership",
        payload=b"",
        qos=1,
        retain=True,
    )


def _presence_for(hass: HomeAssistant, kind: str, device_id: str) -> str:
    """Return current fabric presence, or unknown if not tracked."""
    if get_presence_tracker is None:
        return "unknown"
    tracker = get_presence_tracker(hass, kind)
    if tracker is None:
        return "unknown"
    tracked = tracker.devices.get(device_id)
    if tracked is None:
        return "unknown"
    return tracked.presence


async def _cleanup_owner_integration(
    hass: HomeAssistant, kind: str, device_id: str
) -> None:
    """Drop owner-integration caches so a reused id can spawn fresh entities."""
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    domain = KIND_DOMAIN.get(kind)
    if not domain:
        return
    data = hass.data.get(domain) or {}
    devices = data.get("devices")
    if isinstance(devices, dict):
        devices.pop(device_id, None)
    meta = data.get("device_meta")
    if isinstance(meta, dict):
        meta.pop(device_id, None)
        store = data.get("store")
        if store is not None:
            await store.async_save(meta)
    # AlleycatTV media_player keeps a closed-over known set; signal lets it reset.
    async_dispatcher_send(hass, f"{domain}_device_removed", device_id)


async def async_remove_fabric_device(
    hass: HomeAssistant, kind: str, device_id: str
) -> None:
    """Remove an inactive fabric device from BGC + fabric + owner integration."""
    device_id = (device_id or "").strip()
    if not device_id:
        raise HomeAssistantError("device_id is required")
    if kind not in SUPPORTED_KINDS:
        raise HomeAssistantError(f"Unsupported kind: {kind}")

    presence = _presence_for(hass, kind, device_id)
    if presence == PRESENCE_ONLINE:
        raise HomeAssistantError(
            f"Cannot remove {kind}/{device_id} while it is online. "
            "Power it off or wait until it stops publishing, then try again."
        )

    key = _store_key(kind, device_id)
    _membership_map(hass).pop(key, None)
    await _save(hass)

    last_presence = hass.data.get(DOMAIN, {}).get("last_presence")
    if isinstance(last_presence, dict):
        last_presence.pop((kind, device_id), None)

    await _clear_retained_membership(hass, kind, device_id)

    if get_presence_tracker is not None:
        tracker = get_presence_tracker(hass, kind)
        if tracker is not None:
            await tracker.async_forget_device(device_id)
        else:
            # Still clear retained status if fabric tracker is not running.
            if async_publish is not None:
                await async_publish(
                    hass,
                    kind,
                    "status",
                    device_id,
                    payload=b"",
                    qos=1,
                    retain=True,
                )
            registry = dr.async_get(hass)
            domain = KIND_DOMAIN.get(kind)
            if domain:
                device = registry.async_get_device(
                    identifiers={(domain, device_id)}
                )
                if device is not None:
                    registry.async_remove_device(device.id)

    await _cleanup_owner_integration(hass, kind, device_id)
    _LOGGER.info("BGC: removed fabric device %s/%s", kind, device_id)


async def _republish_stored_membership(
    hass: HomeAssistant, kind: str, device_id: str
) -> None:
    """Re-publish Store membership when a device comes online."""
    mem = _get_entry(hass, kind, device_id)
    bg = (mem.get("broadcast_group_id") or "").strip()
    if not bg:
        return
    _LOGGER.info(
        "BGC: device %s/%s online — republishing membership %s",
        kind,
        device_id,
        bg,
    )
    await _publish_membership(hass, kind, device_id, bg)


async def _start_presence_republish(hass: HomeAssistant) -> None:
    """Watch fabric status topics and republish membership on online transitions."""
    if async_subscribe is None or parse_presence_payload is None:
        _LOGGER.warning("BGC: cannot start presence republish (shared_libraries missing)")
        return

    store = hass.data.setdefault(DOMAIN, {})
    if store.get("presence_unsubs"):
        return

    last_presence: dict[tuple[str, str], str] = store.setdefault(
        "last_presence", {}
    )
    unsubs: list = []

    for kind in SUPPORTED_KINDS:

        @callback
        def _on_status(msg, *, _kind: str = kind) -> None:
            if device_id_from_status_topic is None:
                return
            topic = getattr(msg, "topic", "") or ""
            device_id = device_id_from_status_topic(_kind, topic)
            if not device_id:
                return
            presence = parse_presence_payload(getattr(msg, "payload", None))
            key = (_kind, device_id)
            previous = last_presence.get(key)
            last_presence[key] = presence
            if presence != PRESENCE_ONLINE or previous == PRESENCE_ONLINE:
                return
            hass.async_create_task(
                _republish_stored_membership(hass, _kind, device_id)
            )

        unsub = await async_subscribe(
            hass,
            kind,
            "status",
            "#",
            callback=_on_status,
            qos=1,
        )
        unsubs.append(unsub)

    store["presence_unsubs"] = unsubs
    _LOGGER.info("BGC: presence republish watchers started for %s", SUPPORTED_KINDS)


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

    await _start_presence_republish(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = hass.data.get(DOMAIN, {})
    for unsub in data.pop("presence_unsubs", []) or []:
        try:
            unsub()
        except Exception:  # noqa: BLE001
            pass
    data.pop("last_presence", None)
    data.pop("entry_id", None)
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

    async def handle_remove_device(call: ServiceCall) -> None:
        await async_remove_fabric_device(
            hass, call.data["kind"], call.data["device_id"]
        )

    for name, handler, schema in (
        (SERVICE_SET_AREA, handle_set_area, _SET_AREA_SCHEMA),
        (SERVICE_SET_BROADCAST_GROUP, handle_set_bg, _SET_BG_SCHEMA),
        (SERVICE_CLEAR_BROADCAST_GROUP, handle_clear_bg, _CLEAR_BG_SCHEMA),
        (SERVICE_REMOVE_DEVICE, handle_remove_device, _REMOVE_DEVICE_SCHEMA),
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


async def _list_broadcast_groups(hass: HomeAssistant) -> list[dict]:
    """Available Broadcast Group ids: AlleycatTV content buckets + assigned ids.

    Playlist buckets live on the content server. Membership-only ids (assigned
    before a bucket existed, or DNN-only) are merged so the dropdown stays
    complete for the operator.
    """
    by_id: dict[str, dict] = {}

    try:
        from custom_components.shared_libraries.http import async_request
    except ImportError:  # pragma: no cover
        async_request = None  # type: ignore[assignment]

    if async_request is not None:
        try:
            resp = await async_request(
                hass, "alleycattv", "GET", "/api/broadcast_groups/"
            )
            if resp is not None and resp.status < 400:
                rows = await resp.json()
                if isinstance(rows, list):
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        gid = (
                            row.get("broadcast_group_id")
                            or row.get("zone_id")
                            or ""
                        ).strip()
                        if not gid:
                            continue
                        by_id[gid] = {
                            "broadcast_group_id": gid,
                            "name": (row.get("name") or gid).strip() or gid,
                            "source": "content",
                        }
            elif resp is not None:
                _LOGGER.debug(
                    "BGC: content broadcast_groups HTTP %s", resp.status
                )
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("BGC: could not list content broadcast groups: %s", err)

    for mem in _membership_map(hass).values():
        gid = (mem.get("broadcast_group_id") or "").strip()
        if not gid:
            continue
        if gid not in by_id:
            by_id[gid] = {
                "broadcast_group_id": gid,
                "name": gid,
                "source": "membership",
            }

    return sorted(by_id.values(), key=lambda g: g["broadcast_group_id"].lower())


@websocket_api.websocket_command({vol.Required("type"): WS_LIST_BROADCAST_GROUPS})
@websocket_api.async_response
async def ws_list_broadcast_groups(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(
        msg["id"], {"broadcast_groups": await _list_broadcast_groups(hass)}
    )


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
    websocket_api.async_register_command(hass, ws_list_broadcast_groups)
    websocket_api.async_register_command(hass, ws_get_membership)
    store["ws_registered"] = True
