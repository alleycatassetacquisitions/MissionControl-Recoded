"""JSON playback payloads for AlleycatTV MQTT commands.

Field names match docs/alleycatTV proto messages. HA publishes UTF-8 JSON;
Pi clients decode the same field names.
"""
from __future__ import annotations

import json


def encode_play_cmd() -> bytes:
    return b"{}"


def encode_stop_cmd() -> bytes:
    return b"{}"


def encode_interrupt_cmd(*, file_url: str) -> bytes:
    return json.dumps({"file_url": file_url}, separators=(",", ":")).encode("utf-8")


def encode_reload_cmd() -> bytes:
    return b"{}"


def encode_volume_cmd(*, volume: int) -> bytes:
    return json.dumps({"volume": int(volume)}, separators=(",", ":")).encode("utf-8")


def encode_desired_playback(
    *,
    state: str,
    volume: int | None = None,
) -> bytes:
    """Retained desired playback for mc/tv/desired/broadcast/{id}/playback."""
    body: dict = {"state": state}
    if volume is not None:
        body["volume"] = int(volume)
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def encode_cache_cmd(payload: dict | None = None) -> bytes:
    return json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
