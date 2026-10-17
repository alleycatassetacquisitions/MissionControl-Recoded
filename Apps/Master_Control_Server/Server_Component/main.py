"""Master Control Server — the only Central HTTP adapter.

Design contracts:
  - MCS is a Proxmox companion. It is NOT a Home Assistant process.
  - HA (Registration integration) pushes Central Server URLs via POST /config.
    MCS stores them in memory and uses them for all Central calls.
  - Env vars (CENTRAL_PRIMARY_URL, CENTRAL_SECONDARY_URL) are first-boot
    defaults only. HA overwrites them on every setup.
  - MCS_API_TOKEN guards /players, /events, /game-state, /device-logs, /config.
  - Players are game records, not Home Assistant devices.
  - Central create/update are application/json; delete is soft-deactivate.
  - Active event comes from Central GET /game-state.
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from central_client import (
    create_event,
    create_player,
    create_team,
    deactivate_player,
    detail_from_body,
    fetch_device_logs,
    fetch_game_state,
    fetch_normalized_players,
    list_events,
    list_teams,
    set_active_event,
    set_delayed_scores,
    set_scoring,
    update_event,
    update_player,
    update_team,
)
from models import (
    ActiveEventMemory,
    ActiveEventState,
    ConfigUpdate,
    DeviceLog,
    DeviceLogsResponse,
    EnabledBody,
    Event,
    EventCreate,
    EventUpdate,
    GameState,
    HealthResponse,
    Pagination,
    Player,
    PlayerWrite,
    Roster,
    ScoringState,
    Team,
    TeamWrite,
)
from player_normalize import (
    normalize_player,
    to_central_create_body,
    to_central_update_body,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime config state — mutable, updated via POST /config
# ---------------------------------------------------------------------------

_config: dict[str, str] = {
    "central_primary": os.getenv("CENTRAL_PRIMARY_URL", ""),
    "central_secondary": os.getenv("CENTRAL_SECONDARY_URL", ""),
    "api_token": os.getenv("MCS_API_TOKEN", ""),
}

# Last-known active event (cache; authoritative source is Central game-state)
_active_event: dict[str, Any] = {
    "id": None,
    "name": None,
    "venue_name": None,
    "created_at": None,
    "set_at": None,
}


def _remember_active_event(event: dict[str, Any] | Event) -> None:
    """Store last-known active event after successful set_active / game-state."""
    if isinstance(event, Event):
        data = event.model_dump()
    else:
        data = event
    _active_event["id"] = str(data.get("id") or "") or None
    _active_event["name"] = data.get("name")
    _active_event["venue_name"] = data.get("venue_name")
    _active_event["created_at"] = data.get("created_at") or ""
    _active_event["set_at"] = datetime.now(timezone.utc).isoformat()


def _active_event_from_memory() -> ActiveEventState:
    event_id = _active_event.get("id")
    event: Event | None = None
    if event_id:
        event = Event(
            id=str(event_id),
            name=str(_active_event.get("name") or ""),
            venue_name=_active_event.get("venue_name"),
            created_at=str(_active_event.get("created_at") or ""),
        )
    return ActiveEventState(
        ready=True,
        active_event_id=str(event_id) if event_id else None,
        event=event,
        source="mcs_memory",
    )


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


def _central_error(
    status_code: int,
    action: str,
    body: Any | None = None,
) -> HTTPException:
    detail = detail_from_body(body)
    if status_code == 0:
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Central Server unreachable during {action}.",
        )
    if 400 <= status_code < 500:
        return HTTPException(
            status_code=status_code,
            detail=detail or f"Central Server returned HTTP {status_code} during {action}.",
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=detail or f"Central Server returned HTTP {status_code} during {action}.",
    )


def _event_from_central(resp: Any) -> Event | None:
    if not isinstance(resp, dict):
        return None
    event_id = resp.get("id")
    name = resp.get("name")
    if not event_id or not name:
        return None
    return Event(
        id=str(event_id),
        name=str(name),
        venue_name=resp.get("venue_name"),
        created_at=str(resp.get("created_at") or ""),
    )


def _game_state_from_central(resp: Any) -> GameState:
    if not isinstance(resp, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central game-state response was not a JSON object.",
        )
    active = _event_from_central(resp.get("active_event"))
    scoring_raw = resp.get("scoring")
    scoring: ScoringState | None = None
    if isinstance(scoring_raw, dict):
        scoring = ScoringState(
            enabled=bool(scoring_raw.get("enabled")),
            started_at=(
                str(scoring_raw["started_at"])
                if scoring_raw.get("started_at") is not None
                else None
            ),
        )
    delayed = resp.get("accepting_delayed_scores")
    if delayed is not None:
        delayed = bool(delayed)
    return GameState(
        active_event=active,
        scoring=scoring,
        accepting_delayed_scores=delayed,
        server_time_utc=str(resp.get("server_time_utc") or ""),
    )


def _team_from_central(resp: Any) -> Team | None:
    if not isinstance(resp, dict):
        return None
    team_id = resp.get("id")
    event_id = resp.get("event_id")
    name = resp.get("name")
    if not team_id or not event_id or not name:
        return None
    return Team(id=str(team_id), event_id=str(event_id), name=str(name))


async def _resolve_active_event_id() -> str:
    """Return Central active event id, or raise 409 if none."""
    status_code, resp = await fetch_game_state(
        _config["central_primary"],
        _config["central_secondary"],
    )
    if status_code == 0 or status_code >= 400:
        # Fall back to MCS memory
        mem_id = _active_event.get("id")
        if mem_id:
            return str(mem_id)
        raise _central_error(status_code, "resolve active event", resp)
    state = _game_state_from_central(resp)
    if state.active_event is None:
        mem_id = _active_event.get("id")
        if mem_id:
            return str(mem_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active event",
        )
    _remember_active_event(state.active_event)
    return state.active_event.id


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
    version="1.2.0",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Liveness check. Does not require auth — polled by DataUpdateCoordinator."""
    return HealthResponse(
        status="ok",
        central_primary=_config["central_primary"] or "",
        central_secondary=_config["central_secondary"] or "",
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
    """Accept Central Server URLs pushed by the Registration HA integration."""
    if update.central_primary:
        _config["central_primary"] = update.central_primary
    if update.central_secondary:
        _config["central_secondary"] = update.central_secondary
    _LOGGER.info(
        "MCS config updated — central_primary=%r central_secondary=%r",
        _config["central_primary"],
        _config["central_secondary"],
    )


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------


@app.get("/players", response_model=Roster, tags=["players"])
async def get_players(
    _token: Annotated[str, Depends(_verify_token)],
    page: Annotated[int | None, Query(ge=0)] = None,
    per_page: Annotated[int | None, Query(ge=0)] = None,
) -> Roster:
    """Return player roster from Central (canonical fields + optional pagination)."""
    players_raw, pagination = await fetch_normalized_players(
        _config["central_primary"],
        _config["central_secondary"],
        page=page,
        per_page=per_page,
    )
    players = [Player(**item) for item in players_raw]
    page_model = Pagination(**pagination) if pagination else None
    return Roster(players=players, count=len(players), pagination=page_model)


@app.get("/players/{player_id}", response_model=Player, tags=["players"])
async def get_player(
    player_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Return a single player by ID."""
    players_raw, _pagination = await fetch_normalized_players(
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
    """Create a player on Central (JSON name + optional email)."""
    _require_central()
    if not (body.name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name is required",
        )
    payload = to_central_create_body(name=body.name, email=body.email or "")
    status_code, resp = await create_player(
        _config["central_primary"],
        _config["central_secondary"],
        payload,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create", resp)
    if isinstance(resp, dict):
        try:
            return Player(**normalize_player(resp))
        except Exception:  # noqa: BLE001
            pass
    return Player(
        id=str(resp.get("id", "")) if isinstance(resp, dict) else "",
        name=body.name,
        email=body.email or "",
        mode="unassigned",
        role="unassigned",
    )


@app.put("/players/{player_id}", response_model=Player, tags=["players"])
async def put_player(
    player_id: str,
    body: PlayerWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> Player:
    """Update a player — proxies to Central PATCH /players/{id}."""
    _require_central()
    payload = to_central_update_body(
        name=body.name if (body.name or "").strip() else None,
        email=body.email if body.email is not None and not body.clear_email else None,
        clear_email=body.clear_email,
        team_id=body.team_id if not body.clear_team else None,
        clear_team=body.clear_team,
        active=body.active,
    )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supply name, email, team_id, or active",
        )
    status_code, resp = await update_player(
        _config["central_primary"],
        _config["central_secondary"],
        player_id,
        payload,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "update", resp)
    if isinstance(resp, dict):
        try:
            return Player(**normalize_player(resp))
        except Exception:  # noqa: BLE001
            pass
    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail="Central updated player but returned an unexpected body.",
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
    """Soft-deactivate a player via Central PATCH {active: false}."""
    _require_central()
    status_code, resp = await deactivate_player(
        _config["central_primary"],
        _config["central_secondary"],
        player_id,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "deactivate", resp)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


@app.get("/events", tags=["events"])
async def get_events(
    _token: Annotated[str, Depends(_verify_token)],
) -> dict[str, Any]:
    """List events from Central."""
    _require_central()
    status_code, resp = await list_events(
        _config["central_primary"],
        _config["central_secondary"],
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "list events", resp)
    if isinstance(resp, list):
        events = [_event_from_central(item) for item in resp]
        return {"events": [e for e in events if e is not None], "ready": True}
    if isinstance(resp, dict) and "events" in resp:
        events = [_event_from_central(item) for item in resp["events"]]
        return {"events": [e for e in events if e is not None], "ready": True}
    return {"events": [], "ready": True}


@app.get("/events/active", response_model=ActiveEventState, tags=["events"])
async def get_active_event_route(
    _token: Annotated[str, Depends(_verify_token)],
) -> ActiveEventState:
    """Return active event from Central GET /game-state (MCS memory fallback)."""
    if not (_config["central_primary"] or _config["central_secondary"]):
        return _active_event_from_memory()
    status_code, resp = await fetch_game_state(
        _config["central_primary"],
        _config["central_secondary"],
    )
    if status_code == 0 or status_code >= 400:
        return _active_event_from_memory()
    state = _game_state_from_central(resp)
    if state.active_event is not None:
        _remember_active_event(state.active_event)
        return ActiveEventState(
            ready=True,
            active_event_id=state.active_event.id,
            event=state.active_event,
            source="central",
        )
    # Clear memory when Central reports none
    _active_event["id"] = None
    _active_event["name"] = None
    _active_event["venue_name"] = None
    _active_event["created_at"] = ""
    return ActiveEventState(
        ready=True,
        active_event_id=None,
        event=None,
        source="central",
    )


@app.post(
    "/events",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    tags=["events"],
)
async def post_event(
    body: EventCreate,
    _token: Annotated[str, Depends(_verify_token)],
    set_active: Annotated[bool, Query()] = False,
) -> Event:
    """Create an event on Central. Optional ``set_active`` then PUT .../active."""
    _require_central()
    payload: dict[str, Any] = {"name": body.name}
    if body.venue_name is not None:
        payload["venue_name"] = body.venue_name
    status_code, resp = await create_event(
        _config["central_primary"],
        _config["central_secondary"],
        payload,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create event", resp)
    event = _event_from_central(resp)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central created event but returned an unexpected body.",
        )
    if set_active:
        act_status, act_body = await set_active_event(
            _config["central_primary"],
            _config["central_secondary"],
            event.id,
        )
        if act_status == 0 or act_status >= 400:
            raise _central_error(act_status, "set active event", act_body)
        _remember_active_event(event)
    return event


@app.patch("/events/{event_id}", response_model=Event, tags=["events"])
async def patch_event(
    event_id: str,
    body: EventUpdate,
    _token: Annotated[str, Depends(_verify_token)],
) -> Event:
    """Update an event on Central."""
    _require_central()
    payload: dict[str, Any] = {}
    if body.name is not None:
        payload["name"] = body.name
    if "venue_name" in body.model_fields_set:
        payload["venue_name"] = body.venue_name
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supply at least one of name or venue_name.",
        )
    status_code, resp = await update_event(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        payload,
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id!r} not found on Central.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "update event", resp)
    event = _event_from_central(resp)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central updated event but returned an unexpected body.",
        )
    if _active_event.get("id") == event.id:
        _remember_active_event(event)
    return event


@app.put(
    "/events/{event_id}/active",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["events"],
)
async def put_active_event(
    event_id: str,
    _token: Annotated[str, Depends(_verify_token)],
    body: ActiveEventMemory | None = None,
) -> None:
    """Select the active event on Central; remember id (+ optional name) in MCS memory.

    Optional JSON body ``{name, venue_name}`` is MCS-only display memory — not
    forwarded to Central (Central PUT /active has no body).
    """
    _require_central()
    status_code, resp = await set_active_event(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event {event_id!r} not found on Central.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "set active event", resp)
    if _active_event.get("id") != event_id:
        _active_event["name"] = None
        _active_event["venue_name"] = None
        _active_event["created_at"] = ""
    _active_event["id"] = event_id
    if body is not None:
        if body.name:
            _active_event["name"] = body.name
        if body.venue_name is not None:
            _active_event["venue_name"] = body.venue_name
    _active_event["set_at"] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Game state / scoring (Game Master)
# ---------------------------------------------------------------------------


@app.get("/game-state", response_model=GameState, tags=["game-state"])
async def get_game_state_route(
    _token: Annotated[str, Depends(_verify_token)],
) -> GameState:
    """Proxy Central GET /game-state."""
    _require_central()
    status_code, resp = await fetch_game_state(
        _config["central_primary"],
        _config["central_secondary"],
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "get game state", resp)
    state = _game_state_from_central(resp)
    if state.active_event is not None:
        _remember_active_event(state.active_event)
    return state


@app.put(
    "/events/{event_id}/scoring",
    response_model=ScoringState,
    tags=["game-state"],
)
async def put_scoring(
    event_id: str,
    body: EnabledBody,
    _token: Annotated[str, Depends(_verify_token)],
) -> ScoringState:
    """Proxy Central PUT /events/{id}/scoring."""
    _require_central()
    status_code, resp = await set_scoring(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        body.enabled,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "set scoring", resp)
    if not isinstance(resp, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central scoring response was not JSON.",
        )
    return ScoringState(
        enabled=bool(resp.get("enabled")),
        started_at=(
            str(resp["started_at"]) if resp.get("started_at") is not None else None
        ),
    )


@app.put(
    "/scoring",
    response_model=ScoringState,
    tags=["game-state"],
)
async def put_scoring_active(
    body: EnabledBody,
    _token: Annotated[str, Depends(_verify_token)],
) -> ScoringState:
    """Toggle scoring for the Central active event (convenience for Game Master)."""
    _require_central()
    event_id = await _resolve_active_event_id()
    status_code, resp = await set_scoring(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        body.enabled,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "set scoring", resp)
    if not isinstance(resp, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central scoring response was not JSON.",
        )
    return ScoringState(
        enabled=bool(resp.get("enabled")),
        started_at=(
            str(resp["started_at"]) if resp.get("started_at") is not None else None
        ),
    )


@app.put(
    "/events/{event_id}/delayed-scores",
    response_model=EnabledBody,
    tags=["game-state"],
)
async def put_delayed_scores_route(
    event_id: str,
    body: EnabledBody,
    _token: Annotated[str, Depends(_verify_token)],
) -> EnabledBody:
    """Proxy Central PUT /events/{id}/delayed-scores."""
    _require_central()
    status_code, resp = await set_delayed_scores(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        body.enabled,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "set delayed scores", resp)
    if isinstance(resp, dict) and "enabled" in resp:
        return EnabledBody(enabled=bool(resp["enabled"]))
    return EnabledBody(enabled=body.enabled)


@app.put(
    "/delayed-scores",
    response_model=EnabledBody,
    tags=["game-state"],
)
async def put_delayed_scores_active(
    body: EnabledBody,
    _token: Annotated[str, Depends(_verify_token)],
) -> EnabledBody:
    """Toggle delayed scores for the Central active event."""
    _require_central()
    event_id = await _resolve_active_event_id()
    status_code, resp = await set_delayed_scores(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        body.enabled,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "set delayed scores", resp)
    if isinstance(resp, dict) and "enabled" in resp:
        return EnabledBody(enabled=bool(resp["enabled"]))
    return EnabledBody(enabled=body.enabled)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


@app.get("/events/{event_id}/teams", response_model=list[Team], tags=["teams"])
async def get_teams(
    event_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> list[Team]:
    """List teams for an event."""
    _require_central()
    status_code, resp = await list_teams(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "list teams", resp)
    if not isinstance(resp, list):
        return []
    teams = [_team_from_central(item) for item in resp]
    return [t for t in teams if t is not None]


@app.post(
    "/events/{event_id}/teams",
    response_model=Team,
    status_code=status.HTTP_201_CREATED,
    tags=["teams"],
)
async def post_team(
    event_id: str,
    body: TeamWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> Team:
    """Create a team on an event."""
    _require_central()
    status_code, resp = await create_team(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        {"name": body.name},
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create team", resp)
    team = _team_from_central(resp)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central created team but returned an unexpected body.",
        )
    return team


@app.patch(
    "/events/{event_id}/teams/{team_id}",
    response_model=Team,
    tags=["teams"],
)
async def patch_team(
    event_id: str,
    team_id: str,
    body: TeamWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> Team:
    """Rename a team."""
    _require_central()
    status_code, resp = await update_team(
        _config["central_primary"],
        _config["central_secondary"],
        event_id,
        team_id,
        {"name": body.name},
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "update team", resp)
    team = _team_from_central(resp)
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central updated team but returned an unexpected body.",
        )
    return team


# ---------------------------------------------------------------------------
# Device logs
# ---------------------------------------------------------------------------


@app.get("/device-logs", response_model=DeviceLogsResponse, tags=["device-logs"])
async def get_device_logs(
    _token: Annotated[str, Depends(_verify_token)],
    page: Annotated[int, Query(ge=0)] = 1,
    per_page: Annotated[int, Query(ge=0)] = 20,
) -> DeviceLogsResponse:
    """Proxy Central GET /device-logs with pagination."""
    _require_central()
    status_code, resp = await fetch_device_logs(
        _config["central_primary"],
        _config["central_secondary"],
        page=page or 1,
        per_page=per_page or 20,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "list device logs", resp)
    if not isinstance(resp, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central device-logs response was not JSON object.",
        )
    raw_logs = resp.get("device_logs") or []
    pagination_raw = resp.get("pagination") or {}
    logs: list[DeviceLog] = []
    for item in raw_logs:
        if not isinstance(item, dict):
            continue
        try:
            logs.append(DeviceLog(**item))
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("Skipping malformed device log: %s", exc)
    return DeviceLogsResponse(
        device_logs=logs,
        pagination=Pagination(
            page=int(pagination_raw.get("page", page or 1)),
            per_page=int(pagination_raw.get("per_page", per_page or 20)),
        ),
    )
