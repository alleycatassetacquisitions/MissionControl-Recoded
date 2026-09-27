"""Playlist management — keyed by broadcast_group_id (legacy zone_id accepted)."""
from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, HTTPException

from app.models import Playlist
from app.playlist_store import load_playlists, save_playlists

router = APIRouter(prefix="/playlists", tags=["playlists"])


def _load() -> Dict[str, dict]:
    return load_playlists()


def _save(data: Dict[str, dict]) -> None:
    save_playlists(data)


@router.get("/")
async def list_playlists():
    return _load()


@router.get("/{group_id}", response_model=Playlist)
async def get_playlist(group_id: str):
    data = _load()
    if group_id not in data:
        return Playlist(broadcast_group_id=group_id)
    return Playlist(**data[group_id])


@router.put("/{group_id}", response_model=Playlist)
async def upsert_playlist(group_id: str, playlist: Playlist):
    playlist = playlist.model_copy(update={"broadcast_group_id": group_id})
    data = _load()
    dumped = playlist.model_dump()
    dumped.pop("zone_id", None)
    data[group_id] = dumped
    _save(data)
    return playlist


@router.delete("/{group_id}")
async def delete_playlist(group_id: str):
    data = _load()
    if group_id not in data:
        raise HTTPException(status_code=404, detail="Playlist not found")
    del data[group_id]
    _save(data)
    return {"deleted": group_id}
