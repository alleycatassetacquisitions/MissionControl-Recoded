"""Normalize Central Server player records to Mission Control fields.

Central PlayerResponse: id, event_id, pdn_code, name, email, created_at,
team_id, team_name, active, affiliations[]. ``role`` / ``mode`` are HA-facing
aliases derived from team_name when it matches hunter/bounty; otherwise
unassigned. Legacy neocorp/faction are derived from Allegiance/NeoCorp and
Faction affiliation categories when present.
"""
from __future__ import annotations

from typing import Any

_VALID_MODES = frozenset({"unassigned", "hunter", "bounty"})
_ROLE_FROM_HUNTER = {1: "hunter", 2: "bounty"}
_VALID_NEOCORPS = frozenset({"freelancer", "helix", "endline", "reboot"})
_ALLEGIANCE_CATEGORY_NAMES = frozenset({"allegiance", "neocorp"})
_FACTION_CATEGORY_NAMES = frozenset({"faction"})


def _first(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def normalize_mode(raw: dict[str, Any]) -> str:
    """Resolve mode from mode / role / team_name / hunter int. Default unassigned."""
    mode = _first(raw.get("mode"), raw.get("role"), raw.get("Role"))
    if isinstance(mode, str):
        lowered = mode.strip().lower()
        if lowered in _VALID_MODES:
            return lowered
        if lowered in ("1", "hunter"):
            return "hunter"
        if lowered in ("2", "bounty"):
            return "bounty"

    team_name = _first(raw.get("team_name"), raw.get("teamName"))
    if isinstance(team_name, str):
        lowered = team_name.strip().lower()
        if "hunter" in lowered:
            return "hunter"
        if "bounty" in lowered:
            return "bounty"

    hunter = raw.get("hunter")
    if hunter is not None:
        try:
            return _ROLE_FROM_HUNTER.get(int(hunter), "unassigned")
        except (TypeError, ValueError):
            pass

    team_id = raw.get("team_id")
    if team_id is None and not team_name:
        return "unassigned"
    return "unassigned"


def normalize_role(raw: dict[str, Any]) -> str:
    """HA ``role`` alias — same values as mode."""
    return normalize_mode(raw)


def _normalize_affiliations(raw: dict[str, Any]) -> list[dict[str, str]]:
    """Pass through Central affiliations array as MCS PlayerAffiliation dicts."""
    raw_list = raw.get("affiliations")
    if not isinstance(raw_list, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        category_id = _first(item.get("category_id"), item.get("categoryId"))
        affiliation_id = _first(
            item.get("affiliation_id"), item.get("affiliationId")
        )
        if category_id is None or affiliation_id is None:
            continue
        out.append(
            {
                "category_id": str(category_id),
                "category_name": str(
                    _first(item.get("category_name"), item.get("categoryName"))
                    or ""
                ),
                "affiliation_id": str(affiliation_id),
                "affiliation_name": str(
                    _first(
                        item.get("affiliation_name"), item.get("affiliationName")
                    )
                    or ""
                ),
            }
        )
    return out


def _derive_neocorp_faction(
    affiliations: list[dict[str, str]], raw: dict[str, Any]
) -> tuple[str, str]:
    """Derive legacy neocorp/faction from affiliations, else legacy fields."""
    neocorp = ""
    faction = ""
    for row in affiliations:
        cat = (row.get("category_name") or "").strip().lower()
        name = (row.get("affiliation_name") or "").strip()
        if not name:
            continue
        if cat in _ALLEGIANCE_CATEGORY_NAMES and not neocorp:
            lowered = name.lower()
            # Prefer slug when it matches known NeoCorp assets; else keep display
            if lowered in _VALID_NEOCORPS:
                neocorp = lowered
            elif " " in name:
                # "Helix Industries" → try first token
                first = name.split()[0].lower()
                neocorp = first if first in _VALID_NEOCORPS else lowered
            else:
                neocorp = lowered
        elif cat in _FACTION_CATEGORY_NAMES and not faction:
            faction = name

    if not neocorp:
        value = _first(
            raw.get("neocorp"),
            raw.get("allegiance"),
            raw.get("NeoCorp"),
            raw.get("Allegiance"),
        )
        if value is not None:
            lowered = str(value).strip().lower()
            neocorp = lowered if lowered in _VALID_NEOCORPS else lowered

    if not faction:
        faction = str(_first(raw.get("faction"), raw.get("Faction")) or "")

    return neocorp, faction


def normalize_neocorp(raw: dict[str, Any]) -> str:
    """Resolve NeoCorp from affiliations or legacy allegiance / neocorp."""
    affiliations = _normalize_affiliations(raw)
    neocorp, _faction = _derive_neocorp_faction(affiliations, raw)
    return neocorp


def normalize_player(raw: dict[str, Any]) -> dict[str, Any]:
    """Map a Central (or mixed) player dict to MCS Player fields."""
    player_id = _first(raw.get("id"), raw.get("ID"), raw.get("player_id"))
    name = _first(raw.get("name"), raw.get("Name"))
    if player_id is None or name is None:
        raise ValueError("player record missing id or name")

    mode = normalize_mode(raw)
    affiliations = _normalize_affiliations(raw)
    neocorp, faction = _derive_neocorp_faction(affiliations, raw)
    neo_id = _first(raw.get("neo_id"), raw.get("neoId"), raw.get("NeoId")) or ""
    pdn = _first(raw.get("pdn_code"), raw.get("pdn"), raw.get("PDN")) or ""
    email = _first(raw.get("email"), raw.get("Email")) or ""
    created_at = _first(raw.get("created_at"), raw.get("createdAt")) or ""
    event_id = raw.get("event_id")
    if event_id is not None:
        event_id = str(event_id)
    team_id = raw.get("team_id")
    if team_id is not None:
        team_id = str(team_id)
    team_name = _first(raw.get("team_name"), raw.get("teamName")) or ""
    active = raw.get("active")
    if active is None:
        active = True
    else:
        active = bool(active)

    return {
        "id": str(player_id),
        "name": str(name),
        "pdn_code": str(pdn),
        "mode": mode,
        "role": mode,
        "created_at": str(created_at),
        "email": str(email),
        "affiliations": affiliations,
        "neocorp": neocorp,
        "faction": str(faction),
        "neo_id": str(neo_id),
        "event_id": event_id,
        "team_id": team_id,
        "team_name": str(team_name),
        "active": active,
    }


def to_central_create_body(
    *,
    name: str,
    email: str = "",
) -> dict[str, Any]:
    """Build Central JSON body for POST /players."""
    body: dict[str, Any] = {"name": name.strip()}
    email_clean = (email or "").strip()
    if email_clean:
        body["email"] = email_clean
    return body


def to_central_update_body(
    *,
    name: str | None = None,
    email: str | None = None,
    clear_email: bool = False,
    team_id: str | None = None,
    clear_team: bool = False,
    active: bool | None = None,
    affiliations: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build Central JSON body for PATCH /players/{id}.

    Omitted fields are left out so Central preserves them. ``clear_email`` /
    ``clear_team`` send JSON null. ``affiliations`` is category UUID →
    affiliation UUID or null to clear.
    """
    body: dict[str, Any] = {}
    if name is not None and name.strip():
        body["name"] = name.strip()
    if clear_email:
        body["email"] = None
    elif email is not None:
        body["email"] = email.strip() if email.strip() else None
    if clear_team:
        body["team_id"] = None
    elif team_id is not None and str(team_id).strip():
        body["team_id"] = str(team_id).strip()
    if active is not None:
        body["active"] = bool(active)
    if affiliations is not None:
        body["affiliations"] = {
            str(k): (None if v is None else str(v)) for k, v in affiliations.items()
        }
    return body


# Back-compat aliases
def to_central_create_form(
    *,
    name: str,
    email: str = "",
) -> dict[str, Any]:
    """Deprecated name — returns JSON body for Central create."""
    return to_central_create_body(name=name, email=email)


def to_central_write_body(
    *,
    name: str,
    role: str = "hunter",  # noqa: ARG001
    neocorp: str = "",  # noqa: ARG001
    faction: str = "",  # noqa: ARG001
    neo_id: str = "",  # noqa: ARG001
    email: str = "",
) -> dict[str, Any]:
    """Deprecated — use to_central_create_body / to_central_update_body."""
    return to_central_create_body(name=name, email=email)
