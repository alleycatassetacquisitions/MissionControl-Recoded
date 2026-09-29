"""Unit tests for AlleycatTV routing and payloads (no HA)."""
from __future__ import annotations

import json

import pytest

from custom_components.alleycattv.payloads import (
    encode_desired_playback,
    encode_interrupt_cmd,
    encode_volume_cmd,
)
from custom_components.alleycattv.routing import resolve_cmd_segments


def test_resolve_device_uses_device_segment():
    assert resolve_cmd_segments(pi_id="pi-1") == ["cmd", "device", "pi-1"]


def test_resolve_all_and_broadcast():
    assert resolve_cmd_segments(target="all") == ["cmd", "all"]
    assert resolve_cmd_segments(broadcast_group_id="lobby") == [
        "cmd",
        "broadcast",
        "lobby",
    ]


def test_resolve_requires_target():
    with pytest.raises(ValueError):
        resolve_cmd_segments()


def test_payloads_json():
    assert json.loads(encode_interrupt_cmd(file_url="http://x/a.mp4")) == {
        "file_url": "http://x/a.mp4"
    }
    assert json.loads(encode_volume_cmd(volume=42)) == {"volume": 42}
    body = json.loads(encode_desired_playback(state="playing", volume=80))
    assert body == {"state": "playing", "volume": 80}
