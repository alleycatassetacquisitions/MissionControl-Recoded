"""AlleycatTV Pi player configuration.

Per-device: PI_ID, SERVER_URL, MQTT (HAOS Mosquitto).
Optional env BROADCAST_GROUP_ID is bootstrap only. Broadcast Group Controller
assigns live membership over MQTT (mc/tv/cmd/device/{id}/membership).
"""
import os
from typing import Optional

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
