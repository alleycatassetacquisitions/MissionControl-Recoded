"""Master Control Server — the only Central HTTP adapter.

Design contracts:
  - MCS is a Proxmox companion. It is NOT a Home Assistant process.
  - HA (Registration integration) pushes Central Server URLs via POST /config.
    MCS stores them in memory and uses them for all Central calls.
  - Env vars (CENTRAL_PRIMARY_URL, CENTRAL_SECONDARY_URL) are first-boot
    defaults only. HA overwrites them on every setup.
  - MCS_API_TOKEN guards /players and /config. HA stores this token in the
    Registration config entry. Set it as an env var on the Proxmox LXC.
  - Players are game records, not Home Assistant devices.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .central_client import fetch_players
from .models import ConfigUpdate, HealthResponse, Player, Roster

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime config state — mutable, updated via POST /config
# ---------------------------------------------------------------------------

_config: dict[str, str] = {
    "central_primary": os.getenv("CENTRAL_PRIMARY_URL", ""),
    "central_secondary": os.getenv("CENTRAL_SECONDARY_URL", ""),
    "api_token": os.getenv("MCS_API_TOKEN", ""),
}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


def _verify_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
) -> str:
    """Validate the Bearer token. Raises 401 on failure."""
    token = _config["api_token"]
    if not token:
        # If MCS has no token configured yet, deny all protected calls.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCS token not configured. Push /config from Home Assistant first.",
        )
    if credentials is None or credentials.credentials != token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    _LOGGER.info(
        "MCS starting — central_primary=%r central_secondary=%r",
        _config["central_primary"] or "(not set)",
        _config["central_secondary"] or "(not set)",
    )
    yield
    _LOGGER.info("MCS stopping.")


app = FastAPI(
    title="Master Control Server",
    description=(
        "Sole Central HTTP adapter for Mission Control. "
        "Owned by Home Assistant Registration integration."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness check. Does not require auth — polled by DataUpdateCoordinator."""
    return HealthResponse(
        status="ok",
        central_primary=_config["central_primary"] or "",
        central_secondary=_config["central_secondary"] or "",
    )


@app.get("/players", response_model=Roster, tags=["players"])
async def get_players(
    _token: Annotated[str, Depends(_verify_token)],
) -> Roster:
    """Return the full player roster from Central Server."""
    raw = await fetch_players(
        _config["central_primary"],
        _config["central_secondary"],
    )
    players = []
    for item in raw:
        try:
            players.append(Player(**item))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("MCS: skipping malformed player record: %s", exc)
    return Roster(players=players, count=len(players))


@app.get("/players/{player_id}", response_model=Player, tags=["players"])
async def get_player(
    player_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Return a single player by ID."""
    raw = await fetch_players(
        _config["central_primary"],
        _config["central_secondary"],
    )
    for item in raw:
        if str(item.get("id", "")) == player_id:
            return Player(**item)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Player {player_id!r} not found.",
    )


@app.post(
    "/config",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["ops"],
)
async def update_config(
    update: ConfigUpdate,
    _token: Annotated[str, Depends(_verify_token)],
) -> None:
    """Accept Central Server URLs pushed by the Registration HA integration.

    Called on every HA start and whenever Core Configurator fires
    core_configurator_updated with central_primary or central_secondary.
    """
    if update.central_primary:
        _config["central_primary"] = update.central_primary
    if update.central_secondary:
        _config["central_secondary"] = update.central_secondary
    _LOGGER.info(
        "MCS config updated — central_primary=%r central_secondary=%r",
        _config["central_primary"],
        _config["central_secondary"],
    )
