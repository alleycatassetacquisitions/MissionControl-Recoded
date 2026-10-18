"""Tests for MCS /events proxy and active-event via game-state."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from main import _active_event


def test_get_events_lists_from_central(client: TestClient, auth_headers: dict):
    events = [
        {
            "id": "e1",
            "name": "Alleycat 2026",
            "venue_name": "Main Hall",
            "created_at": "2026-01-01T00:00:00Z",
        }
    ]
    with patch(
        "main.list_events",
        new=AsyncMock(return_value=(200, events)),
    ):
        resp = client.get("/events", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert len(data["events"]) == 1
    assert data["events"][0]["name"] == "Alleycat 2026"


def test_get_events_requires_auth(client: TestClient):
    resp = client.get("/events")
    assert resp.status_code == 401


def test_get_active_from_game_state(client: TestClient, auth_headers: dict):
    game_state = {
        "active_event": {
            "id": "e1",
            "name": "Night Run",
            "venue_name": "Hall",
            "created_at": "2026-01-01T00:00:00Z",
        },
        "scoring": {"enabled": False, "started_at": None},
        "accepting_delayed_scores": True,
        "server_time_utc": "2026-01-01T02:00:00Z",
    }
    with patch(
        "main.fetch_game_state",
        new=AsyncMock(return_value=(200, game_state)),
    ):
        resp = client.get("/events/active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert data["source"] == "central"
    assert data["active_event_id"] == "e1"
    assert data["event"]["name"] == "Night Run"


def test_get_active_falls_back_to_mcs_memory(client: TestClient, auth_headers: dict):
    _active_event["id"] = "mem1"
    _active_event["name"] = "Cached"
    with patch(
        "main.fetch_game_state",
        new=AsyncMock(return_value=(0, None)),
    ):
        resp = client.get("/events/active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "mcs_memory"
    assert data["active_event_id"] == "mem1"
    assert data["event"]["name"] == "Cached"


def test_post_event_forwards_to_central(client: TestClient, auth_headers: dict):
    created = {
        "id": "e1",
        "name": "Alleycat 2026",
        "venue_name": "Main Hall",
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch(
        "main.create_event",
        new=AsyncMock(return_value=(201, created)),
    ) as mock_create:
        resp = client.post(
            "/events",
            headers=auth_headers,
            json={"name": "Alleycat 2026", "venue_name": "Main Hall"},
        )
    assert resp.status_code == 201
    assert resp.json()["id"] == "e1"
    assert mock_create.await_args.args[2]["name"] == "Alleycat 2026"


def test_post_event_set_active_remembers(client: TestClient, auth_headers: dict):
    created = {
        "id": "e2",
        "name": "Night Run",
        "venue_name": None,
        "created_at": "2026-01-02T00:00:00Z",
    }
    with (
        patch("main.create_event", new=AsyncMock(return_value=(201, created))),
        patch("main.set_active_event", new=AsyncMock(return_value=(204, None))),
        patch("main.fetch_game_state", new=AsyncMock(return_value=(0, None))),
    ):
        resp = client.post(
            "/events?set_active=true",
            headers=auth_headers,
            json={"name": "Night Run"},
        )
        assert resp.status_code == 201
        assert _active_event["id"] == "e2"
        assert _active_event["name"] == "Night Run"

        active = client.get("/events/active", headers=auth_headers)
    assert active.status_code == 200
    assert active.json()["active_event_id"] == "e2"
    assert active.json()["event"]["name"] == "Night Run"


def test_put_active_event_remembers_id(client: TestClient, auth_headers: dict):
    with (
        patch("main.set_active_event", new=AsyncMock(return_value=(204, None))),
        patch("main.fetch_game_state", new=AsyncMock(return_value=(0, None))),
    ):
        resp = client.put("/events/e9/active", headers=auth_headers)
        assert resp.status_code == 204
        assert _active_event["id"] == "e9"

        active = client.get("/events/active", headers=auth_headers)
    assert active.json()["active_event_id"] == "e9"


def test_put_active_event_remembers_name_hint(client: TestClient, auth_headers: dict):
    """Optional body enriches MCS memory so Active can show a title, not just UUID."""
    with (
        patch("main.set_active_event", new=AsyncMock(return_value=(204, None))),
        patch("main.fetch_game_state", new=AsyncMock(return_value=(0, None))),
    ):
        resp = client.put(
            "/events/e9/active",
            headers=auth_headers,
            json={"name": "Test Event 2027", "venue_name": "Hall"},
        )
        assert resp.status_code == 204
        active = client.get("/events/active", headers=auth_headers).json()
    assert active["active_event_id"] == "e9"
    assert active["event"]["name"] == "Test Event 2027"


def test_patch_event_forwards(client: TestClient, auth_headers: dict):
    updated = {
        "id": "e1",
        "name": "Renamed",
        "venue_name": None,
        "created_at": "2026-01-01T00:00:00Z",
    }
    with patch(
        "main.update_event",
        new=AsyncMock(return_value=(200, updated)),
    ) as mock_patch:
        resp = client.patch(
            "/events/e1",
            headers=auth_headers,
            json={"name": "Renamed", "venue_name": None},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed"
    assert mock_patch.await_args.args[2] == "e1"


def test_put_active_404(client: TestClient, auth_headers: dict):
    with patch(
        "main.set_active_event",
        new=AsyncMock(return_value=(404, None)),
    ):
        resp = client.put("/events/missing/active", headers=auth_headers)
    assert resp.status_code == 404


def test_get_game_state(client: TestClient, auth_headers: dict):
    game_state = {
        "active_event": {
            "id": "e1",
            "name": "Night Run",
            "venue_name": None,
            "created_at": "2026-01-01T00:00:00Z",
        },
        "scoring": {"enabled": True, "started_at": "2026-01-01T01:00:00Z"},
        "accepting_delayed_scores": False,
        "server_time_utc": "2026-01-01T02:00:00Z",
    }
    with patch(
        "main.fetch_game_state",
        new=AsyncMock(return_value=(200, game_state)),
    ):
        resp = client.get("/game-state", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_event"]["id"] == "e1"
    assert data["scoring"]["enabled"] is True
    assert data["accepting_delayed_scores"] is False


def test_put_scoring_for_event(client: TestClient, auth_headers: dict):
    with patch(
        "main.set_scoring",
        new=AsyncMock(
            return_value=(200, {"enabled": True, "started_at": "2026-01-01T01:00:00Z"})
        ),
    ):
        resp = client.put(
            "/events/e1/scoring",
            headers=auth_headers,
            json={"enabled": True},
        )
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_put_scoring_active_convenience(client: TestClient, auth_headers: dict):
    with (
        patch(
            "main.fetch_game_state",
            new=AsyncMock(
                return_value=(
                    200,
                    {
                        "active_event": {
                            "id": "e1",
                            "name": "N",
                            "created_at": "2026-01-01T00:00:00Z",
                        },
                        "scoring": None,
                        "accepting_delayed_scores": None,
                        "server_time_utc": "2026-01-01T02:00:00Z",
                    },
                )
            ),
        ),
        patch(
            "main.set_scoring",
            new=AsyncMock(
                return_value=(200, {"enabled": False, "started_at": None})
            ),
        ) as mock_score,
    ):
        resp = client.put(
            "/scoring",
            headers=auth_headers,
            json={"enabled": False},
        )
    assert resp.status_code == 200
    assert mock_score.await_args.args[2] == "e1"


def test_get_teams(client: TestClient, auth_headers: dict):
    with patch(
        "main.list_teams",
        new=AsyncMock(
            return_value=(
                200,
                [{"id": "t1", "event_id": "e1", "name": "Hunter"}],
            )
        ),
    ):
        resp = client.get("/events/e1/teams", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "Hunter"
