"""MQTT subscriber for AlleycatTV Pi — mc/tv fabric, JSON payloads.

Subscribes:
  mc/tv/cmd/device/{PI_ID}/#
  mc/tv/cmd/all/#
  mc/tv/cmd/broadcast/{id}/#   (when a Broadcast Group is assigned)
  mc/tv/desired/broadcast/{id}/playback  (retained desired state)

Membership assign (Phase 7):
  mc/tv/cmd/device/{PI_ID}/membership
  {"broadcast_group_id": "lobby" | null}

Publishes:
  mc/tv/status/{PI_ID}          plain online/offline (fabric presence + LWT)
  mc/tv/status/{PI_ID}/json     playback telemetry

Cache commands (JSON): cache_delete / cache_purge / cache_sync
"""
from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any, Optional

import paho.mqtt.client as mqtt

from config import (
    CACHE_ENABLED,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    PI_ID,
    TOPIC_CMD_ALL,
    TOPIC_CMD_DEVICE,
    TOPIC_PREFIX,
    TOPIC_STATUS,
    TOPIC_STATUS_JSON,
    get_broadcast_group_id,
    set_broadcast_group_id,
)

_LOGGER = logging.getLogger(__name__)

_CACHE_ACTIONS = {"cache_delete", "cache_purge", "cache_sync"}
_PLAYBACK_ACTIONS = {"play", "stop", "interrupt", "reload", "volume"}


class MQTTHandler:
    """Subscribes to fabric command topics and queues decoded JSON commands."""

    def __init__(self) -> None:
        self.cmd_queue: queue.Queue[Any] = queue.Queue()
        self._client = mqtt.Client(client_id=f"alleycattv-pi-{PI_ID}")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._connected = threading.Event()
        # Mutable membership — env is bootstrap only until BGC assigns.
        self._broadcast_group_id: str = get_broadcast_group_id()
        self._topic_cmd_broadcast: Optional[str] = None
        self._topic_desired: Optional[str] = None
        self._apply_group_topics(self._broadcast_group_id)

    @property
    def broadcast_group_id(self) -> str:
        return self._broadcast_group_id

    def _apply_group_topics(self, group_id: str) -> None:
        gid = set_broadcast_group_id(group_id)
        self._broadcast_group_id = gid
        if gid:
            self._topic_cmd_broadcast = f"{TOPIC_PREFIX}/cmd/broadcast/{gid}/#"
            self._topic_desired = (
                f"{TOPIC_PREFIX}/desired/broadcast/{gid}/playback"
            )
        else:
            self._topic_cmd_broadcast = None
            self._topic_desired = None

    def start(self) -> None:
        if MQTT_USER:
            self._client.username_pw_set(MQTT_USER, MQTT_PASS or None)
        # Fabric LWT: empty payload → offline
        self._client.will_set(TOPIC_STATUS, payload=b"", qos=1, retain=True)
        self._client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        self._client.loop_start()
        _LOGGER.info(
            "MQTT handler started — connecting to %s:%d", MQTT_BROKER, MQTT_PORT
        )

    def stop(self) -> None:
        try:
            self._client.publish(TOPIC_STATUS, payload=b"", qos=1, retain=True)
        except Exception:
            pass
        self._client.loop_stop()
        self._client.disconnect()

    def publish_presence(self, online: bool) -> None:
        payload = b"online" if online else b"offline"
        self._client.publish(TOPIC_STATUS, payload=payload, qos=1, retain=True)

    def publish_status_json(self, status: dict) -> None:
        """Publish playback telemetry JSON (fabric presence stays plain text)."""
        body = {
            "pi_id": PI_ID,
            "broadcast_group_id": self._broadcast_group_id,
            "online": True,
            **status,
        }
        self._client.publish(
            TOPIC_STATUS_JSON,
            payload=json.dumps(body).encode("utf-8"),
            qos=0,
            retain=False,
        )
        self.publish_presence(True)

    def set_broadcast_group(self, group_id: str | None) -> None:
        """Apply membership from BGC; resubscribe broadcast + desired topics."""
        new_id = (group_id or "").strip()
        old_broadcast = self._topic_cmd_broadcast
        old_desired = self._topic_desired
        if new_id == self._broadcast_group_id:
            return
        if self._connected.is_set():
            if old_broadcast:
                try:
                    self._client.unsubscribe(old_broadcast)
                except Exception as err:
                    _LOGGER.debug("unsubscribe broadcast failed: %s", err)
            if old_desired:
                try:
                    self._client.unsubscribe(old_desired)
                except Exception as err:
                    _LOGGER.debug("unsubscribe desired failed: %s", err)
        self._apply_group_topics(new_id)
        if self._connected.is_set():
            if self._topic_cmd_broadcast:
                self._client.subscribe(self._topic_cmd_broadcast, qos=1)
                _LOGGER.info("Subscribed %s", self._topic_cmd_broadcast)
            if self._topic_desired:
                self._client.subscribe(self._topic_desired, qos=1)
                _LOGGER.info("Subscribed %s", self._topic_desired)
        # Ask playlist manager to reload for the new group key.
        self.cmd_queue.put({"action": "reload", "payload": {}})
        _LOGGER.info("Broadcast Group membership set to %r", new_id or None)

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            _LOGGER.error("MQTT connect failed rc=%s", rc)
            return
        topics = [TOPIC_CMD_DEVICE, TOPIC_CMD_ALL]
        if self._topic_cmd_broadcast:
            topics.append(self._topic_cmd_broadcast)
        if self._topic_desired:
            topics.append(self._topic_desired)
        for t in topics:
            client.subscribe(t, qos=1)
            _LOGGER.info("Subscribed %s", t)
        self.publish_presence(True)
        self._connected.set()

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected.clear()
        _LOGGER.warning("MQTT disconnected rc=%s", rc)

    def _on_message(self, client, userdata, msg) -> None:
        topic = msg.topic
        raw = msg.payload or b""

        # Desired playback retained state
        if self._topic_desired and topic == self._topic_desired:
            try:
                data = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                return
            state = (data.get("state") or "").lower()
            if state == "playing":
                self.cmd_queue.put({"action": "play", "payload": {}})
            elif state == "stopped":
                self.cmd_queue.put({"action": "stop", "payload": {}})
            if "volume" in data:
                self.cmd_queue.put(
                    {"action": "volume", "payload": {"volume": int(data["volume"])}}
                )
            return

        action = topic.rstrip("/").split("/")[-1]
        try:
            text = raw.decode("utf-8") if raw else "{}"
            payload = json.loads(text) if text.strip() else {}
        except Exception:
            payload = {}

        if action == "membership":
            bg = payload.get("broadcast_group_id")
            if bg is None:
                bg = ""
            self.set_broadcast_group(str(bg) if bg else "")
            return

        if action in _CACHE_ACTIONS:
            if CACHE_ENABLED:
                try:
                    from cache_manager import get_cache_manager

                    cm = get_cache_manager()
                    if not cm:
                        return
                    if action == "cache_delete":
                        cm.delete_file(
                            payload.get("subdir", ""), payload.get("filename", "")
                        )
                    elif action == "cache_purge":
                        cm.purge()
                    elif action == "cache_sync":
                        cm.sync_now()
                except Exception as err:
                    _LOGGER.warning("Cache cmd %s failed: %s", action, err)
            return

        if action in _PLAYBACK_ACTIONS:
            self.cmd_queue.put({"action": action, "payload": payload})
            return

        _LOGGER.debug("Ignoring topic %s", topic)
