"""Unit tests for page/LED/haptic JSON payloads and cmd segment routing."""
from __future__ import annotations

import json

import pytest

from custom_components.digital_node_nexus.payloads import (
    encode_haptic_cmd,
    encode_led_cmd,
    encode_page_cmd,
)
from custom_components.digital_node_nexus.routing import resolve_cmd_segments


def test_encode_page_cmd_includes_stamps():
    raw = encode_page_cmd(
        text="Hello",
        duration=5,
        scroll=True,
        player_id="p1",
        role="hunter",
        neocorp="helix",
    )
    data = json.loads(raw.decode("utf-8"))
    assert data == {
        "text": "Hello",
        "duration": 5,
        "scroll": True,
        "player_id": "p1",
        "role": "hunter",
        "neocorp": "helix",
    }


def test_encode_led_and_haptic_shapes():
    led = json.loads(encode_led_cmd(state=False, effect="blink").decode())
    assert led["state"] is False
    assert led["effect"] == "blink"
    haptic = json.loads(encode_haptic_cmd(pattern="sos", repeat=2).decode())
    assert haptic["pattern"] == "sos"
    assert haptic["repeat"] == 2


def test_resolve_cmd_segments_priority():
    assert resolve_cmd_segments(device_id="fdn-1") == ["cmd", "fdn-1"]
    assert resolve_cmd_segments(broadcast_group_id="bg-9") == [
        "cmd",
        "broadcast",
        "bg-9",
    ]
    assert resolve_cmd_segments(target="all") == ["cmd", "all"]
    assert resolve_cmd_segments(default_all_for_stamps=True) == ["cmd", "all"]


def test_resolve_cmd_segments_requires_target():
    with pytest.raises(ValueError):
        resolve_cmd_segments()
