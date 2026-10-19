"""Event-scoped data and media paths for GBN."""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path
from typing import List, Optional

from app.config import ALLOWED_VIDEO_EXT, DATA_DIR, MEDIA_BASE, POSTERS_FILE

_LOGGER = logging.getLogger(__name__)

_SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def sanitize_event_id(event_id: str) -> str:
    eid = (event_id or "").strip()
    if not eid or not _SAFE_EVENT_ID.match(eid):
        raise ValueError(f"Invalid event_id: {event_id!r}")
    return eid


def event_data_dir(event_id: str) -> Path:
    return DATA_DIR / "events" / sanitize_event_id(event_id)


def event_posters_file(event_id: str) -> Path:
    return event_data_dir(event_id) / "posters.json"


def event_videos_dir(event_id: str) -> Path:
    return MEDIA_BASE / "events" / sanitize_event_id(event_id) / "videos"


def legacy_videos_dir() -> Path:
    return Path(MEDIA_BASE) / "videos"


def ensure_event_dirs(event_id: str) -> None:
    eid = sanitize_event_id(event_id)
    event_data_dir(eid).mkdir(parents=True, exist_ok=True)
    event_videos_dir(eid).mkdir(parents=True, exist_ok=True)


def video_url_path(event_id: Optional[str], filename: str) -> str:
    """Relative media path (under /media mount)."""
    name = (filename or "").strip()
    if not name:
        return ""
    if event_id:
        return f"events/{sanitize_event_id(event_id)}/videos/{name}"
    return f"videos/{name}"


def dir_total_bytes(path: Path) -> int:
    if not path.is_dir():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def count_clips(videos_dir: Path) -> int:
    if not videos_dir.is_dir():
        return 0
    n = 0
    for p in videos_dir.iterdir():
        if p.is_file() and p.suffix.lower() in ALLOWED_VIDEO_EXT:
            n += 1
    return n


def list_event_media_dirs() -> List[dict]:
    """Scan media/events/* and data/events/* for known event folders."""
    ids: set[str] = set()
    media_root = Path(MEDIA_BASE) / "events"
    data_root = Path(DATA_DIR) / "events"
    if media_root.is_dir():
        for child in media_root.iterdir():
            if child.is_dir() and _SAFE_EVENT_ID.match(child.name):
                ids.add(child.name)
    if data_root.is_dir():
        for child in data_root.iterdir():
            if child.is_dir() and _SAFE_EVENT_ID.match(child.name):
                ids.add(child.name)

    rows: List[dict] = []
    for eid in sorted(ids):
        vdir = event_videos_dir(eid)
        ddir = event_data_dir(eid)
        clip_count = count_clips(vdir)
        bytes_total = dir_total_bytes(vdir) + dir_total_bytes(ddir)
        rows.append(
            {
                "event_id": eid,
                "clip_count": clip_count,
                "bytes_total": bytes_total,
                "has_media": vdir.is_dir(),
                "has_posters": event_posters_file(eid).is_file(),
            }
        )
    return rows


def delete_event_storage(event_id: str) -> dict:
    """Remove media and posters for an event. Returns what was deleted."""
    eid = sanitize_event_id(event_id)
    media_root = Path(MEDIA_BASE) / "events" / eid
    data_root = event_data_dir(eid)
    removed = {"media": False, "data": False}
    if media_root.exists():
        shutil.rmtree(media_root)
        removed["media"] = True
        _LOGGER.info("Deleted event media %s", media_root)
    if data_root.exists():
        shutil.rmtree(data_root)
        removed["data"] = True
        _LOGGER.info("Deleted event data %s", data_root)
    return {"event_id": eid, "removed": removed}


def legacy_posters_path() -> Path:
    return Path(POSTERS_FILE)
