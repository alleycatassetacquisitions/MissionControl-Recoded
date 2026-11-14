"""Constants for the Digital Node Nexus integration."""
from __future__ import annotations

DOMAIN = "digital_node_nexus"

# MQTT fabric kind — topics are mc/dnn/...
MQTT_KIND = "dnn"

WS_GET_DEVICES = f"{DOMAIN}/get_devices"

# Role stamps for page payloads (derived display aliases — Central SoT is team_name).
ROLES = ("hunter", "bounty", "unassigned")
NEOCORPS = ("freelancer", "helix", "endline", "reboot")
