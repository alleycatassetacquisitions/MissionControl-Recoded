"""Constants for the Game Master integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "game_master"

KEY_MCS = "master_control_server"
EXTRA_MCS_TOKEN = "token"

# GBN poster server — receives active-event push for /poster-cycle kiosks.
KEY_GBN = "gbn"

WS_GET_GAME_STATE = f"{DOMAIN}/get_game_state"
WS_SET_SCORING = f"{DOMAIN}/set_scoring"
WS_SET_DELAYED_SCORES = f"{DOMAIN}/set_delayed_scores"
WS_GET_AFFILIATION_CATALOG = f"{DOMAIN}/get_affiliation_catalog"

# Event list websocket (moved from Registration; Registration is read-only for events).
WS_GET_EVENTS = f"{DOMAIN}/get_events"

# Event-keyed affiliation catalog cache (Game Master owns CRUD).
AFFILIATION_CATALOG_KEY = "affiliation_catalog"

# HA-only defaults: event_id → category_id → affiliation_id (not sent to Central).
AFFILIATION_DEFAULTS_KEY = "affiliation_defaults"
AFFILIATION_DEFAULTS_STORE = f"{DOMAIN}.affiliation_defaults"
AFFILIATION_DEFAULTS_VERSION = 1

# hass.data keys for event cache + active-event persistence.
EVENT_CACHE_KEY = "event_cache"
EVENT_STORE = "event_store"
ACTIVE_EVENT_ID_KEY = "active_event_id"

# Persist known events + last active across HA restarts.
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.events"
