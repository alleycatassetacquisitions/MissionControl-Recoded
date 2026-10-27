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


ACTIVE_EVENT_ID = "evt-test"


async def _fake_active_event():
    return {
        "ready": True,
        "active_event_id": ACTIVE_EVENT_ID,
        "event": {"id": ACTIVE_EVENT_ID, "name": "Test Event"},
        "source": "test",
    }


async def _fake_active_event_id():
    return ACTIVE_EVENT_ID


@pytest.fixture()
def client(tmp_path, monkeypatch):
    media = tmp_path / "media"
    media.mkdir()
    (media / "videos").mkdir()
    (media / "events").mkdir()
    data = tmp_path / "data"
    data.mkdir()
    (data / "events").mkdir()
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
    import app.routers.posters as posters_mod
    import app.routers.events_media as events_mod
    import app.services.mcs_client as mcs_mod

    monkeypatch.setattr(mcs_mod, "get_active_event", _fake_active_event)
    monkeypatch.setattr(mcs_mod, "resolve_active_event_id", _fake_active_event_id)
    monkeypatch.setattr(posters_mod, "resolve_active_event_id", _fake_active_event_id)
    monkeypatch.setattr(events_mod, "get_active_event", _fake_active_event)
    monkeypatch.setattr(events_mod, "resolve_active_event_id", _fake_active_event_id)

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

    # Kiosk script must resolve active event — not bare /api/posters (legacy).
    js = (Path(__file__).resolve().parent.parent / "app" / "static" / "poster-cycle.js").read_text(
        encoding="utf-8"
    )
    assert "/api/events/active" in js
    assert "event_id=" in js
    assert "include_legacy" not in js


def test_list_posters_empty_without_active_event(client, monkeypatch):
    """Without an active event, do not leak legacy global posters into the cycle."""
    import app.routers.posters as posters_mod

    async def _none():
        return None

    monkeypatch.setattr(posters_mod, "resolve_active_event_id", _none)

    # Seed legacy store directly
    from app.main import app

    stores = app.state.event_stores
    from app.models import PosterRecord, PosterStats, PosterStatus

    stores.legacy.save(
        PosterRecord(
            id="legacy-1",
            player_id="legacy-1",
            name="Old Poster",
            role="bounty",
            neocorp="freelancer",
            faction="",
            bounty_amount=1,
            crimes=[],
            stats=PosterStats(),
            flavor_text="",
            status=PosterStatus(),
            video_filename="",
            created_at="2020-01-01T00:00:00Z",
            updated_at="2020-01-01T00:00:00Z",
        )
    )

    listed = client.get("/api/posters")
    assert listed.status_code == 200
    assert listed.json() == []

    legacy = client.get("/api/posters?include_legacy=true")
    assert legacy.status_code == 200
    assert any(p["player_id"] == "legacy-1" for p in legacy.json())


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
    assert created["event_id"] == ACTIVE_EVENT_ID
    assert f"/media/events/{ACTIVE_EVENT_ID}/videos/" in created["video_url"]

    # Simulate HA proxy (or venue client) hitting the CT at a new DHCP IP.
    resp = client.get(
        "/api/posters/by-player/host-check",
        headers={"Host": "10.10.50.187:8100"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["poster_url"] == "http://10.10.50.187:8100/poster/player/host-check"
    assert f"/media/events/{ACTIVE_EVENT_ID}/videos/" in data["video_url"]


def test_create_poster_requires_active_event(client, monkeypatch):
    import app.routers.posters as posters_mod

    async def _none():
        return None

    monkeypatch.setattr(posters_mod, "resolve_active_event_id", _none)
    fields = {
        "name": "No Event",
        "neocorp": "freelancer",
        "role": "bounty",
        "player_id": "p-noevt",
        "bounty_amount": "1000000",
        "crimes": "[]",
        "stats": "{}",
        "flavor_text": "",
    }
    files = {"video": ("capture.webm", _tiny_webm(), "video/webm")}
    resp = client.post("/api/posters", data=fields, files=files)
    assert resp.status_code == 409


def test_event_media_list_export_delete(client, tmp_path):
    created = _create_poster(client, player_id="clip-1")
    assert created["has_video"] is True

    listed = client.get("/api/events/media")
    assert listed.status_code == 200
    rows = listed.json()
    assert any(r["event_id"] == ACTIVE_EVENT_ID for r in rows)
    row = next(r for r in rows if r["event_id"] == ACTIVE_EVENT_ID)
    assert row["clip_count"] >= 1
    assert row["bytes_total"] > 0
    assert row["is_active"] is True

    active = client.get("/api/events/active")
    assert active.status_code == 200
    assert active.json()["active_event_id"] == ACTIVE_EVENT_ID

    export = client.get(f"/api/events/{ACTIVE_EVENT_ID}/clips/export")
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("application/zip")
    assert "attachment" in export.headers.get("content-disposition", "")
    assert export.content[:2] == b"PK"

    deleted = client.delete(f"/api/events/{ACTIVE_EVENT_ID}/media")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    # After delete, clips gone; active event folder may be recreated empty
    export2 = client.get(f"/api/events/{ACTIVE_EVENT_ID}/clips/export")
    assert export2.status_code == 404


def test_event_media_ensure_when_mcs_empty(client, monkeypatch):
    """Panel ensure_event_id seeds a folder when GBN→MCS has no active event."""
    import app.routers.events_media as events_mod

    async def _none_active():
        return None

    monkeypatch.setattr(events_mod, "get_active_event", _none_active)

    panel_event = "evt-from-registration"
    listed = client.get(
        f"/api/events/media?ensure_event_id={panel_event}"
        f"&ensure_event_name=Development%20Event"
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert any(r["event_id"] == panel_event for r in rows)
    row = next(r for r in rows if r["event_id"] == panel_event)
    assert row["is_active"] is True
    assert row["clip_count"] == 0
    assert row["event_name"] == "Development Event"


def test_create_poster_uses_form_event_when_mcs_empty(client, monkeypatch):
    import app.routers.posters as posters_mod

    async def _none():
        return None

    monkeypatch.setattr(posters_mod, "resolve_active_event_id", _none)

    fields = {
        "name": "Fallback",
        "neocorp": "freelancer",
        "faction": "",
        "role": "bounty",
        "player_id": "fb1",
        "bounty_amount": "100",
        "crimes": "[]",
        "stats": "{}",
        "flavor_text": "",
        "event_id": "evt-panel-fallback",
    }
    files = {"video": ("capture.webm", _tiny_webm(), "video/webm")}
    resp = client.post("/api/posters", data=fields, files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert "evt-panel-fallback" in data["video_url"]


def test_active_event_cache_feeds_poster_cycle(client, monkeypatch):
    """When MCS is down, GBN cache (from panel ensure) still drives /api/events/active."""
    import app.routers.events_media as events_mod
    from app.services.event_paths import read_cached_active_event

    async def _none():
        return None

    monkeypatch.setattr(events_mod, "get_active_event", _none)
    # Seed cache via panel ensure on media list
    seed = client.get(
        "/api/events/media"
        "?ensure_event_id=evt-kiosk"
        "&ensure_event_name=Kiosk%20Event"
    )
    assert seed.status_code == 200
    cached = read_cached_active_event()
    assert cached is not None
    assert cached["active_event_id"] == "evt-kiosk"
    assert cached["event_name"] == "Kiosk Event"

    async def _from_cache():
        return read_cached_active_event()

    monkeypatch.setattr(events_mod, "get_active_event", _from_cache)
    active = client.get("/api/events/active")
    assert active.status_code == 200
    body = active.json()
    assert body["active_event_id"] == "evt-kiosk"
    assert body["event_name"] == "Kiosk Event"

    posters = client.get("/api/posters?event_id=evt-kiosk")
    assert posters.status_code == 200
    assert isinstance(posters.json(), list)


def test_put_active_event_from_registration(client, monkeypatch):
    """Registration PUT seeds cache used by GET /api/events/active + posters."""
    import app.routers.events_media as events_mod
    from app.services.event_paths import read_cached_active_event

    async def _none():
        return None

    monkeypatch.setattr(events_mod, "get_active_event", _none)

    put = client.put(
        "/api/events/active",
        json={
            "active_event_id": "evt-reg-push",
            "event_name": "Development Event",
        },
    )
    assert put.status_code == 200
    assert put.json()["active_event_id"] == "evt-reg-push"
    assert put.json()["source"] == "registration"
    assert read_cached_active_event()["active_event_id"] == "evt-reg-push"

    async def _from_cache():
        return read_cached_active_event()

    monkeypatch.setattr(events_mod, "get_active_event", _from_cache)
    active = client.get("/api/events/active")
    assert active.json()["event_name"] == "Development Event"



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


def test_update_poster_keeps_video_without_reupload(client):
    created = _create_poster(
        client,
        player_id="keep-vid-1",
        name="Original",
        flavor_text="Old flavor",
        crimes=["Old charge"],
    )
    assert created["has_video"] is True
    old_video_path = created["video_url"].split("?")[0]
    old_filename = created["video_url"].split("/videos/")[-1].split("?")[0]

    fields = {
        "name": "Updated Name",
        "neocorp": "freelancer",
        "faction": "",
        "role": "bounty",
        "player_id": "keep-vid-1",
        "bounty_amount": "2500000",
        "crimes": json.dumps(["New charge"]),
        "stats": json.dumps({"height": "6'0\""}),
        "flavor_text": "New flavor",
        "headline": "UPDATED",
        "amount_label": "BOUNTY",
        "list_label": "CRIMES",
    }
    resp = client.post("/api/posters", data=fields)
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["id"] == created["id"]
    assert updated["name"] == "Updated Name"
    assert updated["flavor_text"] == "New flavor"
    assert updated["crimes"] == ["New charge"]
    assert updated["bounty_amount"] == 2_500_000
    assert updated["headline"] == "UPDATED"
    assert updated["has_video"] is True
    assert updated["video_url"].split("?")[0] == old_video_path
    assert old_filename in updated["video_url"]
    assert updated["updated_at"] != created["updated_at"] or updated["updated_at"]


def test_create_poster_without_video_fails(client):
    fields = {
        "name": "No Clip",
        "role": "bounty",
        "player_id": "no-vid-1",
        "bounty_amount": "1000000",
        "crimes": "[]",
        "stats": "{}",
    }
    resp = client.post("/api/posters", data=fields)
    assert resp.status_code == 400
    assert "video" in resp.text.lower()
