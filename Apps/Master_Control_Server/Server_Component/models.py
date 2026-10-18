"""Pydantic models for Master Control Server.

Player fields follow Central's PlayerResponse (pdn_code, email, team_id,
team_name, active) with ``role`` / ``mode`` as HA-facing aliases derived from
team_name. NeoCorp/faction/neo_id remain optional empty fields for older HA
consumers until affiliation APIs land.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Pagination(BaseModel):
    """Central pagination echo (page / per_page)."""

    page: int = 1
    per_page: int = 20


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
    # Legacy optional fields — empty until Central affiliations API ships
    neocorp: str = ""
    faction: str = ""
    neo_id: str = ""


class PlayerWrite(BaseModel):
    """Create / update payload from Registration (HA → MCS).

    Central create accepts JSON ``name`` + optional ``email``. Update also
    accepts ``team_id`` and ``active``. Legacy role / neocorp / faction /
    neo_id fields are accepted but ignored on write.
    """

    name: str = ""
    email: str | None = None
    team_id: str | None = None
    active: bool | None = None
    clear_email: bool = False
    clear_team: bool = False
    role: str = ""
    neocorp: str = ""
    faction: str = ""
    neo_id: str = ""


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
    """Payload for POST /config pushed by the Registration HA integration."""

    central_primary: str = ""
    central_secondary: str = ""


class HealthResponse(BaseModel):
    status: str
    central_primary: str = ""
    central_secondary: str = ""
