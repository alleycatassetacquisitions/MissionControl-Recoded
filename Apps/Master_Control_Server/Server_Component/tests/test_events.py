"""Tests for MCS /events proxy and active-event memory."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from central_client import EVENTS_LIST_NOT_READY
from main import _active_event


def test_get_events_returns_501(client: TestClient, auth_headers: dict):
    resp = client.get("/events", headers=auth_headers)
    assert resp.status_code == 501
    assert resp.json()["detail"] == EVENTS_LIST_NOT_READY


def test_get_events_requires_auth(client: TestClient):
    resp = client.get("/events")
    assert resp.status_code == 401


def test_get_active_returns_mcs_memory(client: TestClient, auth_headers: dict):
    resp = client.get("/events/active", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False
    assert data["source"] == "mcs_memory"
    assert data["active_event_id"] is None


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
    with patch(
        "main.set_active_event",
        new=AsyncMock(return_value=(204, None)),
    ):
        resp = client.put("/events/e9/active", headers=auth_headers)
    assert resp.status_code == 204
    assert _active_event["id"] == "e9"

    active = client.get("/events/active", headers=auth_headers)
    assert active.json()["active_event_id"] == "e9"


def test_put_active_event_remembers_name_hint(client: TestClient, auth_headers: dict):
    """Optional body enriches MCS memory so Active can show a title, not just UUID."""
    with patch(
        "main.set_active_event",
        new=AsyncMock(return_value=(204, None)),
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
