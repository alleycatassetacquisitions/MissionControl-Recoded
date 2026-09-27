"""Device cache inventory — HTTP only.

Pis POST cache reports here. Cache delete/purge/sync commands are Home Assistant
MQTT services (alleycattv.cache_*), not published by this server.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.config import DEVICES_FILE
from app.models import CacheReport

router = APIRouter(prefix="/devices", tags=["devices"])
_LOGGER = logging.getLogger(__name__)


def load_devices() -> Dict[str, Any]:
    p = Path(DEVICES_FILE)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_devices(data: Dict[str, Any]) -> None:
    p = Path(DEVICES_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


@router.get("/", response_model=List[Dict[str, Any]])
async def list_devices():
    return list(load_devices().values())


@router.get("/{pi_id}")
async def get_device(pi_id: str):
    data = load_devices()
    if pi_id not in data:
        raise HTTPException(status_code=404, detail="Device not found")
    return data[pi_id]


@router.post("/{pi_id}/cache")
async def report_cache(pi_id: str, report: CacheReport):
    """Pi posts local cache inventory (replaces MQTT cache/status)."""
    data = load_devices()
    row = report.model_dump()
    row["pi_id"] = pi_id
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    data[pi_id] = row
    save_devices(data)
    _LOGGER.info(
        "Stored cache report for %s (%d files)", pi_id, len(report.files)
    )
    return {"ok": True, "pi_id": pi_id}


@router.delete("/{pi_id}/cache/{subdir}/{filename:path}")
async def delete_cache_file(pi_id: str, subdir: str, filename: str):
    raise HTTPException(
        status_code=410,
        detail=(
            "Use Home Assistant service alleycattv.cache_delete "
            f"(pi_id={pi_id}, subdir={subdir}, filename={filename})"
        ),
    )


@router.post("/{pi_id}/cache/purge")
async def purge_cache(pi_id: str):
    raise HTTPException(
        status_code=410,
        detail=f"Use Home Assistant service alleycattv.cache_purge (pi_id={pi_id})",
    )


@router.post("/{pi_id}/cache/sync")
async def sync_cache(pi_id: str):
    raise HTTPException(
        status_code=410,
        detail=f"Use Home Assistant service alleycattv.cache_sync (pi_id={pi_id})",
    )
