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
        "neocorp": "Helix",
        "faction": "Phoenix",
        "neo_id": "neo-001",
    },
    {
        "id": "p2",
        "name": "Bob",
        "role": "freelancer",
        "neocorp": "Freelancer",
        "faction": "",
        "neo_id": "neo-002",
    },
]


def _patch_fetch(players: list[dict] | None = None):
    return patch(
        "main.fetch_players",
        new_callable=lambda: lambda *_a, **_kw: AsyncMock(return_value=players or [])(),
        # simpler: use AsyncMock directly
    )


def _patch_central(players: list[dict]):
    return patch("main.fetch_players", new=AsyncMock(return_value=players))


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
    """Malformed records are skipped; valid ones still returned."""
    mixed = [MOCK_PLAYERS[0], {"bad": "record"}]
    with _patch_central(mixed):
        resp = client.get("/players", headers=auth_headers)
    assert resp.status_code == 200
    # Only the valid player survives
    assert resp.json()["count"] == 1


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
