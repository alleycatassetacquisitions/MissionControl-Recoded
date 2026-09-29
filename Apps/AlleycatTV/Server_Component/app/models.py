"""Pydantic models for the AlleycatTV content API.

Playlist buckets use broadcast_group_id (legacy JSON may still say zone_id).
Playback commands are NOT served here — Home Assistant owns MQTT commands.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class MediaType(str, Enum):
    video = "video"
    photo = "photo"
    announcement = "announcement"
    webpage = "webpage"
    rtsp = "rtsp"


class PlaylistMode(str, Enum):
    manual = "manual"
    auto = "auto"


class MediaItem(BaseModel):
    filename: str = ""
    media_type: MediaType
    photo_duration: int = Field(
        default=10, description="Seconds to display if media_type=photo"
    )
    url: Optional[str] = Field(
        default=None, description="Required for media_type=webpage"
    )
    duration: int = Field(
        default=30, description="Seconds to display if media_type=webpage"
    )


class Playlist(BaseModel):
    broadcast_group_id: str = ""
    zone_id: Optional[str] = None  # legacy alias accepted on read
    items: List[MediaItem] = []
    photo_interval: int = Field(
        default=5,
        description="Insert one random photo every N videos (0 = no photos)",
    )
    mode: PlaylistMode = Field(
        default=PlaylistMode.manual,
        description="manual = saved order; auto = shuffle loop items each cycle",
    )
    bumper_url: str = Field(
        default="",
        description="URL of the transition bumper between items (empty = none)",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_id(cls, data):
        if isinstance(data, dict):
            bg = data.get("broadcast_group_id") or data.get("zone_id") or ""
            data = {**data, "broadcast_group_id": bg}
        return data


class BroadcastGroup(BaseModel):
    broadcast_group_id: str
    name: str
    pi_ids: List[str] = []  # informational only until Phase 7 owns membership

    @model_validator(mode="before")
    @classmethod
    def _from_zone(cls, data):
        if isinstance(data, dict) and "zone_id" in data and "broadcast_group_id" not in data:
            data = {**data, "broadcast_group_id": data["zone_id"]}
        return data


# Back-compat alias for manage.html / older clients
Zone = BroadcastGroup


class AnnouncementUrlEntry(BaseModel):
    entry_id: str
    label: str
    url: str
    duration: int = 30


class ContentFile(BaseModel):
    filename: str
    media_type: MediaType
    size_bytes: int
    url: str
    subdir: Optional[str] = Field(
        default=None, description="Media folder: videos, photos, or announcements"
    )
    duration: Optional[int] = None
    entry_id: Optional[str] = None


class CacheReport(BaseModel):
    """Pi posts local cache inventory over HTTP (no MQTT from content server)."""

    files: List[dict] = []
    cache_bytes: int = 0
    free_bytes: Optional[int] = None
