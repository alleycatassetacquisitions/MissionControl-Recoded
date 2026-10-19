"""Event media admin — list sizes, export clips zip, delete event folders."""
from __future__ import annotations

import io
import logging
import zipfile

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.models import ActiveEventInfo, EventMediaRow
from app.services.event_paths import (
    delete_event_storage,
    event_videos_dir,
    list_event_media_dirs,
    remember_active_event,
    sanitize_event_id,
    write_event_meta,
)
from app.services.mcs_client import get_active_event, resolve_active_event_id

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["events-media"])


def _event_stores(request: Request):
    return request.app.state.event_stores


def _ensure_event_store(
    request: Request,
    event_id: str | None,
    event_name: str | None = None,
) -> str | None:
    """Create per-event dirs when id is valid; return sanitized id or None."""
    if not event_id:
        return None
    try:
        eid = sanitize_event_id(event_id)
    except ValueError as exc:
        _LOGGER.warning("Ignoring invalid event_id for media ensure: %s", exc)
        return None
    try:
        _event_stores(request).for_event(eid)
    except ValueError as exc:
        _LOGGER.warning("Could not ensure event store %s: %s", eid, exc)
        return None
    if (event_name or "").strip():
        write_event_meta(eid, event_name or "")
    return eid


async def _active_meta() -> tuple[str | None, str, str]:
    state = await get_active_event()
    if not state:
        return None, "", ""
    eid = state.get("active_event_id")
    if eid is None and isinstance(state.get("event"), dict):
        eid = state["event"].get("id")
    eid_s = str(eid).strip() if eid is not None else ""
    name = ""
    event = state.get("event")
    if isinstance(event, dict):
        name = str(event.get("name") or "").strip()
    source = str(state.get("source") or "")
    return (eid_s or None), name, source


@router.get("/api/events/active", response_model=ActiveEventInfo)
async def api_active_event() -> ActiveEventInfo:
    eid, name, source = await _active_meta()
    return ActiveEventInfo(
        ready=True,
        active_event_id=eid,
        event_name=name,
        source=source or ("mcs" if eid else ""),
    )


@router.get("/api/events/media", response_model=list[EventMediaRow])
async def api_list_event_media(
    request: Request,
    ensure_event_id: str | None = Query(
        default=None,
        description=(
            "Event id known to the panel (e.g. Registration active). "
            "Seeds that folder when MCS active-event is unavailable."
        ),
    ),
    ensure_event_name: str | None = Query(
        default=None,
        description="Display name for ensure_event_id (stored in event meta.json).",
    ),
) -> list[EventMediaRow]:
    active_id, active_name, _ = await _active_meta()
    panel_name = (ensure_event_name or "").strip()
    # Prefer MCS active; fall back to panel-supplied id (Registration WS).
    seed_id = active_id or (ensure_event_id or "").strip() or None
    seed_name = active_name or panel_name or None
    ensured = _ensure_event_store(request, seed_id, event_name=seed_name)
    if ensured and not active_id:
        active_id = ensured
        _LOGGER.info(
            "Event media list using panel ensure_event_id=%s (MCS active unset)",
            ensured,
        )
    # Persist MCS / panel name + active pointer for /poster-cycle on AlleycatTV Pis
    if active_id:
        remember_active_event(
            active_id,
            active_name or panel_name or "",
            source="mcs" if active_name else "panel",
        )

    rows = list_event_media_dirs()
    out: list[EventMediaRow] = []
    for row in rows:
        is_active = bool(active_id and row["event_id"] == active_id)
        name = (
            (active_name if is_active else "")
            or row.get("event_name")
            or (panel_name if is_active else "")
            or ""
        )
        out.append(
            EventMediaRow(
                event_id=row["event_id"],
                event_name=name,
                clip_count=row["clip_count"],
                bytes_total=row["bytes_total"],
                has_media=row["has_media"],
                has_posters=row["has_posters"],
                is_active=is_active,
            )
        )
    return out


@router.get("/api/events/{event_id}/clips/export")
async def api_export_clips(event_id: str):
    try:
        eid = sanitize_event_id(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    vdir = event_videos_dir(eid)
    if not vdir.is_dir():
        raise HTTPException(status_code=404, detail="No clips folder for event")

    files = [p for p in sorted(vdir.iterdir()) if p.is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="No clips to export")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            zf.write(path, arcname=path.name)
    buf.seek(0)
    filename = f"gbn-clips-{eid}.zip"
    _LOGGER.info("Exporting %d clips for event %s", len(files), eid)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.delete("/api/events/{event_id}/media")
async def api_delete_event_media(event_id: str, request: Request):
    try:
        eid = sanitize_event_id(event_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    active = await resolve_active_event_id()
    result = delete_event_storage(eid)
    _event_stores(request).drop_cached(eid)
    # Recreate empty dirs if this is still the active event
    if active and active == eid:
        _event_stores(request).for_event(eid)
    return {"ok": True, **result}
