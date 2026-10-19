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
    templates = data / "poster_templates.json"

    monkeypatch.setenv("GBN_MEDIA", str(media))
    monkeypatch.setenv("GBN_DATA", str(data))
    monkeypatch.setenv("GBN_POSTERS", str(posters))
    monkeypatch.setenv("GBN_TEMPLATES", str(templates))
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
    for key in (
        "template_id",
        "headline",
        "subtitle",
        "amount_label",
        "list_label",
        "list_empty",
    ):
        if key in extra:
            fields[key] = extra[key]
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


def test_poster_cycle_page(client):
    page = client.get("/poster-cycle")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    body = page.text
    assert "poster-cycle.js" in body
    assert "GBN_CYCLE" in body

    custom = client.get("/poster-cycle?interval=45")
    assert custom.status_code == 200
    assert "45" in custom.text


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
    assert created["poster_url"].endswith("/poster/player/hunter-1")
    # Links follow the request Host (not a stale GBN_PUBLIC_BASE alone).
    assert created["poster_url"].startswith("http://testserver/")

    listed = client.get("/api/posters")
    assert listed.status_code == 200
    assert any(p["player_id"] == "hunter-1" for p in listed.json())

    by_id = client.get(f"/api/posters/{created['id']}")
    assert by_id.status_code == 200
    assert by_id.json()["id"] == created["id"]


def test_poster_urls_follow_request_host(client):
    """New LAN IP / Host header must appear in poster_url and video_url."""
    created = _create_poster(client, player_id="host-check")
    assert created["poster_url"] == "http://testserver/poster/player/host-check"
    assert created["video_url"].startswith("http://testserver/media/videos/")

    # Simulate HA proxy (or venue client) hitting the CT at a new DHCP IP.
    resp = client.get(
        "/api/posters/by-player/host-check",
        headers={"Host": "10.10.50.187:8100"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["poster_url"] == "http://10.10.50.187:8100/poster/player/host-check"
    assert data["video_url"].startswith("http://10.10.50.187:8100/media/videos/")


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
        assert "REWARD" in html.text


def test_poster_templates_seeded(client):
    resp = client.get("/api/poster-templates")
    assert resp.status_code == 200
    rows = resp.json()
    ids = {t["id"] for t in rows}
    assert "hunter" in ids
    assert "bounty" in ids
    hunter = next(t for t in rows if t["id"] == "hunter")
    assert hunter["builtin"] is True
    assert hunter["headline"] == "GUN FOR HIRE"
    assert hunter["amount_label"] == "RATE"


def test_poster_templates_crud_blocks_builtins(client):
    assert client.put(
        "/api/poster-templates/hunter",
        json={"headline": "NOPE"},
    ).status_code == 400
    assert client.delete("/api/poster-templates/bounty").status_code == 400

    created = client.post(
        "/api/poster-templates",
        json={
            "name": "VIP Guest",
            "headline": "HONORED GUEST",
            "subtitle": "ALL ACCESS",
            "amount_label": "COVER",
            "list_label": "KNOWN FOR",
            "list_empty": "Details pending",
        },
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["id"]
    assert body["builtin"] is False
    assert body["headline"] == "HONORED GUEST"

    updated = client.put(
        f"/api/poster-templates/{body['id']}",
        json={"headline": "VIP CLEARANCE"},
    )
    assert updated.status_code == 200
    assert updated.json()["headline"] == "VIP CLEARANCE"

    deleted = client.delete(f"/api/poster-templates/{body['id']}")
    assert deleted.status_code == 200
    assert client.get(f"/api/poster-templates/{body['id']}").status_code == 404


def test_create_poster_snapshots_custom_chrome(client):
    created = _create_poster(
        client,
        player_id="custom-1",
        role="bounty",
        template_id="bounty",
        headline="MOST WANTED",
        subtitle="ALIVE PREFERRED",
        amount_label="PAYOUT",
        list_label="CHARGES",
        list_empty="None listed",
    )
    assert created["template_id"] == "bounty"
    assert created["headline"] == "MOST WANTED"
    assert created["subtitle"] == "ALIVE PREFERRED"
    assert created["amount_label"] == "PAYOUT"
    assert created["list_label"] == "CHARGES"

    with patch(
        "app.routers.posters.lookup_by_id",
        new=AsyncMock(return_value=None),
    ):
        html = client.get("/poster/player/custom-1")
        assert html.status_code == 200
        assert "MOST WANTED" in html.text
        assert "ALIVE PREFERRED" in html.text
        assert "PAYOUT" in html.text
        assert "CHARGES" in html.text


def test_create_poster_uses_custom_template_id(client):
    tmpl = client.post(
        "/api/poster-templates",
        json={
            "name": "Sponsor",
            "headline": "FEATURED",
            "amount_label": "FEE",
            "list_label": "CREDITS",
        },
    ).json()
    created = _create_poster(
        client,
        player_id="sponsor-1",
        role="bounty",
        template_id=tmpl["id"],
    )
    assert created["template_id"] == tmpl["id"]
    assert created["headline"] == "FEATURED"
    assert created["amount_label"] == "FEE"
    assert created["list_label"] == "CREDITS"
