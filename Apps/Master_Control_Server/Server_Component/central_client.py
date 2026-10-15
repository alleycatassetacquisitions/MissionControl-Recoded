"""HTTP client for the Central Server.

Master Control Server is the only process that opens a Central socket.
Primary URL is tried first; if it fails or is empty, falls back to secondary.
Both URLs are pushed from Home Assistant via POST /config — MCS never reads
them from env at runtime after the first HA push.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import httpx

from player_normalize import normalize_player

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(10.0)

# Stable readiness signals for stubbed Central routes
EVENTS_LIST_NOT_READY = "Event list not available; waiting on Central GET /events"
EVENTS_ACTIVE_NOT_READY = (
    "Active event lookup not available; waiting on Central GET /events/active"
)
PLAYER_UPDATE_NOT_READY = (
    "Player update not available; waiting on Central PATCH/PUT /players/{id}"
)
PLAYER_DELETE_NOT_READY = (
    "Player delete not available; waiting on Central DELETE /players/{id}"
)


def _service_base(base_or_full: str) -> str:
    """Normalize a Central base URL (strip trailing slash / accidental /players)."""
    base = base_or_full.rstrip("/")
    if base.endswith("/players"):
        return base[: -len("/players")]
    return base


def _players_url(base_or_full: str) -> str:
    """Build the Central players collection URL.

    Accepts either a service base (``https://host``) or a full players endpoint
    (``https://host/players``) so Core Configurator values are not doubled to
    ``/players/players``.
    """
    return _service_base(base_or_full) + "/players"


def _player_url(base_or_full: str, player_id: str) -> str:
    return f"{_players_url(base_or_full).rstrip('/')}/{player_id}"


def _events_url(base_or_full: str) -> str:
    return _service_base(base_or_full) + "/events"


def _event_url(base_or_full: str, event_id: str) -> str:
    return f"{_events_url(base_or_full).rstrip('/')}/{event_id}"


def _event_active_url(base_or_full: str, event_id: str) -> str:
    return f"{_event_url(base_or_full, event_id)}/active"


def _device_logs_url(base_or_full: str) -> str:
    return _service_base(base_or_full) + "/device-logs"


def _iter_central_bases(primary_url: str, secondary_url: str) -> list[str]:
    return [u for u in (primary_url, secondary_url) if u]


def _parse_body(resp: httpx.Response) -> Any | None:
    """Parse JSON when present; otherwise return stripped text (409 plain)."""
    content_type = (resp.headers.get("content-type") or "").lower()
    if "application/json" in content_type:
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            pass
    text = (resp.text or "").strip()
    if not text:
        return None
    if text[:1] in "{[":
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return text
    return text


async def _fetch_json(url: str, *, params: dict[str, Any] | None = None) -> Any | None:
    """GET url, return parsed JSON or None on any error."""
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("central_client: %s failed: %s", url, exc)
        return None


async def _request(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
) -> tuple[int, Any | None]:
    """Perform a request against Central. Returns (status, body or None).

    ``status`` is 0 when the transport fails entirely.
    """
    headers: dict[str, str] = {}
    content: bytes | None = None
    json_payload = json_body
    if form_body is not None:
        content = urlencode(form_body).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        json_payload = None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                method.upper(),
                url,
                json=json_payload,
                content=content,
                headers=headers or None,
                params=params,
            )
            return resp.status_code, _parse_body(resp)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("central_client: %s %s failed: %s", method.upper(), url, exc)
        return 0, None


async def _request_json(
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
) -> tuple[int, Any | None]:
    """Back-compat wrapper — JSON write."""
    return await _request(method, url, json_body=json_body)


def _detail_from_body(body: Any | None) -> str | None:
    if body is None:
        return None
    if isinstance(body, str):
        return body or None
    if isinstance(body, dict):
        for key in ("detail", "message", "error"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return None


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


async def fetch_players_page(
    primary_url: str,
    secondary_url: str,
    *,
    page: int | None = None,
    per_page: int | None = None,
) -> tuple[list[dict], dict[str, int] | None]:
    """Return (players, pagination) from one Central page.

    Falls back across primary/secondary. Returns ([], None) when both fail.
    """
    params: dict[str, Any] = {}
    if page is not None:
        params["page"] = page
    if per_page is not None:
        params["per_page"] = per_page

    for url in _iter_central_bases(primary_url, secondary_url):
        data = await _fetch_json(_players_url(url), params=params or None)
        if data is None:
            continue
        if isinstance(data, list):
            return data, None
        if isinstance(data, dict) and "players" in data:
            players = data["players"] if isinstance(data["players"], list) else []
            pagination = data.get("pagination")
            page_meta: dict[str, int] | None = None
            if isinstance(pagination, dict):
                page_meta = {
                    "page": int(pagination.get("page", page or 1)),
                    "per_page": int(pagination.get("per_page", per_page or 20)),
                }
            return players, page_meta
        _LOGGER.warning("central_client: unexpected players shape from %s", url)
    _LOGGER.warning(
        "central_client: both Central URLs failed or empty — returning empty roster"
    )
    return [], None


async def fetch_players(primary_url: str, secondary_url: str) -> list[dict]:
    """Return the raw player list from Central (all pages, up to per_page=100)."""
    players, _pagination = await fetch_all_players(primary_url, secondary_url)
    return players


async def fetch_all_players(
    primary_url: str,
    secondary_url: str,
    *,
    per_page: int = 100,
) -> tuple[list[dict], dict[str, int] | None]:
    """Fetch every page from Central and concatenate players."""
    all_players: list[dict] = []
    page = 1
    last_pagination: dict[str, int] | None = None
    while True:
        batch, pagination = await fetch_players_page(
            primary_url, secondary_url, page=page, per_page=per_page
        )
        if pagination is None and page == 1 and not batch:
            # Transport failure or empty with no meta
            if page == 1:
                return [], None
        last_pagination = pagination
        all_players.extend(batch)
        if not batch:
            break
        if pagination is None:
            break
        if len(batch) < pagination.get("per_page", per_page):
            break
        page += 1
        if page > 1000:  # safety cap
            _LOGGER.warning("central_client: player page safety cap reached")
            break
    return all_players, last_pagination


async def fetch_normalized_players(
    primary_url: str,
    secondary_url: str,
    *,
    page: int | None = None,
    per_page: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int] | None]:
    """Fetch Central roster and map each record to canonical Player fields.

    When ``page`` / ``per_page`` are omitted, all pages are fetched so HA
    coordinators that expect a full roster keep working.
    """
    if page is not None or per_page is not None:
        raw, pagination = await fetch_players_page(
            primary_url,
            secondary_url,
            page=page if page is not None else 1,
            per_page=per_page if per_page is not None else 20,
        )
    else:
        raw, pagination = await fetch_all_players(primary_url, secondary_url)

    players: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            players.append(normalize_player(item))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("central_client: skipping malformed player: %s", exc)
    return players, pagination


async def create_player(
    primary_url: str,
    secondary_url: str,
    form: dict[str, str],
) -> tuple[int, Any | None]:
    """POST a new player to Central as form-urlencoded. Tries primary then secondary."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "POST", _players_url(base), form_body=form
        )
        last_status, last_body = status, resp_body
        # Retry only on transport failure / 5xx
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def update_player(
    primary_url: str,
    secondary_url: str,
    player_id: str,
    body: dict[str, Any],
) -> tuple[int, Any | None]:
    """PUT player update to Central (unused while MCS returns 501)."""
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
    """DELETE player on Central (unused while MCS returns 501)."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request("DELETE", _player_url(base, player_id))
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def create_event(
    primary_url: str,
    secondary_url: str,
    body: dict[str, Any],
) -> tuple[int, Any | None]:
    """POST /events → Central."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "POST", _events_url(base), json_body=body
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def update_event(
    primary_url: str,
    secondary_url: str,
    event_id: str,
    body: dict[str, Any],
) -> tuple[int, Any | None]:
    """PATCH /events/{id} → Central."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "PATCH", _event_url(base, event_id), json_body=body
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def set_active_event(
    primary_url: str,
    secondary_url: str,
    event_id: str,
) -> tuple[int, Any | None]:
    """PUT /events/{id}/active → Central (204)."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "PUT", _event_active_url(base, event_id)
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def list_events(
    primary_url: str,
    secondary_url: str,
) -> tuple[int, Any | None]:
    """GET /events — not live on Central yet; callers should stub with 501.

    Implemented so wiring is ready when Central notifies.
    """
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request("GET", _events_url(base))
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


async def get_active_event(
    primary_url: str,
    secondary_url: str,
) -> tuple[int, Any | None]:
    """GET /events/active — not live on Central yet."""
    last_status = 0
    last_body: Any | None = None
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "GET", _events_url(base) + "/active"
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


# ---------------------------------------------------------------------------
# Device logs
# ---------------------------------------------------------------------------


async def fetch_device_logs(
    primary_url: str,
    secondary_url: str,
    *,
    page: int = 1,
    per_page: int = 20,
) -> tuple[int, Any | None]:
    """GET /device-logs?page&per_page → Central."""
    last_status = 0
    last_body: Any | None = None
    params = {"page": page, "per_page": per_page}
    for base in _iter_central_bases(primary_url, secondary_url):
        status, resp_body = await _request(
            "GET", _device_logs_url(base), params=params
        )
        last_status, last_body = status, resp_body
        if status and status < 500:
            return status, resp_body
    return last_status, last_body


# Re-export detail helper for main.py
detail_from_body = _detail_from_body
