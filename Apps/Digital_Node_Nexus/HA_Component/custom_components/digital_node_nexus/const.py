"""Constants for the Digital Node Nexus integration."""
from __future__ import annotations

DOMAIN = "digital_node_nexus"

# MQTT fabric kind — topics are mc/dnn/...
MQTT_KIND = "dnn"

# Core Configurator service key for Master Control Server.
KEY_MCS = "master_control_server"
EXTRA_MCS_TOKEN = "token"

# Websocket commands for the DNN panel.
WS_GET_DEVICES = f"{DOMAIN}/get_devices"
WS_GET_ROSTER = f"{DOMAIN}/get_roster"

# Canonical role / NeoCorp values (same as Registration / MCS).
ROLES = ("hunter", "bounty")
NEOCORPS = ("freelancer", "helix", "endline", "reboot")
