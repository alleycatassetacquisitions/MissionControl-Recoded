"""Tests for the MQTT fabric helpers (shared_libraries.mqtt).

Groups:
  1. mc_topic          — pure unit tests; no hass needed
  2. async_subscribe   — correct topic forwarded to mqtt.async_subscribe
  3. async_publish     — correct topic + payload forwarded to mqtt.async_publish
  4. async_subscribe_presence — correct presence topic constructed

Design contracts under test:
  - mc_topic() returns "mc/{kind}/{'/'.join(segments)}".
  - async_subscribe / async_publish never open a second broker client;
    they always delegate to homeassistant.components.mqtt.
  - async_subscribe_presence subscribes to mc/{kind}/status/{device_id}.
  - "broadcast" is the correct group-command segment; "zone" must never appear.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.shared_libraries.mqtt import (
    async_publish,
    async_subscribe,
    async_subscribe_presence,
    mc_topic,
)


# ---------------------------------------------------------------------------
# 1. mc_topic — pure unit tests
# ---------------------------------------------------------------------------


class TestMcTopic:
    def test_kind_only(self):
        assert mc_topic("dnn") == "mc/dnn"

    def test_kind_and_one_segment(self):
        assert mc_topic("dnn", "cmd") == "mc/dnn/cmd"

    def test_device_command_topic(self):
        assert mc_topic("dnn", "cmd", "abc123") == "mc/dnn/cmd/abc123"

    def test_all_command_topic(self):
        assert mc_topic("dnn", "cmd", "all") == "mc/dnn/cmd/all"

    def test_tv_all_command_topic(self):
        assert mc_topic("tv", "cmd", "all") == "mc/tv/cmd/all"

    def test_broadcast_group_command_topic(self):
        assert mc_topic("dnn", "cmd", "broadcast", "group-1") == "mc/dnn/cmd/broadcast/group-1"

    def test_status_topic(self):
        assert mc_topic("dnn", "status", "abc123") == "mc/dnn/status/abc123"

    def test_desired_topic(self):
        assert mc_topic("tv", "desired", "broadcast", "2", "playback") == (
            "mc/tv/desired/broadcast/2/playback"
        )

    def test_root_prefix_is_always_mc(self):
        topic = mc_topic("anything", "segment")
        assert topic.startswith("mc/")

    def test_no_zone_segment_needed(self):
        """'broadcast' is the correct group segment; 'zone' must not appear."""
        topic = mc_topic("dnn", "cmd", "broadcast", "g1")
        assert "zone" not in topic
        assert "broadcast" in topic

    def test_segments_joined_with_slash(self):
        assert mc_topic("dnn", "a", "b", "c") == "mc/dnn/a/b/c"

    def test_empty_segments_yields_kind_only(self):
        assert mc_topic("tv") == "mc/tv"


# ---------------------------------------------------------------------------
# Helpers for subscribe/publish tests
# ---------------------------------------------------------------------------


def _patch_mqtt_subscribe(unsub=None):
    mock_unsub = unsub or (lambda: None)
    return patch(
        "custom_components.shared_libraries.mqtt.mqtt.async_subscribe",
        new_callable=AsyncMock,
        return_value=mock_unsub,
    )


def _patch_mqtt_publish():
    return patch(
        "custom_components.shared_libraries.mqtt.mqtt.async_publish",
        new_callable=AsyncMock,
    )


# ---------------------------------------------------------------------------
# 2. async_subscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_calls_ha_mqtt_with_correct_topic(hass):
    """async_subscribe delegates to mqtt.async_subscribe with the right topic."""
    callback = lambda msg: None  # noqa: E731
    with _patch_mqtt_subscribe() as mock_sub:
        with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
            mock_mqtt.async_subscribe = AsyncMock(return_value=lambda: None)
            await async_subscribe(hass, "dnn", "cmd", "abc123", callback=callback)
            mock_mqtt.async_subscribe.assert_called_once()
            call_args = mock_mqtt.async_subscribe.call_args
            # Second positional arg is the topic
            assert call_args[0][1] == "mc/dnn/cmd/abc123"


@pytest.mark.asyncio
async def test_subscribe_passes_callback_to_ha_mqtt(hass):
    """The callback is forwarded to mqtt.async_subscribe unchanged."""
    callback = lambda msg: None  # noqa: E731
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=lambda: None)
        await async_subscribe(hass, "tv", "cmd", "all", callback=callback)
        call_args = mock_mqtt.async_subscribe.call_args
        assert call_args[0][2] is callback


@pytest.mark.asyncio
async def test_subscribe_returns_unsubscribe_callable(hass):
    """async_subscribe returns the unsubscribe function from mqtt.async_subscribe."""
    unsub = lambda: None  # noqa: E731
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=unsub)
        result = await async_subscribe(hass, "dnn", "cmd", "all", callback=lambda m: None)
    assert result is unsub


@pytest.mark.asyncio
async def test_subscribe_default_qos_is_zero(hass):
    """Default QoS is 0 when not specified."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=lambda: None)
        await async_subscribe(hass, "dnn", "cmd", "all", callback=lambda m: None)
        call_kwargs = mock_mqtt.async_subscribe.call_args[1]
        assert call_kwargs.get("qos", 0) == 0


# ---------------------------------------------------------------------------
# 3. async_publish
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_calls_ha_mqtt_with_correct_topic(hass):
    """async_publish delegates to mqtt.async_publish with the right topic."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_publish = AsyncMock()
        await async_publish(hass, "tv", "cmd", "all", payload='{"cmd":"stop"}')
        mock_mqtt.async_publish.assert_called_once()
        call_args = mock_mqtt.async_publish.call_args
        assert call_args[0][1] == "mc/tv/cmd/all"


@pytest.mark.asyncio
async def test_publish_forwards_payload(hass):
    """The payload is forwarded verbatim to mqtt.async_publish."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_publish = AsyncMock()
        payload = '{"brightness":128}'
        await async_publish(hass, "dnn", "cmd", "abc123", payload=payload)
        call_args = mock_mqtt.async_publish.call_args
        assert call_args[0][2] == payload


@pytest.mark.asyncio
async def test_publish_default_qos_is_zero(hass):
    """Default QoS is 0 when not specified."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_publish = AsyncMock()
        await async_publish(hass, "dnn", "cmd", "all", payload="ping")
        call_kwargs = mock_mqtt.async_publish.call_args[1]
        assert call_kwargs.get("qos", 0) == 0


@pytest.mark.asyncio
async def test_publish_default_retain_is_false(hass):
    """retain defaults to False."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_publish = AsyncMock()
        await async_publish(hass, "dnn", "cmd", "all", payload="ping")
        call_kwargs = mock_mqtt.async_publish.call_args[1]
        assert call_kwargs.get("retain", False) is False


@pytest.mark.asyncio
async def test_publish_retain_flag_forwarded(hass):
    """retain=True is forwarded to mqtt.async_publish."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_publish = AsyncMock()
        await async_publish(hass, "tv", "desired", "broadcast", "1", "playback",
                            payload="playing", retain=True)
        call_kwargs = mock_mqtt.async_publish.call_args[1]
        assert call_kwargs.get("retain") is True


# ---------------------------------------------------------------------------
# 4. async_subscribe_presence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_presence_subscribes_to_status_topic(hass):
    """async_subscribe_presence subscribes to mc/{kind}/status/{device_id}."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=lambda: None)
        await async_subscribe_presence(hass, "dnn", "node-42", callback=lambda m: None)
        call_args = mock_mqtt.async_subscribe.call_args
        assert call_args[0][1] == "mc/dnn/status/node-42"


@pytest.mark.asyncio
async def test_presence_subscribes_to_tv_status_topic(hass):
    """Presence works for tv namespace as well as dnn."""
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=lambda: None)
        await async_subscribe_presence(hass, "tv", "pi-7", callback=lambda m: None)
        call_args = mock_mqtt.async_subscribe.call_args
        assert call_args[0][1] == "mc/tv/status/pi-7"


@pytest.mark.asyncio
async def test_presence_returns_unsubscribe_callable(hass):
    """async_subscribe_presence returns the unsubscribe function."""
    unsub = lambda: None  # noqa: E731
    with patch("custom_components.shared_libraries.mqtt.mqtt") as mock_mqtt:
        mock_mqtt.async_subscribe = AsyncMock(return_value=unsub)
        result = await async_subscribe_presence(hass, "dnn", "node-1", callback=lambda m: None)
    assert result is unsub
