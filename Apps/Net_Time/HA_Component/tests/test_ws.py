"""Websocket handler unit tests for Net Time (mocked HTTP)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.net_time import (
    handle_health,
    handle_set_timezone,
    handle_status,
    handle_sync,
)
from custom_components.net_time.const import KEY_NET_TIME


class _FakeResponse:
    def __init__(self, status: int, payload):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return str(self._payload)


@pytest.fixture
def hass():
    return MagicMock()


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.mark.asyncio
async def test_ws_health_ok(hass, connection):
    resp = _FakeResponse(200, {"status": "ok", "service": "net_time"})
    with patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(return_value=resp),
    ) as req:
        await handle_health(hass, connection, {"id": 1, "type": "net_time/health"})
    req.assert_awaited_once()
    assert req.await_args.args[1] == KEY_NET_TIME
    connection.send_result.assert_called_once()
    payload = connection.send_result.call_args.args[1]
    assert payload["online"] is True


@pytest.mark.asyncio
async def test_ws_health_unreachable(hass, connection):
    with patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(return_value=None),
    ):
        await handle_health(hass, connection, {"id": 2, "type": "net_time/health"})
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == "net_time_unreachable"


@pytest.mark.asyncio
async def test_ws_status_needs_token(hass, connection):
    with patch(
        "custom_components.net_time._net_time_token", return_value=""
    ), patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(),
    ) as req:
        await handle_status(hass, connection, {"id": 3, "type": "net_time/status"})
    req.assert_not_called()
    connection.send_error.assert_called_once()
    assert connection.send_error.call_args.args[1] == "net_time_token"


@pytest.mark.asyncio
async def test_ws_status_ok(hass, connection):
    body = {
        "iso": "2026-10-18T21:00:00Z",
        "unix": 1.0,
        "public_ntp": "unavailable",
        "serving": True,
        "stratum": 10,
        "reference": "LOCAL",
        "sources": [],
    }
    resp = _FakeResponse(200, body)
    with patch(
        "custom_components.net_time._net_time_token", return_value="tok"
    ), patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(return_value=resp),
    ):
        await handle_status(hass, connection, {"id": 4, "type": "net_time/status"})
    connection.send_result.assert_called_once_with(4, body)


@pytest.mark.asyncio
async def test_ws_sync_posts_iso(hass, connection):
    body = {
        "applied_iso": "2026-10-18T21:00:00Z",
        "status": {"public_ntp": "unavailable"},
    }
    resp = _FakeResponse(200, body)
    with patch(
        "custom_components.net_time._net_time_token", return_value="tok"
    ), patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(return_value=resp),
    ) as req:
        await handle_sync(
            hass,
            connection,
            {
                "id": 5,
                "type": "net_time/sync",
                "iso8601": "2026-10-18T21:00:00.000Z",
            },
        )
    assert req.await_args.kwargs["json"] == {
        "iso8601": "2026-10-18T21:00:00.000Z"
    }
    connection.send_result.assert_called_once_with(5, body)


@pytest.mark.asyncio
async def test_ws_set_timezone(hass, connection):
    body = {"timezone": "America/Chicago", "status": {"public_ntp": "reachable"}}
    resp = _FakeResponse(200, body)
    with patch(
        "custom_components.net_time._net_time_token", return_value="tok"
    ), patch(
        "custom_components.net_time.async_request",
        new=AsyncMock(return_value=resp),
    ) as req:
        await handle_set_timezone(
            hass,
            connection,
            {
                "id": 6,
                "type": "net_time/set_timezone",
                "timezone": "America/Chicago",
            },
        )
    assert req.await_args.kwargs["json"] == {"timezone": "America/Chicago"}
    connection.send_result.assert_called_once_with(6, body)
