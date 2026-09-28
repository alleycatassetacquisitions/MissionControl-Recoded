"""Content management router â€” upload, list, and delete media files."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile, File
from pydantic import BaseModel, Field

from app.config import (
    MEDIA_BASE,
    ANNOUNCEMENTS_URLS_FILE,
    ALLOWED_VIDEO_EXT,
    ALLOWED_PHOTO_EXT,
    ALLOWED_BUMPER_EXT,
    MAX_UPLOAD_MB,
)
from app.models import AnnouncementUrlEntry, ContentFile, MediaType
from app.playlist_store import find_zones_with_file, load_playlists, remove_file_from_all_playlists, save_playlists


def _notify_zones_reload(zone_ids: List[str]) -> None:
    """Playlist changed — operators reload via Home Assistant (no MQTT from this server)."""
    if not zone_ids:
        return
    _LOGGER.info(
        "Playlist(s) updated for %s — use alleycattv.reload_playlist in Home Assistant",
        ", ".join(zone_ids),
    )

router = APIRouter(prefix="/content", tags=["content"])
_LOGGER = logging.getLogger(__name__)

_MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024
_CHUNK_SIZE = 4 * 1024 * 1024
_uploads: dict[str, dict] = {}


def _classify(filename: str) -> MediaType:
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_VIDEO_EXT:
        return MediaType.video
    if ext in ALLOWED_PHOTO_EXT:
        return MediaType.photo
    raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")


def _load_url_announcements() -> List[AnnouncementUrlEntry]:
    p = Path(ANNOUNCEMENTS_URLS_FILE)
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text())
    except json.JSONDecodeError:
        return []
    return [AnnouncementUrlEntry(**item) for item in raw]


def _save_url_announcements(entries: List[AnnouncementUrlEntry]) -> None:
    p = Path(ANNOUNCEMENTS_URLS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([e.model_dump() for e in entries], indent=2))


class AnnouncementUrlCreate(BaseModel):
    label: str = Field(min_length=1)
    url: str = Field(min_length=1)
    duration: int = Field(default=30, ge=1, le=600)


class FileRef(BaseModel):
    """Reference to a file in videos/ or photos/."""
    subdir: str
    filename: str


class AnnouncementFileRef(BaseModel):
    filename: str


@router.get("/manifest")
async def content_manifest():
    """Return filename + size_bytes + mtime for all media files.
    Pi cache managers call this once per playlist refresh to detect stale files."""
    result: dict = {}
    for subdir in ("videos", "photos", "announcements"):
        folder = Path(MEDIA_BASE) / subdir
        folder.mkdir(parents=True, exist_ok=True)
        entries = []
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            if f.name.startswith("_") and f.suffix == ".json":
                continue
            ext = f.suffix.lower()
            if ext not in ALLOWED_VIDEO_EXT and ext not in ALLOWED_PHOTO_EXT:
                continue
            stat = f.stat()
            entries.append({
                "filename": f.name,
                "size_bytes": stat.st_size,
                "mtime": stat.st_mtime,
            })
        result[subdir] = entries
    return result


@router.get("/", response_model=List[ContentFile])
async def list_content(base_url: str = "http://localhost:8000"):
    """Return all media files across videos, photos, announcements, and URL entries."""
    files: List[ContentFile] = []
    for subdir in ("videos", "photos", "announcements"):
        folder = Path(MEDIA_BASE) / subdir
        folder.mkdir(parents=True, exist_ok=True)
        for f in sorted(folder.iterdir()):
            if not f.is_file():
                continue
            if f.name.startswith("_") and f.suffix == ".json":
                continue
            ext = f.suffix.lower()
            if ext in ALLOWED_VIDEO_EXT:
                mt = MediaType.announcement if subdir == "announcements" else MediaType.video
            elif ext in ALLOWED_PHOTO_EXT:
                mt = (
                    MediaType.announcement
                    if subdir == "announcements"
                    else MediaType.photo
                )
            else:
                continue
            duration = 30 if mt == MediaType.announcement and ext in ALLOWED_PHOTO_EXT else None
            if mt == MediaType.announcement and ext in ALLOWED_VIDEO_EXT:
                duration = None  # play full video
            files.append(ContentFile(
                filename=f.name,
                media_type=mt,
                size_bytes=f.stat().st_size,
                url=f"{base_url}/media/{subdir}/{quote(f.name)}",
                subdir=subdir,
                duration=duration,
            ))

    for entry in _load_url_announcements():
        files.append(ContentFile(
            filename=entry.label,
            media_type=MediaType.webpage,
            size_bytes=0,
            url=entry.url,
            subdir="announcements",
            duration=entry.duration,
            entry_id=entry.entry_id,
        ))

    # Live RTSP is owned by Core Configurator / HA AlleycatTV proxy overlay.
    # Do not inject from local settings.json (legacy path).

    return files


@router.get("/bumpers")
async def list_bumpers(base_url: str = "http://localhost:8000"):
    """Return all files in the bumpers folder with their server URLs."""
    folder = Path(MEDIA_BASE) / "bumpers"
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for f in sorted(folder.iterdir()):
        if not f.is_file():
            continue
        if f.suffix.lower() not in ALLOWED_BUMPER_EXT:
            continue
        stat = f.stat()
        results.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "url": f"{base_url}/media/bumpers/{quote(f.name)}",
        })
    return results


@router.post("/bumpers/upload")
async def upload_bumper(
    file: UploadFile = File(...),
):
    """Upload a transition bumper file (video, image, or gif)."""
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_BUMPER_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported bumper file type: {ext}")
    dest = Path(MEDIA_BASE) / "bumpers" / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > _MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
            out.write(chunk)
    return {"filename": file.filename, "size_bytes": total, "subdir": "bumpers"}


@router.delete("/bumpers/{filename:path}")
async def delete_bumper(filename: str):
    """Delete a bumper file."""
    target = _safe_media_path("bumpers", filename)
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Bumper not found: {filename}")
    target.unlink()
    return {"deleted": filename}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    subdir: str = Form(default="videos"),
    zone_id: Optional[str] = Form(default=None),
):
    """Upload a media file. If zone_id is provided, auto-adds it to that zone's playlist."""
    if subdir not in ("videos", "photos", "announcements"):
        raise HTTPException(status_code=400, detail="subdir must be videos, photos, or announcements")

    media_type = _classify(file.filename)
    if subdir == "announcements":
        media_type = MediaType.announcement

    dest = Path(MEDIA_BASE) / subdir / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    with open(dest, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            total += len(chunk)
            if total > _MAX_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
            out.write(chunk)

    if zone_id:
        _add_to_playlist(zone_id, file.filename, media_type.value)

    return {
        "filename": file.filename,
        "media_type": media_type,
        "size_bytes": total,
        "subdir": subdir,
        "added_to_zone": zone_id,
    }


class UploadStart(BaseModel):
    filename: str
    subdir: str = "videos"
    size_bytes: int = 0
    zone_id: Optional[str] = None


@router.post("/uploads")
async def start_chunked_upload(body: UploadStart):
    """Begin a chunked upload (Registration / HA proxy)."""
    if body.subdir not in ("videos", "photos", "announcements", "bumpers"):
        raise HTTPException(status_code=400, detail="subdir must be videos, photos, announcements, or bumpers")
    if body.size_bytes > _MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    upload_id = str(uuid.uuid4())
    tmp_dir = Path(MEDIA_BASE) / "_uploads" / upload_id
    tmp_dir.mkdir(parents=True, exist_ok=True)
    _uploads[upload_id] = {
        "filename": Path(body.filename).name,
        "subdir": body.subdir,
        "size_bytes": body.size_bytes,
        "zone_id": body.zone_id,
        "tmp_dir": str(tmp_dir),
        "received": 0,
    }
    return {"upload_id": upload_id, "chunk_size": _CHUNK_SIZE}


@router.put("/uploads/{upload_id}/chunks/{index}")
async def put_chunk(upload_id: str, index: int, request: Request):
    info = _uploads.get(upload_id)
    if not info:
        raise HTTPException(status_code=404, detail="Unknown upload_id")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty chunk")
    dest = Path(info["tmp_dir"]) / f"{int(index):08d}.part"
    dest.write_bytes(body)
    info["received"] = info.get("received", 0) + len(body)
    if info["received"] > _MAX_BYTES:
        _abort_upload(upload_id)
        raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
    return {"index": index, "bytes": len(body)}


@router.post("/uploads/{upload_id}/complete")
async def complete_chunked_upload(upload_id: str):
    info = _uploads.get(upload_id)
    if not info:
        raise HTTPException(status_code=404, detail="Unknown upload_id")
    tmp_dir = Path(info["tmp_dir"])
    parts = sorted(tmp_dir.glob("*.part"))
    if not parts:
        raise HTTPException(status_code=400, detail="No chunks received")
    filename = info["filename"]
    subdir = info["subdir"]
    media_type = _classify(filename)
    if subdir == "announcements":
        media_type = MediaType.announcement
    dest = Path(MEDIA_BASE) / subdir / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with open(dest, "wb") as out:
        for part in parts:
            data = part.read_bytes()
            total += len(data)
            if total > _MAX_BYTES:
                dest.unlink(missing_ok=True)
                _abort_upload(upload_id)
                raise HTTPException(status_code=413, detail=f"File exceeds {MAX_UPLOAD_MB} MB limit")
            out.write(data)
    zone_id = info.get("zone_id")
    if zone_id:
        _add_to_playlist(zone_id, filename, media_type.value)
    _abort_upload(upload_id)
    return {
        "filename": filename,
        "media_type": media_type,
        "size_bytes": total,
        "subdir": subdir,
        "added_to_zone": zone_id,
    }


@router.delete("/uploads/{upload_id}")
async def delete_chunked_upload(upload_id: str):
    if upload_id not in _uploads:
        raise HTTPException(status_code=404, detail="Unknown upload_id")
    _abort_upload(upload_id)
    return {"deleted": upload_id}


def _abort_upload(upload_id: str) -> None:
    info = _uploads.pop(upload_id, None)
    if not info:
        return
    tmp_dir = Path(info["tmp_dir"])
    if tmp_dir.exists():
        for f in tmp_dir.iterdir():
            f.unlink(missing_ok=True)
        tmp_dir.rmdir()


@router.post("/announcements/url", response_model=AnnouncementUrlEntry)
async def add_announcement_url(body: AnnouncementUrlCreate):
    """Add a scoreboard / webpage URL to the interrupt announcements library."""
    entries = _load_url_announcements()
    entry = AnnouncementUrlEntry(
        entry_id=str(uuid.uuid4()),
        label=body.label.strip(),
        url=body.url.strip(),
        duration=body.duration,
    )
    entries.append(entry)
    _save_url_announcements(entries)
    return entry


@router.delete("/announcements/url/{entry_id}")
async def delete_announcement_url(entry_id: str):
    """Remove a URL-based announcement."""
    entries = _load_url_announcements()
    kept = [e for e in entries if e.entry_id != entry_id]
    if len(kept) == len(entries):
        raise HTTPException(status_code=404, detail="Announcement URL not found")
    _save_url_announcements(kept)
    return {"deleted": entry_id}


def _safe_media_path(subdir: str, filename: str) -> Path:
    """Resolve a media file path and reject directory traversal."""
    base = (Path(MEDIA_BASE) / subdir).resolve()
    target = (Path(MEDIA_BASE) / subdir / filename).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=400, detail="Invalid filename")
    return target


@router.post("/usage-check")
async def content_usage_post(body: FileRef):
    """Return zone playlists that reference a library file (JSON body â€” avoids long URL issues)."""
    if body.subdir not in ("videos", "photos"):
        raise HTTPException(status_code=400, detail="Usage lookup only applies to videos and photos")
    zones = find_zones_with_file(body.filename, body.subdir)
    return {"filename": body.filename, "subdir": body.subdir, "zones": zones}


@router.post("/delete-file")
async def delete_file_post(body: FileRef):
    """Delete a videos/photos library file (JSON body â€” reliable for long filenames)."""
    return await _delete_library_file(body.subdir, body.filename)


@router.post("/announcements/delete-file")
async def delete_announcement_file_post(body: AnnouncementFileRef):
    """Delete an announcement file (JSON body)."""
    return await _delete_announcement_file(body.filename)


async def _delete_announcement_file(filename: str):
    _LOGGER.info("Delete announcement file requested: %r", filename)
    target = _safe_media_path("announcements", filename)
    if not target.is_file():
        _LOGGER.warning("Announcement delete failed â€” not found: %s", target)
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    target.unlink()
    _LOGGER.info("Deleted announcement file: %s", target)
    return {"deleted": filename}


@router.delete("/announcements/file/{filename:path}")
async def delete_announcement_file(filename: str):
    """Delete a file from the announcements library (explicit route for /manage UI)."""
    return await _delete_announcement_file(filename)


def _add_to_playlist(zone_id: str, filename: str, media_type: str) -> None:
    """Append a file to a zone's playlist, creating the playlist if needed."""
    data = load_playlists()
    playlist = data.get(zone_id, {"zone_id": zone_id, "items": [], "photo_interval": 5})
    items = playlist.get("items", [])
    if not any(i.get("filename") == filename for i in items):
        items.append({"filename": filename, "media_type": media_type})
    playlist["items"] = items
    data[zone_id] = playlist
    save_playlists(data)


@router.get("/usage/{subdir}/{filename:path}")
async def content_usage(subdir: str, filename: str):
    """Return zone playlists that reference a library file (for delete confirmation)."""
    if subdir not in ("videos", "photos"):
        raise HTTPException(status_code=400, detail="Usage lookup only applies to videos and photos")
    zones = find_zones_with_file(filename, subdir)
    return {"filename": filename, "subdir": subdir, "zones": zones}


@router.delete("/{subdir}/{filename:path}")
async def delete_file(subdir: str, filename: str):
    """Delete a videos/photos library file and remove it from any zone playlists."""
    return await _delete_library_file(subdir, filename)


async def _delete_library_file(subdir: str, filename: str):
    _LOGGER.info("Delete file requested: subdir=%s filename=%r", subdir, filename)
    if subdir not in ("videos", "photos"):
        raise HTTPException(
            status_code=400,
            detail="Use POST /api/content/announcements/delete-file for announcements",
        )
    target = _safe_media_path(subdir, filename)
    if not target.is_file():
        _LOGGER.warning("Delete failed â€” not found: %s", target)
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    removed_from = remove_file_from_all_playlists(filename, subdir)
    target.unlink()
    _notify_zones_reload(removed_from)
    _LOGGER.info("Deleted file: %s (removed from zones: %s)", target, removed_from)
    return {"deleted": filename, "subdir": subdir, "removed_from_zones": removed_from}
