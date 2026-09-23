"""HTTP client for the Central Server.

Master Control Server is the only process that opens a Central socket.
Primary URL is tried first; if it fails or is empty, falls back to secondary.
Both URLs are pushed from Home Assistant via POST /config — MCS never reads
them from env at runtime after the first HA push.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)


def _players_url(base_or_full: str) -> str:
    """Build the Central players URL.

    Accepts either a service base (``https://host``) or a full players endpoint
    (``https://host/players``) so Core Configurator values are not doubled to
    ``/players/players``.
    """
    base = base_or_full.rstrip("/")
    if base.endswith("/players"):
        return base
    return base + "/players"


async def _fetch_json(url: str) -> Any | None:
    """GET url, return parsed JSON or None on any error."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("central_client: %s failed: %s", url, exc)
        return None


async def fetch_players(primary_url: str, secondary_url: str) -> list[dict]:
    """Return the raw player list from Central Server.

    Tries primary_url first. Falls back to secondary_url if primary is empty
    or unreachable. Returns an empty list when both fail.
    """
    for url in (primary_url, secondary_url):
        if not url:
            continue
        data = await _fetch_json(_players_url(url))
        if data is not None:
            # Central may return a list directly or a wrapped dict
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "players" in data:
                return data["players"]
            _LOGGER.warning("central_client: unexpected shape from %s", url)
    _LOGGER.warning(
        "central_client: both Central URLs failed or empty — returning empty roster"
    )
    return []
