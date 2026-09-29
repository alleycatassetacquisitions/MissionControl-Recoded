"""Tests for the HTTP helper (shared_libraries.http).

Groups:
  1. Fail-closed contract — returns None when no URL is configured
  2. URL assembly       — base URL + path are joined correctly
  3. Bearer auth        — Authorization header is set when token is given
  4. No-auth path       — no Authorization header when token is omitted
  5. Session errors     — network exceptions return None, never raise

Design contracts under test:
  - async_request returns None when Core Configurator has no URL for the key.
  - async_request never falls back to a hardcoded IP.
  - async_request adds Authorization: Bearer {token} only when token is given.
  - async_request uses async_get_clientsession, never a bare ClientSession.
  - Network errors return None instead of propagating.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import ClientResponse

from custom_components.shared_libraries.http import async_request


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status: int = 200) -> MagicMock:
    resp = MagicMock(spec=ClientResponse)
    resp.status = status
    return resp


def _patch_get_url(url: str):
    """Patch core_configurator.helpers.get_url to return url."""
    return patch(
        "custom_components.shared_libraries.http.get_url",
        return_value=url,
    )


def _patch_session(response=None, raise_exc=None):
    """Patch async_get_clientsession to return a mock session."""
    session = MagicMock()
    if raise_exc:
        session.request = AsyncMock(side_effect=raise_exc)
    else:
        session.request = AsyncMock(return_value=response or _mock_response())

    return patch(
        "custom_components.shared_libraries.http.async_get_clientsession",
        return_value=session,
    ), session


# ---------------------------------------------------------------------------
# 1. Fail-closed contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_none_when_no_url_configured(hass):
    """Fail-closed: async_request returns None when no URL is stored."""
    with _patch_get_url(""):
        result = await async_request(hass, "gbn", "GET", "/api/posters")
    assert result is None


@pytest.mark.asyncio
async def test_does_not_call_session_when_no_url(hass):
    """No HTTP call is made when there is no URL — fail-closed."""
    patcher, session = _patch_session()
    with _patch_get_url(""), patcher:
        await async_request(hass, "gbn", "GET", "/api/posters")
    session.request.assert_not_called()


# ---------------------------------------------------------------------------
# 2. URL assembly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_assembled_from_base_and_path(hass):
    """The full URL is base_url + path, trailing slash stripped from base."""
    patcher, session = _patch_session()
    with _patch_get_url("http://192.168.1.206:8100"), patcher:
        await async_request(hass, "gbn", "GET", "/api/posters")

    call_kwargs = session.request.call_args
    assert call_kwargs[0][1] == "http://192.168.1.206:8100/api/posters"


@pytest.mark.asyncio
async def test_trailing_slash_on_base_url_is_stripped(hass):
    """Trailing slash on the stored base URL does not produce a double slash."""
    patcher, session = _patch_session()
    with _patch_get_url("http://192.168.1.206:8100/"), patcher:
        await async_request(hass, "gbn", "GET", "/api/posters")

    call_kwargs = session.request.call_args
    assert call_kwargs[0][1] == "http://192.168.1.206:8100/api/posters"


@pytest.mark.asyncio
async def test_method_is_uppercased(hass):
    """HTTP method is normalised to upper-case."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(hass, "gbn", "get", "/ping")

    assert session.request.call_args[0][0] == "GET"


# ---------------------------------------------------------------------------
# 3. Bearer auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bearer_header_added_when_token_given(hass):
    """Authorization: Bearer header is present when token is provided."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(hass, "gbn", "GET", "/secure", token="mytoken123")

    sent_headers = session.request.call_args[1].get("headers") or {}
    assert sent_headers.get("Authorization") == "Bearer mytoken123"


@pytest.mark.asyncio
async def test_bearer_token_value_is_passed_through_unchanged(hass):
    """The token value is used verbatim in the header."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(
            hass, "gbn", "GET", "/secure",
            token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
        )

    sent_headers = session.request.call_args[1].get("headers") or {}
    assert sent_headers["Authorization"].startswith("Bearer eyJ")


# ---------------------------------------------------------------------------
# 4. No-auth path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_authorization_header_when_token_is_none(hass):
    """No Authorization header is sent when token is not provided."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(hass, "gbn", "GET", "/public")

    sent_headers = session.request.call_args[1].get("headers")
    # headers kwarg should be None (not passed) when no auth
    assert not sent_headers or "Authorization" not in sent_headers


@pytest.mark.asyncio
async def test_caller_supplied_headers_are_forwarded(hass):
    """Extra headers passed by the caller are included in the request."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(
            hass, "gbn", "GET", "/api",
            headers={"X-Custom": "value"},
        )

    sent_headers = session.request.call_args[1].get("headers") or {}
    assert sent_headers.get("X-Custom") == "value"


@pytest.mark.asyncio
async def test_caller_headers_merged_with_bearer(hass):
    """Caller headers and bearer token are both present when combined."""
    patcher, session = _patch_session()
    with _patch_get_url("http://server.local"), patcher:
        await async_request(
            hass, "gbn", "GET", "/api",
            token="tok",
            headers={"Accept": "application/json"},
        )

    sent_headers = session.request.call_args[1].get("headers") or {}
    assert sent_headers.get("Authorization") == "Bearer tok"
    assert sent_headers.get("Accept") == "application/json"


# ---------------------------------------------------------------------------
# 5. Session errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_network_error_returns_none(hass):
    """A network exception returns None instead of propagating to the caller."""
    import aiohttp

    patcher, _ = _patch_session(raise_exc=aiohttp.ClientConnectionError("timeout"))
    with _patch_get_url("http://server.local"), patcher:
        result = await async_request(hass, "gbn", "GET", "/api")

    assert result is None


@pytest.mark.asyncio
async def test_successful_response_is_returned(hass):
    """When the request succeeds the ClientResponse is returned to the caller."""
    expected = _mock_response(status=200)
    patcher, _ = _patch_session(response=expected)
    with _patch_get_url("http://server.local"), patcher:
        result = await async_request(hass, "gbn", "GET", "/api")

    assert result is expected
