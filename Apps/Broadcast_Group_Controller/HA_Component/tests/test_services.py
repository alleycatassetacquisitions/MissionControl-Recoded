"""Unit-level tests for BGC helpers that do not need the HA fixture."""
from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.broadcast_group_controller.const import (
    DOMAIN,
    KIND_DOMAIN,
    KIND_TV,
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
