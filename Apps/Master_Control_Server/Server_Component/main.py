"""Master Control Server — the only Central HTTP adapter.

Design contracts:
  - MCS is a Proxmox companion. It is NOT a Home Assistant process.
  - HA pushes Central Server URLs + a venue peer snapshot via POST /config.
    MCS stores them in memory, uses Central URLs for all Central calls, and
    fans out peer config to LXC companions (GBN, Net Time).
  - Env vars (CENTRAL_PRIMARY_URL, CENTRAL_SECONDARY_URL) are first-boot
    defaults only. HA overwrites them on every setup.
  - MCS_API_TOKEN guards /players, /events, /game-state, /device-logs, /config,
    /config/status.
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
    create_affiliation,
    create_affiliation_category,
    create_event,
    create_player,
    create_team,
    deactivate_player,
    detail_from_body,
    fetch_device_logs,
    fetch_game_state,
    fetch_normalized_players,
    list_affiliation_categories,
    list_affiliations,
    list_events,
    list_teams,
    rename_affiliation,
    rename_affiliation_category,
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
    AffiliationCategory,
    AffiliationCategoryWrite,
    AffiliationChoice,
    AffiliationChoiceWrite,
    ConfigStatusPeers,
    ConfigStatusResponse,
    ConfigUpdate,
    DeviceLog,
    DeviceLogsResponse,
    EnabledBody,
    Event,
    EventCreate,
    EventUpdate,
    GameState,
    HealthResponse,
    PLAYER_NAME_MAX_LEN,
    Pagination,
    Player,
    PlayerWrite,
    Roster,
    ScoringState,
    Team,
    TeamWrite,
)
from peer_fanout import fanout_peers
from player_normalize import (
    normalize_player,
    to_central_create_body,
    to_central_update_body,
)

# Ensure app INFO/WARNING reach journalctl under systemd/uvicorn.
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
    force=True,
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

# Venue peers — env seed empty; HA peer snapshot overwrites non-empty fields.
_peers: dict[str, str] = {
    "mcs_url": "",
    "gbn_url": "",
    "net_time_url": "",
    "net_time_token": "",
    "alleycattv_url": "",
    "host_clock_url": "",
    "mqtt_host": "",
    "mqtt_port": "",
}

_PEER_KEYS = tuple(_peers.keys())
_last_fanout: dict[str, Any] = {}

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


def _redacted_peers() -> ConfigStatusPeers:
    token = (_peers.get("net_time_token") or "").strip()
    return ConfigStatusPeers(
        mcs_url=_peers.get("mcs_url") or "",
        gbn_url=_peers.get("gbn_url") or "",
        net_time_url=_peers.get("net_time_url") or "",
        net_time_token="set" if token else "",
        alleycattv_url=_peers.get("alleycattv_url") or "",
        host_clock_url=_peers.get("host_clock_url") or "",
        mqtt_host=_peers.get("mqtt_host") or "",
        mqtt_port=_peers.get("mqtt_port") or "",
    )


@app.get("/config/status", response_model=ConfigStatusResponse, tags=["ops"])
async def config_status(
    _token: Annotated[str, Depends(_verify_token)],
) -> ConfigStatusResponse:
    """Inspect Central URLs, redacted peers, and last soft-fail fan-out results."""
    return ConfigStatusResponse(
        central_primary=_config["central_primary"] or "",
        central_secondary=_config["central_secondary"] or "",
        peers=_redacted_peers(),
        last_fanout=dict(_last_fanout),
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
    """Accept Central URLs + venue peer snapshot; fan-out to LXC companions."""
    if update.central_primary:
        _config["central_primary"] = update.central_primary
    # None = omit (leave current); "" = clear dead mirror; non-empty = set.
    if update.central_secondary is not None:
        _config["central_secondary"] = update.central_secondary.strip()

    peer_touched = False
    for key in _PEER_KEYS:
        value = getattr(update, key, "") or ""
        if value:
            _peers[key] = value.strip()
            peer_touched = True

    _LOGGER.info(
        "MCS config updated — central_primary=%r central_secondary=%r "
        "peers_touched=%s mcs_url=%r gbn_url=%r net_time_url=%r",
        _config["central_primary"],
        _config["central_secondary"],
        peer_touched,
        _peers.get("mcs_url") or "",
        _peers.get("gbn_url") or "",
        _peers.get("net_time_url") or "",
    )

    if peer_touched or _peers.get("gbn_url") or _peers.get("net_time_url"):
        results = await fanout_peers(
            api_token=_config["api_token"],
            peers=dict(_peers),
        )
        _last_fanout.clear()
        _last_fanout.update(results)
        _LOGGER.info("MCS peer fan-out results: %s", _last_fanout)


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


def _validate_player_name(name: str, *, required: bool) -> str:
    """Strip and enforce Mission Control 32-char name limit."""
    cleaned = (name or "").strip()
    if required and not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name is required",
        )
    if cleaned and len(cleaned) > PLAYER_NAME_MAX_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"name must be at most {PLAYER_NAME_MAX_LEN} characters",
        )
    return cleaned


def _affiliation_category_from_central(raw: Any) -> AffiliationCategory | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    return AffiliationCategory(
        id=str(raw["id"]),
        event_id=str(raw.get("event_id") or ""),
        name=str(raw.get("name") or ""),
    )


def _affiliation_choice_from_central(raw: Any) -> AffiliationChoice | None:
    if not isinstance(raw, dict) or not raw.get("id"):
        return None
    return AffiliationChoice(
        id=str(raw["id"]),
        event_id=str(raw.get("event_id") or ""),
        category_id=str(raw.get("category_id") or ""),
        name=str(raw.get("name") or ""),
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
    """Create a player on Central; optionally assign affiliations via PATCH."""
    _require_central()
    name = _validate_player_name(body.name, required=True)
    payload = to_central_create_body(name=name, email=body.email or "")
    status_code, resp = await create_player(
        _config["central_primary"],
        _config["central_secondary"],
        payload,
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create", resp)

    player_id = ""
    if isinstance(resp, dict):
        player_id = str(resp.get("id") or "")

    if player_id and body.affiliations:
        patch = to_central_update_body(affiliations=body.affiliations)
        patch_status, patch_resp = await update_player(
            _config["central_primary"],
            _config["central_secondary"],
            player_id,
            patch,
        )
        if patch_status == 0 or patch_status >= 400:
            raise _central_error(patch_status, "assign affiliations", patch_resp)
        if isinstance(patch_resp, dict):
            try:
                return Player(**normalize_player(patch_resp))
            except Exception:  # noqa: BLE001
                pass

    if isinstance(resp, dict):
        try:
            return Player(**normalize_player(resp))
        except Exception:  # noqa: BLE001
            pass
    return Player(
        id=player_id,
        name=name,
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
    name_for_update: str | None = None
    if (body.name or "").strip():
        name_for_update = _validate_player_name(body.name, required=False)
    payload = to_central_update_body(
        name=name_for_update,
        email=body.email if body.email is not None and not body.clear_email else None,
        clear_email=body.clear_email,
        team_id=body.team_id if not body.clear_team else None,
        clear_team=body.clear_team,
        active=body.active,
        affiliations=body.affiliations,
    )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supply name, email, team_id, active, or affiliations",
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
# Affiliations (live proxy — active-event scoped on Central)
# ---------------------------------------------------------------------------


@app.get(
    "/affiliation-categories",
    response_model=list[AffiliationCategory],
    tags=["affiliations"],
)
async def get_affiliation_categories(
    _token: Annotated[str, Depends(_verify_token)],
) -> list[AffiliationCategory]:
    """List affiliation categories for the Central active event."""
    _require_central()
    status_code, resp = await list_affiliation_categories(
        _config["central_primary"],
        _config["central_secondary"],
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "list affiliation categories", resp)
    if not isinstance(resp, list):
        return []
    return [
        c
        for c in (_affiliation_category_from_central(item) for item in resp)
        if c is not None
    ]


@app.post(
    "/affiliation-categories",
    response_model=AffiliationCategory,
    status_code=status.HTTP_201_CREATED,
    tags=["affiliations"],
)
async def post_affiliation_category(
    body: AffiliationCategoryWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> AffiliationCategory:
    """Create an affiliation category on the Central active event."""
    _require_central()
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="name is required"
        )
    status_code, resp = await create_affiliation_category(
        _config["central_primary"],
        _config["central_secondary"],
        {"name": name},
    )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create affiliation category", resp)
    category = _affiliation_category_from_central(resp)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central created category but returned an unexpected body.",
        )
    return category


@app.patch(
    "/affiliation-categories/{category_id}",
    response_model=AffiliationCategory,
    tags=["affiliations"],
)
async def patch_affiliation_category(
    category_id: str,
    body: AffiliationCategoryWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> AffiliationCategory:
    """Rename an affiliation category on the Central active event."""
    _require_central()
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="name is required"
        )
    status_code, resp = await rename_affiliation_category(
        _config["central_primary"],
        _config["central_secondary"],
        category_id,
        {"name": name},
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id!r} not found.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "rename affiliation category", resp)
    category = _affiliation_category_from_central(resp)
    if category is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central renamed category but returned an unexpected body.",
        )
    return category


@app.get(
    "/affiliation-categories/{category_id}/affiliations",
    response_model=list[AffiliationChoice],
    tags=["affiliations"],
)
async def get_affiliations(
    category_id: str,
    _token: Annotated[str, Depends(_verify_token)],
) -> list[AffiliationChoice]:
    """List affiliations (choices) in a category for the active event."""
    _require_central()
    status_code, resp = await list_affiliations(
        _config["central_primary"],
        _config["central_secondary"],
        category_id,
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id!r} not found.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "list affiliations", resp)
    if not isinstance(resp, list):
        return []
    return [
        c
        for c in (_affiliation_choice_from_central(item) for item in resp)
        if c is not None
    ]


@app.post(
    "/affiliation-categories/{category_id}/affiliations",
    response_model=AffiliationChoice,
    status_code=status.HTTP_201_CREATED,
    tags=["affiliations"],
)
async def post_affiliation(
    category_id: str,
    body: AffiliationChoiceWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> AffiliationChoice:
    """Create an affiliation choice under a category."""
    _require_central()
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="name is required"
        )
    status_code, resp = await create_affiliation(
        _config["central_primary"],
        _config["central_secondary"],
        category_id,
        {"name": name},
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Category {category_id!r} not found.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "create affiliation", resp)
    choice = _affiliation_choice_from_central(resp)
    if choice is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central created affiliation but returned an unexpected body.",
        )
    return choice


@app.patch(
    "/affiliation-categories/{category_id}/affiliations/{affiliation_id}",
    response_model=AffiliationChoice,
    tags=["affiliations"],
)
async def patch_affiliation(
    category_id: str,
    affiliation_id: str,
    body: AffiliationChoiceWrite,
    _token: Annotated[str, Depends(_verify_token)],
) -> AffiliationChoice:
    """Rename an affiliation choice."""
    _require_central()
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="name is required"
        )
    status_code, resp = await rename_affiliation(
        _config["central_primary"],
        _config["central_secondary"],
        category_id,
        affiliation_id,
        {"name": name},
    )
    if status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Affiliation or category not found.",
        )
    if status_code == 0 or status_code >= 400:
        raise _central_error(status_code, "rename affiliation", resp)
    choice = _affiliation_choice_from_central(resp)
    if choice is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Central renamed affiliation but returned an unexpected body.",
        )
    return choice


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
