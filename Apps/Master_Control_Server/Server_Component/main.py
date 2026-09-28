"""Master Control Server — the only Central HTTP adapter.

Design contracts:
  - MCS is a Proxmox companion. It is NOT a Home Assistant process.
  - HA (Registration integration) pushes Central Server URLs via POST /config.
    MCS stores them in memory and uses them for all Central calls.
  - Env vars (CENTRAL_PRIMARY_URL, CENTRAL_SECONDARY_URL) are first-boot
    defaults only. HA overwrites them on every setup.
  - MCS_API_TOKEN guards /players and /config. The same token is stored in
    Core Configurator (master_control_server extra.token) and set as this
    env var on the Proxmox LXC (see ProxmoxInstallFiles/install-mcs-proxmox.sh).
  - Players are game records, not Home Assistant devices.
  - Central legacy keys (allegiance, hunter/mode) are normalized to canonical
    Design Terms fields (neocorp, role) on read; writes reverse-map.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from central_client import (
    create_player,
    delete_player,
    fetch_normalized_players,
    update_player,
)
from models import ConfigUpdate, HealthResponse, Player, PlayerWrite, Roster
from player_normalize import normalize_player, to_central_create_body, to_central_write_body

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


def _require_central() -> None:
    if not (_config["central_primary"] or _config["central_secondary"]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No Central Server URL configured. Push /config from Home Assistant.",
        )


def _central_error(status_code: int, action: str) -> HTTPException:
    if status_code == 0:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Central Server unreachable during {action}.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Central Server returned HTTP {status_code} during {action}.",
    )


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
    """Return the full player roster from Central Server (canonical fields)."""
    players_raw = await fetch_normalized_players(
        _config["central_primary"],
        _config["central_secondary"],
    )
    players = [Player(**item) for item in players_raw]
    return Roster(players=players, count=len(players))


@app.get("/players/{player_id}", response_model=Player, tags=["players"])
async def get_player(
    player_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Return a single player by ID."""
    players_raw = await fetch_normalized_players(
        _config["central_primary"],
        _config["central_secondary"],
    )
    for item in players_raw:
        if item["id"] == player_id:
            return Player(**item)
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Player {player_id!r} not found.",
    )


@app.post(
    "/players",
    response_model=Player,
    status_code=status.HTTP_201_CREATED,
    tags=["players"],
)
async def post_player(
    body: PlayerWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Create a player on Central. Accepts canonical fields; writes legacy keys."""
    _require_central()
    central_body = to_central_create_body(
        name=body.name,
        role=body.role,
        neocorp=body.neocorp,
        faction=body.faction,
        neo_id=body.neo_id,
    )
    status_code, resp = await create_player(
        _config["central_primary"],
        _config["central_secondary"],
        central_body,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create")
    if isinstance(resp, dict):
        try:
            return Player(**normalize_player(resp))
        except Exception:  # noqa: BLE001
            pass
    # Central may return minimal payload — echo request with unknown id.
    return Player(
        id=str((resp or {}).get("id", "")) if isinstance(resp, dict) else "",
        name=body.name,
        role=central_body["role"],
        neocorp=central_body["allegiance"],
        faction=body.faction,
        neo_id=body.neo_id,
    )


@app.put("/players/{player_id}", response_model=Player, tags=["players"])
async def put_player(
    player_id: str,
    body: PlayerWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Update a player on Central."""
    _require_central()
    central_body = to_central_write_body(
        name=body.name,
        role=body.role,
        neocorp=body.neocorp,
        faction=body.faction,
        neo_id=body.neo_id,
    )
    status_code, resp = await update_player(
        _config["central_primary"],
        _config["central_secondary"],
        player_id,
        central_body,
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player {player_id!r} not found on Central.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "update")
    if isinstance(resp, dict):
        try:
            return Player(**normalize_player({**resp, "id": resp.get("id", player_id)}))
        except Exception:  # noqa: BLE001
            pass
    return Player(
        id=player_id,
        name=body.name,
        role=central_body["role"],
        neocorp=central_body["allegiance"],
        faction=body.faction,
        neo_id=body.neo_id,
    )


@app.delete(
    "/players/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["players"],
)
async def remove_player(
    player_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> None:
    """Delete a player on Central."""
    _require_central()
    status_code, _resp = await delete_player(
        _config["central_primary"],
        _config["central_secondary"],
        player_id,
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Player {player_id!r} not found on Central.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "delete")


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
