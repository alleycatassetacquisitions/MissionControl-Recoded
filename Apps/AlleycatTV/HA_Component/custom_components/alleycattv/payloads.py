"""AlleycatTV MQTT payloads — field names/numbers from docs/alleycattv.proto (D16).

Command bodies go through ``mc_codec`` (JSON default; optional protobuf).
Desired / cache stay JSON-only until those messages are added to the proto.
"""
from __future__ import annotations

import json

from custom_components.shared_libraries.mc_codec import encode_message


def encode_play_cmd(*, wire: str = "json") -> bytes:
    return encode_message("PlayCmd", {}, wire=wire)  # type: ignore[arg-type]


def encode_stop_cmd(*, wire: str = "json") -> bytes:
    return encode_message("StopCmd", {}, wire=wire)  # type: ignore[arg-type]


def encode_interrupt_cmd(*, file_url: str, wire: str = "json") -> bytes:
    return encode_message(
        "InterruptCmd", {"file_url": file_url}, wire=wire  # type: ignore[arg-type]
    )


def encode_reload_cmd(*, wire: str = "json") -> bytes:
    return encode_message("ReloadPlaylistCmd", {}, wire=wire)  # type: ignore[arg-type]


def encode_volume_cmd(*, volume: int, wire: str = "json") -> bytes:
    return encode_message(
        "SetVolumeCmd", {"volume": volume}, wire=wire  # type: ignore[arg-type]
    )


def encode_desired_playback(
    *,
    state: str | None = None,
    volume: int | None = None,
) -> bytes:
    """Retained desired playback — JSON until desired is in alleycattv.proto."""
    body: dict = {}
    if state is not None:
        body["state"] = state
    if volume is not None:
        body["volume"] = int(volume)
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def encode_cache_cmd(payload: dict | None = None) -> bytes:
    return json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
