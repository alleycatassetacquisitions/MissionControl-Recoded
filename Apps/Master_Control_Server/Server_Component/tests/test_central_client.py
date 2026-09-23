"""Tests for central_client.fetch_players.

All HTTP calls are mocked — no live network access in CI.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from central_client import fetch_players


def _mock_response(json_data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock(
        side_effect=None if status_code < 400 else Exception(f"HTTP {status_code}")
    )
    return resp


def _patch_httpx(response=None, raise_exc=None):
    """Patch httpx.AsyncClient to return a mock response."""
    mock_client = MagicMock()
    if raise_exc:
        mock_client.get = AsyncMock(side_effect=raise_exc)
    else:
        mock_client.get = AsyncMock(return_value=response)
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    return patch("central_client.httpx.AsyncClient", return_value=mock_cm)


SAMPLE_PLAYERS = [{"id": "p1", "name": "Alice", "role": "hunter"}]


@pytest.mark.asyncio
async def test_returns_players_from_primary(monkeypatch):
    with _patch_httpx(_mock_response(SAMPLE_PLAYERS)):
        result = await fetch_players("http://primary.example.com", "")
    assert len(result) == 1
    assert result[0]["id"] == "p1"


@pytest.mark.asyncio
async def test_falls_back_to_secondary_when_primary_fails(monkeypatch):
    call_count = 0

    async def side_effect(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("primary down")
        return _mock_response(SAMPLE_PLAYERS)

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
    with _patch_httpx(raise_exc=Exception("network error")):
        result = await fetch_players(
            "http://primary.example.com", "http://secondary.example.com"
        )
    assert result == []


@pytest.mark.asyncio
async def test_skips_empty_primary_url():
    """Empty primary URL is skipped; secondary is tried directly."""
    with _patch_httpx(_mock_response(SAMPLE_PLAYERS)):
        result = await fetch_players("", "http://secondary.example.com")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_returns_empty_when_both_urls_empty():
    result = await fetch_players("", "")
    assert result == []


@pytest.mark.asyncio
async def test_handles_wrapped_response():
    """Central may return {players: [...]} instead of a bare list."""
    wrapped = {"players": SAMPLE_PLAYERS, "total": 1}
    with _patch_httpx(_mock_response(wrapped)):
        result = await fetch_players("http://primary.example.com", "")
    assert len(result) == 1
