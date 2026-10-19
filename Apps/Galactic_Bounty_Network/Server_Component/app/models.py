"""Pydantic models for the Galactic Bounty Network API.

Field names use canonical vocabulary from Design Terms.md
(neocorp, role hunter|bounty).
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

NeoCorp = Literal["reboot", "helix", "endline", "freelancer"]
Role = Literal["hunter", "bounty"]


class PosterStats(BaseModel):
    height: str = "5'10\""
    weight: str = "165 LBS"
    age: str = "29"


class PosterStatus(BaseModel):
    current_score: str = ""
    fastest_win: str = ""
    longest_streak: str = ""


class PosterTemplate(BaseModel):
    """Poster chrome preset (headline / amount / list labels)."""

    id: str
    name: str
    headline: str
    subtitle: str = ""
    amount_label: str = "REWARD"
    list_label: str = "WANTED FOR"
    list_empty: str = "Charges pending"
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
    id: str = ""  # optional; server generates slug if empty


class PosterTemplateUpdate(BaseModel):
    name: Optional[str] = None
    headline: Optional[str] = None
    subtitle: Optional[str] = None
    amount_label: Optional[str] = None
    list_label: Optional[str] = None
    list_empty: Optional[str] = None


class PosterRecord(BaseModel):
    id: str
    player_id: str = ""
    name: str
    role: Role = "bounty"
    neocorp: NeoCorp = "freelancer"
    faction: str = ""
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
    created_at: str = ""
    updated_at: str = ""


class PosterPublic(BaseModel):
    """Poster payload returned by the API (includes public URLs)."""

    id: str
    player_id: str = ""
    event_id: str = ""
    name: str
    role: Role = "bounty"
    neocorp: NeoCorp = "freelancer"
    faction: str = ""
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


class FlavorRequest(BaseModel):
    name: str
    neocorp: NeoCorp = "freelancer"
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
    neocorp: NeoCorp = "freelancer"
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
