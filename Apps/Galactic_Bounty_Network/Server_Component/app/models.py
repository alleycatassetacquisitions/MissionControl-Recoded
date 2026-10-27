"""Pydantic models for the Galactic Bounty Network API.

Field names use canonical vocabulary from Design Terms.md.
``neocorp`` / ``faction`` remain poster snapshot fields; values come from
the active event's affiliation catalog (no longer a fixed enum).
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Role = Literal["hunter", "bounty"]

ACCENT_PALETTE: dict[str, str] = {
    "blue": "#5ec8ff",
    "green": "#5eff9a",
    "red": "#ff5e6e",
    "yellow": "#ffe15e",
    "purple": "#b85eff",
    "gold": "#ffc857",
    "cyan": "#5effef",
    "orange": "#ff9a5e",
    "pink": "#ff5ec8",
    "white": "#e8f4ff",
}
DEFAULT_ACCENT = "blue"


def normalize_accent(value: str | None) -> str:
    slug = (value or DEFAULT_ACCENT).strip().lower()
    return slug if slug in ACCENT_PALETTE else DEFAULT_ACCENT


def accent_hex(value: str | None) -> str:
    return ACCENT_PALETTE[normalize_accent(value)]


def accent_dim(value: str | None) -> str:
    """CSS rgba dim glow derived from accent hex."""
    hex_color = accent_hex(value).lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return f"rgba({r}, {g}, {b}, 0.35)"


class PosterStats(BaseModel):
    height: str = "5'10\""
    weight: str = "165 LBS"
    age: str = "29"


class PosterStatus(BaseModel):
    current_score: str = ""
    fastest_win: str = ""
    longest_streak: str = ""


class PosterAffiliationSnap(BaseModel):
    """Snapshot of a category → choice used on a poster."""

    category_name: str = ""
    affiliation_name: str = ""


class PosterTemplate(BaseModel):
    """Poster chrome preset (headline / amount / list labels / accent)."""

    id: str
    name: str
    headline: str
    subtitle: str = ""
    amount_label: str = "REWARD"
    list_label: str = "WANTED FOR"
    list_empty: str = "Charges pending"
    accent: str = DEFAULT_ACCENT
    builtin: bool = False
    created_at: str = ""
    updated_at: str = ""


class PosterTemplateCreate(BaseModel):
    name: str
    headline: str
    subtitle: str = ""
    amount_label: str = "REWARD"
    list_label: str = "WANTED FOR"
    list_empty: str = "Charges pending"
    accent: str = DEFAULT_ACCENT
    id: str = ""  # optional; server generates slug if empty


class PosterTemplateUpdate(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    subtitle: Optional[str] = None
    amount_label: Optional[str] = None
    list_label: Optional[str] = None
    list_empty: Optional[str] = None
    accent: Optional[str] = None


class PosterRecord(BaseModel):
    id: str
    player_id: str = ""
    name: str
    role: Role = "bounty"
    neocorp: str = ""
    faction: str = ""
    affiliations: List[PosterAffiliationSnap] = Field(default_factory=list)
    bounty_amount: int = Field(default=1_000_000, ge=0)
    crimes: List[str] = Field(default_factory=list)
    stats: PosterStats = Field(default_factory=PosterStats)
    status: PosterStatus = Field(default_factory=PosterStatus)
    flavor_text: str = ""
    video_filename: str = ""
    # Chrome snapshot (stable if the template is later edited)
    template_id: str = ""
    headline: str = ""
    subtitle: str = ""
    amount_label: str = ""
    list_label: str = ""
    list_empty: str = ""
    accent: str = DEFAULT_ACCENT
    created_at: str = ""
    updated_at: str = ""


class PosterPublic(BaseModel):
    """Poster payload returned by the API (includes public URLs)."""

    id: str
    player_id: str = ""
    event_id: str = ""
    name: str
    role: Role = "bounty"
    neocorp: str = ""
    faction: str = ""
    affiliations: List[PosterAffiliationSnap] = Field(default_factory=list)
    bounty_amount: int
    crimes: List[str]
    stats: PosterStats
    status: PosterStatus = Field(default_factory=PosterStatus)
    flavor_text: str
    video_url: str = ""
    poster_url: str = ""
    has_video: bool = False
    template_id: str = ""
    headline: str = ""
    subtitle: str = ""
    amount_label: str = ""
    list_label: str = ""
    list_empty: str = ""
    accent: str = DEFAULT_ACCENT
    created_at: str = ""
    updated_at: str = ""


class EventMediaRow(BaseModel):
    event_id: str
    event_name: str = ""
    clip_count: int = 0
    bytes_total: int = 0
    has_media: bool = False
    has_posters: bool = False
    is_active: bool = False


class ActiveEventInfo(BaseModel):
    ready: bool = True
    active_event_id: str | None = None
    event_name: str = ""
    source: str = ""


class ActiveEventSet(BaseModel):
    """Registration → GBN push when the venue active event changes."""

    active_event_id: str
    event_name: str = ""


class FlavorRequest(BaseModel):
    name: str
    neocorp: str = "freelancer"
    role: Role = "bounty"


class FlavorResponse(BaseModel):
    bounty_amount: int
    crimes: List[str]
    stats: PosterStats
    flavor_text: str
    source: str = "templates"  # later: "local_llm"


class IntakeRequest(BaseModel):
    mac: str


class IntakePlayer(BaseModel):
    player_id: str
    name: str
    role: Role = "bounty"
    neocorp: str = ""
    faction: str = ""
    status: PosterStatus = Field(default_factory=PosterStatus)


class IntakeResponse(BaseModel):
    ok: bool
    mac: str
    reason: str = ""
    player: Optional[IntakePlayer] = None


class ActivePlayersRequest(BaseModel):
    player_ids: List[str] = Field(default_factory=list)
    interval_sec: int = Field(default=30, ge=5, le=300)


class ActivePlayersState(BaseModel):
    player_ids: List[str] = Field(default_factory=list)
    interval_sec: int = 30
    updated_at: str = ""
