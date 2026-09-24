"""Pydantic models for Master Control Server.

All field names use canonical vocabulary from Design Terms.md.
Players are game records, not Home Assistant devices.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Player(BaseModel):
    """A person playing the game — a Central Server record."""

    id: str
    name: str
    role: str = ""
    neocorp: str = ""
    faction: str = ""
    neo_id: str = ""


class PlayerWrite(BaseModel):
    """Canonical create/update payload from Registration (HA → MCS)."""

    name: str
    role: str = "hunter"
    neocorp: str = "freelancer"
    faction: str = ""
    neo_id: str = ""


class Roster(BaseModel):
    """Full player list returned by GET /players."""

    players: list[Player]
    count: int = Field(default=0)

    def model_post_init(self, __context) -> None:  # noqa: ANN001
        if self.count == 0:
            object.__setattr__(self, "count", len(self.players))


class ConfigUpdate(BaseModel):
    """Payload for POST /config pushed by the Registration HA integration."""

    central_primary: str = ""
    central_secondary: str = ""


class HealthResponse(BaseModel):
    status: str
    central_primary: str = ""
    central_secondary: str = ""
