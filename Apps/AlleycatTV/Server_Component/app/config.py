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
