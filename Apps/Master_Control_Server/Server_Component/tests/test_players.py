"""Tests for GET/POST/PUT/DELETE /players.

Central Server responses are mocked via unittest.mock so no live HTTP is made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

MOCK_PLAYERS = [
    {
        "id": "p1",
        "name": "Alice",
        "pdn_code": "1234",
        "mode": "hunter",
        "role": "hunter",
        "created_at": "2026-01-01T00:00:00Z",
        "email": "a@example.com",
        "neocorp": "",
        "faction": "",
        "neo_id": "",
        "event_id": "e1",
        "team_id": "t1",
        "team_name": "Hunter",
        "active": True,
    },
    {
        "id": "p2",
        "name": "Bob",
        "pdn_code": "5678",
        "mode": "unassigned",
        "role": "unassigned",
        "created_at": "2026-01-02T00:00:00Z",
        "email": "",
        "neocorp": "",
        "faction": "",
        "neo_id": "",
        "event_id": "e1",
        "team_id": None,
        "team_name": "",
        "active": True,
    },
]


def _patch_central(players: list[dict], pagination: dict | None = None):
    """Patch normalized fetch used by GET handlers."""
    return patch(
        "main.fetch_normalized_players",
        new=AsyncMock(return_value=(players, pagination)),
    )


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


def test_get_players_requires_auth(client: TestClient):
    resp = client.get("/players")
    assert resp.status_code == 401


def test_get_player_by_id_requires_auth(client: TestClient):
    resp = client.get("/players/p1")
    assert resp.status_code == 401


def test_wrong_token_rejected(client: TestClient):
    resp = client.get("/players", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /players
# ---------------------------------------------------------------------------


def test_get_players_returns_roster(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert len(data["players"]) == 2


def test_get_players_field_names(client: TestClient, auth_headers: dict):
    """Response uses Central-aligned fields + role alias."""
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players", headers=auth_headers)
    player = resp.json()["players"][0]
    assert player["id"] == "p1"
    assert player["name"] == "Alice"
    assert player["pdn_code"] == "1234"
    assert player["mode"] == "hunter"
    assert player["role"] == "hunter"
    assert player["email"] == "a@example.com"
    assert player["team_name"] == "Hunter"
    assert player["active"] is True


def test_get_players_empty_roster(client: TestClient, auth_headers: dict):
    with _patch_central([]):
        resp = client.get("/players", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["players"] == []


def test_get_players_includes_pagination(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS[:1], {"page": 1, "per_page": 20}):
        resp = client.get("/players?page=1&per_page=20", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["pagination"] == {"page": 1, "per_page": 20}


# ---------------------------------------------------------------------------
# GET /players/{player_id}
# ---------------------------------------------------------------------------


def test_get_player_by_id_found(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players/p1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == "p1"
    assert resp.json()["pdn_code"] == "1234"


def test_get_player_by_id_not_found(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST / PUT / DELETE /players
# ---------------------------------------------------------------------------


def test_post_player_sends_json_body(client: TestClient, auth_headers: dict):
    with patch(
        "main.create_player",
        new=AsyncMock(return_value=(200, None)),
    ) as mock_create:
        resp = client.post(
            "/players",
            headers=auth_headers,
            json={"name": "Alex", "email": "alex@example.com"},
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Alex"
    assert resp.json()["email"] == "alex@example.com"
    assert resp.json()["mode"] == "unassigned"
    body = mock_create.await_args.args[2]
    assert body == {"name": "Alex", "email": "alex@example.com"}
    assert "allegiance" not in body


def test_post_player_passthrough_409(client: TestClient, auth_headers: dict):
    with patch(
        "main.create_player",
        new=AsyncMock(return_value=(409, "No active event")),
    ):
        resp = client.post(
            "/players",
            headers=auth_headers,
            json={"name": "Alex"},
        )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "No active event"


def test_post_player_with_central_json_body(client: TestClient, auth_headers: dict):
    with patch(
        "main.create_player",
        new=AsyncMock(
            return_value=(
                200,
                {
                    "id": "new1",
                    "name": "N",
                    "pdn_code": "9999",
                    "created_at": "2026-01-01T00:00:00Z",
                    "event_id": "e1",
                    "email": None,
                    "team_id": None,
                    "team_name": None,
                    "active": True,
                },
            )
        ),
    ):
        resp = client.post(
            "/players",
            headers=auth_headers,
            json={"name": "N"},
        )
    assert resp.status_code == 201
    assert resp.json()["pdn_code"] == "9999"
    assert resp.json()["active"] is True


def test_put_player_proxies_patch(client: TestClient, auth_headers: dict):
    updated = {
        "id": "p1",
        "name": "Alice Updated",
        "pdn_code": "1234",
        "created_at": "2026-01-01T00:00:00Z",
        "event_id": "e1",
        "email": "a@example.com",
        "team_id": "t1",
        "team_name": "Hunter",
        "active": True,
    }
    with patch(
        "main.update_player",
        new=AsyncMock(return_value=(200, updated)),
    ) as mock_update:
        resp = client.put(
            "/players/p1",
            headers=auth_headers,
            json={"name": "Alice Updated", "email": "a@example.com", "team_id": "t1"},
        )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Alice Updated"
    assert resp.json()["team_name"] == "Hunter"
    assert mock_update.await_args.args[2] == "p1"
    assert mock_update.await_args.args[3]["name"] == "Alice Updated"


def test_delete_player_soft_deactivates(client: TestClient, auth_headers: dict):
    with patch(
        "main.deactivate_player",
        new=AsyncMock(return_value=(200, {"id": "p1", "active": False})),
    ) as mock_deact:
        resp = client.delete("/players/p1", headers=auth_headers)
    assert resp.status_code == 204
    assert mock_deact.await_args.args[2] == "p1"


def test_post_player_requires_auth(client: TestClient):
    resp = client.post("/players", json={"name": "X"})
    assert resp.status_code == 401
