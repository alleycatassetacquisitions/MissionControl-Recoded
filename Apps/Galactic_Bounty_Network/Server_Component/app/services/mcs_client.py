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
