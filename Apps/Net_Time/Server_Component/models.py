"""Pydantic models for the Net Time management API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PublicNtp = Literal["reachable", "unavailable"]


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "net_time"


class SourceRow(BaseModel):
    """One chrony source line (simplified for operators / HA)."""

    name: str
    mode: str = ""
    stratum: int | None = None
    state: str = ""


class StatusResponse(BaseModel):
    iso: str
    unix: float
    public_ntp: PublicNtp
    serving: bool = True
    stratum: int | None = None
    reference: str = ""
    timezone: str = ""
    sources: list[SourceRow] = Field(default_factory=list)


class SyncRequest(BaseModel):
    iso8601: str = Field(..., description="Operator PC time as ISO-8601")


class SyncResponse(BaseModel):
    status: StatusResponse
    applied_iso: str
    via: str = "local"


class TimezoneRequest(BaseModel):
    timezone: str = Field(
        ...,
        description="IANA timezone, e.g. America/Chicago",
    )


class TimezoneResponse(BaseModel):
    timezone: str
    status: StatusResponse
