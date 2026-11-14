"""Tests for Game Master event services (Phase 1c — moved from Registration).

create_event / update_event / set_active_event

All HTTP is mocked — no live MCS needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.game_master.const import DOMAIN

TOKEN = "gm-token"


def _mock_response(json_data=None, status: int = 200, text: str | None = None):
    import json as _json

    resp = AsyncMock()
    resp.status = status
    resp.release = AsyncMock()
    if text is not None:
        resp.text = AsyncMock(return_value=text)
        resp.json = AsyncMock(side_effect=Exception("not json"))
    elif json_data is not None:
        raw = _json.dumps(json_data)
        resp.text = AsyncMock(return_value=raw)
        resp.json = AsyncMock(return_value=json_data)
    else:
        resp.text = AsyncMock(return_value="")
        resp.json = AsyncMock(return_value=None)
    return resp


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.game_master.affiliations.async_request",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.game_master.events.restore_active_to_mcs",
            new=AsyncMock(),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.asyncio
async def test_create_event_calls_mcs(hass: HomeAssistant, loaded_entry):
    created = {
        "id": "e1",
        "name": "Night Run",
        "venue_name": "Hall",
        "created_at": "2026-01-01T00:00:00Z",
    }

    async def _side_effect(_hass, _key, method, path, **kwargs):
        if method == "POST":
            return _mock_response(created, 201)
        return _mock_response(None, 204)

    with (
        patch("custom_components.game_master._mcs_token", return_value=TOKEN),
        patch(
            "custom_components.game_master.async_request",
            new=AsyncMock(side_effect=_side_effect),
        ) as mock_req,
        patch(
            "custom_components.game_master.events.push_active_event_to_gbn",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.game_master.affiliations.async_request",
            new=AsyncMock(return_value=_mock_response([], 200)),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "create_event",
            {"name": "Night Run", "venue_name": "Hall", "set_active": True},
            blocking=True,
        )
        await hass.async_block_till_done()

    methods_paths = [(c.args[2], c.args[3]) for c in mock_req.await_args_list]
    assert ("POST", "/events") in methods_paths
    assert ("PUT", "/events/e1/active") in methods_paths
    put_call = next(c for c in mock_req.await_args_list if c.args[2] == "PUT")
    assert put_call.kwargs.get("json") == {"name": "Night Run", "venue_name": "Hall"}
    # Event should be in Game Master's cache
    from custom_components.game_master.events import event_cache
    cache = event_cache(hass)
    assert cache["e1"]["name"] == "Night Run"
    assert hass.data[DOMAIN]["active_event_id"] == "e1"


@pytest.mark.asyncio
async def test_set_active_event_calls_mcs(hass: HomeAssistant, loaded_entry):
    from custom_components.game_master.events import event_cache

    event_cache(hass)["e9"] = {
        "id": "e9",
        "name": "Test Event 2027",
        "venue_name": None,
        "created_at": "",
    }
    with (
        patch("custom_components.game_master._mcs_token", return_value=TOKEN),
        patch(
            "custom_components.game_master.async_request",
            new=AsyncMock(return_value=_mock_response(None, 204)),
        ) as mock_req,
        patch(
            "custom_components.game_master.events.push_active_event_to_gbn",
            new=AsyncMock(),
        ) as mock_gbn,
        patch(
            "custom_components.game_master.affiliations.async_request",
            new=AsyncMock(return_value=_mock_response([], 200)),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "set_active_event",
            {"event_id": "e9"},
            blocking=True,
        )
        await hass.async_block_till_done()

    # MCS set-active PUT
    assert mock_req.await_count >= 1
    mcs_call = mock_req.await_args_list[0]
    assert mcs_call.args[2] == "PUT"
    assert mcs_call.args[3] == "/events/e9/active"
    assert mcs_call.kwargs.get("json") == {"name": "Test Event 2027"}
    # GBN push called
    mock_gbn.assert_awaited_once()
    gbn_args = mock_gbn.await_args
    assert gbn_args.args[1] == "e9"
    assert gbn_args.args[2] == "Test Event 2027"
    # active_event_id persisted
    assert hass.data[DOMAIN]["active_event_id"] == "e9"
