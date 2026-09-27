"""MQTT subscriber for AlleycatTV Pi — mc/tv fabric, JSON payloads.

Subscribes:
  mc/tv/cmd/device/{PI_ID}/#
  mc/tv/cmd/all/#
  mc/tv/cmd/broadcast/{id}/#   (when BROADCAST_GROUP_ID is set)
  mc/tv/desired/broadcast/{id}/playback  (retained desired state)

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
from typing import Any

import paho.mqtt.client as mqtt

from config import (
    BROADCAST_GROUP_ID,
    CACHE_ENABLED,
    MQTT_BROKER,
    MQTT_PASS,
    MQTT_PORT,
    MQTT_USER,
    PI_ID,
    TOPIC_CMD_ALL,
    TOPIC_CMD_BROADCAST,
    TOPIC_CMD_DEVICE,
    TOPIC_DESIRED_PLAYBACK,
    TOPIC_STATUS,
    TOPIC_STATUS_JSON,
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
            "broadcast_group_id": BROADCAST_GROUP_ID,
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

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc != 0:
            _LOGGER.error("MQTT connect failed rc=%s", rc)
            return
        topics = [TOPIC_CMD_DEVICE, TOPIC_CMD_ALL]
        if TOPIC_CMD_BROADCAST:
            topics.append(TOPIC_CMD_BROADCAST)
        if TOPIC_DESIRED_PLAYBACK:
            topics.append(TOPIC_DESIRED_PLAYBACK)
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
        if TOPIC_DESIRED_PLAYBACK and topic == TOPIC_DESIRED_PLAYBACK:
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
