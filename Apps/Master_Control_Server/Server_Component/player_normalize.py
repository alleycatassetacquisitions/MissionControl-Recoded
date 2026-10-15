"""Normalize Central Server player records to Mission Control fields.

Central PlayerResponse: id, pdn_code, name, created_at (+ optional team_id).
Mode / email may appear when Central adds them. ``role`` is the HA-facing
alias of ``mode`` (unassigned / hunter / bounty).
"""
from __future__ import annotations

from typing import Any

_VALID_MODES = frozenset({"unassigned", "hunter", "bounty"})
_ROLE_FROM_HUNTER = {1: "hunter", 2: "bounty"}
_VALID_NEOCORPS = frozenset({"freelancer", "helix", "endline", "reboot"})


def _first(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_mode(raw: dict[str, Any]) -> str:
    """Resolve mode from mode / role / hunter int. Default unassigned."""
    mode = _first(raw.get("mode"), raw.get("role"), raw.get("Role"))
    if isinstance(mode, str):
        lowered = mode.strip().lower()
        if lowered in _VALID_MODES:
            return lowered
        if lowered in ("1", "hunter"):
            return "hunter"
        if lowered in ("2", "bounty"):
            return "bounty"

    hunter = raw.get("hunter")
    if hunter is not None:
        try:
            return _ROLE_FROM_HUNTER.get(int(hunter), "unassigned")
        except (TypeError, ValueError):
            pass
    return "unassigned"


def normalize_role(raw: dict[str, Any]) -> str:
    """HA ``role`` alias — same values as mode."""
    return normalize_mode(raw)


def normalize_neocorp(raw: dict[str, Any]) -> str:
    """Resolve NeoCorp from allegiance / neocorp when present (usually empty)."""
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
    return lowered


def normalize_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a Central (or mixed) player dict to MCS Player fields."""
    player_id = _first(raw.get("id"), raw.get("ID"), raw.get("player_id"))
    name = _first(raw.get("name"), raw.get("Name"))
    if player_id is None or name is None:
        raise ValueError("player record missing id or name")

    mode = normalize_mode(raw)
    faction = _first(raw.get("faction"), raw.get("Faction")) or ""
    neo_id = _first(raw.get("neo_id"), raw.get("neoId"), raw.get("NeoId")) or ""
    pdn = _first(raw.get("pdn_code"), raw.get("pdn"), raw.get("PDN")) or ""
    email = _first(raw.get("email"), raw.get("Email")) or ""
    created_at = _first(raw.get("created_at"), raw.get("createdAt")) or ""
    team_id = raw.get("team_id")
    if team_id is not None:
        team_id = str(team_id)

    return {
        "id": str(player_id),
        "name": str(name),
        "pdn_code": str(pdn),
        "mode": mode,
        "role": mode,
        "created_at": str(created_at),
        "email": str(email),
        "neocorp": normalize_neocorp(raw),
        "faction": str(faction),
        "neo_id": str(neo_id),
        "team_id": team_id,
    }


def to_central_create_form(
    *,
    name: str,
    email: str = "",
) -> dict[str, str]:
    """Build Central form fields for POST /players (x-www-form-urlencoded)."""
    form: dict[str, str] = {"name": name.strip()}
    email_clean = (email or "").strip()
    if email_clean:
        form["email"] = email_clean
    return form


# Back-compat aliases used by older tests / callers
def to_central_create_body(
    *,
    name: str,
    role: str = "hunter",  # noqa: ARG001 — ignored; Central has no role on create
    neocorp: str = "freelancer",  # noqa: ARG001
    faction: str = "",  # noqa: ARG001
    neo_id: str = "",  # noqa: ARG001
    email: str = "",
) -> dict[str, str]:
    """Deprecated name — returns form fields for Central create."""
    return to_central_create_form(name=name, email=email)


def to_central_write_body(
    *,
    name: str,
    role: str = "hunter",  # noqa: ARG001
    neocorp: str = "",  # noqa: ARG001
    faction: str = "",  # noqa: ARG001
    neo_id: str = "",  # noqa: ARG001
    email: str = "",
) -> dict[str, str]:
    """Deprecated — player update is 501 until Central ships PATCH/PUT."""
    return to_central_create_form(name=name, email=email)
