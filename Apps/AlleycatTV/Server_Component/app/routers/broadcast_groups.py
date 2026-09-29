"""Broadcast group CRUD for content / playlist organization.

Does NOT publish MQTT playback commands — Home Assistant owns that path.
Legacy /api/zones routes are aliases of /api/broadcast_groups.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from fastapi import APIRouter, HTTPException

from app.config import ZONES_FILE
from app.models import BroadcastGroup

router = APIRouter(tags=["broadcast_groups"])


def _load() -> Dict[str, dict]:
    p = Path(ZONES_FILE)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save(data: Dict[str, dict]) -> None:
    Path(ZONES_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(ZONES_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _normalize_row(key: str, row: dict) -> BroadcastGroup:
    bg_id = row.get("broadcast_group_id") or row.get("zone_id") or key
    return BroadcastGroup(
        broadcast_group_id=bg_id,
        name=row.get("name") or bg_id,
        pi_ids=list(row.get("pi_ids") or []),
    )


def _register(prefix: str) -> None:
    @router.get(f"{prefix}/", response_model=List[BroadcastGroup])
    async def list_groups():
        return [_normalize_row(k, v) for k, v in _load().items()]

    @router.post(f"{prefix}/", response_model=BroadcastGroup)
    async def create_group(group: BroadcastGroup):
        data = _load()
        gid = group.broadcast_group_id
        if gid in data or any(
            (v.get("zone_id") == gid or v.get("broadcast_group_id") == gid)
            for v in data.values()
        ):
            raise HTTPException(status_code=409, detail="Broadcast group already exists")
        data[gid] = group.model_dump()
        _save(data)
        return group

    @router.get(f"{prefix}/{{group_id}}", response_model=BroadcastGroup)
    async def get_group(group_id: str):
        data = _load()
        if group_id not in data:
            raise HTTPException(status_code=404, detail="Broadcast group not found")
        return _normalize_row(group_id, data[group_id])

    @router.put(f"{prefix}/{{group_id}}", response_model=BroadcastGroup)
    async def update_group(group_id: str, group: BroadcastGroup):
        data = _load()
        group = group.model_copy(update={"broadcast_group_id": group_id})
        data[group_id] = group.model_dump()
        _save(data)
        return group

    @router.delete(f"{prefix}/{{group_id}}")
    async def delete_group(group_id: str):
        data = _load()
        if group_id not in data:
            raise HTTPException(status_code=404, detail="Broadcast group not found")
        del data[group_id]
        _save(data)
        return {"deleted": group_id}

    @router.post(f"{prefix}/{{group_id}}/command")
    async def command_gone(group_id: str):
        raise HTTPException(
            status_code=410,
            detail=(
                "Playback commands are owned by Home Assistant "
                "(alleycattv.play_broadcast_group / stop_broadcast_group / …). "
                f"group_id={group_id}"
            ),
        )


_register("/broadcast_groups")
_register("/zones")  # legacy alias for manage.html
