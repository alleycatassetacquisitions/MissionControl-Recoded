"""MQTT fabric helpers — build topics via mc_topic, subscribe/publish through HA's mqtt component.

Never open a second broker client; never hard-code topic strings; use ``broadcast`` not ``zone``.

Command address grammar (all kinds):
  ``mc/{kind}/cmd/device/{id}/{action}``
  ``mc/{kind}/cmd/all/{action}``
  ``mc/{kind}/cmd/broadcast/{bg_id}/{action}``
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import MC_TOPIC_ROOT

_LOGGER = logging.getLogger(__name__)


async def async_ensure_mqtt(hass: HomeAssistant) -> None:
    """Wait for HA's MQTT client; raise if the MQTT integration is not set up.

    Call before the first subscribe/publish in an integration setup path.
    Returns normally when the client exists (connected or not).
    """
    available = await mqtt.async_wait_for_mqtt_client(hass)
    if not available:
        raise HomeAssistantError(
            "MQTT is not set up. Install the official Mosquitto broker add-on "
            "(Settings → Add-ons), then add the MQTT integration "
            "(Settings → Devices & services → MQTT → Use the official Mosquitto "
            "Mqtt Broker app). Reload Data Node Nexus or restart Home Assistant."
        )


def mc_topic(kind: str, *segments: str) -> str:
    """Build ``mc/{kind}/…`` from path segments."""
    parts = [MC_TOPIC_ROOT, kind, *segments]
    return "/".join(parts)


def resolve_cmd_segments(
    *,
    device_id: str | None = None,
    pi_id: str | None = None,
    target: str | None = None,
    broadcast_group_id: str | None = None,
    default_all_for_stamps: bool = False,
) -> list[str]:
    """Build ``cmd/…`` segments under ``mc/{kind}/`` (shared by TV, DNN, BGC).

    Priority: device (``device_id`` or AlleycatTV ``pi_id``) → broadcast_group_id →
    target=all → optional all when only filter stamps are present.
    """
    device = (device_id or pi_id or "").strip() or None
    if device:
        return ["cmd", "device", device]
    if broadcast_group_id:
        return ["cmd", "broadcast", str(broadcast_group_id).strip()]
    if target == "all":
        return ["cmd", "all"]
    if default_all_for_stamps:
        return ["cmd", "all"]
    raise ValueError(
        "command requires device_id (or pi_id), target=all, or broadcast_group_id"
    )


async def async_subscribe(
    hass: HomeAssistant,
    kind: str,
    *segments: str,
    callback: Callable[[Any], None],
    qos: int = 0,
) -> Callable[[], None]:
    """Subscribe to a Mission Control topic via HA's mqtt integration."""
    topic = mc_topic(kind, *segments)
    _LOGGER.debug("shared_libraries.mqtt: subscribing to %s", topic)
    return await mqtt.async_subscribe(hass, topic, callback, qos=qos)


async def async_publish(
    hass: HomeAssistant,
    kind: str,
    *segments: str,
    payload: str | bytes,
    qos: int = 0,
    retain: bool = False,
) -> None:
    """Publish a message to a Mission Control topic via HA's mqtt integration."""
    topic = mc_topic(kind, *segments)
    _LOGGER.debug("shared_libraries.mqtt: publishing to %s", topic)
    await mqtt.async_publish(hass, topic, payload, qos=qos, retain=retain)


async def async_subscribe_presence(
    hass: HomeAssistant,
    kind: str,
    device_id: str,
    callback: Callable[[Any], None],
    qos: int = 0,
) -> Callable[[], None]:
    """Subscribe to ``mc/{kind}/status/{device_id}``."""
    return await async_subscribe(
        hass,
        kind,
        "status",
        device_id,
        callback=callback,
        qos=qos,
    )
