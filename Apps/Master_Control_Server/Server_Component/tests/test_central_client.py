"""Tests for central_client — players, events, device-logs.

All HTTP calls are mocked — no live network access in CI.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from central_client import (
    create_player,
    fetch_device_logs,
    fetch_players,
    fetch_players_page,
    set_active_event,
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
        return _mock_response({"players": SAMPLE_PLAYERS, "pagination": {"page": 1, "per_page": 100}})

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
async def test_create_player_sends_form_urlencoded():
    patcher, mock_client = _patch_client(
        request=_mock_response(None, status_code=200, text="")
    )
    with patcher:
        status, body = await create_player(
            "http://primary.example.com",
            "",
            {"name": "Alex", "email": "a@ex.com"},
        )
    assert status == 200
    assert body is None
    kwargs = mock_client.request.await_args.kwargs
    assert kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert b"name=Alex" in kwargs["content"]
    assert b"email=a%40ex.com" in kwargs["content"]


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
