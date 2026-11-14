"""Mission Control MQTT payload codec — protobuf schema + dual-read wire.

Field numbers match Apps/*/docs/*.proto (SoR). Wire formats:

* JSON (default publish): UTF-8 object, first byte ``{``
* Protobuf v1: ``b\"MC\\x01\"`` + proto3 binary (empty messages allowed)

Decode accepts either. Encode defaults to JSON so FDN firmware that still
expects JSON keeps working; set ``wire=\"protobuf\"`` for binary publish.
"""
from __future__ import annotations

import json
import struct
from typing import Any, Literal

WireFormat = Literal["json", "protobuf"]

WIRE_MAGIC = b"MC\x01"

# name -> {field_number: (json_key, wire_type)}
# wire_type: string | int32 | int64 | sint32 | bool
_SCHEMAS: dict[str, dict[int, tuple[str, str]]] = {
    "PageCmd": {
        1: ("text", "string"),
        2: ("duration", "int32"),
        3: ("scroll", "bool"),
        4: ("player_id", "string"),
        5: ("role", "string"),
        6: ("neocorp", "string"),
    },
    "LedCmd": {
        1: ("state", "bool"),
        2: ("brightness", "int32"),
        3: ("r", "int32"),
        4: ("g", "int32"),
        5: ("b", "int32"),
        6: ("effect", "string"),
    },
    "HapticCmd": {
        1: ("pattern", "string"),
        2: ("intensity", "int32"),
        3: ("duration_ms", "int32"),
        4: ("repeat", "int32"),
    },
    "PlayCmd": {},
    "StopCmd": {},
    "ReloadPlaylistCmd": {},
    "InterruptCmd": {1: ("file_url", "string")},
    "SetVolumeCmd": {1: ("volume", "int32")},
}

ACTION_TO_MESSAGE: dict[str, str] = {
    "page": "PageCmd",
    "led": "LedCmd",
    "haptic": "HapticCmd",
    "play": "PlayCmd",
    "stop": "StopCmd",
    "reload": "ReloadPlaylistCmd",
    "interrupt": "InterruptCmd",
    "volume": "SetVolumeCmd",
}


def _encode_varint(value: int) -> bytes:
    if value < 0:
        value &= (1 << 64) - 1
    out = bytearray()
    while value > 0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value & 0x7F)
    return bytes(out)


def _decode_varint(buf: bytes, idx: int) -> tuple[int, int]:
    shift = 0
    result = 0
    while True:
        if idx >= len(buf):
            raise ValueError("truncated varint")
        b = buf[idx]
        idx += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, idx
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


def _zigzag_encode(n: int) -> int:
    return (n << 1) ^ (n >> 63)


def _zigzag_decode(n: int) -> int:
    return (n >> 1) ^ (-(n & 1))


def _encode_key(field_number: int, wire_type: int) -> bytes:
    return _encode_varint((field_number << 3) | wire_type)


def _encode_field(field_number: int, wire_name: str, value: Any) -> bytes:
    if wire_name == "string":
        raw = str(value).encode("utf-8")
        return _encode_key(field_number, 2) + _encode_varint(len(raw)) + raw
    if wire_name == "bool":
        return _encode_key(field_number, 0) + _encode_varint(1 if value else 0)
    if wire_name == "int32":
        return _encode_key(field_number, 0) + _encode_varint(int(value) & 0xFFFFFFFF)
    if wire_name == "int64":
        return _encode_key(field_number, 0) + _encode_varint(int(value) & ((1 << 64) - 1))
    if wire_name == "sint32":
        return _encode_key(field_number, 0) + _encode_varint(
            _zigzag_encode(int(value)) & 0xFFFFFFFF
        )
    raise ValueError(f"unsupported wire type {wire_name}")


def _default_for(wire_name: str) -> Any:
    if wire_name == "string":
        return ""
    if wire_name == "bool":
        return False
    return 0


def _coerce(wtype: str, val: Any) -> Any:
    if wtype == "bool":
        return bool(val)
    if wtype in ("int32", "int64", "sint32"):
        return int(val)
    return "" if val is None else str(val)


def encode_message(
    message_name: str,
    fields: dict[str, Any] | None = None,
    *,
    wire: WireFormat = "json",
    fill_defaults: bool = True,
) -> bytes:
    """Encode a proto-named message to JSON or magic+protobuf bytes.

    ``fill_defaults`` matches historical HA JSON encoders that always emit
    every schema key (empty messages still encode as ``{}``).
    """
    if message_name not in _SCHEMAS:
        raise KeyError(f"unknown message {message_name}")
    schema = _SCHEMAS[message_name]
    src = fields or {}
    body: dict[str, Any] = {}
    for _num, (key, wtype) in sorted(schema.items()):
        if key in src and src[key] is not None:
            body[key] = _coerce(wtype, src[key])
        elif fill_defaults:
            body[key] = _default_for(wtype)

    if wire == "json":
        return json.dumps(body, separators=(",", ":")).encode("utf-8")

    out = bytearray()
    for num, (key, wtype) in sorted(schema.items()):
        if key not in body:
            continue
        val = body[key]
        if wtype == "string" and val == "":
            continue
        if wtype == "bool" and not val:
            continue
        if wtype in ("int32", "int64", "sint32") and int(val) == 0:
            continue
        out.extend(_encode_field(num, wtype, val))
    return WIRE_MAGIC + bytes(out)


def decode_message(raw: bytes | str | None, message_name: str) -> dict[str, Any]:
    """Dual-read JSON or magic+protobuf into a dict of proto field names."""
    if message_name not in _SCHEMAS:
        raise KeyError(f"unknown message {message_name}")
    schema = _SCHEMAS[message_name]
    if raw is None:
        return {}
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw:
        return {}

    if raw.startswith(WIRE_MAGIC):
        return _decode_protobuf(raw[len(WIRE_MAGIC) :], schema)

    # Legacy / default JSON
    try:
        text = raw.decode("utf-8")
        if not text.strip():
            return {}
        data = json.loads(text)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, Any] = {}
    for _num, (key, wtype) in schema.items():
        if key not in data:
            continue
        val = data[key]
        if wtype == "bool":
            out[key] = bool(val)
        elif wtype in ("int32", "int64", "sint32"):
            out[key] = int(val)
        else:
            out[key] = str(val)
    # Preserve unknown JSON keys for forward-compat (desired/cache not in schema).
    for key, val in data.items():
        if key not in out:
            out[key] = val
    return out


def decode_action_payload(raw: bytes | str | None, action: str) -> dict[str, Any]:
    """Decode by MQTT action segment when registered; else JSON dual-read."""
    message_name = ACTION_TO_MESSAGE.get(action)
    if message_name is None:
        if raw is None:
            return {}
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not raw or raw.startswith(WIRE_MAGIC):
            return {}
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return decode_message(raw, message_name)


def _decode_protobuf(
    buf: bytes, schema: dict[int, tuple[str, str]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    idx = 0
    by_num = schema
    while idx < len(buf):
        key, idx = _decode_varint(buf, idx)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number not in by_num:
            # Skip unknown field
            if wire_type == 0:
                _, idx = _decode_varint(buf, idx)
            elif wire_type == 1:
                idx += 8
            elif wire_type == 2:
                length, idx = _decode_varint(buf, idx)
                idx += length
            elif wire_type == 5:
                idx += 4
            else:
                break
            continue
        key_name, wtype = by_num[field_number]
        if wtype == "string":
            if wire_type != 2:
                raise ValueError("string field wrong wire type")
            length, idx = _decode_varint(buf, idx)
            out[key_name] = buf[idx : idx + length].decode("utf-8")
            idx += length
        elif wtype == "bool":
            val, idx = _decode_varint(buf, idx)
            out[key_name] = bool(val)
        elif wtype in ("int32", "int64"):
            val, idx = _decode_varint(buf, idx)
            if wtype == "int32":
                if val >= 0x80000000:
                    val -= 0x100000000
            out[key_name] = int(val)
        elif wtype == "sint32":
            val, idx = _decode_varint(buf, idx)
            out[key_name] = int(_zigzag_decode(val))
        else:
            raise ValueError(f"unsupported decode type {wtype}")
    return out


# Silence unused import if struct is reserved for future fixed64 — keep lean.
del struct
