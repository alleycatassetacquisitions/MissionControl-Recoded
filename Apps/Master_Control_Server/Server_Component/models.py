"""Pydantic models for Master Control Server.

Player fields follow Central's PlayerResponse (pdn_code, email, team_id,
team_name, active, affiliations) with ``role`` / ``mode`` as HA-facing aliases
derived from team_name. Legacy neocorp/faction/neo_id remain optional overlays
derived from affiliation category names when present.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


PLAYER_NAME_MAX_LEN = 32


class Pagination(BaseModel):
    """Central pagination echo (page / per_page)."""

    page: int = 1
    per_page: int = 20


class PlayerAffiliation(BaseModel):
    """One assigned affiliation within a category (Central PlayerAffiliation)."""

    category_id: str
    category_name: str = ""
    affiliation_id: str
    affiliation_name: str = ""


class Player(BaseModel):
    """A person playing the game — a Central Server record."""

    id: str
    name: str
    pdn_code: str = ""
    mode: str = "unassigned"
    role: str = "unassigned"  # HA alias of mode
    created_at: str = ""
    email: str = ""
    event_id: str | None = None
    team_id: str | None = None
    team_name: str = ""
    active: bool = True
    affiliations: list[PlayerAffiliation] = Field(default_factory=list)
    # Legacy overlays — derived from Allegiance/NeoCorp + Faction categories
    neocorp: str = ""
    faction: str = ""
    neo_id: str = ""


class PlayerWrite(BaseModel):
    """Create / update payload from Registration (HA → MCS).

    Central create accepts JSON ``name`` + optional ``email``. Update also
    accepts ``team_id``, ``active``, and ``affiliations``. Name is capped at
    32 characters for PDN / other device displays (Central allows more).
    """

    name: str = Field(default="", max_length=PLAYER_NAME_MAX_LEN)
    email: str | None = None
    team_id: str | None = None
    active: bool | None = None
    clear_email: bool = False
    clear_team: bool = False
    affiliations: dict[str, str | None] | None = None
    role: str = ""
    neocorp: str = ""
    faction: str = ""
    neo_id: str = ""


class AffiliationCategory(BaseModel):
    id: str
    event_id: str = ""
    name: str


class AffiliationCategoryWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class AffiliationChoice(BaseModel):
    id: str
    event_id: str = ""
    category_id: str = ""
    name: str


class AffiliationChoiceWrite(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class Roster(BaseModel):
    """Player list returned by GET /players."""

    players: list[Player]
    count: int = Field(default=0)
    pagination: Pagination | None = None

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN401
        if self.count == 0:
            object.__setattr__(self, "count", len(self.players))


class EventCreate(BaseModel):
    """POST /events body."""

    name: str
    venue_name: str | None = None


class EventUpdate(BaseModel):
    """PATCH /events/{id} body — at least one field required by Central."""

    name: str | None = None
    venue_name: str | None = None


class ActiveEventMemory(BaseModel):
    """Optional MCS-only hints on PUT /events/{id}/active (not sent to Central).

    Lets Registration keep the Active label as a name after set-active by id.
    """

    name: str | None = None
    venue_name: str | None = None


class Event(BaseModel):
    """Central EventResponse."""

    id: str
    name: str
    venue_name: str | None = None
    created_at: str = ""


class ActiveEventState(BaseModel):
    """GET /events/active — derived from Central GET /game-state."""

    ready: bool = True
    active_event_id: str | None = None
    event: Event | None = None
    source: str = "central"


class ScoringState(BaseModel):
    enabled: bool
    started_at: str | None = None


class GameState(BaseModel):
    """Central GET /game-state snapshot."""

    active_event: Event | None = None
    scoring: ScoringState | None = None
    accepting_delayed_scores: bool | None = None
    server_time_utc: str = ""


class EnabledBody(BaseModel):
    """PUT scoring / delayed-scores body."""

    enabled: bool


class Team(BaseModel):
    id: str
    event_id: str
    name: str


class TeamWrite(BaseModel):
    name: str


class DeviceLog(BaseModel):
    """Central DeviceLogResponse."""

    id: str
    device_mac: str
    crash_number: int
    uptime_ms: int
    received_at: str
    reset_reason: int
    software_version: str | None = None
    program_counter: int | None = None
    exception_cause: int | None = None
    task_name: str | None = None


class DeviceLogsResponse(BaseModel):
    device_logs: list[DeviceLog]
    pagination: Pagination


class ConfigUpdate(BaseModel):
    """Payload for POST /config pushed by Home Assistant (peer snapshot).

    Central URLs keep existing overwrite semantics (empty string leaves current).
    Peer fields are stored for fan-out to LXC companions; empty leaves current.
    """

    central_primary: str = ""
    central_secondary: str = ""
    # Venue peer snapshot (HA → MCS hub → LXC fan-out)
    mcs_url: str = ""
    gbn_url: str = ""
    net_time_url: str = ""
    net_time_token: str = ""
    alleycattv_url: str = ""
    host_clock_url: str = ""
    mqtt_host: str = ""
    mqtt_port: str = ""


class HealthResponse(BaseModel):
    status: str
    central_primary: str = ""
    central_secondary: str = ""
