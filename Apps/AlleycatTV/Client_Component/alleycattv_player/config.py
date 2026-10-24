"""AlleycatTV Pi player configuration.

Per-device: PI_ID, SERVER_URL, MQTT (HAOS Mosquitto).
Optional env BROADCAST_GROUP_ID is bootstrap only. Broadcast Group Controller
assigns live membership over MQTT (mc/tv/cmd/device/{id}/membership).

Year-1 runtime: retained MQTT ``config`` command can rewrite SERVER_URL /
MQTT broker in memory and best-effort persist ``/etc/alleycattv.env``.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

_LOGGER = logging.getLogger(__name__)
_ENV_PATH = Path("/etc/alleycattv.env")

# -- Per-device identity ------------------------------------------------------
PI_ID = os.getenv("ALLEYCATV_PI_ID", "pi-01")
BROADCAST_GROUP_ID = os.getenv(
    "ALLEYCATV_BROADCAST_GROUP_ID",
    os.getenv("ALLEYCATV_ZONE_ID", ""),  # legacy env alias
)

# Runtime override from BGC membership assign (None = use env bootstrap).
_runtime_broadcast_group_id: Optional[str] = None


def get_broadcast_group_id() -> str:
    """Return the active Broadcast Group id (BGC assign wins over env)."""
    if _runtime_broadcast_group_id is not None:
        return _runtime_broadcast_group_id
    return (BROADCAST_GROUP_ID or "").strip()


def set_broadcast_group_id(group_id: str | None) -> str:
    """Apply BGC membership; empty string clears. Returns the new id."""
    global _runtime_broadcast_group_id, ZONE_ID
    _runtime_broadcast_group_id = (group_id or "").strip()
    ZONE_ID = _runtime_broadcast_group_id
    return _runtime_broadcast_group_id

# -- Network ------------------------------------------------------------------
SERVER_URL = os.getenv(
    "ALLEYCATV_SERVER", "http://headless-alleycat-streaming-server.local"
).rstrip("/")
MQTT_BROKER = os.getenv("ALLEYCATV_MQTT", "homeassistant.local")
MQTT_PORT = int(os.getenv("ALLEYCATV_MQTT_PORT", "1883"))
MQTT_USER = os.getenv("ALLEYCATV_MQTT_USER", "")
MQTT_PASS = os.getenv("ALLEYCATV_MQTT_PASS", "")

# -- Playlist behaviour -------------------------------------------------------
PHOTO_INTERVAL = int(os.getenv("ALLEYCATV_PHOTO_INTERVAL", "5"))
PHOTO_DURATION = int(os.getenv("ALLEYCATV_PHOTO_DURATION", "10"))
PLAYLIST_REFRESH_INTERVAL = int(os.getenv("ALLEYCATV_PLAYLIST_REFRESH", "300"))

# -- Player -------------------------------------------------------------------
MPV_SOCKET_PATH = os.getenv("ALLEYCATV_MPV_SOCKET", "/tmp/alleycattv-mpv.sock")
STATUS_INTERVAL = int(os.getenv("ALLEYCATV_STATUS_INTERVAL", "30"))

# -- MQTT topics (mc/tv fabric) -----------------------------------------------
TOPIC_PREFIX = "mc/tv"
TOPIC_STATUS = f"{TOPIC_PREFIX}/status/{PI_ID}"
TOPIC_STATUS_JSON = f"{TOPIC_PREFIX}/status/{PI_ID}/json"
TOPIC_CMD_DEVICE = f"{TOPIC_PREFIX}/cmd/device/{PI_ID}/#"
TOPIC_CMD_ALL = f"{TOPIC_PREFIX}/cmd/all/#"
TOPIC_CMD_BROADCAST = (
    f"{TOPIC_PREFIX}/cmd/broadcast/{BROADCAST_GROUP_ID}/#"
    if BROADCAST_GROUP_ID
    else None
)
TOPIC_DESIRED_PLAYBACK = (
    f"{TOPIC_PREFIX}/desired/broadcast/{BROADCAST_GROUP_ID}/playback"
    if BROADCAST_GROUP_ID
    else None
)

MEDIA_BASE_URL = f"{SERVER_URL}/media"

# -- Transition bumper --------------------------------------------------------
BUMPER_PATH = os.getenv("ALLEYCATV_BUMPER", "")
BUMPER_DURATION = int(os.getenv("ALLEYCATV_BUMPER_DURATION", "0"))

# -- Local video cache --------------------------------------------------------
CACHE_ENABLED = os.getenv("ALLEYCATV_CACHE", "1") == "1"
CACHE_DIR = os.getenv("ALLEYCATV_CACHE_DIR", "/opt/alleycattv/cache")
CACHE_MAX_GB = float(os.getenv("ALLEYCATV_CACHE_MAX_GB", "10"))

# Back-compat names used by older player code paths
ZONE_ID = BROADCAST_GROUP_ID


def apply_runtime_config(
    *,
    server_url: str = "",
    mqtt_host: str = "",
    mqtt_port: str | int = "",
) -> dict:
    """Apply non-empty network fields; persist env best-effort.

    Returns ``{"server_changed": bool, "mqtt_changed": bool}``.
    """
    global SERVER_URL, MEDIA_BASE_URL, MQTT_BROKER, MQTT_PORT
    server_changed = False
    mqtt_changed = False

    cleaned_server = (server_url or "").strip().rstrip("/")
    if cleaned_server and cleaned_server != SERVER_URL:
        SERVER_URL = cleaned_server
        MEDIA_BASE_URL = f"{SERVER_URL}/media"
        server_changed = True

    cleaned_host = (mqtt_host or "").strip()
    if cleaned_host and cleaned_host != MQTT_BROKER:
        MQTT_BROKER = cleaned_host
        mqtt_changed = True

    if mqtt_port not in ("", None):
        try:
            port_i = int(mqtt_port)
        except (TypeError, ValueError):
            port_i = None
        if port_i and port_i != MQTT_PORT:
            MQTT_PORT = port_i
            mqtt_changed = True

    if server_changed or mqtt_changed:
        _persist_env()
        _LOGGER.info(
            "Runtime config applied — server=%r mqtt=%s:%s",
            SERVER_URL,
            MQTT_BROKER,
            MQTT_PORT,
        )
    return {"server_changed": server_changed, "mqtt_changed": mqtt_changed}


def _persist_env() -> None:
    """Merge key network fields into /etc/alleycattv.env (may be root-owned)."""
    updates = {
        "ALLEYCATV_SERVER": SERVER_URL,
        "ALLEYCATV_MQTT": MQTT_BROKER,
        "ALLEYCATV_MQTT_PORT": str(MQTT_PORT),
    }
    try:
        existing: dict[str, str] = {}
        order: list[str] = []
        if _ENV_PATH.is_file():
            for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key not in existing:
                    order.append(key)
                existing[key] = value
        for key, value in updates.items():
            if key not in existing:
                order.append(key)
            existing[key] = value
        # Preserve PI_ID if file was missing
        if "ALLEYCATV_PI_ID" not in existing:
            order.insert(0, "ALLEYCATV_PI_ID")
            existing["ALLEYCATV_PI_ID"] = PI_ID
        text = "".join(f"{k}={existing[k]}\n" for k in order)
        _ENV_PATH.write_text(text, encoding="utf-8")
        _LOGGER.info("Persisted %s", _ENV_PATH)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Could not persist %s: %s (in-memory config still applied)", _ENV_PATH, exc)
