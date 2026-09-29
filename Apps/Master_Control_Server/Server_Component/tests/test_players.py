"""Tests for GET /players and GET /players/{player_id}.

Central Server responses are mocked via unittest.mock so no live HTTP is made.
Player field names use canonical vocabulary from Design Terms.md.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

MOCK_PLAYERS = [
    {
        "id": "p1",
        "name": "Alice",
        "role": "hunter",
        "neocorp": "helix",
        "faction": "Phoenix",
        "neo_id": "neo-001",
    },
    {
        "id": "p2",
        "name": "Bob",
        "role": "bounty",
        "neocorp": "freelancer",
        "faction": "",
        "neo_id": "neo-002",
    },
]


def _patch_central(players: list[dict]):
    """Patch normalized fetch used by GET handlers."""
    return patch("main.fetch_normalized_players", new=AsyncMock(return_value=players))


LEGACY_CENTRAL = [
    {
        "id": "p1",
        "name": "Alice",
        "allegiance": "Helix",
        "mode": "hunter",
        "faction": "Phoenix",
        "neo_id": "neo-001",
    },
]


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
    """Response uses canonical Design Terms field names."""
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players", headers=auth_headers)
    player = resp.json()["players"][0]
    assert "id" in player
    assert "name" in player
    assert "role" in player
    assert "neocorp" in player
    assert "faction" in player
    assert "neo_id" in player


def test_get_players_empty_roster(client: TestClient, auth_headers: dict):
    with _patch_central([]):
        resp = client.get("/players", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
    assert resp.json()["players"] == []


def test_get_players_skips_malformed_records(client: TestClient, auth_headers: dict):
    """Malformed records are skipped upstream; GET returns only normalized ones."""
    with _patch_central([MOCK_PLAYERS[0]]):
        resp = client.get("/players", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["count"] == 1


def test_get_players_maps_legacy_central_shape(client: TestClient, auth_headers: dict):
    """Legacy allegiance/mode from Central surface as neocorp/role."""
    from player_normalize import normalize_player

    normalized = [normalize_player(LEGACY_CENTRAL[0])]
    with _patch_central(normalized):
        resp = client.get("/players", headers=auth_headers)
    player = resp.json()["players"][0]
    assert player["neocorp"] == "helix"
    assert player["role"] == "hunter"
    assert player["faction"] == "Phoenix"


# ---------------------------------------------------------------------------
# GET /players/{player_id}
# ---------------------------------------------------------------------------


def test_get_player_by_id_found(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players/p1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == "p1"
    assert resp.json()["name"] == "Alice"


def test_get_player_by_id_not_found(client: TestClient, auth_headers: dict):
    with _patch_central(MOCK_PLAYERS):
        resp = client.get("/players/nonexistent", headers=auth_headers)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST / PUT / DELETE /players
# ---------------------------------------------------------------------------


def test_post_player_forwards_legacy_body(client: TestClient, auth_headers: dict):
    with patch(
        "main.create_player",
        new=AsyncMock(return_value=(201, {"id": "new1", "name": "N", "allegiance": "helix", "role": "hunter"})),
    ) as mock_create:
        resp = client.post(
            "/players",
            headers=auth_headers,
            json={
                "name": "N",
                "role": "hunter",
                "neocorp": "Helix",
                "faction": "",
                "neo_id": "",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["neocorp"] == "helix"
    assert mock_create.await_args.args[2]["allegiance"] == "helix"
    assert mock_create.await_args.args[2]["hunter"] == 1


def test_put_player_forwards_to_central(client: TestClient, auth_headers: dict):
    with patch(
        "main.update_player",
        new=AsyncMock(return_value=(200, {"id": "p1", "name": "Alice", "allegiance": "endline", "mode": "bounty"})),
    ) as mock_put:
        resp = client.put(
            "/players/p1",
            headers=auth_headers,
            json={
                "name": "Alice",
                "role": "bounty",
                "neocorp": "endline",
                "faction": "F",
                "neo_id": "n",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["role"] == "bounty"
    assert mock_put.await_args.args[2] == "p1"


def test_delete_player_forwards_to_central(client: TestClient, auth_headers: dict):
    with patch(
        "main.delete_player",
        new=AsyncMock(return_value=(204, None)),
    ) as mock_del:
        resp = client.delete("/players/p1", headers=auth_headers)
    assert resp.status_code == 204
    assert mock_del.await_args.args[2] == "p1"


def test_post_player_requires_auth(client: TestClient):
    resp = client.post("/players", json={"name": "X"})
    assert resp.status_code == 401
