"""Event-scoped data and media paths for GBN."""
from __future__ import annotations

import json
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


def event_meta_file(event_id: str) -> Path:
    return event_data_dir(event_id) / "meta.json"


def event_videos_dir(event_id: str) -> Path:
    return MEDIA_BASE / "events" / sanitize_event_id(event_id) / "videos"


def legacy_videos_dir() -> Path:
    return Path(MEDIA_BASE) / "videos"


def ensure_event_dirs(event_id: str, event_name: str | None = None) -> None:
    eid = sanitize_event_id(event_id)
    event_data_dir(eid).mkdir(parents=True, exist_ok=True)
    event_videos_dir(eid).mkdir(parents=True, exist_ok=True)
    name = (event_name or "").strip()
    if name:
        write_event_meta(eid, name)


def read_event_name(event_id: str) -> str:
    path = event_meta_file(event_id)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        if isinstance(data, dict):
            return str(data.get("name") or "").strip()
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def write_event_meta(event_id: str, name: str) -> None:
    eid = sanitize_event_id(event_id)
    clean = (name or "").strip()
    if not clean:
        return
    path = event_meta_file(eid)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
            if isinstance(raw, dict):
                existing = raw
        except (OSError, json.JSONDecodeError):
            existing = {}
    if existing.get("name") == clean:
        return
    existing["name"] = clean
    existing["id"] = eid
    path.write_text(json.dumps(existing, indent=2), encoding="utf-8")


def active_event_cache_path() -> Path:
    """Last-known active event for kiosk when MCS is unreachable."""
    return Path(DATA_DIR) / "active_event.json"


def remember_active_event(
    event_id: str,
    event_name: str = "",
    source: str = "local",
) -> None:
    """Persist active event so /poster-cycle works without a live MCS round-trip."""
    try:
        eid = sanitize_event_id(event_id)
    except ValueError:
        return
    name = (event_name or "").strip() or read_event_name(eid)
    if name:
        write_event_meta(eid, name)
    from datetime import datetime, timezone

    payload = {
        "active_event_id": eid,
        "event_name": name,
        "event": {"id": eid, "name": name} if eid else None,
        "source": source or "local",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path = active_event_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _LOGGER.debug("Remembered active event %s (%s)", eid, name or "unnamed")


def clear_cached_active_event() -> None:
    path = active_event_cache_path()
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        _LOGGER.warning("Could not clear active event cache: %s", exc)


def read_cached_active_event() -> Optional[dict]:
    path = active_event_cache_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    eid = str(data.get("active_event_id") or "").strip()
    if not eid:
        return None
    name = str(data.get("event_name") or "").strip() or read_event_name(eid)
    return {
        "ready": True,
        "active_event_id": eid,
        "event_name": name,
        "event": {"id": eid, "name": name},
        "source": str(data.get("source") or "gbn_cache"),
    }


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
                "event_name": read_event_name(eid),
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
