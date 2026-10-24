"""Constants for the Game Master integration."""
from __future__ import annotations

DOMAIN = "game_master"

KEY_MCS = "master_control_server"
EXTRA_MCS_TOKEN = "token"

WS_GET_GAME_STATE = f"{DOMAIN}/get_game_state"
WS_SET_SCORING = f"{DOMAIN}/set_scoring"
WS_SET_DELAYED_SCORES = f"{DOMAIN}/set_delayed_scores"
WS_GET_AFFILIATION_CATALOG = f"{DOMAIN}/get_affiliation_catalog"

# Event-keyed affiliation catalog cache (Game Master owns CRUD).
AFFILIATION_CATALOG_KEY = "affiliation_catalog"
