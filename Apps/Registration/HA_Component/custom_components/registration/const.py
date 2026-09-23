"""Constants for the Registration integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "registration"

# Core Configurator service key for MCS — other integrations use this too.
KEY_MCS = "master_control_server"

# Extra field on the MCS service key that holds the Bearer token.
EXTRA_MCS_TOKEN = "token"

# Core Configurator keys that MCS reads from HA.
KEY_CENTRAL_PRIMARY = "central_primary"
KEY_CENTRAL_SECONDARY = "central_secondary"

# DataUpdateCoordinator poll interval.
UPDATE_INTERVAL = timedelta(seconds=60)

# Websocket command namespace.
WS_GET_ROSTER = f"{DOMAIN}/get_roster"
WS_REGISTER_PLAYER = f"{DOMAIN}/register_player"
