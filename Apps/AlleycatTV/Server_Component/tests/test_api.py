"""FastAPI tests for AlleycatTV content server (no MQTT)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_SERVER = Path(__file__).resolve().parent.parent
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setenv("ALLEYCATV_MEDIA", str(media))
    monkeypatch.setenv("ALLEYCATV_PLAYLISTS", str(tmp_path / "playlists.json"))
    monkeypatch.setenv("ALLEYCATV_ZONES", str(tmp_path / "groups.json"))
    monkeypatch.setenv("ALLEYCATV_DEVICES", str(tmp_path / "devices.json"))
    monkeypatch.setenv("ALLEYCATV_SETTINGS", str(tmp_path / "settings.json"))

    # Re-import app with patched env — config reads env at import time
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_reports_no_mqtt(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["mqtt"] is False


def test_broadcast_group_crud(client):
    resp = client.post(
        "/api/broadcast_groups/",
        json={"broadcast_group_id": "lobby", "name": "Lobby", "pi_ids": []},
    )
    assert resp.status_code == 200
    assert resp.json()["broadcast_group_id"] == "lobby"

    listed = client.get("/api/broadcast_groups/")
    assert listed.status_code == 200
    assert any(g["broadcast_group_id"] == "lobby" for g in listed.json())

    # Legacy alias
    legacy = client.get("/api/zones/")
    assert legacy.status_code == 200


def test_zone_command_gone(client):
    client.post(
        "/api/broadcast_groups/",
        json={"broadcast_group_id": "lobby", "name": "Lobby"},
    )
    resp = client.post("/api/zones/lobby/command", json={"action": "play"})
    assert resp.status_code == 410


def test_cache_report_http(client):
    resp = client.post(
        "/api/devices/pi-1/cache",
        json={"files": [{"subdir": "videos", "filename": "a.mp4"}], "cache_bytes": 10},
    )
    assert resp.status_code == 200
    listed = client.get("/api/devices/")
    assert any(d.get("pi_id") == "pi-1" for d in listed.json())


def test_cache_mqtt_endpoints_gone(client):
    assert client.post("/api/devices/pi-1/cache/purge").status_code == 410
    assert client.post("/api/devices/pi-1/cache/sync").status_code == 410
