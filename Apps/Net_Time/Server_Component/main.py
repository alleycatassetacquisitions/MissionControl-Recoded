"""Net Time — LAN NTP authority management API.

Design contracts:
  - Net Time is a Proxmox companion. It is NOT a Home Assistant process.
  - chrony serves NTP/SNTP on UDP 123; this API manages status, timezone, Offline Sync.
  - NET_TIME_API_TOKEN guards /status, /sync, /timezone, /config. /health is open.
  - Offline Sync may set the Proxmox host clock via NET_TIME_HOST_CLOCK_URL when the
    LXC cannot call settimeofday (normal on Proxmox).
  - POST /config (MCS peer fan-out) updates host_clock_url at runtime and persists
    /etc/net-time.env.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chrony_ops import ChronyOps, SystemChronyOps, get_host_clock_url, set_host_clock_url
from models import (
    ConfigUpdate,
    HealthResponse,
    StatusResponse,
    SyncRequest,
    SyncResponse,
    TimezoneRequest,
    TimezoneResponse,
)

_LOGGER = logging.getLogger(__name__)

_config: dict[str, str] = {
    "api_token": os.getenv("NET_TIME_API_TOKEN", ""),
}

_ops: ChronyOps = SystemChronyOps()

app = FastAPI(title="Net Time", version="1.0.0")

_bearer = HTTPBearer(auto_error=False)


def set_ops(ops: ChronyOps) -> None:
    global _ops
    _ops = ops


def set_api_token(token: str) -> None:
    _config["api_token"] = token


def _verify_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
) -> str:
    token = _config["api_token"]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Net Time token not configured. Set NET_TIME_API_TOKEN.",
        )
    if credentials is None or credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


def _parse_iso8601(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="iso8601 is required.")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as err:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid iso8601: {err}",
        ) from err


_ETC_ENV = Path("/etc/net-time.env")


def _persist_env(*, host_clock_url: str | None = None, api_token: str | None = None) -> None:
    """Best-effort merge into /etc/net-time.env."""
    try:
        existing: dict[str, str] = {}
        order: list[str] = []
        if _ETC_ENV.is_file():
            for line in _ETC_ENV.read_text(encoding="utf-8").splitlines():
                if not line.strip() or line.strip().startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                if key not in existing:
                    order.append(key)
                existing[key] = value
        if host_clock_url is not None:
            if "NET_TIME_HOST_CLOCK_URL" not in existing:
                order.append("NET_TIME_HOST_CLOCK_URL")
            existing["NET_TIME_HOST_CLOCK_URL"] = host_clock_url
        if api_token is not None:
            if "NET_TIME_API_TOKEN" not in existing:
                order.append("NET_TIME_API_TOKEN")
            existing["NET_TIME_API_TOKEN"] = api_token
        text = "".join(f"{k}={existing[k]}\n" for k in order)
        _ETC_ENV.write_text(text, encoding="utf-8")
        _LOGGER.info("Net Time updated %s", _ETC_ENV)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Net Time env persist skipped: %s", exc)


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse()


@app.post("/config", status_code=status.HTTP_204_NO_CONTENT, tags=["ops"])
def config_endpoint(
    body: ConfigUpdate,
    _: Annotated[str, Depends(_verify_token)],
) -> None:
    """Accept host_clock_url (+ optional token) from MCS peer fan-out."""
    if body.host_clock_url:
        applied = set_host_clock_url(body.host_clock_url)
        _persist_env(host_clock_url=applied)
        _LOGGER.info("Net Time host_clock_url=%r", applied)
    if body.api_token:
        _config["api_token"] = body.api_token.strip()
        _persist_env(api_token=_config["api_token"])
        _LOGGER.info("Net Time api_token rotated via /config")
    if not body.host_clock_url and not body.api_token:
        _LOGGER.debug(
            "Net Time /config no-op (host_clock_url effective=%r)",
            get_host_clock_url(),
        )


@app.get("/status", response_model=StatusResponse, tags=["ops"])
def status_endpoint(_: Annotated[str, Depends(_verify_token)]) -> StatusResponse:
    try:
        return _ops.read_status()
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("status failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to read chrony status: {err}",
        ) from err


@app.post("/sync", response_model=SyncResponse, tags=["ops"])
def sync_endpoint(
    body: SyncRequest,
    _: Annotated[str, Depends(_verify_token)],
) -> SyncResponse:
    when = _parse_iso8601(body.iso8601)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when_utc = when.astimezone(timezone.utc)
    try:
        via = _ops.apply_time(when_utc)
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("sync failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to apply time: {err}",
        ) from err
    applied = when_utc.isoformat().replace("+00:00", "Z")
    return SyncResponse(
        status=_ops.read_status(),
        applied_iso=applied,
        via=via,
    )


@app.post("/timezone", response_model=TimezoneResponse, tags=["ops"])
def timezone_endpoint(
    body: TimezoneRequest,
    _: Annotated[str, Depends(_verify_token)],
) -> TimezoneResponse:
    try:
        _ops.set_timezone(body.timezone)
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("timezone failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to set timezone: {err}",
        ) from err
    return TimezoneResponse(
        timezone=_ops.get_timezone(),
        status=_ops.read_status(),
    )
