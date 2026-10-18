"""chrony and system-clock helpers for Net Time.

Real implementations shell out to ``chronyc`` / ``date``. Tests inject fakes
via ``main.set_ops(...)``.
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol

from models import PublicNtp, SourceRow, StatusResponse

_LOGGER = logging.getLogger(__name__)

# chronyc tracking CSV (chronyc -c tracking): Reference ID, Stratum, ...
# We only need a few fields; tolerate parse failures.
_TRACKING_MIN_FIELDS = 8


class ChronyOps(Protocol):
    def read_status(self) -> StatusResponse: ...

    def apply_time(self, when: datetime) -> None: ...


def _run(cmd: list[str], *, timeout: float = 5.0) -> str:
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        _LOGGER.warning("command failed %s: %s", cmd, err)
        return ""
    if proc.returncode != 0:
        _LOGGER.debug(
            "command %s rc=%s stderr=%s",
            cmd,
            proc.returncode,
            (proc.stderr or "").strip(),
        )
        return (proc.stdout or "").strip()
    return (proc.stdout or "").strip()


def _parse_tracking(csv: str) -> tuple[str, int | None]:
    """Return (reference, stratum) from ``chronyc -c tracking``."""
    line = (csv or "").splitlines()[0] if csv else ""
    if not line:
        return "", None
    parts = line.split(",")
    if len(parts) < _TRACKING_MIN_FIELDS:
        return parts[0].strip() if parts else "", None
    ref = parts[0].strip()
    try:
        stratum = int(parts[2])
    except (TypeError, ValueError):
        stratum = None
    return ref, stratum


def _parse_sources(csv: str) -> list[SourceRow]:
    """Parse ``chronyc -c sources`` rows.

    chrony CSV columns (4.x)::

        Mode, State, Name, Stratum, Poll, Reach, LastRx, ...

    Mode is source type: ``^`` server, ``=`` peer, ``#`` local clock.
    State is selection: ``*`` selected, ``+`` candidate, ``-`` / ``?`` / ``x`` / ``~``.
    """
    rows: list[SourceRow] = []
    for line in (csv or "").splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        mode = parts[0]
        sel = parts[1]
        name = parts[2]
        try:
            stratum = int(parts[3])
        except (TypeError, ValueError):
            stratum = None
        reach = parts[5] if len(parts) > 5 else ""
        is_local_clock = mode == "#" or name.upper() in {"LOCL", "LOCAL"} or name.upper().startswith(
            "LOCL"
        )
        if is_local_clock:
            state = "local"
        elif sel in {"*", "+"} or _reach_ok(reach):
            state = "reachable"
        else:
            state = "unusable"
        # Keep selection in mode field for operators (e.g. "^/*").
        rows.append(
            SourceRow(name=name, mode=f"{mode}/{sel}", stratum=stratum, state=state)
        )
    return rows


def _reach_ok(reach: str) -> bool:
    """chronyc reach is an octal bitmap; non-zero means recent replies."""
    try:
        return int(reach, 8) > 0
    except ValueError:
        return bool(reach) and reach not in {"0", "000"}


def _is_local_reference(reference: str) -> bool:
    ref = (reference or "").strip().upper()
    return (not ref) or ref in {"LOCAL", "LOCL", "00000000", "UNSYNC"}


def _public_ntp_from_sources(
    sources: list[SourceRow], *, reference: str = "", stratum: int | None = None
) -> PublicNtp:
    """Public pool is reachable if any non-local source looks usable.

    Also treat a non-local tracking reference with stratum under 10 as reachable
    (covers parse edge cases when sources CSV is empty/odd).
    """
    for src in sources:
        if src.state == "local":
            continue
        name = src.name.lower()
        if name in {"locl", "local"} or name.startswith("locl"):
            continue
        if src.state == "reachable":
            return "reachable"
    if (
        stratum is not None
        and stratum < 10
        and not _is_local_reference(reference)
    ):
        return "reachable"
    return "unavailable"


class SystemChronyOps:
    """Production ops: chronyc + date -u -s."""

    def read_status(self) -> StatusResponse:
        now = datetime.now(timezone.utc)
        tracking = _run(["chronyc", "-c", "tracking"])
        sources_csv = _run(["chronyc", "-c", "sources"])
        reference, stratum = _parse_tracking(tracking)
        sources = _parse_sources(sources_csv)
        public = _public_ntp_from_sources(
            sources, reference=reference, stratum=stratum
        )
        return StatusResponse(
            iso=now.isoformat().replace("+00:00", "Z"),
            unix=now.timestamp(),
            public_ntp=public,
            serving=True,
            stratum=stratum,
            reference=reference,
            sources=sources,
        )

    def apply_time(self, when: datetime) -> None:
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when_utc = when.astimezone(timezone.utc)
        errors: list[str] = []

        # Prefer chronyc (manual + settime) — works when chronyd has CAP_SYS_TIME
        # even if a bare `date -s` is blocked by the container profile.
        chrony_stamp = when_utc.strftime("%H:%M:%S %b %d %Y")
        man = subprocess.run(
            ["chronyc", "manual", "on"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if man.returncode != 0:
            errors.append(
                f"chronyc manual on: {(man.stderr or man.stdout or '').strip()}"
            )
        setp = subprocess.run(
            ["chronyc", "settime", chrony_stamp],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if setp.returncode == 0:
            _run(["chronyc", "makestep"])
            return

        errors.append(
            f"chronyc settime: {(setp.stderr or setp.stdout or '').strip()}"
        )

        # Fallback: GNU date (needs CAP_SYS_TIME on the LXC).
        date_stamp = when_utc.strftime("%Y-%m-%d %H:%M:%S")
        proc = subprocess.run(
            ["date", "-u", "-s", date_stamp],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            _run(["chronyc", "makestep"])
            _run(["chronyc", "reload", "sources"])
            return

        errors.append(f"date: {(proc.stderr or proc.stdout or '').strip()}")
        raise RuntimeError(
            "Failed to set system clock (LXC needs CAP_SYS_TIME). "
            "On Proxmox host: "
            "echo 'lxc.cap.keep: sys_time' >> /etc/pve/lxc/<CTID>.conf && "
            "pct reboot <CTID>. Details: " + " | ".join(errors)
        )


@dataclass
class FakeChronyOps:
    """In-memory ops for unit tests."""

    public_ntp: PublicNtp = "unavailable"
    stratum: int | None = 10
    reference: str = "LOCAL"
    sources: list[SourceRow] = field(default_factory=list)
    last_applied: datetime | None = None
    fail_apply: bool = False
    _unix: float = field(default_factory=time.time)

    def read_status(self) -> StatusResponse:
        now = datetime.fromtimestamp(self._unix, tz=timezone.utc)
        return StatusResponse(
            iso=now.isoformat().replace("+00:00", "Z"),
            unix=self._unix,
            public_ntp=self.public_ntp,
            serving=True,
            stratum=self.stratum,
            reference=self.reference,
            sources=list(self.sources),
        )

    def apply_time(self, when: datetime) -> None:
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
