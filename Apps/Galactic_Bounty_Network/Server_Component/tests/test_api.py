"""FastAPI TestClient tests for Galactic Bounty Network server."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_SERVER = Path(__file__).resolve().parent.parent
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    (media / "videos").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    posters = data / "posters.json"
    posters.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("GBN_MEDIA", str(media))
    monkeypatch.setenv("GBN_DATA", str(data))
    monkeypatch.setenv("GBN_POSTERS", str(posters))
    monkeypatch.setenv("GBN_PUBLIC_BASE", "http://test.local:8100")
    monkeypatch.setenv("GBN_MCS_BASE", "http://mcs.test")
    monkeypatch.setenv("GBN_MCS_TOKEN", "test-mcs-token")
    monkeypatch.setenv("GBN_ACTIVE_PLAYERS_SECRET", "")

    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from app.main import app

    with TestClient(app) as c:
        yield c


def _tiny_webm() -> io.BytesIO:
    return io.BytesIO(b"FAKEWEBM" + b"\x00" * 64)


def _create_poster(client: TestClient, player_id: str = "p1", **extra) -> dict:
    fields = {
        "name": extra.get("name", "Stored Name"),
        "neocorp": extra.get("neocorp", "freelancer"),
        "faction": extra.get("faction", "old-faction"),
        "role": extra.get("role", "bounty"),
        "player_id": player_id,
        "bounty_amount": str(extra.get("bounty_amount", 1_000_000)),
        "crimes": json.dumps(extra.get("crimes", ["Data siphon"])),
        "stats": json.dumps(extra.get("stats", {})),
        "flavor_text": extra.get("flavor_text", "Flavor line."),
    }
    files = {"video": ("capture.webm", _tiny_webm(), "video/webm")}
    resp = client.post("/api/posters", data=fields, files=files)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health_service_is_gbn(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "gbn"


def test_api_players_returns_404(client):
    assert client.get("/api/players").status_code == 404
    assert client.get("/api/players/p1").status_code == 404


def test_flavor_generate(client):
    resp = client.post(
        "/api/flavor/generate",
        json={"name": "Nova", "neocorp": "helix", "role": "hunter"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["bounty_amount"] > 0
    assert len(data["crimes"]) >= 1
    assert data["flavor_text"]
    assert data["source"] == "templates"
    assert "height" in data["stats"]


def test_active_players_roundtrip(client):
    empty = client.get("/api/active-players")
    assert empty.status_code == 200
    assert empty.json()["player_ids"] == []

    posted = client.post(
        "/api/active-players",
        json={"player_ids": ["p1", "p2"], "interval_sec": 15},
    )
    assert posted.status_code == 200
    body = posted.json()
    assert body["player_ids"] == ["p1", "p2"]
    assert body["interval_sec"] == 15
    assert body["updated_at"]

    page = client.get("/active-players")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]


def test_intake_stub_501(client):
    resp = client.post("/api/intake", json={"mac": "aa:bb:cc:dd:ee:ff"})
    assert resp.status_code == 501
    data = resp.json()
    assert data["ok"] is False
    assert data["reason"] == "mac_lookup_not_configured"


def test_intake_requires_mac(client):
    resp = client.post("/api/intake", json={"mac": "  "})
    assert resp.status_code == 400


def test_poster_crud_and_list(client):
    created = _create_poster(client, player_id="hunter-1", role="hunter", neocorp="reboot")
    assert created["player_id"] == "hunter-1"
    assert created["role"] == "hunter"
    assert created["neocorp"] == "reboot"
    assert created["has_video"] is True
    assert "/poster/player/hunter-1" in created["poster_url"]

    listed = client.get("/api/posters")
    assert listed.status_code == 200
    assert any(p["player_id"] == "hunter-1" for p in listed.json())

    by_id = client.get(f"/api/posters/{created['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["id"] == created["id"]


def test_mcs_overlay_on_poster_read(client):
    _create_poster(
        client,
        player_id="p1",
        name="Stale Name",
        role="bounty",
        neocorp="freelancer",
        faction="stale",
    )

    from app.models import IntakePlayer

    live = IntakePlayer(
        player_id="p1",
        name="Live Name",
        role="hunter",
        neocorp="helix",
        faction="neon-wolves",
    )

    with patch(
        "app.routers.posters.lookup_by_id",
        new=AsyncMock(return_value=live),
    ):
        resp = client.get("/api/posters/by-player/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Live Name"
        assert data["role"] == "hunter"
        assert data["neocorp"] == "helix"
        assert data["faction"] == "neon-wolves"
        assert data["status"]["current_score"] == ""
        assert data["status"]["fastest_win"] == ""
        assert data["status"]["longest_streak"] == ""

        html = client.get("/poster/player/p1")
        assert html.status_code == 200
        text = html.text
        assert "Live Name" in text
        assert "GUN FOR HIRE" in text
        assert 'data-neocorp="helix"' in text
        assert "REASONS TO HIRE" in text


def test_mcs_client_sends_bearer_token(client, monkeypatch):
    """mcs_client.lookup_by_id hits MCS with Authorization Bearer."""
    import httpx

    _create_poster(client, player_id="p9", name="Stale", neocorp="freelancer")

    captured: dict = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {
                "id": "p9",
                "name": "From MCS",
                "role": "bounty",
                "neocorp": "endline",
                "faction": "dockside",
                "neo_id": "N-9",
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, url, headers=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            return FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

    resp = client.get("/api/posters/by-player/p9")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "From MCS"
    assert data["neocorp"] == "endline"
    assert data["faction"] == "dockside"
    assert captured["url"].endswith("/players/p9")
    assert captured["headers"].get("Authorization") == "Bearer test-mcs-token"


def test_poster_html_bounty_role(client):
    _create_poster(client, player_id="b1", role="bounty", name="Target")
    with patch(
        "app.routers.posters.lookup_by_id",
        new=AsyncMock(return_value=None),
    ):
        html = client.get("/poster/player/b1")
        assert html.status_code == 200
        assert "WANTED" in html.text
        assert "DEAD OR ALIVE" in html.text
        assert "WANTED FOR" in html.text
