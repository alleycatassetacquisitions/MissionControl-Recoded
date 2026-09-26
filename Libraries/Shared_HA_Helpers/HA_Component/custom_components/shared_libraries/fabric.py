"""MQTT fabric presence — status/LWT → HA devices and presence entities.

Reusable by Digital Node Nexus (``dnn``) and later AlleycatTV (``tv``).

Design contracts
----------------
- Status and LWT create a Home Assistant device and a presence entity
  (``online`` / ``offline`` / ``unknown``).
- Integrations do not open a private MQTT client; this module uses
  ``shared_libraries.mqtt.async_subscribe``.
- Calling integrations own the config entry id passed into
  ``async_start_presence_tracking`` so devices appear under that entry.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .mqtt import async_subscribe, mc_topic

_LOGGER = logging.getLogger(__name__)

PRESENCE_ONLINE = "online"
PRESENCE_OFFLINE = "offline"
PRESENCE_UNKNOWN = "unknown"

_VALID_PRESENCE = frozenset({PRESENCE_ONLINE, PRESENCE_OFFLINE, PRESENCE_UNKNOWN})

# hass.data[DOMAIN]["presence"][kind] → PresenceTracker
DATA_PRESENCE = "presence"


def _slug_device_id(device_id: str) -> str:
    """Make a device_id safe for entity_id segments."""
    slug = re.sub(r"[^a-zA-Z0-9_]", "_", device_id).lower()
    return slug or "unknown"


def presence_entity_id(domain: str, device_id: str) -> str:
    """Return the sensor entity_id for a fabric presence entity."""
    return f"sensor.{domain}_{_slug_device_id(device_id)}_presence"


def parse_presence_payload(payload: bytes | str | None) -> str:
    """Map an MQTT status/LWT payload to online | offline | unknown.

    Accepted forms:
    - Plain text ``online`` / ``offline`` / ``unknown`` (case-insensitive)
    - Empty or missing payload → ``offline`` (typical LWT)
    - JSON object with boolean ``online`` or string ``state`` / ``status``
    """
    if payload is None:
        return PRESENCE_OFFLINE

    if isinstance(payload, bytes):
        if not payload:
            return PRESENCE_OFFLINE
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return PRESENCE_UNKNOWN
    else:
        text = str(payload)

    text = text.strip()
    if not text:
        return PRESENCE_OFFLINE

    lower = text.lower()
    if lower in _VALID_PRESENCE:
        return lower

    if text[0] == "{":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return PRESENCE_UNKNOWN
        if isinstance(data, dict):
            if "online" in data:
                return PRESENCE_ONLINE if data["online"] else PRESENCE_OFFLINE
            for key in ("state", "status", "presence"):
                value = data.get(key)
                if isinstance(value, str) and value.lower() in _VALID_PRESENCE:
                    return value.lower()
                if isinstance(value, bool):
                    return PRESENCE_ONLINE if value else PRESENCE_OFFLINE

    return PRESENCE_UNKNOWN


def device_id_from_status_topic(kind: str, topic: str) -> str | None:
    """Extract device_id from ``mc/{kind}/status/{device_id}``."""
    prefix = mc_topic(kind, "status") + "/"
    if not topic.startswith(prefix):
        return None
    device_id = topic[len(prefix) :]
    if not device_id or "/" in device_id:
        return None
    return device_id


@dataclass
class PresenceDevice:
    """Tracked fabric endpoint."""

    device_id: str
    presence: str = PRESENCE_UNKNOWN
    attributes: dict[str, Any] = field(default_factory=dict)


class PresenceTracker:
    """Subscribes to ``mc/{kind}/status/#`` and mirrors presence into HA."""

    def __init__(
        self,
        hass: HomeAssistant,
        kind: str,
        *,
        config_entry_id: str,
        domain: str,
        manufacturer: str = "Alleycat",
        model: str | None = None,
        name_prefix: str | None = None,
    ) -> None:
        self.hass = hass
        self.kind = kind
        self.config_entry_id = config_entry_id
        self.domain = domain
        self.manufacturer = manufacturer
        self.model = model or kind.upper()
        self.name_prefix = name_prefix or kind.upper()
        self._devices: dict[str, PresenceDevice] = {}
        self._unsub: Callable[[], None] | None = None

    @property
    def devices(self) -> dict[str, PresenceDevice]:
        return dict(self._devices)

    def list_devices(self) -> list[dict[str, Any]]:
        """Serialisable device list for websocket / panels."""
        return [
            {
                "device_id": device.device_id,
                "presence": device.presence,
                "entity_id": presence_entity_id(self.domain, device.device_id),
                **device.attributes,
            }
            for device in sorted(
                self._devices.values(), key=lambda item: item.device_id
            )
        ]

    async def async_start(self) -> None:
        """Subscribe to the status wildcard for this kind."""
        if self._unsub is not None:
            return

        from .mqtt import async_ensure_mqtt

        await async_ensure_mqtt(self.hass)

        @callback
        def _on_message(msg: Any) -> None:
            self._handle_message(msg)

        self._unsub = await async_subscribe(
            self.hass,
            self.kind,
            "status",
            "#",
            callback=_on_message,
            qos=1,
        )
        _LOGGER.debug(
            "fabric presence: tracking mc/%s/status/# for domain %s",
            self.kind,
            self.domain,
        )

    def async_stop(self) -> None:
        """Unsubscribe from status topics."""
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    @callback
    def _handle_message(self, msg: Any) -> None:
        topic = getattr(msg, "topic", "") or ""
        payload = getattr(msg, "payload", None)
        device_id = device_id_from_status_topic(self.kind, topic)
        if device_id is None:
            _LOGGER.debug("fabric presence: ignoring topic %s", topic)
            return

        presence = parse_presence_payload(payload)
        attributes: dict[str, Any] = {"kind": self.kind, "device_id": device_id}

        if isinstance(payload, bytes):
            try:
                text = payload.decode("utf-8").strip()
            except UnicodeDecodeError:
                text = ""
        else:
            text = str(payload).strip() if payload is not None else ""

        if text.startswith("{"):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = None
            if isinstance(data, dict):
                for key in ("firmware", "ip", "rssi", "uptime", "free_heap"):
                    if key in data:
                        attributes[key] = data[key]

        self._apply_presence(device_id, presence, attributes)

    @callback
    def _apply_presence(
        self,
        device_id: str,
        presence: str,
        attributes: dict[str, Any],
    ) -> None:
        tracked = self._devices.get(device_id)
        if tracked is None:
            tracked = PresenceDevice(device_id=device_id)
            self._devices[device_id] = tracked

        tracked.presence = presence
        tracked.attributes = attributes

        registry = dr.async_get(self.hass)
        registry.async_get_or_create(
            config_entry_id=self.config_entry_id,
            identifiers={(self.domain, device_id)},
            manufacturer=self.manufacturer,
            model=self.model,
            name=f"{self.name_prefix} {device_id}",
        )

        entity_id = presence_entity_id(self.domain, device_id)
        self.hass.states.async_set(
            entity_id,
            presence,
            {
                "friendly_name": f"{self.name_prefix} {device_id} presence",
                "device_class": "enum",
                "options": [PRESENCE_ONLINE, PRESENCE_OFFLINE, PRESENCE_UNKNOWN],
                **attributes,
            },
        )


async def async_start_presence_tracking(
    hass: HomeAssistant,
    kind: str,
    *,
    config_entry_id: str,
    domain: str,
    manufacturer: str = "Alleycat",
    model: str | None = None,
    name_prefix: str | None = None,
) -> PresenceTracker:
    """Start (or return existing) presence tracking for ``mc/{kind}/status/#``."""
    from .const import DOMAIN

    store = hass.data.setdefault(DOMAIN, {})
    by_kind: dict[str, PresenceTracker] = store.setdefault(DATA_PRESENCE, {})

    existing = by_kind.get(kind)
    if existing is not None:
        return existing

    tracker = PresenceTracker(
        hass,
        kind,
        config_entry_id=config_entry_id,
        domain=domain,
        manufacturer=manufacturer,
        model=model,
        name_prefix=name_prefix,
    )
    await tracker.async_start()
    by_kind[kind] = tracker
    return tracker


def async_stop_presence_tracking(hass: HomeAssistant, kind: str) -> None:
    """Stop presence tracking for a kind if it was started."""
    from .const import DOMAIN

    store = hass.data.get(DOMAIN) or {}
    by_kind: dict[str, PresenceTracker] = store.get(DATA_PRESENCE) or {}
    tracker = by_kind.pop(kind, None)
    if tracker is not None:
        tracker.async_stop()


def get_presence_tracker(hass: HomeAssistant, kind: str) -> PresenceTracker | None:
    """Return the active PresenceTracker for ``kind``, if any."""
    from .const import DOMAIN

    store = hass.data.get(DOMAIN) or {}
    by_kind: dict[str, PresenceTracker] = store.get(DATA_PRESENCE) or {}
    return by_kind.get(kind)
