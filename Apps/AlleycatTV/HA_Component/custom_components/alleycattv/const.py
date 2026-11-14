"""Constants for the AlleycatTV Home Assistant integration."""
from __future__ import annotations

DOMAIN = "alleycattv"

# MQTT fabric kind — topics are mc/tv/...
MQTT_KIND = "tv"

# Core Configurator service key for the Proxmox content server.
KEY_ALLEYCATTV = "alleycattv"
# Core Configurator service key for the live RTSP source.
KEY_RTSP = "rtsp"

SIGNAL_NEW_DEVICE = f"{DOMAIN}_new_device"
SIGNAL_DEVICE_REMOVED = f"{DOMAIN}_device_removed"
SIGNAL_UPDATE = f"{DOMAIN}_update"

WS_GET_DEVICES = f"{DOMAIN}/get_devices"

# Services (broadcast, not zone). Placement lives on broadcast_group_controller.
SERVICE_PLAY_BROADCAST_GROUP = "play_broadcast_group"
SERVICE_STOP_BROADCAST_GROUP = "stop_broadcast_group"
SERVICE_INTERRUPT_BROADCAST_GROUP = "interrupt_broadcast_group"
SERVICE_INTERRUPT_PI = "interrupt_pi"
SERVICE_RELOAD_PLAYLIST = "reload_playlist"
SERVICE_SET_VOLUME_BROADCAST_GROUP = "set_volume_broadcast_group"
SERVICE_CACHE_DELETE = "cache_delete"
SERVICE_CACHE_PURGE = "cache_purge"
SERVICE_CACHE_SYNC = "cache_sync"
