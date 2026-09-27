"""Server settings — RTSP live sources and other venue-wide options.

Shape is intentionally a list so multiple RTSP sources can be added later
without an API redesign. For now the UI manages a single live-1 entry.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

try:
    from app.config import SETTINGS_FILE
except ImportError:  # pragma: no cover — older server installs
    SETTINGS_FILE = "/opt/alleycattv/settings.json"

router = APIRouter(prefix="/settings", tags=["settings"])
_LOGGER = logging.getLogger(__name__)

_DEFAULT: Dict[str, Any] = {"rtsp_sources": []}


class RtspSource(BaseModel):
    id: str = "live-1"
    label: str = "Live RTSP"
    url: str = ""
    enabled: bool = False


class SettingsPayload(BaseModel):
    rtsp_sources: Optional[List[RtspSource]] = Field(default=None)


def load_settings() -> Dict[str, Any]:
    p = Path(SETTINGS_FILE)
    if not p.exists():
        return dict(_DEFAULT)
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            return dict(_DEFAULT)
        data.setdefault("rtsp_sources", [])
        return data
    except Exception as exc:
        _LOGGER.warning("Could not load settings: %s", exc)
        return dict(_DEFAULT)


def save_settings(data: Dict[str, Any]) -> None:
    p = Path(SETTINGS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def enabled_rtsp_sources() -> List[Dict[str, Any]]:
    """Return enabled RTSP sources with a usable URL (for content list injection)."""
    out: List[Dict[str, Any]] = []
    for src in load_settings().get("rtsp_sources", []):
        if not isinstance(src, dict):
            continue
        if not src.get("enabled"):
            continue
        url = (src.get("url") or "").strip()
        if not url:
            continue
        out.append(src)
    return out


@router.get("/")
async def get_settings():
    return load_settings()


@router.put("/")
async def put_settings(body: SettingsPayload):
    """Merge settings. Only keys present in the body are updated."""
    data = load_settings()
    if body.rtsp_sources is not None:
        data["rtsp_sources"] = [s.model_dump() for s in body.rtsp_sources]
    save_settings(data)
    _LOGGER.info("Settings updated (%d rtsp source(s))", len(data.get("rtsp_sources", [])))
    return data
