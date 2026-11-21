"""DNN MQTT payloads — field names/numbers from docs/dnn_commands.proto (D16).

Default wire is JSON so FDN firmware stays compatible. Binary (``MC\\x01`` +
protobuf) is available via ``wire=\"protobuf\"``; consumers dual-read both.
"""
from __future__ import annotations

from custom_components.shared_libraries.mc_codec import encode_message


def encode_page_cmd(
    *,
    text: str,
    duration: int = 10,
    scroll: bool = False,
    player_id: str = "",
    role: str = "",
    neocorp: str = "",
    id: str = "",
    wire: str = "json",
) -> bytes:
    return encode_message(
        "PageCmd",
        {
            "text": text,
            "duration": duration,
            "scroll": scroll,
            "player_id": player_id or "",
            "role": role or "",
            "neocorp": neocorp or "",
            "id": id or "",
        },
        wire=wire,  # type: ignore[arg-type]
    )


def encode_led_cmd(
    *,
    state: bool = True,
    brightness: int = 255,
    r: int = 255,
    g: int = 255,
    b: int = 255,
    effect: str = "solid",
    wire: str = "json",
) -> bytes:
    return encode_message(
        "LedCmd",
        {
            "state": state,
            "brightness": brightness,
            "r": r,
            "g": g,
            "b": b,
            "effect": effect or "solid",
        },
        wire=wire,  # type: ignore[arg-type]
    )


def encode_haptic_cmd(
    *,
    pattern: str = "short",
    intensity: int = 255,
    duration_ms: int = 100,
    repeat: int = 1,
    wire: str = "json",
) -> bytes:
    return encode_message(
        "HapticCmd",
        {
            "pattern": pattern or "short",
            "intensity": intensity,
            "duration_ms": duration_ms,
            "repeat": repeat,
        },
        wire=wire,  # type: ignore[arg-type]
    )
