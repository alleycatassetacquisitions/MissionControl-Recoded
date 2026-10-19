"""Unit-level tests for BGC helpers that do not need the HA fixture."""
from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.broadcast_group_controller.const import (
    DOMAIN,
    KIND_DOMAIN,
    KIND_TV,
    SERVICE_REMOVE_DEVICE,
    SERVICE_SET_BROADCAST_GROUP,
    SUPPORTED_KINDS,
)

bgc_mod = importlib.import_module(
    "custom_components.broadcast_group_controller"
)


def test_store_key():
    assert bgc_mod._store_key("tv", "pi-01") == "tv:pi-01"


def test_constants():
    assert DOMAIN == "broadcast_group_controller"
    assert KIND_TV in SUPPORTED_KINDS
    assert KIND_DOMAIN["tv"] == "alleycattv"
    assert SERVICE_SET_BROADCAST_GROUP == "set_broadcast_group"
    assert SERVICE_REMOVE_DEVICE == "remove_device"


def test_publish_membership_uses_retain_true():
    async def _run():
        hass = MagicMock()
        mock_publish = AsyncMock()
        with patch.object(bgc_mod, "async_publish", mock_publish):
            await bgc_mod._publish_membership(hass, "tv", "pi-01", "lobby")

        mock_publish.assert_awaited_once()
        kwargs = mock_publish.await_args.kwargs
        assert kwargs["retain"] is True
        assert kwargs["qos"] == 1
        body = json.loads(kwargs["payload"].decode("utf-8"))
        assert body["broadcast_group_id"] == "lobby"
        assert mock_publish.await_args.args[1:] == (
            "tv",
            "cmd",
            "device",
            "pi-01",
            "membership",
        )

    asyncio.run(_run())


def test_publish_membership_clear_retains_null():
    async def _run():
        hass = MagicMock()
        mock_publish = AsyncMock()
        with patch.object(bgc_mod, "async_publish", mock_publish):
            await bgc_mod._publish_membership(hass, "tv", "pi-01", "")

        body = json.loads(mock_publish.await_args.kwargs["payload"].decode("utf-8"))
        assert body["broadcast_group_id"] is None
        assert mock_publish.await_args.kwargs["retain"] is True

    asyncio.run(_run())


def test_republish_stored_membership_skips_when_empty():
    async def _run():
        hass = MagicMock()
        hass.data = {DOMAIN: {"membership": {}}}
        with patch.object(bgc_mod, "_publish_membership", new=AsyncMock()) as mock_pub:
            await bgc_mod._republish_stored_membership(hass, "tv", "pi-01")
        mock_pub.assert_not_awaited()

    asyncio.run(_run())


def test_republish_stored_membership_publishes_group():
    async def _run():
        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "membership": {
                    "tv:pi-01": {
                        "kind": "tv",
                        "device_id": "pi-01",
                        "broadcast_group_id": "lobby",
                    }
                }
            }
        }
        with patch.object(bgc_mod, "_publish_membership", new=AsyncMock()) as mock_pub:
            await bgc_mod._republish_stored_membership(hass, "tv", "pi-01")
        mock_pub.assert_awaited_once_with(hass, "tv", "pi-01", "lobby")

    asyncio.run(_run())


def test_presence_online_triggers_republish():
    async def _run():
        hass = MagicMock()
        hass.data = {DOMAIN: {}}
        hass.async_create_task = MagicMock()

        captured = {}

        async def fake_subscribe(hass_arg, kind, *segments, callback=None, qos=0):
            captured[kind] = callback
            return MagicMock(name=f"unsub-{kind}")

        with (
            patch.object(bgc_mod, "async_subscribe", side_effect=fake_subscribe),
            patch.object(
                bgc_mod,
                "device_id_from_status_topic",
                side_effect=lambda kind, topic: (
                    "pi-01" if topic.endswith("/pi-01") else None
                ),
            ),
            patch.object(
                bgc_mod,
                "parse_presence_payload",
                side_effect=lambda payload: str(payload),
            ),
            patch.object(bgc_mod, "PRESENCE_ONLINE", "online"),
        ):
            await bgc_mod._start_presence_republish(hass)

        assert "tv" in captured
        assert "dnn" in captured

        captured["tv"](
            SimpleNamespace(topic="mc/tv/status/pi-01", payload="online")
        )
        assert hass.async_create_task.call_count == 1

        captured["tv"](
            SimpleNamespace(topic="mc/tv/status/pi-01", payload="online")
        )
        assert hass.async_create_task.call_count == 1

        captured["tv"](
            SimpleNamespace(topic="mc/tv/status/pi-01", payload="offline")
        )
        captured["tv"](
            SimpleNamespace(topic="mc/tv/status/pi-01", payload="online")
        )
        assert hass.async_create_task.call_count == 2

    asyncio.run(_run())


def test_remove_fabric_device_refuses_online():
    async def _run():
        hass = MagicMock()
        hass.data = {DOMAIN: {"membership": {}}}
        tracker = MagicMock()
        tracked = MagicMock()
        tracked.presence = "online"
        tracker.devices = {"pi-01": tracked}
        with (
            patch.object(bgc_mod, "get_presence_tracker", return_value=tracker),
            patch.object(bgc_mod, "PRESENCE_ONLINE", "online"),
        ):
            with pytest.raises(HomeAssistantError, match="online"):
                await bgc_mod.async_remove_fabric_device(hass, "tv", "pi-01")

    asyncio.run(_run())


def test_list_broadcast_groups_merges_content_and_membership():
    async def _run():
        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "membership": {
                    "tv:pi-01": {
                        "kind": "tv",
                        "device_id": "pi-01",
                        "broadcast_group_id": "orphan",
                    }
                }
            }
        }

        class _Resp:
            status = 200

            async def json(self):
                return [
                    {"broadcast_group_id": "lobby", "name": "Lobby"},
                    {"zone_id": "bar", "name": "Bar"},
                ]

        mock_request = AsyncMock(return_value=_Resp())
        with patch.dict(
            "sys.modules",
            {
                "custom_components.shared_libraries.http": SimpleNamespace(
                    async_request=mock_request
                )
            },
        ):
            groups = await bgc_mod._list_broadcast_groups(hass)

        ids = [g["broadcast_group_id"] for g in groups]
        assert ids == ["bar", "lobby", "orphan"]
        assert groups[1]["name"] == "Lobby"
        assert groups[2]["source"] == "membership"
        mock_request.assert_awaited_once_with(
            hass, "alleycattv", "GET", "/api/broadcast_groups/"
        )

    asyncio.run(_run())


def test_remove_fabric_device_clears_membership_and_forgets():
    async def _run():
        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "membership": {
                    "tv:pi-old": {
                        "kind": "tv",
                        "device_id": "pi-old",
                        "broadcast_group_id": "lobby",
                    }
                },
                "last_presence": {("tv", "pi-old"): "offline"},
                "store": AsyncMock(),
            },
            "alleycattv": {
                "devices": {"pi-old": {"pi_id": "pi-old"}},
                "device_meta": {"pi-old": {"area_id": "kitchen"}},
                "store": AsyncMock(),
            },
        }
        tracker = MagicMock()
        tracked = MagicMock()
        tracked.presence = "offline"
        tracker.devices = {"pi-old": tracked}
        tracker.async_forget_device = AsyncMock(return_value=True)

        with (
            patch.object(bgc_mod, "get_presence_tracker", return_value=tracker),
            patch.object(bgc_mod, "PRESENCE_ONLINE", "online"),
            patch.object(
                bgc_mod, "_clear_retained_membership", new=AsyncMock()
            ) as mock_clear,
            patch(
                "homeassistant.helpers.dispatcher.async_dispatcher_send"
            ) as mock_dispatch,
        ):
            await bgc_mod.async_remove_fabric_device(hass, "tv", "pi-old")

        assert "tv:pi-old" not in hass.data[DOMAIN]["membership"]
        assert ("tv", "pi-old") not in hass.data[DOMAIN]["last_presence"]
        mock_clear.assert_awaited_once_with(hass, "tv", "pi-old")
        tracker.async_forget_device.assert_awaited_once_with("pi-old")
        assert "pi-old" not in hass.data["alleycattv"]["devices"]
        assert "pi-old" not in hass.data["alleycattv"]["device_meta"]
        mock_dispatch.assert_called_once_with(
            hass, "alleycattv_device_removed", "pi-old"
        )
        hass.data[DOMAIN]["store"].async_save.assert_awaited()

    asyncio.run(_run())
