"""Normalize Central Server player records to canonical Mission Control fields.

Central historically uses ``allegiance`` and ``hunter``/``mode``; Design Terms
use ``neocorp`` and ``role``. MCS is the adapter — HA always sees canonical names.
"""
from __future__ import annotations

from typing import Any

_ROLE_FROM_HUNTER = {1: "hunter", 2: "bounty"}
_HUNTER_FROM_ROLE = {"hunter": 1, "bounty": 2}
_VALID_NEOCORPS = frozenset({"freelancer", "helix", "endline", "reboot"})
_VALID_ROLES = frozenset({"hunter", "bounty"})


def _first(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_role(raw: dict[str, Any]) -> str:
    """Resolve role from mode / role / hunter int. Default hunter."""
    mode = _first(raw.get("mode"), raw.get("role"), raw.get("Role"))
    if isinstance(mode, str):
        lowered = mode.strip().lower()
        if lowered in _VALID_ROLES:
            return lowered
        if lowered in ("1", "hunter"):
            return "hunter"
        if lowered in ("2", "bounty"):
            return "bounty"

    hunter = raw.get("hunter")
    if hunter is not None:
        try:
            return _ROLE_FROM_HUNTER.get(int(hunter), "hunter")
        except (TypeError, ValueError):
            pass
    return "hunter"


def normalize_neocorp(raw: dict[str, Any]) -> str:
    """Resolve NeoCorp from allegiance / neocorp. Lowercase wire value."""
    value = _first(
        raw.get("neocorp"),
        raw.get("allegiance"),
        raw.get("NeoCorp"),
        raw.get("Allegiance"),
    )
    if value is None:
        return ""
    lowered = str(value).strip().lower()
    if lowered in _VALID_NEOCORPS:
        return lowered
    return lowered  # pass through unknown strings rather than drop


def normalize_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a Central (or mixed) player dict to canonical Player fields."""
    player_id = _first(raw.get("id"), raw.get("ID"), raw.get("player_id"))
    name = _first(raw.get("name"), raw.get("Name"))
    if player_id is None or name is None:
        raise ValueError("player record missing id or name")

    faction = _first(raw.get("faction"), raw.get("Faction")) or ""
    neo_id = _first(raw.get("neo_id"), raw.get("neoId"), raw.get("NeoId")) or ""

    return {
        "id": str(player_id),
        "name": str(name),
        "role": normalize_role(raw),
        "neocorp": normalize_neocorp(raw),
        "faction": str(faction),
        "neo_id": str(neo_id),
    }


def to_central_write_body(
    *,
    name: str,
    role: str = "hunter",
    neocorp: str = "",
    faction: str = "",
    neo_id: str = "",
) -> dict[str, Any]:
    """Build Central-facing JSON for create/update (legacy field names)."""
    role_norm = (role or "hunter").strip().lower()
    if role_norm not in _VALID_ROLES:
        role_norm = "hunter"
    allegiance = (neocorp or "").strip().lower()
    return {
        "name": name,
        "role": role_norm,
        "hunter": _HUNTER_FROM_ROLE.get(role_norm, 1),
        "allegiance": allegiance,
        "faction": faction or "",
        "neo_id": neo_id or "",
    }


def to_central_create_body(
    *,
    name: str,
    role: str = "hunter",
    neocorp: str = "freelancer",
    faction: str = "",
    neo_id: str = "",
) -> dict[str, Any]:
    """Build Central create payload (matches old rest_commands shape + extras)."""
    body = to_central_write_body(
        name=name, role=role, neocorp=neocorp or "freelancer", faction=faction, neo_id=neo_id
    )
    # Old register endpoint accepted hunter + allegiance; keep those primary.
    return body
