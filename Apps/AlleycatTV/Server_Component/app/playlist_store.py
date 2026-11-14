"""Shared playlist JSON read/write and filename lookups."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from app.config import PLAYLISTS_FILE

_SUBDIR_MEDIA_TYPE = {
    "videos": "video",
    "photos": "photo",
    "announcements": "announcement",
}


def load_playlists() -> Dict[str, dict]:
    p = Path(PLAYLISTS_FILE)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_playlists(data: Dict[str, dict]) -> None:
    p = Path(PLAYLISTS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def media_type_for_subdir(subdir: str) -> Optional[str]:
    return _SUBDIR_MEDIA_TYPE.get(subdir)


def find_broadcast_groups_with_file(filename: str, subdir: str) -> List[str]:
    """Return broadcast_group_ids whose playlist contains this file (filename + media type)."""
    expected = media_type_for_subdir(subdir)
    if not expected:
        return []
    groups: List[str] = []
    for broadcast_group_id, playlist in load_playlists().items():
        for item in playlist.get("items", []):
            if item.get("filename") == filename and item.get("media_type") == expected:
                groups.append(broadcast_group_id)
                break
    return groups


def remove_file_from_all_playlists(filename: str, subdir: str) -> List[str]:
    """Remove matching playlist entries; return broadcast_group_ids that were updated."""
    expected = media_type_for_subdir(subdir)
    if not expected:
        return []
    data = load_playlists()
    updated: List[str] = []
    for broadcast_group_id, playlist in data.items():
        items = playlist.get("items", [])
        kept = [
            i for i in items
            if not (i.get("filename") == filename and i.get("media_type") == expected)
        ]
        if len(kept) != len(items):
            playlist["items"] = kept
            data[broadcast_group_id] = playlist
            updated.append(broadcast_group_id)
    if updated:
        save_playlists(data)
    return updated
