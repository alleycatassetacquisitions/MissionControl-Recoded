"""Tests for Registration HA services.

sync_now / register_player / events / update&delete 501 path

All HTTP is mocked — no live MCS needed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.registration.const import DOMAIN

TOKEN = "svc-token"
MOCK_ROSTER = {
    "count": 1,
    "players": [
        {
            "id": "p1",
            "name": "Alice",
            "pdn_code": "1234",
            "mode": "hunter",
            "role": "hunter",
            "created_at": "2026-01-01T00:00:00Z",
            "email": "a@example.com",
        }
    ],
}


def _mock_response(json_data=None, status: int = 200, text: str | None = None):
    import json as _json

    resp = AsyncMock()
    resp.status = status
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
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration._push_central_config",
            new=AsyncMock(),
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


@pytest.mark.asyncio
async def test_sync_now_triggers_coordinator_refresh(
    hass: HomeAssistant, loaded_entry
):
    with (
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ) as mock_req,
        patch(
            "custom_components.registration._push_central_config",
            new=AsyncMock(),
        ),
    ):
        await hass.services.async_call(DOMAIN, "sync_now", {}, blocking=True)
        await hass.async_block_till_done()

    mock_req.assert_called()


@pytest.mark.asyncio
async def test_register_player_calls_mcs_post(hass: HomeAssistant, loaded_entry):
    """register_player POSTs name + email only."""
    with (
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(return_value=_mock_response({}, 201)),
        ) as mock_post,
    ):
        await hass.services.async_call(
            DOMAIN,
            "register_player",
            {"name": "New Player", "email": "n@example.com"},
            blocking=True,
        )
        await hass.async_block_till_done()

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[2] == "POST"
    assert args[3] == "/players"
    assert kwargs.get("token") == TOKEN
    body = kwargs.get("json", {})
    assert body == {"name": "New Player", "email": "n@example.com"}
    assert "role" not in body
    assert "neocorp" not in body


@pytest.mark.asyncio
async def test_register_player_surfaces_409(hass: HomeAssistant, loaded_entry):
    with (
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(
                return_value=_mock_response(
                    None, 409, text='{"detail":"No active event"}'
                )
            ),
        ),
    ):
        with pytest.raises(HomeAssistantError, match="No active event"):
            await hass.services.async_call(
                DOMAIN,
                "register_player",
                {"name": "Alex"},
                blocking=True,
            )


@pytest.mark.asyncio
async def test_update_player_calls_mcs(hass: HomeAssistant, loaded_entry):
    updated = {
        "id": "p1",
        "name": "Alice",
        "pdn_code": "1234",
        "email": "a@example.com",
        "active": True,
    }
    with (
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(return_value=_mock_response(updated, 200)),
        ) as mock_req,
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "update_player",
            {"player_id": "p1", "name": "Alice", "email": "a@example.com"},
            blocking=True,
        )
    assert mock_req.await_args.args[2] == "PUT"
    assert mock_req.await_args.args[3] == "/players/p1"


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
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(side_effect=_side_effect),
        ) as mock_req,
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
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
    assert put_call.kwargs.get("json") == {
        "name": "Night Run",
        "venue_name": "Hall",
    }
    cache = hass.data[DOMAIN]["event_cache"]
    assert cache["e1"]["name"] == "Night Run"
    assert hass.data[DOMAIN]["active_event_id"] == "e1"


@pytest.mark.asyncio
async def test_set_active_event_calls_mcs(hass: HomeAssistant, loaded_entry):
    from custom_components.registration import _event_cache

    _event_cache(hass)["e9"] = {
        "id": "e9",
        "name": "Test Event 2027",
        "venue_name": None,
        "created_at": "",
    }
    with (
        patch(
            "custom_components.registration._mcs_token",
            return_value=TOKEN,
        ),
        patch(
            "custom_components.registration.async_request",
            new=AsyncMock(return_value=_mock_response(None, 204)),
        ) as mock_req,
        patch(
            "custom_components.registration.coordinator.async_request",
            new=AsyncMock(return_value=_mock_response(MOCK_ROSTER)),
        ),
        patch(
            "custom_components.registration.coordinator._mcs_token",
            return_value=TOKEN,
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "set_active_event",
            {"event_id": "e9"},
            blocking=True,
        )
        await hass.async_block_till_done()

    assert mock_req.call_args.args[2] == "PUT"
    assert mock_req.call_args.args[3] == "/events/e9/active"
    assert mock_req.call_args.kwargs.get("json") == {"name": "Test Event 2027"}
