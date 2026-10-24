"""Galactic Bounty Network Server — FastAPI entry point.

Serves:
  /api/*       — posters, flavor, intake, active-players
  /poster/*    — animated 16:9 bounty poster page
  /poster-cycle — kiosk that rotates all made posters
  /media/*     — uploaded capture videos + NeoCorp assets
  /health      — liveness probe

Does NOT expose GET /api/players — Player roster lives on MCS.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import (
    API_HOST,
    API_PORT,
    DATA_DIR,
    MEDIA_BASE,
    MEDIA_SUBDIRS,
    POSTERS_FILE,
    STATIC_DIR,
    TEMPLATES_FILE,
)
from app.event_stores import EventPosterStores
from app.models import ActivePlayersState
from app.routers import (
    active_players,
    config as config_routes,
    events_media,
    flavor,
    intake,
    posters,
    templates as template_routes,
)
from app.runtime_config import load_persisted
from app.template_store import TemplateStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="Galactic Bounty Network",
    version="1.0.0",
    description="Bounty poster capture and display for Alleycat Mission Control",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-be-revalidate"
        response.headers["Pragma"] = "no-cache"
        ms = (time.perf_counter() - start) * 1000
        _LOGGER.info(
            "%s %s -> %s (%.0fms)", request.method, path, response.status_code, ms
        )
    return response


app.include_router(posters.router)
app.include_router(events_media.router)
app.include_router(template_routes.router)
app.include_router(active_players.router)
app.include_router(flavor.router)
app.include_router(intake.router)
app.include_router(config_routes.router)


@app.on_event("startup")
async def startup() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    load_persisted()
    Path(DATA_DIR, "events").mkdir(parents=True, exist_ok=True)
    for sub in MEDIA_SUBDIRS:
        Path(MEDIA_BASE, sub).mkdir(parents=True, exist_ok=True)
    Path(MEDIA_BASE, "events").mkdir(parents=True, exist_ok=True)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.state.event_stores = EventPosterStores(POSTERS_FILE)
    # Back-compat alias for any code still expecting poster_store
    app.state.poster_store = app.state.event_stores.legacy
    app.state.template_store = TemplateStore(TEMPLATES_FILE)
    app.state.active_playlist = ActivePlayersState()
    # Warm active-event cache from MCS (or keep disk cache) so /poster-cycle
    # does not need a human to open the page once after restart.
    try:
        from app.services.mcs_client import get_active_event

        warm = await get_active_event()
        if warm and warm.get("active_event_id"):
            _LOGGER.info(
                "Active event ready at startup: %s (%s)",
                warm.get("active_event_id"),
                warm.get("source") or "?",
            )
        else:
            _LOGGER.warning(
                "No active event at startup — set one in Registration "
                "(pushes to GBN) or Pis show NO ACTIVE EVENT until then"
            )
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("Active event warmup failed: %s", exc)
    _LOGGER.info(
        "GBN started. Media: %s Legacy posters: %s Templates: %s",
        MEDIA_BASE,
        POSTERS_FILE,
        TEMPLATES_FILE,
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gbn"}


app.mount("/media", StaticFiles(directory=str(MEDIA_BASE)), name="media")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=API_HOST, port=API_PORT, reload=True)
