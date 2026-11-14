"""Constants for the Digital Node Nexus integration."""
from __future__ import annotations

DOMAIN = "digital_node_nexus"

# MQTT fabric kind — topics are mc/dnn/...
MQTT_KIND = "dnn"

WS_GET_DEVICES = f"{DOMAIN}/get_devices"

# Role and NeoCorp choices stamped into page payloads (DNN only; Registration has no ROLES).
ROLES = ("hunter", "bounty")
NEOCORPS = ("freelancer", "helix", "endline", "reboot")
