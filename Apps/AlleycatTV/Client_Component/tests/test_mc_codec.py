"""Pi-side mc_codec dual-read tests (mirrors shared_libraries.mc_codec)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PLAYER = Path(__file__).resolve().parents[1] / "alleycattv_player"
if str(_PLAYER) not in sys.path:
    sys.path.insert(0, str(_PLAYER))

from mc_codec import (  # noqa: E402
    WIRE_MAGIC,
    decode_action_payload,
    decode_message,
    encode_message,
)


def test_json_roundtrip_page_cmd():
    raw = encode_message(
        "PageCmd",
        {
            "text": "hello",
            "duration": 12,
            "scroll": True,
            "player_id": "p1",
            "role": "hunter",
            "neocorp": "helix",
        },
        wire="json",
    )
    assert raw.startswith(b"{")
    assert json.loads(raw)["text"] == "hello"
    assert decode_message(raw, "PageCmd")["scroll"] is True


def test_protobuf_roundtrip_interrupt_and_volume():
    interrupt = encode_message(
        "InterruptCmd", {"file_url": "http://x/a.mp4"}, wire="protobuf"
    )
    assert interrupt.startswith(WIRE_MAGIC)
    assert decode_message(interrupt, "InterruptCmd")["file_url"] == "http://x/a.mp4"
    volume = encode_message("SetVolumeCmd", {"volume": 40}, wire="protobuf")
    assert decode_action_payload(volume, "volume")["volume"] == 40


def test_empty_play_cmd_both_wires():
    assert encode_message("PlayCmd", {}, wire="json") == b"{}"
    assert encode_message("PlayCmd", {}, wire="protobuf") == WIRE_MAGIC
    assert decode_action_payload(WIRE_MAGIC, "play") == {}
