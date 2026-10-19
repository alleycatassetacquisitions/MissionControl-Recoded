"""Resolve player video files on disk (event-scoped + legacy flat)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from app.config import ALLOWED_VIDEO_EXT, MEDIA_BASE
from app.services.event_paths import event_videos_dir, legacy_videos_dir, sanitize_event_id


def video_filename_for_player(player_id: str, ext: str = ".webm") -> str:
    pid = (player_id or "").strip()
    if not pid:
        raise ValueError("player_id required for video filename")
    suffix = ext if ext.startswith(".") else f".{ext}"
    return f"{pid}{suffix}"


def _find_in_dir(videos_dir: Path, player_id: str, stored_filename: str = "") -> str:
    pid = (player_id or "").strip()
    if pid and videos_dir.is_dir():
        for ext in sorted(ALLOWED_VIDEO_EXT):
            name = f"{pid}{ext}"
            if (videos_dir / name).is_file():
                return name
    if stored_filename and (videos_dir / stored_filename).is_file():
        return stored_filename
    return ""


def find_video_filename(
    player_id: str,
    stored_filename: str = "",
    event_id: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Return (filename, event_id_or_None_for_legacy).

    Prefers the active/event directory when ``event_id`` is set, then legacy
    flat ``media/videos/``.
    """
    if event_id:
        try:
            eid = sanitize_event_id(event_id)
        except ValueError:
            eid = ""
        if eid:
            name = _find_in_dir(event_videos_dir(eid), player_id, stored_filename)
            if name:
                return name, eid

    name = _find_in_dir(legacy_videos_dir(), player_id, stored_filename)
    if name:
        return name, None

    if stored_filename:
        return stored_filename, event_id if event_id else None
    return "", None


def player_has_video(
    player_id: str, stored_filename: str = "", event_id: Optional[str] = None
) -> bool:
    name, _ = find_video_filename(player_id, stored_filename, event_id=event_id)
    return bool(name)


def video_filesystem_path(
    filename: str, event_id: Optional[str] = None
) -> Path:
    if event_id:
        return event_videos_dir(event_id) / filename
    return Path(MEDIA_BASE) / "videos" / filename
