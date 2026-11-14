"""In-memory ChronyOps for unit tests (not used in production)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from chrony_ops import _validate_timezone
from models import PublicNtp, SourceRow, StatusResponse


@dataclass
class FakeChronyOps:
    public_ntp: PublicNtp = "unavailable"
    stratum: int | None = 10
    reference: str = "LOCAL"
    sources: list[SourceRow] = field(default_factory=list)
    last_applied: datetime | None = None
    fail_apply: bool = False
    timezone: str = "UTC"
    apply_via: str = "local"
    _unix: float = field(default_factory=time.time)

    def get_timezone(self) -> str:
        return self.timezone

    def set_timezone(self, name: str) -> None:
        self.timezone = _validate_timezone(name)

    def read_status(self) -> StatusResponse:
        now = datetime.fromtimestamp(self._unix, tz=timezone.utc)
        return StatusResponse(
            iso=now.isoformat().replace("+00:00", "Z"),
            unix=self._unix,
            public_ntp=self.public_ntp,
            serving=True,
            stratum=self.stratum,
            reference=self.reference,
            timezone=self.timezone,
            sources=list(self.sources),
        )

    def apply_time(self, when: datetime) -> str:
        if self.fail_apply:
            raise RuntimeError("fake apply failure")
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when_utc = when.astimezone(timezone.utc)
        self.last_applied = when_utc
        self._unix = when_utc.timestamp()
        self.public_ntp = "unavailable"
        self.reference = "LOCAL"
        self.stratum = 10
        return self.apply_via
