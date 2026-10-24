"""Tests for player_normalize — Central shape → MCS Player fields."""
from __future__ import annotations

import pytest

from player_normalize import (
    normalize_mode,
    normalize_player,
    normalize_role,
    to_central_create_body,
    to_central_create_form,
    to_central_update_body,
)


def test_normalize_central_player_response():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "pdn_code": "1234",
            "created_at": "2026-01-01T00:00:00Z",
            "mode": "hunter",
            "email": "a@example.com",
        }
    )
    assert out["pdn_code"] == "1234"
    assert out["mode"] == "hunter"
    assert out["role"] == "hunter"
    assert out["email"] == "a@example.com"
    assert out["created_at"] == "2026-01-01T00:00:00Z"
    assert out["neocorp"] == ""


def test_normalize_defaults_mode_unassigned():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "pdn_code": "0001",
            "created_at": "2026-01-01T00:00:00Z",
        }
    )
    assert out["mode"] == "unassigned"
    assert out["role"] == "unassigned"
    assert out["active"] is True
    assert out["team_name"] == ""


def test_normalize_team_name_to_mode():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "pdn_code": "0001",
            "created_at": "2026-01-01T00:00:00Z",
            "event_id": "e1",
            "team_id": "t1",
            "team_name": "Hunter",
            "active": True,
        }
    )
    assert out["mode"] == "hunter"
    assert out["team_name"] == "Hunter"
    assert out["event_id"] == "e1"
    assert out["active"] is True


def test_normalize_legacy_allegiance_still_maps():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "allegiance": "Helix",
            "mode": "hunter",
            "faction": "Phoenix",
            "neo_id": "n1",
        }
    )
    assert out["neocorp"] == "helix"
    assert out["role"] == "hunter"
    assert out["faction"] == "Phoenix"
    assert out["neo_id"] == "n1"


def test_normalize_hunter_int_to_mode():
    assert normalize_mode({"hunter": 1}) == "hunter"
    assert normalize_mode({"hunter": 2}) == "bounty"
    assert normalize_role({"mode": "bounty", "hunter": 1}) == "bounty"


def test_normalize_missing_id_or_name_raises():
    with pytest.raises(ValueError):
        normalize_player({"name": "NoId"})
    with pytest.raises(ValueError):
        normalize_player({"id": "x"})


def test_to_central_create_form_name_and_email():
    form = to_central_create_form(name="Alex", email="alex@example.com")
    assert form == {"name": "Alex", "email": "alex@example.com"}


def test_to_central_create_form_omits_empty_email():
    form = to_central_create_form(name="Alex", email="")
    assert form == {"name": "Alex"}
    assert "email" not in form


def test_to_central_create_body_is_json_fields():
    """Helper returns JSON create fields, not allegiance payload."""
    body = to_central_create_body(name="New", email="n@ex.com")
    assert body == {"name": "New", "email": "n@ex.com"}
    assert "allegiance" not in body
    assert "hunter" not in body


def test_normalize_affiliations_derive_neocorp_faction():
    out = normalize_player(
        {
            "id": "p1",
            "name": "Alice",
            "pdn_code": "0001",
            "affiliations": [
                {
                    "category_id": "c1",
                    "category_name": "Allegiance",
                    "affiliation_id": "a1",
                    "affiliation_name": "Helix Industries",
                },
                {
                    "category_id": "c2",
                    "category_name": "Faction",
                    "affiliation_id": "a2",
                    "affiliation_name": "Corvid Alliance",
                },
            ],
        }
    )
    assert len(out["affiliations"]) == 2
    assert out["neocorp"] == "helix"
    assert out["faction"] == "Corvid Alliance"


def test_to_central_update_body_includes_affiliations():
    body = to_central_update_body(
        affiliations={"c1": "a1", "c2": None},
    )
    assert body == {"affiliations": {"c1": "a1", "c2": None}}
