"""chrony, timezone, and system-clock helpers for Net Time.

Real implementations shell out to ``chronyc`` / ``date`` / ``timedatectl``.
When the LXC cannot set the clock (typical on Proxmox), Sync Now falls back
to the host clock agent (``NET_TIME_HOST_CLOCK_URL``).

Tests inject fakes via ``main.set_ops(...)``.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from models import PublicNtp, SourceRow, StatusResponse

_LOGGER = logging.getLogger(__name__)

_TRACKING_MIN_FIELDS = 8


class ChronyOps(Protocol):
    def read_status(self) -> StatusResponse: ...

    def apply_time(self, when: datetime) -> str: ...

    def get_timezone(self) -> str: ...

    def set_timezone(self, name: str) -> None: ...


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
    """Parse ``chronyc -c sources`` (Mode, State, Name, Stratum, Poll, Reach, …)."""
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
        rows.append(
            SourceRow(name=name, mode=f"{mode}/{sel}", stratum=stratum, state=state)
        )
    return rows


def _reach_ok(reach: str) -> bool:
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


def _read_timezone() -> str:
    out = _run(["timedatectl", "show", "-p", "Timezone", "--value"])
    if out:
        return out.strip()
    try:
        return open("/etc/timezone", encoding="utf-8").read().strip()
    except OSError:
        return ""


def _validate_timezone(name: str) -> str:
    text = (name or "").strip()
    if not text:
        raise ValueError("timezone is required")
    try:
        ZoneInfo(text)
    except ZoneInfoNotFoundError as err:
        raise ValueError(f"Unknown IANA timezone: {text}") from err
    return text


def _default_host_clock_url() -> str:
    configured = (os.getenv("NET_TIME_HOST_CLOCK_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    # Default gateway is usually the Proxmox host on vmbr0.
    route = _run(["ip", "route", "show", "default"])
    # default via 10.10.50.205 dev eth0 ...
    parts = route.split()
    if "via" in parts:
        idx = parts.index("via")
        if idx + 1 < len(parts):
            host = parts[idx + 1]
            port = os.getenv("NET_TIME_HOST_CLOCK_PORT", "8721")
            return f"http://{host}:{port}"
    return ""


class SystemChronyOps:
    """Production ops: chronyc + timedatectl + optional host clock agent."""

    def get_timezone(self) -> str:
        return _read_timezone()

    def set_timezone(self, name: str) -> None:
        tz = _validate_timezone(name)
        proc = subprocess.run(
            ["timedatectl", "set-timezone", tz],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"timedatectl set-timezone failed: "
                f"{(proc.stderr or proc.stdout or '').strip()}"
            )

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
            timezone=self.get_timezone(),
            sources=sources,
        )

    def apply_time(self, when: datetime) -> str:
        """Set clock. Returns ``local`` or ``host`` depending on which path worked."""
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when_utc = when.astimezone(timezone.utc)
        errors: list[str] = []

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
            return "local"
        errors.append(
            f"chronyc settime: {(setp.stderr or setp.stdout or '').strip()}"
        )

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
            return "local"
        errors.append(f"date: {(proc.stderr or proc.stdout or '').strip()}")

        # LXC cannot set the shared host clock — ask the Proxmox host agent.
        via_host = self._apply_via_host_agent(when_utc)
        if via_host:
            _run(["chronyc", "makestep"])
            return "host"

        host_url = _default_host_clock_url() or "(unset)"
        raise RuntimeError(
            "Failed to set system clock inside the LXC (expected on Proxmox). "
            f"Host clock agent also failed or is unreachable at {host_url}. "
            "Install host_clock_agent.py on the Proxmox host (see Net Time Config Steps). "
            "Details: " + " | ".join(errors)
        )

    def _apply_via_host_agent(self, when_utc: datetime) -> bool:
        base = _default_host_clock_url()
        token = (os.getenv("NET_TIME_API_TOKEN") or "").strip()
        if not base or not token:
            _LOGGER.warning(
                "host clock agent skipped (url=%r token_set=%s)",
                base,
                bool(token),
            )
            return False
        body = json.dumps(
            {"iso8601": when_utc.isoformat().replace("+00:00", "Z")}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{base}/sync",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                if 200 <= resp.status < 300:
                    return True
                _LOGGER.warning("host clock agent HTTP %s", resp.status)
                return False
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            _LOGGER.warning("host clock agent HTTPError %s: %s", err.code, detail)
            return False
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("host clock agent error: %s", err)
            return False


@dataclass
class FakeChronyOps:
    """In-memory ops for unit tests."""

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
