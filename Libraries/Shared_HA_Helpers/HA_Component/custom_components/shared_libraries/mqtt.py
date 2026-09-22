"""MQTT fabric helpers for Mission Control integrations.

All integrations use these wrappers instead of calling HA's mqtt component
directly, to ensure consistent topic naming and to prevent private broker
clients from being opened.

Topic schema
------------
All Mission Control topics are rooted at ``mc/``:

    mc/{kind}/cmd/{device_id}/#          — per-device commands
    mc/{kind}/cmd/all/#                  — broadcast to every device of a kind
    mc/{kind}/cmd/broadcast/{group_id}/# — Broadcast Group commands
    mc/{kind}/status/{device_id}         — LWT / presence
    mc/{kind}/desired/…                  — desired state (e.g. playback)

Usage
-----
    from custom_components.shared_libraries.mqtt import (
        mc_topic,
        async_subscribe,
        async_publish,
        async_subscribe_presence,
    )

    # Pure topic builder — no hass needed
    topic = mc_topic("dnn", "cmd", device_id)
    # → "mc/dnn/cmd/<device_id>"

    # Subscribe (returns an unsubscribe callable)
    unsub = await async_subscribe(hass, "dnn", "cmd", device_id, callback=handle_msg)

    # Publish
    await async_publish(hass, "tv", "cmd", "all", payload=json.dumps(cmd))

    # Presence
    unsub = await async_subscribe_presence(hass, "dnn", device_id, callback=on_presence)

Design contracts
----------------
- Home Assistant is the only MQTT command publisher.  Never open a second
  broker client inside an integration.
- All topics are built through mc_topic().  Do not hard-code topic strings
  in individual integrations.
- Use the ``broadcast`` segment for group commands.  Never use ``zone``.
- Status and LWT topics follow the pattern mc/{kind}/status/{device_id}.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant

from .const import MC_TOPIC_ROOT

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topic builder
# ---------------------------------------------------------------------------


def mc_topic(kind: str, *segments: str) -> str:
    """Build a Mission Control MQTT topic.

    Parameters
    ----------
    kind:
        Topic namespace, e.g. ``"dnn"`` or ``"tv"``.
    *segments:
        Additional path segments.

    Returns
    -------
    str
        Full topic string, e.g. ``"mc/dnn/cmd/abc123"``.

    Examples
    --------
    >>> mc_topic("dnn", "cmd", "abc123")
    'mc/dnn/cmd/abc123'
    >>> mc_topic("tv", "cmd", "all")
    'mc/tv/cmd/all'
    >>> mc_topic("dnn", "cmd", "broadcast", "group-1")
    'mc/dnn/cmd/broadcast/group-1'
    >>> mc_topic("dnn", "status", "abc123")
    'mc/dnn/status/abc123'
    """
    parts = [MC_TOPIC_ROOT, kind, *segments]
    return "/".join(parts)


# ---------------------------------------------------------------------------
# Subscribe / publish
# ---------------------------------------------------------------------------


async def async_subscribe(
    hass: HomeAssistant,
    kind: str,
    *segments: str,
    callback: Callable[[Any], None],
    qos: int = 0,
) -> Callable[[], None]:
    """Subscribe to a Mission Control topic via HA's mqtt integration.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    kind:
        Topic namespace, e.g. ``"dnn"`` or ``"tv"``.
    *segments:
        Additional topic segments (see ``mc_topic``).
    callback:
        Callable invoked with each received ``mqtt.ReceiveMessage``.
    qos:
        MQTT QoS level (0, 1, or 2).  Defaults to 0.

    Returns
    -------
    Callable
        An unsubscribe function.  Call it to stop receiving messages.
    """
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
    """Publish a message to a Mission Control topic via HA's mqtt integration.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    kind:
        Topic namespace, e.g. ``"dnn"`` or ``"tv"``.
    *segments:
        Additional topic segments (see ``mc_topic``).
    payload:
        Message payload (string or bytes).
    qos:
        MQTT QoS level (0, 1, or 2).  Defaults to 0.
    retain:
        Whether the broker should retain the message.  Defaults to False.
    """
    topic = mc_topic(kind, *segments)
    _LOGGER.debug("shared_libraries.mqtt: publishing to %s", topic)
    await mqtt.async_publish(hass, topic, payload, qos=qos, retain=retain)


# ---------------------------------------------------------------------------
# Presence helper
# ---------------------------------------------------------------------------


async def async_subscribe_presence(
    hass: HomeAssistant,
    kind: str,
    device_id: str,
    callback: Callable[[Any], None],
    qos: int = 0,
) -> Callable[[], None]:
    """Subscribe to the LWT / status topic for a single device.

    The presence topic pattern is ``mc/{kind}/status/{device_id}``.
    The callback receives the raw ``mqtt.ReceiveMessage``; payloads are
    typically ``"online"`` or ``"offline"``.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    kind:
        Topic namespace, e.g. ``"dnn"`` or ``"tv"``.
    device_id:
        The unique identifier for the device.
    callback:
        Callable invoked on each status message.
    qos:
        MQTT QoS level.  Defaults to 0.

    Returns
    -------
    Callable
        An unsubscribe function.
    """
    return await async_subscribe(
        hass,
        kind,
        "status",
        device_id,
        callback=callback,
        qos=qos,
    )
