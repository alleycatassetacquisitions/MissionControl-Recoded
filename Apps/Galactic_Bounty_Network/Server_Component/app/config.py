"""Galactic Bounty Network server configuration."""
from __future__ import annotations

import os
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent
_SERVER_DIR = _APP_DIR.parent

DATA_DIR = Path(os.getenv("GBN_DATA", str(_SERVER_DIR / "data")))
MEDIA_BASE = Path(os.getenv("GBN_MEDIA", str(_SERVER_DIR / "media")))
POSTERS_FILE = Path(os.getenv("GBN_POSTERS", str(DATA_DIR / "posters.json")))
TEMPLATES_FILE = Path(
    os.getenv("GBN_TEMPLATES", str(DATA_DIR / "poster_templates.json"))
)

API_HOST = os.getenv("GBN_HOST", "0.0.0.0")
API_PORT = int(os.getenv("GBN_PORT", "8100"))

# Fallback public base when no request Host is available (install-time DHCP IP).
# Poster/media links prefer ``public_base_for(request)`` so a new LAN IP is
# picked up automatically when Core Configurator / clients hit the new address.
PUBLIC_BASE = os.getenv("GBN_PUBLIC_BASE", f"http://127.0.0.1:{API_PORT}").rstrip("/")


def public_base_for(request=None) -> str:
    """Absolute base URL for poster and media links.

    Prefer the Host the client used (HA proxy uses Core Configurator's ``gbn``
    URL; direct browsers use whatever IP they opened). Fall back to runtime
    / env ``GBN_PUBLIC_BASE`` only when there is no request context.
    """
    if request is not None:
        base_url = getattr(request, "base_url", None)
        if base_url is not None:
            base = str(base_url).rstrip("/")
            if base:
                return base
    try:
        from app.runtime_config import public_base as _runtime_public

        runtime = (_runtime_public() or "").rstrip("/")
        if runtime:
            return runtime
    except Exception:  # noqa: BLE001
        pass
    return PUBLIC_BASE

# Master Control Server base (player overlay) — first-boot seed only.
# Runtime reads go through app.runtime_config getters (POST /config).
MCS_BASE = os.getenv("GBN_MCS_BASE", "").rstrip("/")
MCS_TOKEN = os.getenv("GBN_MCS_TOKEN", "").strip()

# Optional shared secret for POST /api/active-players from game server.
ACTIVE_PLAYERS_SECRET = os.getenv("GBN_ACTIVE_PLAYERS_SECRET", "").strip()

ALLOWED_VIDEO_EXT = {".webm", ".mp4", ".mov", ".mkv"}
MAX_UPLOAD_MB = int(os.getenv("GBN_MAX_UPLOAD_MB", "100"))
MEDIA_SUBDIRS = (
    "videos",
    "assets",
    "assets/neocorp",
    "assets/animations",
    "assets/marks",
)

ASSETS_BASE = MEDIA_BASE / "assets"

TEMPLATES_DIR = _APP_DIR / "templates"
STATIC_DIR = _APP_DIR / "static"
