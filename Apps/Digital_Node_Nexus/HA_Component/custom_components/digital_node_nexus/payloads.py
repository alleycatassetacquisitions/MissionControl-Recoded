"""JSON MQTT payloads for Digital Node Nexus commands.

Field names match the Phase 5 contract (evolved from esp32_commander MessageCmd /
LedCmd / HapticCmd). Firmware may later switch to binary protobuf using the
same field numbers documented in docs/dnn_commands.proto.
"""
from __future__ import annotations

import json
from typing import Any


def encode_page_cmd(
    *,
    text: str,
    duration: int = 10,
    scroll: bool = False,
    player_id: str = "",
    role: str = "",
    neocorp: str = "",
) -> bytes:
    """Encode a PageCmd as UTF-8 JSON bytes."""
    body: dict[str, Any] = {
        "text": text,
        "duration": int(duration),
        "scroll": bool(scroll),
        "player_id": player_id or "",
        "role": role or "",
        "neocorp": neocorp or "",
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def encode_led_cmd(
    *,
    state: bool = True,
    brightness: int = 255,
    r: int = 255,
    g: int = 255,
    b: int = 255,
    effect: str = "solid",
) -> bytes:
    """Encode a LedCmd as UTF-8 JSON bytes."""
    body = {
        "state": bool(state),
        "brightness": int(brightness),
        "r": int(r),
        "g": int(g),
        "b": int(b),
        "effect": effect or "solid",
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def encode_haptic_cmd(
    *,
    pattern: str = "short",
    intensity: int = 255,
    duration_ms: int = 100,
    repeat: int = 1,
) -> bytes:
    """Encode a HapticCmd as UTF-8 JSON bytes."""
    body = {
        "pattern": pattern or "short",
        "intensity": int(intensity),
        "duration_ms": int(duration_ms),
        "repeat": int(repeat),
    }
    return json.dumps(body, separators=(",", ":")).encode("utf-8")
