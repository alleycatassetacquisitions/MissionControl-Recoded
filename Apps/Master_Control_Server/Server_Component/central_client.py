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

from player_normalize import normalize_player

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)


def _players_url(base_or_full: str) -> str:
    """Build the Central players collection URL.

    Accepts either a service base (``https://host``) or a full players endpoint
    (``https://host/players``) so Core Configurator values are not doubled to
    ``/players/players``.
    """
    base = base_or_full.rstrip("/")
    if base.endswith("/players"):
        return base
    return base + "/players"


def _player_url(base_or_full: str, player_id: str) -> str:
    return f"{_players_url(base_or_full).rstrip('/')}/{player_id}"


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


async def _request_json(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any | None]:
    """Perform a write against Central. Returns (status, parsed body or None)."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(method.upper(), url, json=json_body)
            body: Any | None
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = None
            return resp.status_code, body
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("central_client: %s %s failed: %s", method.upper(), url, exc)
        return 0, None


def _iter_central_bases(primary_url: str, secondary_url: str) -> list[str]:
    return [u for u in (primary_url, secondary_url) if u]


async def fetch_players(primary_url: str, secondary_url: str) -> list[dict]:
    """Return the raw player list from Central Server.

    Tries primary_url first. Falls back to secondary_url if primary is empty
    or unreachable. Returns an empty list when both fail.
    """
    for url in _iter_central_bases(primary_url, secondary_url):
        data = await _fetch_json(_players_url(url))
        if data is not None:
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "players" in data:
                return data["players"]
            _LOGGER.warning("central_client: unexpected shape from %s", url)
    _LOGGER.warning(
        "central_client: both Central URLs failed or empty — returning empty roster"
    )
    return []


async def fetch_normalized_players(
    primary_url: str, secondary_url: str
) -> list[dict[str, Any]]:
    """Fetch Central roster and map each record to canonical Player fields."""
    raw = await fetch_players(primary_url, secondary_url)
    players: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            players.append(normalize_player(item))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("central_client: skipping malformed player: %s", exc)
    return players


async def create_player(
    primary_url: str,
    secondary_url: str,
    body: dict[str, Any],
) -> tuple[int, Any | None]:
    """POST a new player to Central. Tries primary then secondary."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request_json(
            "POST", _players_url(base), json_body=body
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def update_player(
    primary_url: str,
    secondary_url: str,
    player_id: str,
    body: dict[str, Any],
) -> tuple[int, Any | None]:
    """PUT player update to Central. Tries primary then secondary."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request_json(
            "PUT", _player_url(base, player_id), json_body=body
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def delete_player(
    primary_url: str,
    secondary_url: str,
    player_id: str,
) -> tuple[int, Any | None]:
    """DELETE player on Central. Tries primary then secondary."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request_json(
            "DELETE", _player_url(base, player_id)
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body
