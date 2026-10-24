"""Tests for central_client — players, events, game-state, device-logs.

All HTTP calls are mocked — no live network access in CI.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from central_client import (
    create_player,
    fetch_device_logs,
    fetch_game_state,
    fetch_players,
    fetch_players_page,
    list_teams,
    set_active_event,
    set_scoring,
    update_player,
)


def _mock_response(json_data=None, status_code: int = 200, text: str = ""):
    import json as _json

    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = json_data
        resp.text = _json.dumps(json_data)
    else:
        resp.headers = {}
        resp.json.side_effect = Exception("not json")
        resp.text = text
    resp.raise_for_status = MagicMock(
        side_effect=None if status_code < 400 else Exception(f"HTTP {status_code}")
    )
    return resp


def _patch_client(*, get=None, request=None, raise_exc=None):
    mock_client = MagicMock()
    if raise_exc:
        mock_client.get = AsyncMock(side_effect=raise_exc)
        mock_client.request = AsyncMock(side_effect=raise_exc)
    else:
        if get is not None:
            mock_client.get = AsyncMock(return_value=get)
        if request is not None:
            mock_client.request = AsyncMock(return_value=request)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return patch("central_client.httpx.AsyncClient", return_value=mock_cm), mock_client


SAMPLE_PLAYERS = [
    {
        "id": "p1",
        "name": "Alice",
        "pdn_code": "1234",
        "created_at": "2026-01-01T00:00:00Z",
    }
]


@pytest.mark.asyncio
async def test_returns_players_from_primary():
    patcher, _ = _patch_client(get=_mock_response(SAMPLE_PLAYERS))
    with patcher:
        result = await fetch_players("http://primary.example.com", "")
    assert len(result) == 1
    assert result[0]["id"] == "p1"


@pytest.mark.asyncio
async def test_falls_back_to_secondary_when_primary_fails():
    call_count = 0

    async def side_effect(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("primary down")
        return _mock_response(
            {"players": SAMPLE_PLAYERS, "pagination": {"page": 1, "per_page": 100}}
        )

    mock_client = MagicMock()
    mock_client.get = side_effect
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("central_client.httpx.AsyncClient", return_value=mock_cm):
        result = await fetch_players(
            "http://primary.example.com", "http://secondary.example.com"
        )
    assert len(result) == 1


@pytest.mark.asyncio
async def test_returns_empty_when_both_fail():
    patcher, _ = _patch_client(raise_exc=Exception("network error"))
    with patcher:
        result = await fetch_players(
            "http://primary.example.com", "http://secondary.example.com"
        )
    assert result == []


@pytest.mark.asyncio
async def test_skips_empty_primary_url():
    patcher, _ = _patch_client(get=_mock_response(SAMPLE_PLAYERS))
    with patcher:
        result = await fetch_players("", "http://secondary.example.com")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_returns_empty_when_both_urls_empty():
    result = await fetch_players("", "")
    assert result == []


@pytest.mark.asyncio
async def test_handles_wrapped_response_with_pagination():
    wrapped = {
        "players": SAMPLE_PLAYERS,
        "pagination": {"page": 1, "per_page": 20},
    }
    patcher, _ = _patch_client(get=_mock_response(wrapped))
    with patcher:
        players, pagination = await fetch_players_page(
            "http://primary.example.com", "", page=1, per_page=20
        )
    assert len(players) == 1
    assert pagination == {"page": 1, "per_page": 20}


@pytest.mark.asyncio
async def test_create_player_sends_json():
    created = {
        "id": "new1",
        "name": "Alex",
        "pdn_code": "0001",
        "email": "a@ex.com",
        "created_at": "2026-01-01T00:00:00Z",
        "event_id": "e1",
        "team_id": None,
        "team_name": None,
        "active": True,
    }
    patcher, mock_client = _patch_client(
        request=_mock_response(created, status_code=200)
    )
    with patcher:
        status, body = await create_player(
            "http://primary.example.com",
            "",
            {"name": "Alex", "email": "a@ex.com"},
        )
    assert status == 200
    assert body["pdn_code"] == "0001"
    kwargs = mock_client.request.await_args.kwargs
    assert kwargs["json"] == {"name": "Alex", "email": "a@ex.com"}
    assert kwargs.get("content") is None


@pytest.mark.asyncio
async def test_create_player_409_text_body():
    resp = _mock_response(None, status_code=409, text="No active event")
    resp.headers = {}
    patcher, _ = _patch_client(request=resp)
    with patcher:
        status, body = await create_player(
            "http://primary.example.com", "", {"name": "Alex"}
        )
    assert status == 409
    assert body == "No active event"


@pytest.mark.asyncio
async def test_update_player_sends_patch():
    updated = {
        "id": "p1",
        "name": "Alice",
        "pdn_code": "1234",
        "email": None,
        "created_at": "2026-01-01T00:00:00Z",
        "event_id": "e1",
        "team_id": None,
        "team_name": None,
        "active": True,
    }
    patcher, mock_client = _patch_client(
        request=_mock_response(updated, status_code=200)
    )
    with patcher:
        status, body = await update_player(
            "http://primary.example.com",
            "",
            "p1",
            {"name": "Alice", "email": None},
        )
    assert status == 200
    assert body["id"] == "p1"
    assert mock_client.request.await_args.args[0] == "PATCH"
    assert mock_client.request.await_args.args[1].endswith("/players/p1")


@pytest.mark.asyncio
async def test_set_active_event():
    patcher, mock_client = _patch_client(
        request=_mock_response(None, status_code=204, text="")
    )
    with patcher:
        status, _body = await set_active_event(
            "http://primary.example.com", "", "e1"
        )
    assert status == 204
    assert mock_client.request.await_args.args[0] == "PUT"
    assert mock_client.request.await_args.args[1].endswith("/events/e1/active")


@pytest.mark.asyncio
async def test_fetch_game_state():
    payload = {
        "active_event": {
            "id": "e1",
            "name": "Night Run",
            "venue_name": None,
            "created_at": "2026-01-01T00:00:00Z",
        },
        "scoring": {"enabled": True, "started_at": "2026-01-01T01:00:00Z"},
        "accepting_delayed_scores": True,
        "server_time_utc": "2026-01-01T02:00:00Z",
    }
    patcher, mock_client = _patch_client(
        request=_mock_response(payload, status_code=200)
    )
    with patcher:
        status, body = await fetch_game_state("http://primary.example.com", "")
    assert status == 200
    assert body["active_event"]["id"] == "e1"
    assert mock_client.request.await_args.args[1].endswith("/game-state")


@pytest.mark.asyncio
async def test_fetch_game_state_falls_through_on_primary_404():
    """Primary 404 should try secondary (bad primary must not brick the venue)."""
    secondary_payload = {
        "active_event": {
            "id": "e2",
            "name": "Backup",
            "venue_name": None,
            "created_at": "2026-01-01T00:00:00Z",
        },
        "scoring": {"enabled": False, "started_at": None},
        "accepting_delayed_scores": False,
        "server_time_utc": "2026-01-01T02:00:00Z",
    }
    call_count = 0

    async def side_effect(method, url, **kwargs):
        nonlocal call_count
        call_count += 1
        if "primary" in url:
            return _mock_response(None, status_code=404, text="not found")
        return _mock_response(secondary_payload, status_code=200)

    mock_client = MagicMock()
    mock_client.request = side_effect
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("central_client.httpx.AsyncClient", return_value=mock_cm):
        status, body = await fetch_game_state(
            "http://primary.example.com", "http://secondary.example.com"
        )
    assert call_count == 2
    assert status == 200
    assert body["active_event"]["id"] == "e2"


@pytest.mark.asyncio
async def test_set_scoring():
    patcher, mock_client = _patch_client(
        request=_mock_response(
            {"enabled": True, "started_at": "2026-01-01T01:00:00Z"},
            status_code=200,
        )
    )
    with patcher:
        status, body = await set_scoring(
            "http://primary.example.com", "", "e1", True
        )
    assert status == 200
    assert body["enabled"] is True
    assert mock_client.request.await_args.args[1].endswith("/events/e1/scoring")
    assert mock_client.request.await_args.kwargs["json"] == {"enabled": True}


@pytest.mark.asyncio
async def test_list_teams():
    teams = [{"id": "t1", "event_id": "e1", "name": "Hunter"}]
    patcher, mock_client = _patch_client(
        request=_mock_response(teams, status_code=200)
    )
    with patcher:
        status, body = await list_teams("http://primary.example.com", "", "e1")
    assert status == 200
    assert body[0]["name"] == "Hunter"
    assert mock_client.request.await_args.args[1].endswith("/events/e1/teams")


@pytest.mark.asyncio
async def test_fetch_device_logs():
    payload = {
        "device_logs": [],
        "pagination": {"page": 2, "per_page": 10},
    }
    patcher, mock_client = _patch_client(
        request=_mock_response(payload, status_code=200)
    )
    with patcher:
        status, body = await fetch_device_logs(
            "http://primary.example.com", "", page=2, per_page=10
        )
    assert status == 200
    assert body["pagination"]["page"] == 2
    assert mock_client.request.await_args.kwargs["params"] == {
        "page": 2,
        "per_page": 10,
    }
