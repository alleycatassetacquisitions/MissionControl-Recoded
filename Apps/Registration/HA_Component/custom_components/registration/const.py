"""Constants for the Registration integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "registration"

# Core Configurator service key for MCS — other integrations use this too.
KEY_MCS = "master_control_server"

# GBN poster server — still referenced by _push_central_config peer snapshot.
KEY_GBN = "gbn"

# Extra field on the MCS service key that holds the Bearer token.
EXTRA_MCS_TOKEN = "token"

# Core Configurator keys that MCS reads from HA.
KEY_CENTRAL_PRIMARY = "central_primary"
KEY_CENTRAL_SECONDARY = "central_secondary"
KEY_ALLEYCATTV = "alleycattv"
KEY_NET_TIME = "net_time"
KEY_PROXMOX = "proxmox"

UPDATE_INTERVAL = timedelta(seconds=60)

WS_GET_ROSTER = f"{DOMAIN}/get_roster"
WS_GET_ACTIVE_EVENT = f"{DOMAIN}/get_active_event"
WS_GET_TEAMS = f"{DOMAIN}/get_teams"
WS_GET_AFFILIATION_CATALOG = f"{DOMAIN}/get_affiliation_catalog"

# hass.data keys (under DOMAIN)
# Event-keyed affiliation catalog: {event_id, categories:[...]} — not MCS durable.
AFFILIATION_CATALOG_KEY = "affiliation_catalog"

# Mission Control desk / device display limit (Central allows more).
PLAYER_NAME_MAX_LEN = 32
