"""AlleycatTV content server configuration.

No MQTT broker settings — Home Assistant is the only command publisher.
"""
import os

MEDIA_BASE = os.getenv("ALLEYCATV_MEDIA", "/opt/alleycattv/media")
PLAYLISTS_FILE = os.getenv("ALLEYCATV_PLAYLISTS", "/opt/alleycattv/playlists.json")
ZONES_FILE = os.getenv(
    "ALLEYCATV_ZONES",
    os.getenv("ALLEYCATV_BROADCAST_GROUPS", "/opt/alleycattv/broadcast_groups.json"),
)
DEVICES_FILE = os.getenv("ALLEYCATV_DEVICES", "/opt/alleycattv/devices.json")
SETTINGS_FILE = os.getenv("ALLEYCATV_SETTINGS", "/opt/alleycattv/settings.json")
ANNOUNCEMENTS_URLS_FILE = os.getenv(
    "ALLEYCATV_ANNOUNCEMENTS",
    os.path.join(MEDIA_BASE, "announcements", "_urls.json"),
)

API_HOST = os.getenv("ALLEYCATV_HOST", "0.0.0.0")
API_PORT = int(os.getenv("ALLEYCATV_PORT", "8000"))

# Fallback when no request Host is available. Prefer ``public_base_for(request)``
# so HA proxy (Core Configurator ``alleycattv`` URL) stamps the live LAN base.
PUBLIC_BASE = os.getenv(
    "ALLEYCATV_PUBLIC_BASE", f"http://127.0.0.1:{API_PORT}"
).rstrip("/")


def public_base_for(request=None) -> str:
    """Absolute base URL for media links stamped into content/bumper lists."""
    if request is not None:
        base_url = getattr(request, "base_url", None)
        if base_url is not None:
            base = str(base_url).rstrip("/")
            if base:
                return base
    return PUBLIC_BASE


MEDIA_SUBDIRS = ("videos", "photos", "announcements", "bumpers")
ALLOWED_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm"}
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
ALLOWED_BUMPER_EXT = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".webm",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
}
MAX_UPLOAD_MB = int(os.getenv("ALLEYCATV_MAX_UPLOAD_MB", "500"))
