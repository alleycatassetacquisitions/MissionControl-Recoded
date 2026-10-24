"""Poster create/list/detail and HTML poster page.

Player identity is overlaid from MCS on every HTML read path.
``GET /api/players`` is intentionally absent — GBN does not impersonate roster.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import (
    ALLOWED_VIDEO_EXT,
    MAX_UPLOAD_MB,
    TEMPLATES_DIR,
    public_base_for,
)
from app.event_stores import EventPosterStores
from app.models import (
    DEFAULT_ACCENT,
    PosterAffiliationSnap,
    PosterPublic,
    PosterRecord,
    PosterStats,
    PosterStatus,
    PosterTemplate,
    Role,
    accent_dim,
    accent_hex,
    normalize_accent,
)
from app.services.event_paths import (
    ensure_event_dirs,
    sanitize_event_id,
    video_url_path,
)
from app.services.mcs_client import lookup_by_id, resolve_active_event_id
from app.services.video_paths import (
    find_video_filename,
    video_filename_for_player,
    video_filesystem_path,
)
from app.store import PosterStore
from app.template_store import TemplateStore

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["posters"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _event_stores(request: Request) -> EventPosterStores:
    return request.app.state.event_stores


def _templates(request: Request) -> TemplateStore:
    return request.app.state.template_store


async def _require_active_event_id(fallback: str | None = None) -> str:
    """MCS active event first; optional panel-supplied id when MCS is unset."""
    eid = await resolve_active_event_id()
    if not eid and fallback:
        try:
            eid = sanitize_event_id(fallback)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not eid:
        raise HTTPException(
            status_code=409,
            detail="No active event — set one in Registration before creating posters",
        )
    return eid


async def _active_store(
    request: Request, fallback: str | None = None
) -> tuple[str, PosterStore]:
    eid = await _require_active_event_id(fallback=fallback)
    return eid, _event_stores(request).for_event(eid)


async def _resolve_event_id(fallback: str | None = None) -> str | None:
    """Active event for reads: MCS, else sanitized panel fallback."""
    eid = await resolve_active_event_id()
    if eid:
        return eid
    raw = (fallback or "").strip()
    if not raw:
        return None
    try:
        return sanitize_event_id(raw)
    except ValueError:
        return None




def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chrome_fallback(role: Role) -> PosterTemplate:
    if role == "hunter":
        return PosterTemplate(
            id="hunter",
            name="Hunter",
            headline="GUN FOR HIRE",
            subtitle="",
            amount_label="RATE",
            list_label="REASONS TO HIRE",
            list_empty="Details pending",
            accent=DEFAULT_ACCENT,
            builtin=True,
        )
    return PosterTemplate(
        id="bounty",
        name="Bounty",
        headline="WANTED",
        subtitle="DEAD OR ALIVE",
        amount_label="REWARD",
        list_label="WANTED FOR",
        list_empty="Charges pending",
        accent=DEFAULT_ACCENT,
        builtin=True,
    )


def _resolve_chrome(
    request: Request,
    *,
    role: Role,
    template_id: str = "",
    headline: str = "",
    subtitle: str = "",
    amount_label: str = "",
    list_label: str = "",
    list_empty: str = "",
    accent: str = "",
) -> dict:
    """Resolve chrome from template + optional form overrides."""
    store = _templates(request)
    tid = (template_id or "").strip()
    tmpl = store.get(tid) if tid else None
    if tmpl is None:
        tmpl = store.builtin_for_role(role)

    def pick(override: str, default: str) -> str:
        o = (override or "").strip()
        return o if o else default

    accent_slug = normalize_accent(accent) if (accent or "").strip() else normalize_accent(
        tmpl.accent
    )
    return {
        "template_id": tmpl.id,
        "headline": pick(headline, tmpl.headline),
        "subtitle": pick(subtitle, tmpl.subtitle),
        "amount_label": pick(amount_label, tmpl.amount_label),
        "list_label": pick(list_label, tmpl.list_label),
        "list_empty": pick(list_empty, tmpl.list_empty),
        "accent": accent_slug,
    }


def _effective_chrome(poster: PosterRecord) -> dict:
    """Chrome for display: custom snapshot, else role built-in.

    Built-in hunter/bounty templates follow live MCS role overlays.
    Custom template_ids always use the snapshotted chrome.
    """
    fb = _chrome_fallback(poster.role)
    tid = (poster.template_id or "").strip()
    is_custom = bool(tid) and tid not in ("hunter", "bounty")
    accent = normalize_accent(poster.accent or fb.accent)

    if is_custom and (poster.headline or "").strip():
        return {
            "template_id": tid,
            "headline": poster.headline.strip(),
            "subtitle": poster.subtitle or "",
            "amount_label": (poster.amount_label or "").strip() or fb.amount_label,
            "list_label": (poster.list_label or "").strip() or fb.list_label,
            "list_empty": (poster.list_empty or "").strip() or fb.list_empty,
            "accent": accent,
        }

    # Builtin / unset: use snapshot only when it still matches current role
    if (poster.headline or "").strip() and tid == fb.id:
        return {
            "template_id": tid,
            "headline": poster.headline.strip(),
            "subtitle": poster.subtitle or "",
            "amount_label": (poster.amount_label or "").strip() or fb.amount_label,
            "list_label": (poster.list_label or "").strip() or fb.list_label,
            "list_empty": (poster.list_empty or "").strip() or fb.list_empty,
            "accent": accent,
        }

    return {
        "template_id": fb.id,
        "headline": fb.headline,
        "subtitle": fb.subtitle,
        "amount_label": fb.amount_label,
        "list_label": fb.list_label,
        "list_empty": fb.list_empty,
        "accent": normalize_accent(fb.accent),
    }


_KNOWN_LOGO_SLUGS = frozenset({"reboot", "helix", "endline", "freelancer"})


def _normalize_neocorp(value: str) -> str:
    """Store affiliation display/slug as-is; do not coerce unknowns to freelancer."""
    return (value or "").strip()


def _logo_slug(neocorp: str) -> str:
    raw = (neocorp or "").strip().lower()
    if raw in _KNOWN_LOGO_SLUGS:
        return raw
    first = raw.split()[0] if raw else ""
    if first in _KNOWN_LOGO_SLUGS:
        return first
    return "freelancer"


def _parse_affiliations_snap(raw: str) -> list[PosterAffiliationSnap]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[PosterAffiliationSnap] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        cat = str(item.get("category_name") or "").strip()
        name = str(item.get("affiliation_name") or "").strip()
        if cat or name:
            out.append(
                PosterAffiliationSnap(category_name=cat, affiliation_name=name)
            )
    return out


def _normalize_role(value: str) -> Role:
    v = (value or "bounty").strip().lower()
    if v in ("hunter", "bounty"):
        return v  # type: ignore[return-value]
    return "bounty"


def _poster_url_for(poster: PosterRecord, request: Request | None = None) -> str:
    base = public_base_for(request)
    if poster.player_id:
        return f"{base}/poster/player/{poster.player_id}"
    return f"{base}/poster/{poster.id}"


def _video_url_for(
    poster: PosterRecord,
    request: Request | None = None,
    event_id: str | None = None,
) -> str:
    filename, resolved_eid = find_video_filename(
        poster.player_id, poster.video_filename, event_id=event_id
    )
    if not filename:
        return ""
    rel = video_url_path(resolved_eid, filename)
    return f"{public_base_for(request)}/media/{rel}"


def _to_public(
    poster: PosterRecord,
    request: Request | None = None,
    event_id: str | None = None,
) -> PosterPublic:
    video_url = _video_url_for(poster, request, event_id=event_id)
    chrome = _effective_chrome(poster)
    return PosterPublic(
        id=poster.id,
        player_id=poster.player_id,
        event_id=event_id or "",
        name=poster.name,
        role=poster.role,
        neocorp=poster.neocorp,
        faction=poster.faction,
        affiliations=list(poster.affiliations or []),
        bounty_amount=poster.bounty_amount,
        crimes=poster.crimes,
        stats=poster.stats,
        status=poster.status,
        flavor_text=poster.flavor_text,
        video_url=video_url,
        poster_url=_poster_url_for(poster, request),
        has_video=bool(video_url),
        template_id=chrome["template_id"],
        headline=chrome["headline"],
        subtitle=chrome["subtitle"],
        amount_label=chrome["amount_label"],
        list_label=chrome["list_label"],
        list_empty=chrome["list_empty"],
        accent=chrome["accent"],
        created_at=poster.created_at,
        updated_at=poster.updated_at,
    )


def _parse_crimes(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(c).strip() for c in data if str(c).strip()]
    except json.JSONDecodeError:
        pass
    return [line.strip() for line in raw.replace(",", "\n").splitlines() if line.strip()]


def _parse_stats(raw: str) -> PosterStats:
    if not (raw or "").strip():
        return PosterStats()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return PosterStats.model_validate(data)
    except (json.JSONDecodeError, ValueError):
        pass
    return PosterStats()


def _delete_video(filename: str, event_id: str | None = None) -> None:
    if not filename:
        return
    path = video_filesystem_path(filename, event_id=event_id)
    try:
        if path.is_file():
            path.unlink()
    except OSError as exc:
        _LOGGER.warning("Could not delete old video %s: %s", path, exc)


def _delete_other_player_videos(
    player_id: str, keep_filename: str, event_id: str | None = None
) -> None:
    pid = (player_id or "").strip()
    if not pid:
        return
    for ext in ALLOWED_VIDEO_EXT:
        name = f"{pid}{ext}"
        if name != keep_filename:
            _delete_video(name, event_id=event_id)


async def _apply_live_overlay(display: PosterRecord) -> PosterRecord:
    if not display.player_id:
        return display
    live = await lookup_by_id(display.player_id)
    if not live:
        return display
    if live.name:
        display.name = live.name
    display.role = live.role
    display.neocorp = live.neocorp
    display.faction = live.faction
    if any(
        (
            live.status.current_score,
            live.status.fastest_win,
            live.status.longest_streak,
        )
    ):
        display.status = live.status
    return display


def _poster_context(public: PosterPublic) -> dict:
    is_hunter = public.role == "hunter"
    logo_slug = _logo_slug(public.neocorp)
    neocorp_logo = f"/media/assets/neocorp/{logo_slug}.svg"
    return {
        "poster": public,
        "bounty_display": f"₩{public.bounty_amount:,}",
        "crimes_json": json.dumps(public.crimes),
        "is_hunter": is_hunter,
        "list_heading": public.list_label,
        "list_empty": public.list_empty,
        "headline_main": public.headline,
        "headline_sub": public.subtitle,
        "amount_label": public.amount_label,
        "neocorp_logo": neocorp_logo,
        "accent_hex": accent_hex(public.accent),
        "accent_dim": accent_dim(public.accent),
        "status_rows": [
            ("CURRENT SCORE", public.status.current_score or "—"),
            ("FASTEST WIN", public.status.fastest_win or "—"),
            ("LONGEST STREAK", public.status.longest_streak or "—"),
        ],
    }


async def _render_poster(
    request: Request, poster: PosterRecord, event_id: str | None = None
):
    display = await _apply_live_overlay(poster.model_copy(deep=True))
    public = _to_public(display, request, event_id=event_id)
    return templates.TemplateResponse(
        request,
        "poster.html",
        _poster_context(public),
    )


async def _resolve_poster_for_player(
    request: Request, player_id: str, event_id: str | None = None
) -> tuple[PosterRecord, str | None]:
    stores = _event_stores(request)
    active = await _resolve_event_id(event_id)
    poster, eid = stores.get_poster_for_player(player_id, event_id=active)
    if not poster:
        raise HTTPException(status_code=404, detail="No poster for player")
    return poster, eid


@router.get("/api/posters", response_model=List[PosterPublic])
async def list_posters(
    request: Request,
    event_id: str | None = Query(
        default=None,
        description="Panel-known active event when GBN→MCS cannot resolve one",
    ),
    include_legacy: bool = Query(
        default=False,
        description="If true and no active event, list pre-event global posters.json",
    ),
) -> List[PosterPublic]:
    """List posters for the active Event (not the legacy global store).

    ``/poster-cycle`` and Registration thumbs depend on this staying
    event-scoped so AlleycatTV does not rotate old flat ``data/posters.json``.
    """
    out: List[PosterPublic] = []
    active = await _resolve_event_id(event_id)
    stores = _event_stores(request)
    if active:
        for poster in stores.for_event(active).list():
            display = await _apply_live_overlay(poster.model_copy(deep=True))
            out.append(_to_public(display, request, event_id=active))
        return out
    if include_legacy:
        for poster in stores.legacy.list():
            display = await _apply_live_overlay(poster.model_copy(deep=True))
            out.append(_to_public(display, request, event_id=None))
    return out


@router.get("/api/posters/by-player/{player_id}", response_model=PosterPublic)
async def get_poster_by_player(
    player_id: str,
    request: Request,
    event_id: str | None = Query(default=None),
) -> PosterPublic:
    poster, eid = await _resolve_poster_for_player(
        request, player_id, event_id=event_id
    )
    display = await _apply_live_overlay(poster.model_copy(deep=True))
    return _to_public(display, request, event_id=eid)


@router.get("/api/posters/{poster_id}", response_model=PosterPublic)
async def get_poster(
    poster_id: str,
    request: Request,
    event_id: str | None = Query(default=None),
) -> PosterPublic:
    if poster_id == "by-player":
        raise HTTPException(status_code=404, detail="Poster not found")
    stores = _event_stores(request)
    active = await _resolve_event_id(event_id)
    poster = None
    eid: str | None = None
    if active:
        poster = stores.for_event(active).get(poster_id)
        eid = active if poster else None
    if not poster:
        poster = stores.legacy.get(poster_id)
        eid = None
    if not poster:
        raise HTTPException(status_code=404, detail="Poster not found")
    display = await _apply_live_overlay(poster.model_copy(deep=True))
    return _to_public(display, request, event_id=eid)


@router.post("/api/posters", response_model=PosterPublic)
async def create_poster(
    request: Request,
    name: str = Form(...),
    neocorp: str = Form("freelancer"),
    faction: str = Form(""),
    role: str = Form("bounty"),
    player_id: str = Form(""),
    bounty_amount: int = Form(1_000_000),
    crimes: str = Form("[]"),
    stats: str = Form("{}"),
    flavor_text: str = Form(""),
    template_id: str = Form(""),
    headline: str = Form(""),
    subtitle: str = Form(""),
    amount_label: str = Form(""),
    list_label: str = Form(""),
    list_empty: str = Form(""),
    accent: str = Form(""),
    affiliations: str = Form("[]"),
    event_id: str = Form(""),
    video: UploadFile = File(...),
) -> PosterPublic:
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="name is required")

    pid = player_id.strip()
    if not pid:
        raise HTTPException(status_code=400, detail="player_id is required")

    filename = video.filename or "capture.webm"
    ext = Path(filename).suffix.lower() or ".webm"
    if ext not in ALLOWED_VIDEO_EXT:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video type {ext}. Allowed: {sorted(ALLOWED_VIDEO_EXT)}",
        )

    data = await video.read()
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(status_code=400, detail=f"Video exceeds {MAX_UPLOAD_MB}MB limit")
    if not data:
        raise HTTPException(status_code=400, detail="Empty video upload")

    event_id, store = await _active_store(
        request, fallback=(event_id or "").strip() or None
    )
    ensure_event_dirs(event_id)
    existing = store.get_by_player(pid)

    stamp = _now()
    if existing:
        poster_id = existing.id
        created_at = existing.created_at or stamp
        old_video = existing.video_filename
    else:
        poster_id = pid
        created_at = stamp
        old_video = ""

    video_name = video_filename_for_player(pid, ext)
    dest = video_filesystem_path(video_name, event_id=event_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    if old_video and old_video != video_name:
        _delete_video(old_video, event_id=event_id)
    _delete_other_player_videos(pid, video_name, event_id=event_id)

    normalized_role = _normalize_role(role)
    chrome = _resolve_chrome(
        request,
        role=normalized_role,
        template_id=template_id,
        headline=headline,
        subtitle=subtitle,
        amount_label=amount_label,
        list_label=list_label,
        list_empty=list_empty,
        accent=accent,
    )

    record = PosterRecord(
        id=poster_id,
        player_id=pid,
        name=clean_name,
        role=normalized_role,
        neocorp=_normalize_neocorp(neocorp),
        faction=faction.strip(),
        affiliations=_parse_affiliations_snap(affiliations),
        bounty_amount=max(0, int(bounty_amount)),
        crimes=_parse_crimes(crimes),
        stats=_parse_stats(stats),
        status=existing.status if existing else PosterStatus(),
        flavor_text=flavor_text.strip(),
        video_filename=video_name,
        template_id=chrome["template_id"],
        headline=chrome["headline"],
        subtitle=chrome["subtitle"],
        amount_label=chrome["amount_label"],
        list_label=chrome["list_label"],
        list_empty=chrome["list_empty"],
        accent=chrome["accent"],
        created_at=created_at,
        updated_at=stamp,
    )
    store.save(record)
    action = "Updated" if existing else "Created"
    _LOGGER.info(
        "%s poster %s for %s event=%s (%s/%s)",
        action,
        poster_id,
        clean_name,
        event_id,
        record.role,
        record.neocorp,
    )
    return _to_public(record, request, event_id=event_id)


@router.get("/poster-cycle")
async def poster_cycle_page(
    request: Request,
    interval: int = Query(30, ge=5, le=300),
):
    """Kiosk page that rotates every made poster (default 30s)."""
    return templates.TemplateResponse(
        request,
        "poster-cycle.html",
        {
            "public_base": public_base_for(request),
            "interval_sec": interval,
        },
    )


@router.get("/poster/player/{player_id}")
async def poster_page_by_player(player_id: str, request: Request):
    poster, eid = await _resolve_poster_for_player(request, player_id)
    return await _render_poster(request, poster, event_id=eid)


@router.get("/poster/{poster_id}")
async def poster_page(poster_id: str, request: Request):
    stores = _event_stores(request)
    active = await resolve_active_event_id()
    by_player = None
    eid: str | None = None
    if active:
        by_player = stores.for_event(active).get_by_player(poster_id)
        eid = active if by_player else None
    if not by_player:
        by_player = stores.legacy.get_by_player(poster_id)
        eid = None
    if by_player:
        return await _render_poster(request, by_player, event_id=eid)

    poster = None
    if active:
        poster = stores.for_event(active).get(poster_id)
        eid = active if poster else None
    if not poster:
        poster = stores.legacy.get(poster_id)
        eid = None
    if not poster:
        raise HTTPException(status_code=404, detail="Poster not found")

    if poster.player_id and poster.player_id != poster_id:
        return RedirectResponse(
            url=f"/poster/player/{poster.player_id}",
            status_code=302,
        )

    return await _render_poster(request, poster, event_id=eid)
