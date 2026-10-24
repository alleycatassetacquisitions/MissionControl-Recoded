"""Constants for the Registration integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "registration"

# Core Configurator service key for MCS — other integrations use this too.
KEY_MCS = "master_control_server"

# GBN poster server — receive active-event push for /poster-cycle kiosks.
KEY_GBN = "gbn"

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
WS_GET_TEAMS = f"{DOMAIN}/get_teams"
WS_GET_AFFILIATION_CATALOG = f"{DOMAIN}/get_affiliation_catalog"

# hass.data keys (under DOMAIN)
EVENT_CACHE_KEY = "event_cache"
EVENT_STORE = "event_store"
ACTIVE_EVENT_ID_KEY = "active_event_id"
# Event-keyed affiliation catalog: {event_id, categories:[...]} — not MCS durable.
AFFILIATION_CATALOG_KEY = "affiliation_catalog"

# Mission Control desk / device display limit (Central allows more).
PLAYER_NAME_MAX_LEN = 32

# Persist known events + last active across HA restarts (until Central GET /events).
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.events"
