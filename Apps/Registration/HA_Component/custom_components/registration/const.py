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
WS_GET_EVENTS = f"{DOMAIN}/get_events"
WS_GET_ACTIVE_EVENT = f"{DOMAIN}/get_active_event"

# hass.data keys (under DOMAIN)
EVENT_CACHE_KEY = "event_cache"
EVENT_STORE = "event_store"
ACTIVE_EVENT_ID_KEY = "active_event_id"

# Persist known events + last active across HA restarts (until Central GET /events).
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.events"
