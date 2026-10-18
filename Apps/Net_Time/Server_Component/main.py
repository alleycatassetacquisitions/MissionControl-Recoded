"""Net Time — LAN NTP authority management API.

Design contracts:
  - Net Time is a Proxmox companion. It is NOT a Home Assistant process.
  - chrony serves NTP/SNTP on UDP 123; this API manages status and Sync Now.
  - NET_TIME_API_TOKEN guards /status and /sync. /health is open for probes.
  - When public NTP is unreachable, operators push wall time via POST /sync
    (ISO-8601 from the browser / Core Configurator).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from chrony_ops import ChronyOps, SystemChronyOps
from models import HealthResponse, StatusResponse, SyncRequest, SyncResponse

_LOGGER = logging.getLogger(__name__)

_config: dict[str, str] = {
    "api_token": os.getenv("NET_TIME_API_TOKEN", ""),
}

_ops: ChronyOps = SystemChronyOps()

app = FastAPI(title="Net Time", version="1.0.0")

_bearer = HTTPBearer(auto_error=False)


def set_ops(ops: ChronyOps) -> None:
    """Replace chrony/system ops (tests)."""
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
        raise HTTPException(
            status_code=422,
            detail="iso8601 is required.",
        )
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError as err:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid iso8601: {err}",
        ) from err


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse()


@app.get("/status", response_model=StatusResponse, tags=["ops"])
def status_endpoint(_: Annotated[str, Depends(_verify_token)]) -> StatusResponse:
    try:
        return _ops.read_status()
    except Exception as err:  # noqa: BLE001 — surface as 502 for operators
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
        _ops.apply_time(when_utc)
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("sync failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to apply time: {err}",
        ) from err
    applied = when_utc.isoformat().replace("+00:00", "Z")
    return SyncResponse(status=_ops.read_status(), applied_iso=applied)
