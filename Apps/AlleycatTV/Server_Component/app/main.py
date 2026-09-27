"""AlleycatTV content server — Proxmox companion FastAPI app.

Serves media files, playlists, and Content Manager UI.
Does NOT open an MQTT client — Home Assistant is the only command publisher.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import API_HOST, API_PORT, MEDIA_BASE, MEDIA_SUBDIRS
from app.routers import broadcast_groups, content, devices, playlists, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_LOGGER = logging.getLogger(__name__)

app = FastAPI(
    title="AlleycatTV Server",
    version="2.0.0",
    description="Content / playlist server for AlleycatTV (MQTT commands via HA)",
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
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    if path.startswith("/api/") or path == "/manage":
        ms = (time.perf_counter() - start) * 1000
        _LOGGER.info(
            "%s %s -> %s (%.0fms)",
            request.method,
            path,
            response.status_code,
            ms,
        )
    return response


app.include_router(content.router, prefix="/api")
app.include_router(devices.router, prefix="/api")
app.include_router(playlists.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(broadcast_groups.router, prefix="/api")


@app.on_event("startup")
async def startup() -> None:
    for sub in MEDIA_SUBDIRS:
        Path(MEDIA_BASE, sub).mkdir(parents=True, exist_ok=True)
    _LOGGER.info(
        "AlleycatTV content server started. Media root: %s (no MQTT client)",
        MEDIA_BASE,
    )


_media_path = Path(MEDIA_BASE)
_media_path.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_media_path)), name="media")


@app.get("/manage", include_in_schema=False)
async def manage_ui():
    return FileResponse(
        Path(__file__).parent / "static" / "manage.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "media_base": MEDIA_BASE, "mqtt": False}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=False)
