"""MCS client — live Player overlay for posters.

Calls MCS ``GET /players`` and ``GET /players/{id}`` with
``Authorization: Bearer {GBN_MCS_TOKEN}``. Maps canonical Design Terms
fields (``neocorp``, ``role``). GBN does not expose a local ``/api/players``.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import MCS_BASE, MCS_TOKEN
from app.models import IntakePlayer, NeoCorp, PosterStatus, Role

_LOGGER = logging.getLogger(__name__)


def _auth_headers() -> dict[str, str]:
    if not MCS_TOKEN:
        return {}
    return {"Authorization": f"Bearer {MCS_TOKEN}"}


def _norm_neocorp(value: Any) -> NeoCorp:
    v = str(value or "freelancer").strip().lower()
    if v in ("reboot", "helix", "endline", "freelancer"):
        return v  # type: ignore[return-value]
    return "freelancer"


def _norm_role(raw: dict[str, Any]) -> Role:
    v = str(raw.get("role") or "").strip().lower()
    if v in ("hunter", "bounty"):
        return v  # type: ignore[return-value]
    return "bounty"


def _status_from_dict(raw: dict[str, Any]) -> PosterStatus:
    """Keep STATUS empty unless MCS returns status fields."""
    nested = raw.get("status")
    if isinstance(nested, dict):
        return PosterStatus(
            current_score=str(nested.get("current_score") or ""),
            fastest_win=str(nested.get("fastest_win") or ""),
            longest_streak=str(nested.get("longest_streak") or ""),
        )
    return PosterStatus(
        current_score=str(raw["current_score"]) if raw.get("current_score") else "",
        fastest_win=str(raw["fastest_win"]) if raw.get("fastest_win") else "",
        longest_streak=str(raw["longest_streak"]) if raw.get("longest_streak") else "",
    )


def _player_from_dict(raw: dict[str, Any]) -> IntakePlayer:
    return IntakePlayer(
        player_id=str(raw.get("id") or raw.get("player_id") or ""),
        name=str(raw.get("name") or ""),
        role=_norm_role(raw),
        neocorp=_norm_neocorp(raw.get("neocorp")),
        faction=str(raw.get("faction") or ""),
        status=_status_from_dict(raw),
    )


async def lookup_by_id(player_id: str) -> Optional[IntakePlayer]:
    """Resolve a player from MCS ``GET /players/{id}``."""
    pid = (player_id or "").strip()
    if not pid or not MCS_BASE:
        return None

    url = f"{MCS_BASE.rstrip('/')}/players/{pid}"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code == 404:
                _LOGGER.debug("MCS player %s not found", pid)
                return None
            if resp.status_code != 200:
                _LOGGER.warning("MCS GET %s -> %s", url, resp.status_code)
                return None
            data = resp.json()
            if isinstance(data, dict):
                return _player_from_dict(data)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("MCS player lookup failed (%s): %s", url, exc)
    return None


async def list_players() -> list[IntakePlayer]:
    """Fetch the full roster from MCS ``GET /players``."""
    if not MCS_BASE:
        return []

    url = f"{MCS_BASE.rstrip('/')}/players"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=_auth_headers())
            if resp.status_code != 200:
                _LOGGER.warning("MCS GET %s -> %s", url, resp.status_code)
                return []
            data = resp.json()
            if isinstance(data, dict):
                players = data.get("players") or []
                if isinstance(players, list):
                    return [
                        _player_from_dict(p) for p in players if isinstance(p, dict)
                    ]
            if isinstance(data, list):
                return [_player_from_dict(p) for p in data if isinstance(p, dict)]
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("MCS roster fetch failed (%s): %s", url, exc)
    return []


async def lookup_by_mac(mac: str) -> Optional[IntakePlayer]:
    """Resolve a PDN MAC to a registered player (not wired yet)."""
    normalized = (mac or "").strip().lower()
    if not normalized:
        return None
    if not MCS_BASE:
        _LOGGER.debug("MAC lookup skipped — GBN_MCS_BASE not set (%s)", normalized)
        return None
    _LOGGER.info("MAC lookup not implemented yet (mcs=%s mac=%s)", MCS_BASE, normalized)
    return None


def _eid_from_state(state: dict[str, Any]) -> str:
    eid = state.get("active_event_id")
    if eid is None and isinstance(state.get("event"), dict):
        eid = state["event"].get("id")
    return str(eid).strip() if eid is not None else ""


def _name_from_state(state: dict[str, Any]) -> str:
    event = state.get("event")
    if isinstance(event, dict):
        name = str(event.get("name") or "").strip()
        if name:
            return name
    return str(state.get("event_name") or "").strip()


async def get_active_event() -> Optional[dict[str, Any]]:
    """Fetch MCS ``GET /events/active``, with GBN disk cache fallback.

    Returns a dict with ``active_event_id``, optional ``event`` (id/name), and
    ``source``. When MCS is unset/unreachable, returns the last event remembered
    from a successful MCS read or the HA panel (so /poster-cycle keeps working).
    """
    from app.services.event_paths import (
        clear_cached_active_event,
        read_cached_active_event,
        remember_active_event,
    )

    if MCS_BASE:
        url = f"{MCS_BASE.rstrip('/')}/events/active"
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(url, headers=_auth_headers())
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, dict):
                        eid = _eid_from_state(data)
                        if eid:
                            remember_active_event(
                                eid,
                                _name_from_state(data),
                                source=str(data.get("source") or "mcs"),
                            )
                            return data
                        # MCS explicitly reports no active event
                        clear_cached_active_event()
                        return data
                else:
                    _LOGGER.warning("MCS GET %s -> %s", url, resp.status_code)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("MCS active event fetch failed (%s): %s", url, exc)

    cached = read_cached_active_event()
    if cached:
        _LOGGER.info(
            "Using cached active event %s (MCS unset/unreachable)",
            cached.get("active_event_id"),
        )
        return cached
    return None


async def resolve_active_event_id() -> Optional[str]:
    """Return the active event id string, or None."""
    state = await get_active_event()
    if not state:
        return None
    return _eid_from_state(state) or None
